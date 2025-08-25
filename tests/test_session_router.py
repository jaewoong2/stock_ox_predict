import pytest
from datetime import date, datetime
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from myapi.main import app
from myapi.schemas.session import SessionToday, SessionStatus, SessionPhase
from myapi.core.auth_middleware import get_current_active_user


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_session_today():
    return SessionToday(
        trading_day="2024-01-15",
        phase=SessionPhase.OPEN,
        predict_open_at="09:00:00",
        predict_cutoff_at="15:30:00",
        settle_ready_at=None,
        settled_at=None
    )


@pytest.fixture
def sample_session_status():
    return SessionStatus(
        trading_day=date(2024, 1, 15),
        phase=SessionPhase.OPEN,
        predict_open_at=datetime(2024, 1, 15, 9, 0, 0),
        predict_cutoff_at=datetime(2024, 1, 15, 15, 30, 0),
        settle_ready_at=None,
        settled_at=None,
        is_prediction_open=True,
        is_settling=False,
        is_closed=False
    )


class TestSessionRouter:
    """Session 라우터 테스트"""

    def test_get_today_session_success(
        self, client, sample_session_today
    ):
        """오늘의 세션 조회 성공 테스트"""
        # Arrange
        mock_service = Mock()
        mock_service.get_today.return_value = sample_session_today
        
        with app.container.services.session_service.override(mock_service):
            # Act
            response = client.get("/api/v1/session/today")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "session" in data["data"]
        assert data["data"]["session"]["trading_day"] == "2024-01-15"
        assert data["data"]["session"]["phase"] == "OPEN"

    def test_get_today_session_not_found(self, client):
        """오늘의 세션이 없는 경우 테스트"""
        # Arrange
        mock_service = Mock()
        mock_service.get_today.return_value = None
        
        with app.container.services.session_service.override(mock_service):
            # Act
            response = client.get("/api/v1/session/today")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["session"] is None

    def test_flip_to_predict_success(
        self, client, sample_session_status
    ):
        """예측 시작 성공 테스트"""
        # Arrange
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")
        mock_service = Mock()
        mock_service.open_predictions.return_value = sample_session_status
        
        with app.container.services.session_service.override(mock_service):
            # Act
            response = client.post("/api/v1/session/flip-to-predict")
        
        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data["data"]
        mock_service.open_predictions.assert_called_once()

    def test_flip_to_predict_no_session(
        self, client
    ):
        """세션이 없는 경우 예측 시작 테스트"""
        # Arrange
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")
        mock_service = Mock()
        mock_service.open_predictions.return_value = None
        
        with app.container.services.session_service.override(mock_service):
            # Act
            response = client.post("/api/v1/session/flip-to-predict")

        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] is None

    def test_cutoff_predictions_success(
        self, client
    ):
        """예측 마감 성공 테스트"""
        # Arrange
        closed_session = SessionStatus(
            trading_day=date(2024, 1, 15),
            phase=SessionPhase.CLOSED,
            predict_open_at=datetime(2024, 1, 15, 9, 0, 0),
            predict_cutoff_at=datetime(2024, 1, 15, 15, 30, 0),
            settle_ready_at=None,
            settled_at=None,
            is_prediction_open=False,
            is_settling=False,
            is_closed=True
        )
        
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")
        mock_service = Mock()
        mock_service.close_predictions.return_value = closed_session
        
        with app.container.services.session_service.override(mock_service):
            # Act
            response = client.post("/api/v1/session/cutoff")

        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data["data"]
        mock_service.close_predictions.assert_called_once()

    def test_cutoff_predictions_no_session(
        self, client
    ):
        """세션이 없는 경우 예측 마감 테스트"""
        # Arrange
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")
        mock_service = Mock()
        mock_service.close_predictions.return_value = None
        
        with app.container.services.session_service.override(mock_service):
            # Act
            response = client.post("/api/v1/session/cutoff")

        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] is None

    def test_get_today_session_unauthorized_allowed(self, client):
        """오늘의 세션 조회는 인증 없이도 가능해야 함"""
        # Act
        mock_service = Mock()
        mock_service.get_today.return_value = None
        with app.container.services.session_service.override(mock_service):
            response = client.get("/api/v1/session/today")

        # Assert
        assert response.status_code == 200  # Should not require auth

    def test_flip_to_predict_unauthorized(self, client):
        """예측 시작은 인증이 필요해야 함"""
        # Act
        response = client.post("/api/v1/session/flip-to-predict")

        # Assert
        assert response.status_code == 401  # Unauthorized

    def test_cutoff_predictions_unauthorized(self, client):
        """예측 마감은 인증이 필요해야 함"""
        # Act
        response = client.post("/api/v1/session/cutoff")

        # Assert
        assert response.status_code == 401  # Unauthorized

    def test_service_error_handling(
        self, client
    ):
        """서비스 에러 처리 테스트"""
        # Arrange
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")
        mock_service = Mock()
        mock_service.open_predictions.side_effect = Exception("Service error")
        
        with app.container.services.session_service.override(mock_service):
            # Act
            response = client.post("/api/v1/session/flip-to-predict")

        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 500

    def test_get_today_session_service_error(self, client):
        """세션 조회 서비스 에러 테스트"""
        # Arrange
        mock_service = Mock()
        mock_service.get_today.side_effect = Exception("Service error")
        
        with app.container.services.session_service.override(mock_service):
            # Act
            response = client.get("/api/v1/session/today")

        # Assert
        assert response.status_code == 500