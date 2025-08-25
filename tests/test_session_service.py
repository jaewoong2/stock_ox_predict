import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch

from myapi.services.session_service import SessionService
from myapi.schemas.session import SessionStatus, SessionToday, SessionPhase


@pytest.fixture
def mock_db():
    return Mock()


@pytest.fixture
def session_service(mock_db):
    with patch("myapi.services.session_service.SessionRepository") as mock_repo_class:
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        
        service = SessionService(mock_db)
        service.repo = mock_repo
        return service


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


class TestSessionService:
    """SessionService 테스트"""

    def test_get_current_status(self, session_service, sample_session_status):
        """현재 세션 상태 조회 테스트"""
        # Arrange
        session_service.repo.get_current_session.return_value = sample_session_status

        # Act
        result = session_service.get_current_status()

        # Assert
        assert result == sample_session_status
        session_service.repo.get_current_session.assert_called_once()

    def test_get_status_by_date(self, session_service, sample_session_status):
        """특정 날짜 세션 상태 조회 테스트"""
        # Arrange
        target_date = date(2024, 1, 15)
        session_service.repo.get_session_by_date.return_value = sample_session_status

        # Act
        result = session_service.get_status_by_date(target_date)

        # Assert
        assert result == sample_session_status
        session_service.repo.get_session_by_date.assert_called_once_with(target_date)

    def test_get_today_success(self, session_service, sample_session_status):
        """오늘 세션 정보 조회 성공 테스트"""
        # Arrange
        session_service.repo.get_current_session.return_value = sample_session_status

        # Act
        result = session_service.get_today()

        # Assert
        assert result is not None
        assert isinstance(result, SessionToday)
        assert result.trading_day == "2024-01-15"
        assert result.phase == SessionPhase.OPEN
        assert result.predict_open_at == "09:00:00"
        assert result.predict_cutoff_at == "15:30:00"
        assert result.settle_ready_at is None
        assert result.settled_at is None

    def test_get_today_no_current_session(self, session_service):
        """현재 세션이 없는 경우 테스트"""
        # Arrange
        session_service.repo.get_current_session.return_value = None

        # Act
        result = session_service.get_today()

        # Assert
        assert result is None
        session_service.repo.get_current_session.assert_called_once()

    def test_get_today_with_settlement_times(self, session_service):
        """정산 시간이 포함된 세션 테스트"""
        # Arrange
        session_with_settlement = SessionStatus(
            trading_day=date(2024, 1, 15),
            phase=SessionPhase.SETTLING,
            predict_open_at=datetime(2024, 1, 15, 9, 0, 0),
            predict_cutoff_at=datetime(2024, 1, 15, 15, 30, 0),
            settle_ready_at=datetime(2024, 1, 15, 16, 0, 0),
            settled_at=datetime(2024, 1, 15, 17, 0, 0),
            is_prediction_open=False,
            is_settling=True,
            is_closed=False
        )
        
        session_service.repo.get_current_session.return_value = session_with_settlement

        # Act
        result = session_service.get_today()

        # Assert
        assert result is not None
        assert result.settle_ready_at == "16:00:00"
        assert result.settled_at == "17:00:00"
        assert result.phase == SessionPhase.SETTLING

    def test_open_predictions_with_date(self, session_service, sample_session_status):
        """특정 날짜로 예측 시작 테스트"""
        # Arrange
        target_date = date(2024, 1, 15)
        session_service.repo.open_predictions.return_value = sample_session_status

        # Act
        result = session_service.open_predictions(target_date)

        # Assert
        assert result == sample_session_status
        session_service.repo.open_predictions.assert_called_once_with(target_date)

    def test_open_predictions_without_date(self, session_service, sample_session_status):
        """현재 세션으로 예측 시작 테스트"""
        # Arrange
        session_service.repo.get_current_session.return_value = sample_session_status
        session_service.repo.open_predictions.return_value = sample_session_status

        # Act
        result = session_service.open_predictions()

        # Assert
        assert result == sample_session_status
        session_service.repo.get_current_session.assert_called_once()
        session_service.repo.open_predictions.assert_called_once_with(sample_session_status.trading_day)

    def test_open_predictions_no_current_session(self, session_service):
        """현재 세션이 없을 때 예측 시작 테스트"""
        # Arrange
        session_service.repo.get_current_session.return_value = None

        # Act
        result = session_service.open_predictions()

        # Assert
        assert result is None
        session_service.repo.get_current_session.assert_called_once()
        session_service.repo.open_predictions.assert_not_called()

    def test_close_predictions_with_date(self, session_service, sample_session_status):
        """특정 날짜로 예측 마감 테스트"""
        # Arrange
        target_date = date(2024, 1, 15)
        closed_session = sample_session_status.model_copy(update={
            "phase": SessionPhase.CLOSED,
            "is_prediction_open": False,
            "is_closed": True
        })
        session_service.repo.close_predictions.return_value = closed_session

        # Act
        result = session_service.close_predictions(target_date)

        # Assert
        assert result == closed_session
        session_service.repo.close_predictions.assert_called_once_with(target_date)

    def test_close_predictions_without_date(self, session_service, sample_session_status):
        """현재 세션으로 예측 마감 테스트"""
        # Arrange
        closed_session = sample_session_status.model_copy(update={
            "phase": SessionPhase.CLOSED,
            "is_prediction_open": False,
            "is_closed": True
        })
        session_service.repo.get_current_session.return_value = sample_session_status
        session_service.repo.close_predictions.return_value = closed_session

        # Act
        result = session_service.close_predictions()

        # Assert
        assert result == closed_session
        session_service.repo.get_current_session.assert_called_once()
        session_service.repo.close_predictions.assert_called_once_with(sample_session_status.trading_day)

    def test_mark_settle_ready(self, session_service, sample_session_status):
        """정산 준비 상태로 변경 테스트"""
        # Arrange
        settle_ready_session = sample_session_status.model_copy(update={
            "phase": SessionPhase.SETTLING,
            "is_settling": True,
            "settle_ready_at": datetime(2024, 1, 15, 16, 0, 0)
        })
        session_service.repo.get_current_session.return_value = sample_session_status
        session_service.repo.mark_settle_ready.return_value = settle_ready_session

        # Act
        result = session_service.mark_settle_ready()

        # Assert
        assert result == settle_ready_session
        session_service.repo.get_current_session.assert_called_once()
        session_service.repo.mark_settle_ready.assert_called_once_with(sample_session_status.trading_day)

    def test_mark_settlement_complete(self, session_service, sample_session_status):
        """정산 완료 상태로 변경 테스트"""
        # Arrange
        settled_session = sample_session_status.model_copy(update={
            "phase": SessionPhase.SETTLING,
            "settled_at": datetime(2024, 1, 15, 17, 0, 0)
        })
        session_service.repo.get_current_session.return_value = sample_session_status
        session_service.repo.mark_settlement_complete.return_value = settled_session

        # Act
        result = session_service.mark_settlement_complete()

        # Assert
        assert result == settled_session
        session_service.repo.get_current_session.assert_called_once()
        session_service.repo.mark_settlement_complete.assert_called_once_with(sample_session_status.trading_day)

    def test_service_initialization(self, mock_db):
        """서비스 초기화 테스트"""
        # Act
        with patch("myapi.services.session_service.SessionRepository") as mock_repo_class:
            service = SessionService(mock_db)

        # Assert
        assert service.db == mock_db
        mock_repo_class.assert_called_once_with(mock_db)

    def test_datetime_formatting_edge_cases(self, session_service):
        """시간 포맷팅 엣지 케이스 테스트"""
        # Arrange
        session_with_edge_times = SessionStatus(
            trading_day=date(2024, 1, 15),
            phase=SessionPhase.OPEN,
            predict_open_at=datetime(2024, 1, 15, 0, 0, 0),  # Midnight
            predict_cutoff_at=datetime(2024, 1, 15, 23, 59, 59),  # Almost midnight
            settle_ready_at=datetime(2024, 1, 15, 12, 30, 45),  # With seconds
            settled_at=None,
            is_prediction_open=True,
            is_settling=False,
            is_closed=False
        )
        
        session_service.repo.get_current_session.return_value = session_with_edge_times

        # Act
        result = session_service.get_today()

        # Assert
        assert result is not None
        assert result.predict_open_at == "00:00:00"
        assert result.predict_cutoff_at == "23:59:59"
        assert result.settle_ready_at == "12:30:45"
        assert result.settled_at is None