import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch

from myapi.services.universe_service import UniverseService
from myapi.schemas.universe import UniverseUpdate, UniverseItem, UniverseResponse
from myapi.schemas.session import SessionStatus, SessionPhase


@pytest.fixture
def mock_db():
    return Mock()


@pytest.fixture
def mock_active_universe_repo():
    return Mock()


@pytest.fixture
def mock_session_repo():
    return Mock()


@pytest.fixture
def universe_service(mock_db):
    with patch(
        "myapi.services.universe_service.ActiveUniverseRepository"
    ) as mock_repo_class:
        with patch(
            "myapi.services.universe_service.SessionRepository"
        ) as mock_session_class:
            mock_repo = Mock()
            mock_session = Mock()
            mock_repo_class.return_value = mock_repo
            mock_session_class.return_value = mock_session

            service = UniverseService(mock_db)
            service.repo = mock_repo
            service.session_repo = mock_session
            return service


@pytest.fixture
def sample_universe_response():
    return UniverseResponse(
        trading_day="2024-01-15",
        symbols=[
            UniverseItem(symbol="AAPL", seq=1),
            UniverseItem(symbol="GOOGL", seq=2),
            UniverseItem(symbol="MSFT", seq=3),
        ],
        total_count=3,
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
        is_closed=False,
    )


class TestUniverseService:
    """UniverseService 테스트"""

    def test_get_today_universe_success(
        self, universe_service, sample_universe_response, sample_session_status
    ):
        """오늘의 유니버스 조회 성공 테스트"""
        # Arrange
        universe_service.session_repo.get_current_session.return_value = (
            sample_session_status
        )
        universe_service.repo.get_universe_response.return_value = (
            sample_universe_response
        )

        # Act
        result = universe_service.get_today_universe()

        # Assert
        assert result is not None
        assert result.trading_day == "2024-01-15"
        assert result.total_count == 3
        universe_service.session_repo.get_current_session.assert_called_once()
        universe_service.repo.get_universe_response.assert_called_once_with(
            sample_session_status.trading_day
        )

    def test_get_today_universe_no_current_session(self, universe_service):
        """현재 세션이 없는 경우 테스트"""
        # Arrange
        universe_service.session_repo.get_current_session.return_value = None

        # Act
        result = universe_service.get_today_universe()

        # Assert
        assert result is None
        universe_service.session_repo.get_current_session.assert_called_once()
        universe_service.repo.get_universe_response.assert_not_called()

    def test_get_universe_for_date(self, universe_service, sample_universe_response):
        """특정 날짜의 유니버스 조회 테스트"""
        # Arrange
        target_date = date(2024, 1, 15)
        universe_service.repo.get_universe_response.return_value = (
            sample_universe_response
        )

        # Act
        result = universe_service.get_universe_for_date(target_date)

        # Assert
        assert result == sample_universe_response
        universe_service.repo.get_universe_response.assert_called_once_with(target_date)

    def test_upsert_universe_success(self, universe_service, sample_universe_response):
        """유니버스 업서트 성공 테스트"""
        # Arrange
        update_payload = UniverseUpdate(
            trading_day="2024-01-15",
            symbols=[
                UniverseItem(symbol="AAPL", seq=1),
                UniverseItem(symbol="GOOGL", seq=2),
                UniverseItem(symbol="MSFT", seq=3),
            ],
        )

        universe_service.repo.set_universe_for_date.return_value = None
        universe_service.repo.get_universe_response.return_value = (
            sample_universe_response
        )

        # Act
        result = universe_service.upsert_universe(update_payload)

        # Assert
        assert result == sample_universe_response
        universe_service.repo.set_universe_for_date.assert_called_once_with(
            date(2024, 1, 15), update_payload.symbols
        )
        universe_service.repo.get_universe_response.assert_called_once_with(
            date(2024, 1, 15)
        )

    def test_upsert_universe_with_date_parsing(self, universe_service):
        """날짜 파싱이 올바르게 작동하는지 테스트"""
        # Arrange
        update_payload = UniverseUpdate(
            trading_day="2024-12-25", symbols=[UniverseItem(symbol="AAPL", seq=1)]
        )

        mock_response = UniverseResponse(
            trading_day="2024-12-25",
            symbols=[UniverseItem(symbol="AAPL", seq=1)],
            total_count=1,
        )

        universe_service.repo.set_universe_for_date.return_value = None
        universe_service.repo.get_universe_response.return_value = mock_response

        # Act
        result = universe_service.upsert_universe(update_payload)

        # Assert
        assert result == mock_response
        universe_service.repo.set_universe_for_date.assert_called_once_with(
            date(2024, 12, 25), update_payload.symbols
        )

    def test_service_initialization(self, mock_db):
        """서비스 초기화 테스트"""
        # Act
        with patch(
            "myapi.services.universe_service.ActiveUniverseRepository"
        ) as mock_repo_class:
            with patch(
                "myapi.services.universe_service.SessionRepository"
            ) as mock_session_class:
                service = UniverseService(mock_db)

        # Assert
        assert service.db == mock_db
        mock_repo_class.assert_called_once_with(mock_db)
        mock_session_class.assert_called_once_with(mock_db)

    def test_get_today_universe_with_empty_universe(
        self, universe_service, sample_session_status
    ):
        """빈 유니버스 응답 처리 테스트"""
        # Arrange
        empty_universe = UniverseResponse(
            trading_day="2024-01-15", symbols=[], total_count=0
        )

        universe_service.session_repo.get_current_session.return_value = (
            sample_session_status
        )
        universe_service.repo.get_universe_response.return_value = empty_universe

        # Act
        result = universe_service.get_today_universe()

        # Assert
        assert result is not None
        assert result.total_count == 0
        assert len(result.symbols) == 0
