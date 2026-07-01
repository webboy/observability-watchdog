"""HTTP client helpers for the Streamlit dashboard."""

from __future__ import annotations

import time
from typing import Any

import requests

DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1"
POLL_INTERVAL_SECONDS = 1.0
MAX_POLL_ATTEMPTS = 120


class ApiClientError(Exception):
    """Raised when an API request fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class WatchdogApiClient:
    """Thin REST client for dashboard interactions."""

    def __init__(self, base_url: str = DEFAULT_API_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = requests.request(
            method,
            url,
            params=params,
            json=json,
            files=files,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            detail = response.text
            try:
                payload = response.json()
                detail = payload.get("detail", detail)
            except ValueError:
                pass
            raise ApiClientError(str(detail), status_code=response.status_code)
        if response.status_code == 204:
            return None
        if not response.content:
            return None
        return response.json()

    def list_apps(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/apps")
        return payload.get("items", [])

    def create_app(self, *, name: str, slug: str, environment: str, description: str | None = None) -> dict[str, Any]:
        body = {"name": name, "slug": slug, "environment": environment}
        if description:
            body["description"] = description
        return self._request("POST", "/apps", json=body)

    def upload_logs(self, app_id: str, filename: str, content: bytes) -> dict[str, Any]:
        files = {"file": (filename, content, "application/jsonl")}
        return self._request("POST", f"/apps/{app_id}/logs/upload", files=files)

    def load_sample_dataset(self, app_id: str) -> dict[str, Any]:
        return self._request("POST", f"/apps/{app_id}/demo/load-sample-dataset")

    def clear_app_data(self, app_id: str) -> dict[str, Any]:
        return self._request("POST", f"/apps/{app_id}/demo/clear-data")

    def get_ingestion_run(self, app_id: str, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/apps/{app_id}/ingestion-runs/{run_id}")

    def poll_ingestion_run(
        self,
        app_id: str,
        run_id: str,
        *,
        interval_seconds: float = POLL_INTERVAL_SECONDS,
        max_attempts: int = MAX_POLL_ATTEMPTS,
    ) -> dict[str, Any]:
        """Poll ingestion run status until completed or failed."""
        for _ in range(max_attempts):
            run = self.get_ingestion_run(app_id, run_id)
            status = run.get("status")
            if status in {"completed", "failed"}:
                return run
            time.sleep(interval_seconds)
        raise ApiClientError("Timed out waiting for ingestion run to complete")

    def get_overview(self, app_id: str) -> dict[str, Any]:
        return self._request("GET", f"/apps/{app_id}/dashboard/overview")

    def get_metric_windows(self, app_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/apps/{app_id}/dashboard/metric-windows", params={"limit": limit})
        return payload.get("items", [])

    def get_top_failing_services(self, app_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"/apps/{app_id}/dashboard/top-failing-services",
            params={"limit": limit},
        )
        return payload.get("items", [])

    def get_anomalies(self, app_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/apps/{app_id}/dashboard/anomalies", params={"limit": limit})
        return payload.get("items", [])

    def get_alerts(self, app_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/apps/{app_id}/alerts", params={"limit": limit})
        return payload.get("items", [])

    def get_incident_summaries(self, app_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/apps/{app_id}/incidents/summary", params={"limit": limit})
        return payload.get("items", [])
