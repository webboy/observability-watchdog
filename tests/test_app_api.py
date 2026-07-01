"""App API integration tests."""

from fastapi.testclient import TestClient


def test_create_and_get_app(client: TestClient) -> None:
    """Create app endpoint should persist and return the app."""
    response = client.post(
        "/api/v1/apps",
        json={
            "name": "E-commerce Platform",
            "slug": "ecommerce-platform",
            "environment": "production",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["slug"] == "ecommerce-platform"

    get_response = client.get(f"/api/v1/apps/{payload['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "E-commerce Platform"


def test_duplicate_slug_returns_conflict(client: TestClient) -> None:
    """Duplicate app slugs should return HTTP 409."""
    body = {
        "name": "E-commerce Platform",
        "slug": "ecommerce-platform",
        "environment": "production",
    }
    assert client.post("/api/v1/apps", json=body).status_code == 201
    response = client.post("/api/v1/apps", json=body)

    assert response.status_code == 409


def test_list_apps(client: TestClient) -> None:
    """List apps endpoint should return created apps."""
    client.post(
        "/api/v1/apps",
        json={"name": "Platform A", "slug": "platform-a", "environment": "production"},
    )

    response = client.get("/api/v1/apps")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
