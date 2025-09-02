from __future__ import annotations
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from myapi.models.session import PhaseEnum
from myapi.repositories.session_repository import SessionRepository
from myapi.schemas.session import (
    SessionStatus,
    SessionToday,
    SessionPhase,
    PredictionTimeStatus,
)
from myapi.utils.market_hours import USMarketHours


class SessionService:
    """세션 관련 비즈니스 로직"""

    def __init__(self, db: Session):
        self.db = db
        self.repo = SessionRepository(db)

    def get_status_by_date(self, trading_day: date) -> Optional[SessionStatus]:
        """특정 날짜의 세션 상태를 조회합니다."""
        return self.repo.get_session_by_date(trading_day)

    def get_today(self) -> Optional[SessionToday]:
        """
        오늘의 세션 정보를 API 응답 형식에 맞게 조회합니다.
        KST 기준 현재 '거래일'의 세션을 조회하거나 생성합니다.
        """
        # KST 기준으로 현재 거래일을 가져옵니다.
        trading_day = USMarketHours.get_kst_trading_day()

        # 해당 거래일이 실제 미국 증시 거래일인지 확인합니다.
        if not USMarketHours.is_us_trading_day(trading_day):
            return None

        # 해당 거래일의 세션을 조회합니다.
        current_session = self.repo.get_session_by_date(trading_day)

        # 세션이 없으면 새로 생성합니다.
        if not current_session:
            current_session = self.create_session(trading_day)

        return SessionToday(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            phase=current_session.phase,
            predict_open_at=current_session.predict_open_at.strftime("%H:%M:%S"),
            predict_cutoff_at=current_session.predict_cutoff_at.strftime("%H:%M:%S"),
            settle_ready_at=(
                current_session.settle_ready_at.strftime("%H:%M:%S")
                if current_session.settle_ready_at
                else None
            ),
            settled_at=(
                current_session.settled_at.strftime("%H:%M:%S")
                if current_session.settled_at
                else None
            ),
        )

    def create_session(self, trading_day: date) -> SessionStatus:
        """
        새로운 세션을 생성합니다.
        지정된 거래일의 예측 시간을 KST 기준으로 설정합니다.
        """
        if not USMarketHours.is_us_trading_day(trading_day):
            raise ValueError(f"{trading_day}는 미국 증시 거래일이 아닙니다.")

        # KST 기준 예측 세션 시간 (06:00 ~ 23:59:59)
        start_time, end_time = USMarketHours.get_prediction_session_kst(trading_day)

        return self.repo.create_session(
            trading_day=trading_day,
            predict_open_at=start_time,
            predict_cutoff_at=end_time,
            phase=PhaseEnum.CLOSED,  # 생성 시 기본 상태는 CLOSED
        )

    def open_predictions(
        self, trading_day: Optional[date] = None
    ) -> Optional[SessionStatus]:
        """
        예측을 시작합니다. 세션의 단계를 'OPEN'으로 변경합니다.
        `session_router.flip_to_predict` 에서 호출됩니다.
        """
        target_date = trading_day or USMarketHours.get_kst_trading_day()

        if not USMarketHours.is_us_trading_day(target_date):
            raise ValueError(f"{target_date}는 미국 증시 거래일이 아닙니다.")

        # 세션이 있는지 확인하고 없으면 생성
        session = self.repo.get_session_by_date(target_date)
        if not session:
            self.create_session(target_date)

        # 세션을 OPEN 상태로 변경
        return self.repo.open_predictions(target_date)

    def close_predictions(
        self, trading_day: Optional[date] = None
    ) -> Optional[SessionStatus]:
        """
        예측을 마감합니다. 세션의 단계를 'CLOSED'로 변경합니다.
        `session_router.cutoff_predictions` 에서 호출됩니다.
        """
        target_date = trading_day or USMarketHours.get_kst_trading_day()

        session = self.repo.get_session_by_date(target_date)
        if not session:
            # 마감할 세션이 없으면 아무것도 하지 않음
            return None

        return self.repo.close_predictions(target_date)

    def is_prediction_time(self, trading_day: Optional[date] = None) -> bool:
        """
        현재 예측이 가능한지 확인합니다.
        """
        target_date = trading_day or USMarketHours.get_kst_trading_day()

        # 1. KST 시간이 예측 가능 창(06:00-23:59)에 있는지 확인
        if not USMarketHours.is_prediction_window():
            return False

        # 2. 해당 거래일의 세션이 OPEN 상태인지 확인
        session = self.repo.get_session_by_date(target_date)
        if not session or session.phase != SessionPhase.OPEN:
            return False

        return True

    def get_prediction_time_status(
        self, trading_day: Optional[date] = None
    ) -> PredictionTimeStatus:
        """
        예측 시간 관련 상세 상태를 반환합니다.
        """
        target_date = trading_day or USMarketHours.get_kst_trading_day()
        current_kst = USMarketHours.get_current_kst_time()

        status = PredictionTimeStatus(
            can_predict=False,
            is_trading_day=USMarketHours.is_us_trading_day(target_date),
            is_in_time_range=False,
            session_phase=None,
            time_until_start=0,
            time_until_end=0,
            message="",
        )

        if not status.is_trading_day:
            status.message = f"{target_date}는 미국 증시 거래일이 아닙니다."
            return status

        session = self.repo.get_session_by_date(target_date)
        if session:
            status.session_phase = session.phase.value

        start_time, end_time = USMarketHours.get_prediction_session_kst(target_date)
        status.is_in_time_range = start_time <= current_kst <= end_time

        if current_kst < start_time:
            status.time_until_start = int((start_time - current_kst).total_seconds())
            status.message = f"예측 시작까지 {status.time_until_start}초 남았습니다."
        elif current_kst > end_time:
            status.message = "오늘 예측 시간이 종료되었습니다."
        else:  # In prediction time range
            if session and session.phase == SessionPhase.OPEN:
                status.can_predict = True
                status.time_until_end = int((end_time - current_kst).total_seconds())
                status.message = (
                    f"예측 가능. 마감까지 {status.time_until_end}초 남았습니다."
                )
            else:
                status.message = f"예측 시간대이지만 세션이 OPEN 상태가 아닙니다 (현재: {session.phase.value if session else '없음'})."

        return status
