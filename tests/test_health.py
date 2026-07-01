"""Health endpoint tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    """Basic health endpoint should return ok status."""
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app_name"] == "Observability Watchdog"
    assert payload["environment"] == "development"


def test_api_v1_health_endpoint_shape() -> None:
    """Detailed health endpoint should include database field when DB is available."""
    response = client.get("/api/v1/health")

    # When DB is unavailable in CI/local without postgres, endpoint returns 503.
    if response.status_code == 200:
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["database"] == "connected"
    else:
        assert response.status_code == 503
