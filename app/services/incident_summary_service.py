"""Incident summary generation with optional LLM providers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.anomaly import Anomaly
from app.repositories.anomaly_repository import AnomalyRepository
from app.schemas.incident import IncidentSummaryRead

logger = logging.getLogger(__name__)

METRIC_LABELS = {
    "error_count": "error count spike",
    "http_5xx_rate": "HTTP 5xx rate spike",
    "latency_p95": "p95 latency spike",
}

TEMPLATE_GENERATION_SOURCE = "Deterministic Template (Fallback)"

SUMMARY_FIELD_MARKERS = (
    " Likely cause:",
    " Likely business impact:",
    " Recommended action:",
    " The current ",
)


@dataclass(slots=True)
class IncidentSummary:
    """Structured incident summary for one anomaly."""

    summary: str
    what_happened: str
    likely_cause: str
    business_impact: str
    recommended_action: str
    generation_source: str


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
                business_impact=summary.business_impact,
                recommended_action=summary.recommended_action,
                generation_source=summary.generation_source,
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

    @staticmethod
    def build_summary_read(anomaly: Anomaly) -> IncidentSummaryRead:
        """Build an API response model from a persisted anomaly."""
        summary_text = anomaly.ai_summary or ""
        business_impact = anomaly.business_impact or IncidentSummaryService._extract_labeled_field(
            summary_text,
            "Likely business impact",
        )
        if not business_impact:
            business_impact = IncidentSummaryService._business_impact(anomaly)

        what_happened = IncidentSummaryService._extract_what_happened(summary_text)

        return IncidentSummaryRead(
            anomaly_id=anomaly.id,
            app_id=anomaly.app_id,
            service_name=anomaly.service_name,
            url_path=anomaly.url_path,
            severity=anomaly.severity,
            metric_name=anomaly.metric_name,
            window_start=anomaly.window_start,
            window_end=anomaly.window_end,
            summary=summary_text,
            what_happened=what_happened,
            likely_cause=anomaly.likely_cause,
            business_impact=business_impact,
            recommended_action=anomaly.recommended_action,
            generation_source=anomaly.generation_source or TEMPLATE_GENERATION_SOURCE,
        )

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

    def _generation_source_for_provider(self, provider: str) -> str:
        if provider == "gemini":
            return f"Gemini ({self.settings.gemini_model})"
        if provider == "openai":
            return f"OpenAI ({self.settings.openai_model})"
        return TEMPLATE_GENERATION_SOURCE

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
            generation_source=TEMPLATE_GENERATION_SOURCE,
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

    @staticmethod
    def _extract_labeled_field(text: str, label: str) -> str | None:
        """Extract a labeled sentence fragment from a summary string."""
        needle = f"{label}:"
        start = text.find(needle)
        if start == -1:
            return None

        fragment = text[start + len(needle) :].strip()
        end_index = len(fragment)
        for marker in SUMMARY_FIELD_MARKERS:
            marker = marker.strip()
            if marker == label + ":":
                continue
            marker_index = fragment.find(f" {marker}")
            if marker_index != -1:
                end_index = min(end_index, marker_index)
        value = fragment[:end_index].strip().rstrip(".")
        return value or None

    @staticmethod
    def _extract_what_happened(summary_text: str) -> str | None:
        if not summary_text:
            return None
        if " The current " in summary_text:
            return summary_text.split(" The current ", maxsplit=1)[0].strip()
        first_sentence = summary_text.split(".", maxsplit=1)[0].strip()
        return f"{first_sentence}." if first_sentence else None

    @staticmethod
    def _normalize_llm_content(content: str) -> str:
        text = content.strip()
        if not text.startswith("```"):
            return text

        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _coalesce_text(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"null", "none", "n/a"}:
            return None
        return text

    def _resolve_business_impact(
        self,
        *,
        payload: dict[str, object],
        summary_text: str,
        anomaly: Anomaly,
    ) -> str:
        business_impact = self._coalesce_text(payload.get("business_impact"))
        if not business_impact:
            business_impact = self._extract_labeled_field(summary_text, "Likely business impact")
        if not business_impact:
            business_impact = self._business_impact(anomaly)
        return business_impact

    def _resolve_likely_cause(
        self,
        *,
        payload: dict[str, object],
        summary_text: str,
        anomaly: Anomaly,
    ) -> str:
        likely_cause = self._coalesce_text(payload.get("likely_cause"))
        if not likely_cause:
            likely_cause = self._extract_labeled_field(summary_text, "Likely cause")
        if not likely_cause:
            likely_cause = anomaly.likely_cause or self._default_likely_cause(anomaly)
        return likely_cause

    def _resolve_recommended_action(
        self,
        *,
        payload: dict[str, object],
        summary_text: str,
        anomaly: Anomaly,
    ) -> str:
        recommended_action = self._coalesce_text(payload.get("recommended_action"))
        if not recommended_action:
            recommended_action = self._extract_labeled_field(summary_text, "Recommended action")
        if not recommended_action:
            recommended_action = anomaly.recommended_action or self._default_recommended_action(anomaly)
        return recommended_action

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

    def _parse_llm_json(self, content: str, anomaly: Anomaly, *, provider: str) -> IncidentSummary:
        normalized = self._normalize_llm_content(content)
        try:
            payload = json.loads(normalized)
            if not isinstance(payload, dict):
                raise TypeError("LLM JSON payload must be an object")

            summary_text = self._coalesce_text(payload.get("summary"))
            if not summary_text:
                raise KeyError("summary")

            what_happened = self._coalesce_text(payload.get("what_happened")) or self._extract_what_happened(
                summary_text
            )
            if not what_happened:
                what_happened = summary_text

            likely_cause = self._resolve_likely_cause(
                payload=payload,
                summary_text=summary_text,
                anomaly=anomaly,
            )
            business_impact = self._resolve_business_impact(
                payload=payload,
                summary_text=summary_text,
                anomaly=anomaly,
            )
            recommended_action = self._resolve_recommended_action(
                payload=payload,
                summary_text=summary_text,
                anomaly=anomaly,
            )

            return IncidentSummary(
                summary=summary_text,
                what_happened=what_happened,
                likely_cause=likely_cause,
                business_impact=business_impact,
                recommended_action=recommended_action,
                generation_source=self._generation_source_for_provider(provider),
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
        return self._parse_llm_json(content, anomaly, provider="gemini")

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
        return self._parse_llm_json(content, anomaly, provider="openai")
