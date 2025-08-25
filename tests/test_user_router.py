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


class FakeUserService:
    def __init__(self, db):
        pass

    def update_user_profile(self, user_id, update_data):
        from myapi.schemas.user import User, AuthProvider
        from myapi.core.exceptions import ValidationError
        if update_data.nickname == "dup":
            raise ValidationError("Nickname already taken")
        return User(
            id=user_id,
            email=update_data.email or "me@example.com",
            nickname=update_data.nickname or "me",
            auth_provider=AuthProvider.LOCAL,
            created_at=fake_now(),
            last_login_at=None,
            is_active=True,
        )

    def get_user_profile(self, user_id):
        from myapi.schemas.user import UserProfile, AuthProvider

        return UserProfile(
            user_id=user_id,
            email=f"user{user_id}@example.com",
            nickname=f"user{user_id}",
            auth_provider=AuthProvider.LOCAL,
            created_at=fake_now(),
            is_oauth_user=False,
        )

    def get_active_users(self, limit=50, offset=0):
        from myapi.schemas.user import User, AuthProvider

        return [
            User(
                id=1,
                email="a@example.com",
                nickname="a",
                auth_provider=AuthProvider.LOCAL,
                created_at=fake_now(),
                last_login_at=None,
                is_active=True,
            ),
            User(
                id=2,
                email="b@example.com",
                nickname="b",
                auth_provider=AuthProvider.GOOGLE,
                created_at=fake_now(),
                last_login_at=None,
                is_active=True,
            ),
        ]

    def search_users_by_nickname(self, nickname_pattern: str, limit: int = 20):
        return self.get_active_users(limit=limit)

    def get_user_stats(self):
        from myapi.schemas.user import UserStats

        return UserStats(total_users=10, active_users=9, oauth_users=3, local_users=7)

    def validate_email_availability(self, email: str, exclude_user_id=None) -> bool:
        return email != "taken@example.com"

    def validate_nickname_availability(self, nickname: str, exclude_user_id=None) -> bool:
        return nickname != "taken"

    def deactivate_user(self, user_id: int):
        from myapi.schemas.user import User, AuthProvider

        return User(
            id=user_id,
            email="me@example.com",
            nickname="me",
            auth_provider=AuthProvider.LOCAL,
            created_at=fake_now(),
            last_login_at=None,
            is_active=False,
        )


def fake_now():
    # Pydantic v2 BaseModel accepts datetime-like strings if validated,
    # but we ensure a proper datetime object
    import datetime as _dt

    return _dt.datetime.utcnow()


def _stub_current_user():
    from myapi.schemas.user import User, AuthProvider

    return User(
        id=100,
        email="me@example.com",
        nickname="me",
        auth_provider=AuthProvider.LOCAL,
        created_at=fake_now(),
        last_login_at=None,
        is_active=True,
    )


@pytest.fixture(autouse=True)
def patch_user_service_and_auth():
    from myapi.core import auth_middleware

    container: Container = app.container  # type: ignore
    override = providers.Factory(FakeUserService, db=container.repositories.get_db)
    container.services.user_service.override(override)

    # Override auth dependencies
    app.dependency_overrides[auth_middleware.get_current_active_user] = lambda: _stub_current_user()
    app.dependency_overrides[auth_middleware.get_current_user_optional] = lambda: _stub_current_user()

    yield

    container.services.user_service.reset_override()
    app.dependency_overrides.pop(auth_middleware.get_current_active_user, None)
    app.dependency_overrides.pop(auth_middleware.get_current_user_optional, None)


client = TestClient(app)


def test_get_me_success():
    res = client.get("/api/v1/users/me")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["email"] == "me@example.com"


def test_update_me_validation_error():
    payload = {"nickname": "dup"}
    res = client.put("/api/v1/users/me", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AUTH_004"  # INVALID_CREDENTIALS mapping used in router


def test_get_user_by_id_success():
    res = client.get("/api/v1/users/123")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["user_id"] == 123


def test_get_users_list_success():
    res = client.get("/api/v1/users?limit=10&offset=0")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["count"] == 2


def test_validate_email_and_nickname():
    res_email = client.post("/api/v1/users/validate/email", params={"email": "free@example.com"})
    assert res_email.status_code == 200
    assert res_email.json()["data"]["is_available"] is True

    res_nick = client.post("/api/v1/users/validate/nickname", params={"nickname": "taken"})
    assert res_nick.status_code == 200
    assert res_nick.json()["data"]["is_available"] is False


def test_deactivate_me_success():
    res = client.delete("/api/v1/users/me")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "deactivated" in body["data"]["message"].lower()
