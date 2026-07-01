"""Incident summary generation with optional LLM providers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.anomaly import Anomaly
from app.repositories.anomaly_repository import AnomalyRepository

logger = logging.getLogger(__name__)

METRIC_LABELS = {
    "error_count": "error count spike",
    "http_5xx_rate": "HTTP 5xx rate spike",
    "latency_p95": "p95 latency spike",
}


@dataclass(slots=True)
class IncidentSummary:
    """Structured incident summary for one anomaly."""

    summary: str
    what_happened: str
    likely_cause: str
    business_impact: str
    recommended_action: str


class IncidentSummaryService:
    """Generate deterministic or LLM-assisted incident summaries."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.anomaly_repo = AnomalyRepository()

    def enrich_anomalies(self, anomalies: list[Anomaly]) -> list[Anomaly]:
        """Generate summaries and persist them on anomaly rows."""
        enriched: list[Anomaly] = []
        for anomaly in anomalies:
            summary = self.generate_summary(anomaly)
            updated = self.anomaly_repo.update_summary_fields(
                self.db,
                anomaly,
                ai_summary=summary.summary,
                likely_cause=summary.likely_cause,
                recommended_action=summary.recommended_action,
            )
            enriched.append(updated)
        return enriched

    def generate_summary(self, anomaly: Anomaly) -> IncidentSummary:
        """Generate one incident summary using LLM or deterministic fallback."""
        provider = self._resolve_provider()
        if provider == "template":
            return self._build_template_summary(anomaly)

        try:
            if provider == "gemini":
                return self._generate_with_gemini(anomaly)
            if provider == "openai":
                return self._generate_with_openai(anomaly)
        except Exception:
            logger.exception("LLM incident summary failed; using template fallback")
        return self._build_template_summary(anomaly)

    def _resolve_provider(self) -> str:
        provider = (self.settings.llm_provider or "template").lower()
        if provider == "gemini" and self.settings.gemini_api_key:
            return "gemini"
        if provider == "openai" and self.settings.openai_api_key:
            return "openai"
        if provider in {"template", ""}:
            if self.settings.gemini_api_key:
                return "gemini"
            if self.settings.openai_api_key:
                return "openai"
            return "template"
        return "template"

    def _build_template_summary(self, anomaly: Anomaly) -> IncidentSummary:
        metric_label = METRIC_LABELS.get(anomaly.metric_name, anomaly.metric_name)
        scope = anomaly.url_path or anomaly.service_name
        likely_cause = anomaly.likely_cause or self._default_likely_cause(anomaly)
        business_impact = self._business_impact(anomaly)
        recommended_action = (
            anomaly.recommended_action or self._default_recommended_action(anomaly)
        )

        what_happened = (
            f"{anomaly.service_name} is experiencing a {anomaly.severity.lower()} "
            f"{metric_label} on {scope}."
        )
        summary = (
            f"{what_happened} The current {metric_label} is {anomaly.anomaly_score:.1f}x "
            f"above the recent baseline ({anomaly.observed_value:.2f} vs "
            f"{anomaly.baseline_value:.2f}). Likely cause: {likely_cause}. "
            f"Likely business impact: {business_impact}. "
            f"Recommended action: {recommended_action}."
        )
        return IncidentSummary(
            summary=summary,
            what_happened=what_happened,
            likely_cause=likely_cause,
            business_impact=business_impact,
            recommended_action=recommended_action,
        )

    @staticmethod
    def _default_likely_cause(anomaly: Anomaly) -> str:
        if anomaly.metric_name == "error_count":
            return "Elevated application errors in the affected service"
        if anomaly.metric_name == "http_5xx_rate":
            return "Increased upstream or dependency failures"
        if anomaly.metric_name == "latency_p95":
            return "Performance degradation in downstream dependencies"
        return "Abnormal service behavior detected by baseline scoring"

    @staticmethod
    def _default_recommended_action(anomaly: Anomaly) -> str:
        return (
            f"Inspect recent deployments and dependency health for {anomaly.service_name}, "
            "then validate recovery in subsequent metric windows."
        )

    @staticmethod
    def _business_impact(anomaly: Anomaly) -> str:
        if anomaly.service_name == "payment-service" and anomaly.url_path == "/payments/charge":
            return "Failed checkouts and potential revenue loss"
        if anomaly.service_name == "checkout-service":
            return "Checkout abandonment and failed order completion"
        if anomaly.service_name == "auth-service":
            return "User login failures and blocked access"
        return f"Degraded user experience for {anomaly.service_name}"

    def _prompt_for_anomaly(self, anomaly: Anomaly) -> str:
        return (
            "Summarize this SRE anomaly as strict JSON with keys: "
            "summary, what_happened, likely_cause, business_impact, recommended_action.\n"
            f"service_name: {anomaly.service_name}\n"
            f"url_path: {anomaly.url_path}\n"
            f"severity: {anomaly.severity}\n"
            f"metric_name: {anomaly.metric_name}\n"
            f"observed_value: {anomaly.observed_value}\n"
            f"baseline_value: {anomaly.baseline_value}\n"
            f"anomaly_score: {anomaly.anomaly_score}\n"
            f"reason: {anomaly.reason}\n"
        )

    def _parse_llm_json(self, content: str, anomaly: Anomaly) -> IncidentSummary:
        try:
            payload = json.loads(content)
            return IncidentSummary(
                summary=str(payload["summary"]),
                what_happened=str(payload.get("what_happened", payload["summary"])),
                likely_cause=str(payload.get("likely_cause", anomaly.likely_cause or "")),
                business_impact=str(payload.get("business_impact", self._business_impact(anomaly))),
                recommended_action=str(
                    payload.get("recommended_action", anomaly.recommended_action or "")
                ),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Malformed LLM JSON response; using template fallback")
            return self._build_template_summary(anomaly)

    def _generate_with_gemini(self, anomaly: Anomaly) -> IncidentSummary:
        from google import genai

        client = genai.Client(api_key=self.settings.gemini_api_key)
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=self._prompt_for_anomaly(anomaly),
        )
        content = response.text or ""
        return self._parse_llm_json(content, anomaly)

    def _generate_with_openai(self, anomaly: Anomaly) -> IncidentSummary:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key, timeout=self.settings.llm_timeout_seconds)
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": "You summarize SRE incidents from deterministic anomaly metadata.",
                },
                {"role": "user", "content": self._prompt_for_anomaly(anomaly)},
            ],
        )
        content = response.choices[0].message.content or ""
        return self._parse_llm_json(content, anomaly)
