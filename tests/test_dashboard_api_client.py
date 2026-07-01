"""Dashboard API client tests."""

from dashboard.api_client import WatchdogApiClient


def test_poll_ingestion_run_completes_immediately(monkeypatch) -> None:
    """Polling should return as soon as the ingestion run reaches a terminal state."""
    client = WatchdogApiClient(base_url="http://example.test/api/v1")
    calls = {"count": 0}

    def fake_get(app_id: str, run_id: str):
        calls["count"] += 1
        return {"status": "completed", "accepted_events": 10}

    monkeypatch.setattr(client, "get_ingestion_run", fake_get)
    result = client.poll_ingestion_run("app-id", "run-id", interval_seconds=0, max_attempts=3)
    assert result["status"] == "completed"
    assert calls["count"] == 1
