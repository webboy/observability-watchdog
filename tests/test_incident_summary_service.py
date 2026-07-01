"""Incident summary service tests."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.anomaly import Anomaly
from app.models.anomaly_rule import AnomalyRule
from app.models.app import App
from app.services.incident_summary_service import IncidentSummaryService


def _create_anomaly(db: Session) -> Anomaly:
    app = App(name="Platform", slug=f"platform-{uuid.uuid4().hex[:8]}", environment="production")
    db.add(app)
    db.commit()
    rule = db.query(AnomalyRule).filter(AnomalyRule.metric_name == "error_count").one()
    window_start = datetime(2026, 6, 30, 11, 30, tzinfo=timezone.utc)
    anomaly = Anomaly(
        app_id=app.id,
        rule_id=rule.id,
        service_name="payment-service",
        url_path="/payments/charge",
        severity="CRITICAL",
        metric_name="error_count",
        window_start=window_start,
        window_end=window_start + timedelta(minutes=10),
        observed_value=47.0,
        baseline_value=3.2,
        anomaly_score=14.7,
        reason="error_count is 14.7x higher than baseline",
    )
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


def test_template_fallback_without_api_keys(db_session: Session) -> None:
    """Missing API keys should produce deterministic template summaries."""
    anomaly = _create_anomaly(db_session)
    settings = Settings(llm_provider="template", gemini_api_key=None, openai_api_key=None)
    service = IncidentSummaryService(db_session, settings=settings)

    summary = service.generate_summary(anomaly)

    assert "payment-service" in summary.summary
    assert "error count spike" in summary.summary
    assert "/payments/charge" in summary.summary
    assert summary.likely_cause
    assert summary.recommended_action
    assert "revenue loss" in summary.business_impact.lower()
    assert summary.generation_source == "Deterministic Template (Fallback)"


def test_provider_selection_prefers_configured_gemini(db_session: Session) -> None:
    """Explicit Gemini provider should be selected when key is present."""
    settings = Settings(llm_provider="gemini", gemini_api_key="test-key")
    service = IncidentSummaryService(db_session, settings=settings)
    assert service._resolve_provider() == "gemini"


def test_provider_selection_defaults_to_gemini_key(db_session: Session) -> None:
    """Template provider with Gemini key should default to Gemini."""
    settings = Settings(llm_provider="template", gemini_api_key="test-key")
    service = IncidentSummaryService(db_session, settings=settings)
    assert service._resolve_provider() == "gemini"


def test_malformed_llm_output_falls_back_to_template(db_session: Session) -> None:
    """Invalid LLM JSON should fall back to deterministic template text."""
    anomaly = _create_anomaly(db_session)
    settings = Settings(llm_provider="template")
    service = IncidentSummaryService(db_session, settings=settings)

    summary = service._parse_llm_json("not-json", anomaly, provider="openai")

    assert "payment-service" in summary.summary
    assert "error count spike" in summary.summary


def test_enrich_anomalies_persists_summary_fields(db_session: Session) -> None:
    """Enrichment should persist ai_summary and related fields on anomalies."""
    anomaly = _create_anomaly(db_session)
    settings = Settings(llm_provider="template", gemini_api_key=None, openai_api_key=None)
    service = IncidentSummaryService(db_session, settings=settings)

    enriched = service.enrich_anomalies([anomaly])
    db_session.commit()
    db_session.refresh(enriched[0])

    assert enriched[0].ai_summary
    assert enriched[0].likely_cause
    assert enriched[0].business_impact
    assert enriched[0].recommended_action
    assert enriched[0].generation_source == "Deterministic Template (Fallback)"


def test_llm_json_extracts_business_impact_from_summary_when_missing(db_session: Session) -> None:
    """LLM JSON without business_impact should parse it from the summary text."""
    anomaly = _create_anomaly(db_session)
    settings = Settings(llm_provider="template")
    service = IncidentSummaryService(db_session, settings=settings)

    payload = {
        "summary": (
            "Payment-service outage. Likely cause: UpstreamTimeout. "
            "Likely business impact: Failed checkouts and potential revenue loss. "
            "Recommended action: Check provider status."
        ),
        "what_happened": "Errors spiked on /payments/charge.",
        "likely_cause": "UpstreamTimeout",
        "recommended_action": "Check provider status",
    }

    summary = service._parse_llm_json(json.dumps(payload), anomaly, provider="openai")

    assert summary.business_impact == "Failed checkouts and potential revenue loss"
    assert summary.generation_source == "OpenAI (gpt-4o-mini)"


def test_build_summary_read_backfills_business_impact_from_summary_text(db_session: Session) -> None:
    """API read model should backfill business_impact from persisted summary text."""
    anomaly = _create_anomaly(db_session)
    anomaly.ai_summary = (
        "payment-service is experiencing a critical error count spike on /payments/charge. "
        "The current error count spike is 14.7x above the recent baseline (47.00 vs 3.20). "
        "Likely cause: UpstreamTimeout. "
        "Likely business impact: Failed checkouts and potential revenue loss. "
        "Recommended action: Check provider status."
    )
    anomaly.generation_source = "Deterministic Template (Fallback)"

    read_model = IncidentSummaryService.build_summary_read(anomaly)

    assert read_model.business_impact == "Failed checkouts and potential revenue loss"
    assert read_model.generation_source == "Deterministic Template (Fallback)"


def test_openai_provider_can_be_mocked(db_session: Session, monkeypatch) -> None:
    """OpenAI provider path should parse valid JSON responses."""
    anomaly = _create_anomaly(db_session)
    settings = Settings(llm_provider="openai", openai_api_key="test-key")
    service = IncidentSummaryService(db_session, settings=settings)

    payload = {
        "summary": "Payment service outage detected.",
        "what_happened": "Errors spiked on /payments/charge.",
        "likely_cause": "UpstreamTimeout",
        "business_impact": "Failed checkouts",
        "recommended_action": "Check provider status",
    }

    def fake_openai(anomaly_obj: Anomaly):
        return service._parse_llm_json(json.dumps(payload), anomaly_obj, provider="openai")

    monkeypatch.setattr(service, "_generate_with_openai", fake_openai)
    summary = service.generate_summary(anomaly)

    assert summary.summary == "Payment service outage detected."
    assert summary.likely_cause == "UpstreamTimeout"
    assert summary.business_impact == "Failed checkouts"
    assert summary.generation_source == "OpenAI (gpt-4o-mini)"
