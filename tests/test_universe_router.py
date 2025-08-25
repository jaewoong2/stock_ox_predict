import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from myapi.main import app
from myapi.schemas.universe import UniverseResponse, UniverseItem
from myapi.core.auth_middleware import get_current_active_user


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_universe_service():
    return Mock()


@pytest.fixture
def sample_universe_response():
    return UniverseResponse(
        trading_day="2024-01-15",
        symbols=[
            UniverseItem(symbol="AAPL", seq=1),
            UniverseItem(symbol="GOOGL", seq=2),
            UniverseItem(symbol="MSFT", seq=3),
        ],
        total_count=3
    )


class TestUniverseRouter:
    """Universe 라우터 테스트"""

    def test_get_today_universe_success(
        self, client, sample_universe_response
    ):
        """오늘의 유니버스 조회 성공 테스트"""
        # Arrange
        mock_service = Mock()
        mock_service.get_today_universe.return_value = sample_universe_response
        
        with app.container.services.universe_service.override(mock_service):
            # Act
            response = client.get("/api/v1/universe/today")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "universe" in data["data"]
        assert data["data"]["universe"]["total_count"] == 3
        assert len(data["data"]["universe"]["symbols"]) == 3

    def test_get_today_universe_not_found(self, client):
        """오늘의 유니버스가 없는 경우 테스트"""
        # Arrange
        mock_service = Mock()
        mock_service.get_today_universe.return_value = None
        
        with app.container.services.universe_service.override(mock_service):
            # Act
            response = client.get("/api/v1/universe/today")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["universe"] is None

    def test_upsert_universe_success(
        self, client, sample_universe_response
    ):
        """유니버스 업서트 성공 테스트"""
        # Arrange
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")
        mock_service = Mock()
        mock_service.upsert_universe.return_value = sample_universe_response
        
        payload = {
            "trading_day": "2024-01-15",
            "symbols": [
                {"symbol": "AAPL", "seq": 1},
                {"symbol": "GOOGL", "seq": 2},
                {"symbol": "MSFT", "seq": 3},
            ]
        }
        
        with app.container.services.universe_service.override(mock_service):
            # Act
            response = client.post("/api/v1/universe/upsert", json=payload)

        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "universe" in data["data"]
        mock_service.upsert_universe.assert_called_once()

    def test_upsert_universe_validation_error(
        self, client
    ):
        """유니버스 업서트 검증 에러 테스트"""
        # Arrange
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")

        # Invalid payload - missing required fields
        payload = {
            "trading_day": "invalid-date",
            "symbols": []
        }

        # Act
        response = client.post("/api/v1/universe/upsert", json=payload)
        
        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 422  # Validation error

    def test_upsert_universe_duplicate_symbols(
        self, client
    ):
        """유니버스 업서트 중복 심볼 에러 테스트"""
        # Arrange
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")

        payload = {
            "trading_day": "2024-01-15",
            "symbols": [
                {"symbol": "AAPL", "seq": 1},
                {"symbol": "AAPL", "seq": 2},  # Duplicate symbol
            ]
        }

        # Act
        response = client.post("/api/v1/universe/upsert", json=payload)
        
        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 422  # Validation error

    def test_upsert_universe_duplicate_sequences(
        self, client
    ):
        """유니버스 업서트 중복 시퀀스 에러 테스트"""
        # Arrange
        app.dependency_overrides[get_current_active_user] = lambda: Mock(id=1, email="admin@test.com")

        payload = {
            "trading_day": "2024-01-15",
            "symbols": [
                {"symbol": "AAPL", "seq": 1},
                {"symbol": "GOOGL", "seq": 1},  # Duplicate sequence
            ]
        }

        # Act
        response = client.post("/api/v1/universe/upsert", json=payload)
        
        app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 422  # Validation error

    def test_get_today_universe_unauthorized_allowed(self, client):
        """오늘의 유니버스 조회는 인증 없이도 가능해야 함"""
        # This test ensures that the endpoint is accessible without authentication
        # Arrange
        mock_service = Mock()
        mock_service.get_today_universe.return_value = None
        
        with app.container.services.universe_service.override(mock_service):
            # Act
            response = client.get("/api/v1/universe/today")

        # Assert
        assert response.status_code == 200  # Should not require auth

    def test_upsert_universe_unauthorized(self, client):
        """유니버스 업서트는 인증이 필요해야 함"""
        # Arrange
        payload = {
            "trading_day": "2024-01-15",
            "symbols": [{"symbol": "AAPL", "seq": 1}]
        }

        # Act
        response = client.post("/api/v1/universe/upsert", json=payload)

        # Assert
        assert response.status_code == 401  # Unauthorized