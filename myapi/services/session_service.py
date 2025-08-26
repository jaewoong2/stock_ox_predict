from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from myapi.models.session import PhaseEnum
from myapi.repositories.session_repository import SessionRepository
from myapi.schemas.session import SessionStatus, SessionToday, SessionPhase
from myapi.utils.market_hours import USMarketHours

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
        현재 날짜 기준으로 유효성을 검증합니다.
        `session_router.get_today_session` 에서 사용됩니다.
        """
        current_kst = USMarketHours.get_current_kst_time()
        today = current_kst.date()
        
        # 오늘이 거래일인지 확인
        market_status = USMarketHours.is_market_session_valid(today)
        
        # 오늘 날짜의 세션 조회
        current = self.repo.get_session_by_date(today)
        
        if not current:
            # 거래일이 아니면 None 반환
            if not market_status['is_trading_day']:
                return None
            # 거래일인데 세션이 없으면 생성 (장 개장 전에만)
            if market_status['is_before_open']:
                current = self.create_session(today)
            else:
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
        """
        새로운 세션을 생성합니다.
        미국 증시 기준으로 예측 시간을 설정합니다.
        """
        # 거래일 유효성 검증
        if not USMarketHours.is_us_trading_day(trading_day):
            raise ValueError(f"{trading_day}는 미국 증시 거래일이 아닙니다.")
        
        # 예측 시간 설정 (KST 기준)
        # 예측 시작: 06:00 (장 마감 후)
        # 예측 마감: 23:59 (다음날 장 개장 직전)
        predict_open_at = datetime.combine(
            trading_day,
            datetime.min.time().replace(hour=6, minute=0, second=0)
        )
        
        predict_cutoff_at = datetime.combine(
            trading_day,
            datetime.min.time().replace(hour=23, minute=59, second=59)
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
        거래일 유효성 검증 후 실행됩니다.
        `session_router.flip_to_predict` 에서 호출됩니다.
        """
        target_date = trading_day or USMarketHours.get_current_kst_time().date()
        
        # 거래일 유효성 검증
        market_status = USMarketHours.is_market_session_valid(target_date)
        if not market_status['is_trading_day']:
            raise ValueError(f"{target_date}는 미국 증시 거래일이 아닙니다.")
        
        # 세션 조회 또는 생성
        response = self.repo.open_predictions(target_date)
        
        if not response:
            # 세션이 없으면 새로 생성 (장 개장 전에만)
            if market_status['is_before_open']:
                session = self.create_session(target_date)
                return self.repo.open_predictions(target_date)
            else:
                raise ValueError("장 개장 후에는 새 세션을 생성할 수 없습니다.")

        return response

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

    def is_prediction_time(self, trading_day: Optional[date] = None) -> bool:
        """
        현재 시간이 예측 가능한 시간대인지 확인합니다.
        
        Args:
            trading_day: 확인할 거래일 (None이면 오늘)
            
        Returns:
            bool: 예측 가능하면 True, 아니면 False
        """
        target_date = trading_day or USMarketHours.get_current_kst_time().date()
        current_kst = USMarketHours.get_current_kst_time()
        
        # 거래일 확인
        if not USMarketHours.is_us_trading_day(target_date):
            return False
        
        # 세션 조회
        session = self.repo.get_session_by_date(target_date)
        if not session:
            return False
        
        # 예측 시간대 확인 (06:00 ~ 23:59)
        predict_start = datetime.combine(target_date, datetime.min.time().replace(hour=6, minute=0))
        predict_end = datetime.combine(target_date, datetime.min.time().replace(hour=23, minute=59, second=59))
        
        # 현재 시간이 예측 가능 시간대이고, 세션이 OPEN 상태인지 확인
        return (predict_start <= current_kst <= predict_end and 
                session.phase == SessionPhase.OPEN)

    def get_prediction_time_status(self, trading_day: Optional[date] = None) -> dict:
        """
        예측 시간 관련 상태를 상세히 반환합니다.
        
        Returns:
            dict: {
                'can_predict': bool,
                'is_trading_day': bool, 
                'is_in_time_range': bool,
                'session_phase': str,
                'time_until_start': int (seconds),
                'time_until_end': int (seconds),
                'message': str
            }
        """
        target_date = trading_day or USMarketHours.get_current_kst_time().date()
        current_kst = USMarketHours.get_current_kst_time()
        
        # 기본 상태
        status = {
            'can_predict': False,
            'is_trading_day': USMarketHours.is_us_trading_day(target_date),
            'is_in_time_range': False,
            'session_phase': None,
            'time_until_start': 0,
            'time_until_end': 0,
            'message': ''
        }
        
        if not status['is_trading_day']:
            status['message'] = f'{target_date}는 미국 증시 거래일이 아닙니다.'
            return status
        
        # 세션 조회
        session = self.repo.get_session_by_date(target_date)
        if session:
            status['session_phase'] = session.phase.value
        
        # 예측 시간대 계산
        predict_start = datetime.combine(target_date, datetime.min.time().replace(hour=6, minute=0))
        predict_end = datetime.combine(target_date, datetime.min.time().replace(hour=23, minute=59, second=59))
        
        # 시간대 확인
        if current_kst < predict_start:
            status['time_until_start'] = int((predict_start - current_kst).total_seconds())
            status['message'] = f'예측 시작까지 {status["time_until_start"]}초 남음'
        elif current_kst > predict_end:
            status['message'] = '오늘 예측 시간이 종료되었습니다.'
        else:
            status['is_in_time_range'] = True
            status['time_until_end'] = int((predict_end - current_kst).total_seconds())
            
            if session and session.phase == SessionPhase.OPEN:
                status['can_predict'] = True
                status['message'] = f'예측 가능 (종료까지 {status["time_until_end"]}초 남음)'
            else:
                status['message'] = f'예측 시간대이지만 세션이 {"없습니다" if not session else session.phase.value + " 상태입니다"}'
        
        return status
