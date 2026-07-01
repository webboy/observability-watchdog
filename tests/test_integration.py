"""End-to-end FastAPI integration tests."""

import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SAMPLE_INCIDENT_PATH = Path("data/sample_incident_logs.jsonl")


def _create_app(client: TestClient) -> str:
    response = client.post(
        "/api/v1/apps",
        json={
            "name": "Integration Platform",
            "slug": f"integration-{uuid.uuid4().hex[:8]}",
            "environment": "production",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _poll_ingestion_run(client: TestClient, app_id: str, run_id: str, *, timeout_seconds: float = 30.0) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/api/v1/apps/{app_id}/ingestion-runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Ingestion run {run_id} did not complete within {timeout_seconds}s")


@pytest.mark.skipif(not SAMPLE_INCIDENT_PATH.exists(), reason="sample incident dataset missing")
def test_full_mvp_flow_upload_poll_and_dashboard_reads(client: TestClient) -> None:
    """Full MVP path: create app, clear data, upload, poll, and read dashboard APIs."""
    app_id = _create_app(client)

    clear_response = client.post(f"/api/v1/apps/{app_id}/demo/clear-data")
    assert clear_response.status_code == 200

    with SAMPLE_INCIDENT_PATH.open("rb") as handle:
        upload_response = client.post(
            f"/api/v1/apps/{app_id}/logs/upload",
            files={"file": ("sample_incident_logs.jsonl", handle, "application/jsonl")},
        )

    assert upload_response.status_code == 201
    upload_payload = upload_response.json()
    assert upload_payload["accepted_events"] > 0
    assert upload_payload["status"] == "processing"

    run_payload = _poll_ingestion_run(client, app_id, upload_payload["ingestion_run_id"])
    assert run_payload["status"] == "completed"
    assert run_payload["accepted_events"] > 0
    assert run_payload["detected_anomalies"] > 0
    assert run_payload["alerts_triggered"] > 0

    anomalies_response = client.get(f"/api/v1/apps/{app_id}/dashboard/anomalies")
    assert anomalies_response.status_code == 200
    anomalies = anomalies_response.json()["items"]
    assert len(anomalies) > 0

    alerts_response = client.get(f"/api/v1/apps/{app_id}/alerts")
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()["items"]
    assert len(alerts) > 0

    summary_response = client.get(f"/api/v1/apps/{app_id}/incidents/summary")
    assert summary_response.status_code == 200
    summaries = summary_response.json()["items"]
    assert len(summaries) > 0
    first_summary = summaries[0]
    for field in (
        "summary",
        "what_happened",
        "likely_cause",
        "business_impact",
        "recommended_action",
        "generation_source",
    ):
        assert first_summary.get(field)

    overview_response = client.get(f"/api/v1/apps/{app_id}/dashboard/overview")
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["total_logs"] > 0
    assert overview["system_health_score"] >= 0

    metric_windows_response = client.get(f"/api/v1/apps/{app_id}/dashboard/metric-windows")
    assert metric_windows_response.status_code == 200
    assert len(metric_windows_response.json()["items"]) > 0
