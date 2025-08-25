from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from myapi.models.session import PhaseEnum
from myapi.repositories.session_repository import SessionRepository
from myapi.schemas.session import SessionStatus, SessionToday

"""_summary_
세션의 주요 기능 및 상태(Phase)

세션은 하루를 기준으로 생성되며, 시간의 흐름에 따라 다음과 같은 여러 단계(Phase)로 상태가 변경됩니다.

1. OPEN (혹은 PREDICT): 예측 가능
    * session_router.flip_to_predict API를 호출하면 이 상태가 됩니다.
    * 사용자들이 '오늘의 종목(Universe)'에 대해 상승/하락 예측을 제출할 수 있는 시간입니다.
    * service.open_predictions() 함수가 이 상태 변경을 처리합니다.

2. CLOSED (혹은 CUTOFF): 예측 마감
    * session_router.cutoff_predictions API를 호출하면 이 상태가 됩니다.
    * 예측 제출이 마감되고, 더 이상 예측을 할 수 없습니다.
    * service.close_predictions() 함수가 이 상태 변경을 처리합니다.

3. SETTLE_READY: 정산 준비
    * 실제 주식 시장 결과가 나오고, 시스템이 정산을 준비하는 단계입니다.
    * service.mark_settle_ready() 함수가 이 상태를 담당합니다.

4. SETTLED: 정산 완료
    * 사용자 예측과 실제 결과를 비교하여 맞춘 사람에게 보상(포인트 등)을 지급하는 정산 과정이 완료된 상태입니다.
    * service.mark_settlement_complete() 함수가 이 상태를 담당합니다.

요약

결론적으로 세션은 이 애플리케이션의 핵심 비즈니스 로직인 "오늘의 종목 예측 -> 마감 -> 결과 처리 -> 보상" 이라는 전체 사이클을
관리하고 현재 어떤 단계에 있는지를 나타내는 상태 관리자의 역할을 합니다.

사용자는 GET /session/today API를 통해 현재 세션이 어떤 단계(phase)에 있는지 확인할 수 있고, 그 상태에 따라 예측을 하거나
결과를 확인하는 등의 작업을 수행하게 됩니다.
"""


class SessionService:
    """세션 관련 비즈니스 로직"""

    def __init__(self, db: Session):
        self.db = db
        self.repo = SessionRepository(db)

    def get_current_status(self) -> Optional[SessionStatus]:
        """현재 세션의 상태를 조회합니다."""
        return self.repo.get_current_session()

    def get_status_by_date(self, trading_day: date) -> Optional[SessionStatus]:
        """특정 날짜의 세션 상태를 조회합니다."""
        return self.repo.get_session_by_date(trading_day)

    def get_today(self) -> Optional[SessionToday]:
        """
        오늘의 세션 정보를 API 응답 형식에 맞게 조회합니다.
        `session_router.get_today_session` 에서 사용됩니다.
        """
        current = self.repo.get_current_session()
        if not current:
            return None
        # Build SessionToday from SessionStatus
        return SessionToday(
            trading_day=current.trading_day.strftime("%Y-%m-%d"),
            phase=current.phase,
            predict_open_at=current.predict_open_at.strftime("%H:%M:%S"),
            predict_cutoff_at=current.predict_cutoff_at.strftime("%H:%M:%S"),
            settle_ready_at=(
                current.settle_ready_at.strftime("%H:%M:%S")
                if current.settle_ready_at
                else None
            ),
            settled_at=(
                current.settled_at.strftime("%H:%M:%S") if current.settled_at else None
            ),
        )

    def create_session(self, trading_day: date) -> SessionStatus:
        """새로운 세션을 생성합니다."""

        predict_open_at = datetime.combine(
            trading_day, datetime.strptime("09:00:00", "%H:%M:%S").time()
        )
        predict_cutoff_at = datetime.combine(
            trading_day, datetime.strptime("15:30:00", "%H:%M:%S").time()
        )

        return self.repo.create_session(
            trading_day=trading_day,
            predict_open_at=predict_open_at,
            predict_cutoff_at=predict_cutoff_at,
            phase=PhaseEnum.CLOSED,
        )

    def open_predictions(
        self, trading_day: Optional[date] = None
    ) -> Optional[SessionStatus]:
        """
        예측을 시작합니다. 세션의 단계를 'PREDICT'로 변경합니다.
        `session_router.flip_to_predict` 에서 호출됩니다.
        """
        if trading_day:
            response = self.repo.open_predictions(trading_day)

            if not response:
                return self.create_session(trading_day)

            return response

        current = self.repo.get_current_session()

        if not current:
            return self.create_session(date.today())

        return self.repo.open_predictions(current.trading_day)

    def close_predictions(
        self, trading_day: Optional[date] = None
    ) -> Optional[SessionStatus]:
        """
        예측을 마감합니다. 세션의 단계를 'CLOSED'로 변경합니다.
        `session_router.cutoff_predictions` 에서 호출됩니다.
        """
        if trading_day:
            return self.repo.close_predictions(trading_day)
        current = self.repo.get_current_session()
        if not current:
            return None
        return self.repo.close_predictions(current.trading_day)

    def mark_settle_ready(
        self, trading_day: Optional[date] = None
    ) -> Optional[SessionStatus]:
        """세션을 '정산 준비' 상태로 변경합니다."""
        if trading_day:
            return self.repo.mark_settle_ready(trading_day)
        current = self.repo.get_current_session()
        if not current:
            return None
        return self.repo.mark_settle_ready(current.trading_day)

    def mark_settlement_complete(
        self, trading_day: Optional[date] = None
    ) -> Optional[SessionStatus]:
        """세션을 '정산 완료' 상태로 변경합니다."""
        if trading_day:
            return self.repo.mark_settlement_complete(trading_day)
        current = self.repo.get_current_session()
        if not current:
            return None
        return self.repo.mark_settlement_complete(current.trading_day)
