"""Baseline anomaly detection service."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.anomaly_rule import AnomalyRule
from app.models.metric_window import MetricWindow
from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.anomaly_rule_repository import AnomalyRuleRepository
from app.repositories.metric_window_repository import MetricWindowRepository

BASELINE_FLOOR = 1.0
METRIC_FIELDS = {
    "error_count": "error_count",
    "http_5xx_rate": "http_5xx_rate",
    "latency_p95": "latency_p95_ms",
}


class AnomalyDetectionService:
    """Evaluate metric windows against baseline rules and persist anomalies."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.rule_repo = AnomalyRuleRepository()
        self.metric_repo = MetricWindowRepository()
        self.anomaly_repo = AnomalyRepository()

    def detect_for_windows(self, windows: list[MetricWindow]) -> list[Anomaly]:
        """Evaluate windows chronologically and persist detected anomalies."""
        sorted_windows = sorted(windows, key=lambda item: (item.window_start, item.service_name, item.url_path or ""))
        detected: list[Anomaly] = []

        for window in sorted_windows:
            for metric_name in METRIC_FIELDS:
                rule = self.rule_repo.resolve_rule(self.db, window.app_id, metric_name)
                if rule is None:
                    continue

                anomaly = self._evaluate_window_metric(window, rule, metric_name)
                if anomaly is not None:
                    detected.append(anomaly)
                else:
                    self.anomaly_repo.delete_non_anomalous_for_window(
                        self.db,
                        app_id=window.app_id,
                        service_name=window.service_name,
                        url_path=window.url_path,
                        window_start=window.window_start,
                        metric_name=metric_name,
                    )

        return detected

    def _evaluate_window_metric(
        self,
        window: MetricWindow,
        rule: AnomalyRule,
        metric_name: str,
    ) -> Anomaly | None:
        if window.total_events < rule.min_event_count:
            return None

        observed_value = getattr(window, METRIC_FIELDS[metric_name])
        if observed_value is None:
            return None

        baseline_value = self.metric_repo.get_baseline_average(
            self.db,
            app_id=window.app_id,
            service_name=window.service_name,
            url_path=window.url_path,
            window_start=window.window_start,
            window_minutes=rule.window_minutes,
            baseline_window_minutes=rule.baseline_window_minutes,
            metric_name=metric_name,
        )
        if baseline_value is None or baseline_value == 0:
            baseline_value = BASELINE_FLOOR

        anomaly_score = float(observed_value) / float(baseline_value)
        severity = self._classify_severity(anomaly_score, rule)
        if severity is None:
            return None

        reason = (
            f"{metric_name} is {anomaly_score:.1f}x higher than baseline "
            f"({observed_value:.2f} vs {baseline_value:.2f})"
        )
        likely_cause, recommended_action = self._build_recommendations(window, metric_name)

        return self.anomaly_repo.upsert(
            self.db,
            {
                "app_id": window.app_id,
                "rule_id": rule.id,
                "service_name": window.service_name,
                "url_path": window.url_path,
                "severity": severity,
                "metric_name": metric_name,
                "window_start": window.window_start,
                "window_end": window.window_end,
                "observed_value": float(observed_value),
                "baseline_value": float(baseline_value),
                "anomaly_score": anomaly_score,
                "reason": reason,
                "likely_cause": likely_cause,
                "recommended_action": recommended_action,
            },
        )

    @staticmethod
    def _classify_severity(anomaly_score: float, rule: AnomalyRule) -> str | None:
        if anomaly_score >= rule.critical_multiplier:
            return "CRITICAL"
        if anomaly_score >= rule.warning_multiplier:
            return "WARNING"
        return None

    @staticmethod
    def _build_recommendations(window: MetricWindow, metric_name: str) -> tuple[str | None, str | None]:
        if window.service_name == "payment-service" and metric_name in {"error_count", "http_5xx_rate", "latency_p95"}:
            cause = window.most_common_error_type or "External payment provider degradation"
            action = "Check payment provider status and inspect recent payment-service deployment"
            return cause, action
        return None, None
