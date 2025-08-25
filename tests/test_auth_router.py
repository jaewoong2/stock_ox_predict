import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure project root is on path for `myapi` imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from myapi.main import app
from myapi.containers import Container
from dependency_injector import providers


class FakeAuthService:
    def __init__(self, db):
        pass

    # register
    def register_local_user(self, user_data):
        from myapi.schemas.auth import Token

        return Token(access_token="fake_access_token", token_type="bearer")

    # login
    def authenticate_local_user(self, login_data):
        from myapi.schemas.auth import Token

        if login_data.password == "bad":
            from myapi.core.exceptions import AuthenticationError

            raise AuthenticationError("Invalid credentials")
        return Token(access_token="login_token", token_type="bearer")

    # refresh
    def refresh_token(self, current_token: str):
        from myapi.schemas.auth import Token

        if current_token == "expired":
            return None
        return Token(access_token="refreshed_token", token_type="bearer")

    # revoke
    def revoke_token(self, token: str) -> bool:
        return token == "valid"


@pytest.fixture(autouse=True)
def patch_auth_service():
    container: Container = app.container  # type: ignore
    override = providers.Factory(FakeAuthService, db=container.repositories.get_db)
    container.services.auth_service.override(override)
    yield
    container.services.auth_service.reset_override()


client = TestClient(app)



# Local login removed: OAuth-only policy


def test_token_refresh_success():
    res = client.post("/api/v1/auth/token/refresh", params={"current_token": "ok"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["access_token"] == "refreshed_token"


def test_token_refresh_failed():
    res = client.post("/api/v1/auth/token/refresh", params={"current_token": "expired"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AUTH_003"


def test_logout_success():
    res = client.post("/api/v1/auth/logout", params={"token": "valid"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["message"] == "Logout successful"
