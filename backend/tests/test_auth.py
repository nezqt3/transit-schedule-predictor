import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.auth import CurrentUser
from app.services.telemetry import TelemetryService


class FakeAuthService:
    async def authenticate(self, username: str, password: str) -> CurrentUser | None:
        if username == "dispatcher" and password == "transport":
            return CurrentUser(username=username)
        return None

    async def get_current_user(self, username: str) -> CurrentUser | None:
        if username == "dispatcher":
            return CurrentUser(username=username)
        return None


@pytest.fixture
def client():
    app.state.auth_service = FakeAuthService()
    app.state.auth_available = True
    app.state.telemetry = TelemetryService()
    test_client = TestClient(app)
    yield test_client
    test_client.close()


def test_protected_route_requires_authentication(client: TestClient):
    response = client.get("/api/v1/vehicles")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_persists_http_only_cookie_and_logout_clears_it(client: TestClient):
    login = client.post(
        "/api/v1/auth/token",
        data={"username": "dispatcher", "password": "transport"},
    )

    assert login.status_code == 200
    cookie = login.headers["set-cookie"]
    assert "transport_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie

    current_user = client.get("/api/v1/auth/me")
    assert current_user.status_code == 200
    assert current_user.json() == {"username": "dispatcher", "role": "dispatcher"}

    vehicles = client.get("/api/v1/vehicles")
    assert vehicles.status_code == 200

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_rejects_invalid_credentials(client: TestClient):
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "dispatcher", "password": "wrong"},
    )

    assert response.status_code == 401
    assert "transport_session=" not in response.headers.get("set-cookie", "")
