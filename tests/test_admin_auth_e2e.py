from app.core.config import settings


def test_admin_login_returns_bearer_token(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.initial_admin_username,
            "password": settings.initial_admin_password,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["username"] == settings.initial_admin_username


def test_admin_routes_require_bearer_token(client) -> None:
    response = client.get("/api/v1/admin/entities")

    assert response.status_code == 401


def test_admin_route_accepts_login_token(client) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.initial_admin_username,
            "password": settings.initial_admin_password,
        },
    )
    token = login_response.json()["access_token"]

    response = client.get("/api/v1/admin/entities", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    assert "entities" in response.json()
