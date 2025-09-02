import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from dependency_injector import providers

# Ensure project root is on path for `myapi` imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from myapi.main import app
from myapi.containers import Container


def _fake_now():
    return datetime.now(timezone.utc)


def _stub_current_user():
    from myapi.schemas.user import User, AuthProvider

    return User(
        id=42,
        email="user42@example.com",
        nickname="user42",
        auth_provider=AuthProvider.GOOGLE,
        created_at=_fake_now(),
        last_login_at=None,
        is_active=True,
    )


class FakePredictionService:
    def __init__(self, db):
        pass

    def submit_prediction(self, user_id, trading_day, payload):
        from myapi.schemas.prediction import PredictionResponse, PredictionChoice, PredictionStatus
        from myapi.core.exceptions import RateLimitError

        # Simulate a rate limit error for specific symbol
        if payload.symbol == "ERR":
            raise RateLimitError("Daily prediction limit reached")

        return PredictionResponse(
            id=1,
            user_id=user_id,
            trading_day=trading_day,
            symbol=payload.symbol,
            choice=payload.choice,
            status=PredictionStatus.PENDING,
            submitted_at=_fake_now(),
            updated_at=None,
            points_earned=0,
        )

    def update_prediction(self, user_id, prediction_id, payload):
        from myapi.schemas.prediction import PredictionResponse, PredictionStatus
        from datetime import date
        return PredictionResponse(
            id=prediction_id,
            user_id=user_id,
            trading_day=date(2025, 1, 1),
            symbol="AAPL",
            choice=payload.choice,
            status=PredictionStatus.PENDING,
            submitted_at=_fake_now(),
            updated_at=_fake_now(),
            points_earned=0,
        )

    def cancel_prediction(self, user_id, prediction_id):
        from myapi.schemas.prediction import PredictionResponse, PredictionChoice, PredictionStatus
        from datetime import date
        return PredictionResponse(
            id=prediction_id,
            user_id=user_id,
            trading_day=date(2025, 1, 1),
            symbol="AAPL",
            choice=PredictionChoice.UP,
            status=PredictionStatus.CANCELLED,
            submitted_at=_fake_now(),
            updated_at=_fake_now(),
            points_earned=0,
        )

    def get_user_predictions_for_day(self, user_id, trading_day):
        from myapi.schemas.prediction import (
            UserPredictionsResponse,
            PredictionResponse,
            PredictionChoice,
            PredictionStatus,
        )
        return UserPredictionsResponse(
            trading_day=trading_day,
            predictions=[
                PredictionResponse(
                    id=1,
                    user_id=user_id,
                    trading_day=trading_day,
                    symbol="AAPL",
                    choice=PredictionChoice.UP,
                    status=PredictionStatus.PENDING,
                    submitted_at=_fake_now(),
                    updated_at=None,
                    points_earned=0,
                )
            ],
            total_predictions=1,
            completed_predictions=0,
            pending_predictions=1,
        )

    def get_prediction_stats(self, trading_day):
        from myapi.schemas.prediction import PredictionStats
        return PredictionStats(
            trading_day=trading_day,
            total_predictions=10,
            up_predictions=6,
            down_predictions=4,
            correct_predictions=0,
            accuracy_rate=0.0,
            points_distributed=0,
        )

    def get_user_prediction_summary(self, user_id, trading_day):
        from myapi.schemas.prediction import PredictionSummary
        return PredictionSummary(
            user_id=user_id,
            trading_day=trading_day,
            total_submitted=1,
            correct_count=0,
            incorrect_count=0,
            pending_count=1,
            accuracy_rate=0.0,
            total_points_earned=0,
        )


@pytest.fixture(autouse=True)
def patch_prediction_service_and_auth():
    from myapi.core import auth_middleware

    container: Container = app.container  # type: ignore
    override = providers.Factory(FakePredictionService, db=container.repositories.get_db)
    container.services.prediction_service.override(override)

    # Override auth dependencies to simulate a logged-in user
    app.dependency_overrides[auth_middleware.get_current_active_user] = lambda: _stub_current_user()

    yield

    container.services.prediction_service.reset_override()
    app.dependency_overrides.pop(auth_middleware.get_current_active_user, None)


client = TestClient(app)


def test_submit_prediction_success():
    payload = {"choice": "UP"}
    res = client.post("/api/v1/predictions/AAPL", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["prediction"]["symbol"] == "AAPL"
    assert body["data"]["prediction"]["choice"] == "UP"


def test_submit_prediction_rate_limit_error():
    payload = {"choice": "UP"}
    res = client.post("/api/v1/predictions/ERR", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AUTH_004"  # INVALID_CREDENTIALS mapping


def test_get_user_predictions_for_day():
    res = client.get("/api/v1/predictions/day/2025-01-01")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["result"]["trading_day"] == "2025-01-01"
    assert body["data"]["result"]["total_predictions"] == 1


def test_update_prediction_success():
    payload = {"choice": "DOWN"}
    res = client.put("/api/v1/predictions/1", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["prediction"]["id"] == 1
    assert body["data"]["prediction"]["choice"] == "DOWN"


def test_cancel_prediction_success():
    res = client.delete("/api/v1/predictions/1")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["prediction"]["status"] == "CANCELLED"


def test_stats_and_summary_success():
    res_stats = client.get("/api/v1/predictions/stats/2025-01-01")
    assert res_stats.status_code == 200
    assert res_stats.json()["success"] is True

    res_summary = client.get("/api/v1/predictions/summary/2025-01-01")
    assert res_summary.status_code == 200
    assert res_summary.json()["success"] is True

