from pyexpat import model
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from datetime import date, datetime

from myapi.models.session import SessionControl as SessionControlModel, PhaseEnum
from myapi.schemas.session import SessionStatus, SessionToday, SessionPhase
from myapi.repositories.base import BaseRepository


class SessionRepository(BaseRepository[SessionControlModel, SessionStatus]):
    """
    세션 제어 리포지토리
    """

    def __init__(self, db: Session):
        super().__init__(SessionControlModel, SessionStatus, db)

    def _to_session_status(self, model_instance: SessionControlModel) -> SessionStatus:
        """
        SessionControl 모델을 SessionStatus 스키마로 변환
        """

        # SQLAlchemy 모델의 속성들을 딕셔너리로 변환 후 Pydantic 생성
        data = {
            "trading_day": model_instance.trading_day,
            "phase": SessionPhase(model_instance.phase.value),
            "predict_open_at": model_instance.predict_open_at,
            "predict_cutoff_at": model_instance.predict_cutoff_at,
            "settle_ready_at": model_instance.settle_ready_at,
            "settled_at": model_instance.settled_at,
            "is_prediction_open": model_instance.is_prediction_open,
            "is_settling": model_instance.is_settling,
            "is_closed": model_instance.is_closed,
        }

        return SessionStatus(**data)

    def get_current_session(self) -> Optional[SessionStatus]:
        """
        현재 활성 세션 조회 (가장 최근 거래일)
        """
        model_instance = (
            self.db.query(self.model_class)
            .order_by(desc(self.model_class.trading_day))
            .first()
        )

        if not model_instance:
            return None

        return self._to_session_status(model_instance)

    def get_session_by_date(self, trading_day: date) -> Optional[SessionStatus]:
        """
        특정 날짜의 세션 조회
        """
        model_instance = (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .first()
        )

        if not model_instance:
            return None

        return self._to_session_status(model_instance)

    def get_today_session_info(self, trading_day: date) -> Optional[SessionToday]:
        """오늘의 세션 정보 조회 (API 응답용)"""
        model_instance = (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .first()
        )

        if not model_instance:
            return None

        # SQLAlchemy 모델의 속성들을 안전하게 추출하여 변환
        data = {
            "trading_day": model_instance.trading_day.strftime("%Y-%m-%d"),
            "phase": SessionPhase(model_instance.phase.value),
            "predict_open_at": model_instance.predict_open_at.strftime("%H:%M:%S"),
            "predict_cutoff_at": model_instance.predict_cutoff_at.strftime("%H:%M:%S"),
            "settle_ready_at": model_instance.settle_ready_at.strftime("%H:%M:%S"),
            "settled_at": model_instance.settled_at.strftime("%H:%M:%S"),
        }
        return SessionToday(**data)

    def create_session(
        self,
        trading_day: date,
        predict_open_at: datetime,
        predict_cutoff_at: datetime,
        phase: PhaseEnum = PhaseEnum.CLOSED,
    ) -> SessionStatus:
        """새 세션 생성"""
        model_instance = self.model_class(
            trading_day=trading_day,
            phase=phase,
            predict_open_at=predict_open_at,
            predict_cutoff_at=predict_cutoff_at,
        )
        self.db.add(model_instance)
        self.db.commit()
        self.db.flush()
        self.db.refresh(model_instance)
        return self._to_session_status(model_instance)

    def update_session_phase(
        self, trading_day: date, new_phase: PhaseEnum
    ) -> Optional[SessionStatus]:
        """세션 페이즈 업데이트"""
        from datetime import timezone

        model_instance = (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .first()
        )

        if not model_instance:
            return None

        update_data = {
            self.model_class.phase: new_phase,
            self.model_class.settle_ready_at: None,
            self.model_class.settled_at: None,
        }

        # 페이즈에 따른 타임스탬프 업데이트
        current_phase = getattr(model_instance, "phase", None)
        if new_phase == PhaseEnum.SETTLING:
            update_data[self.model_class.settle_ready_at] = datetime.now(timezone.utc)
        elif new_phase == PhaseEnum.CLOSED and current_phase == PhaseEnum.SETTLING:
            update_data[self.model_class.settled_at] = datetime.now(timezone.utc)

        # SQL UPDATE 사용
        updated_count = (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .update(update_data, synchronize_session=False)
        )

        if updated_count == 0:
            return None

        self.db.commit()
        self.db.flush()

        # 업데이트된 모델 재조회
        updated_model = (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .first()
        )

        return self._to_session_status(updated_model)

    def mark_settle_ready(self, trading_day: date) -> Optional[SessionStatus]:
        """정산 준비 완료 표시"""
        return self.update_session_phase(trading_day, PhaseEnum.SETTLING)

    def mark_settlement_complete(self, trading_day: date) -> Optional[SessionStatus]:
        """정산 완료 표시"""
        return self.update_session_phase(trading_day, PhaseEnum.CLOSED)

    def open_predictions(self, trading_day: date) -> Optional[SessionStatus]:
        """예측 접수 시작"""
        return self.update_session_phase(trading_day, PhaseEnum.OPEN)

    def close_predictions(self, trading_day: date) -> Optional[SessionStatus]:
        """예측 접수 종료"""
        return self.update_session_phase(trading_day, PhaseEnum.CLOSED)

    def get_sessions_in_range(
        self, start_date: date, end_date: date, phase_filter: PhaseEnum
    ) -> List[SessionStatus]:
        """날짜 범위의 세션 조회"""
        query = self.db.query(self.model_class).filter(
            self.model_class.trading_day.between(start_date, end_date)
        )

        if phase_filter:
            query = query.filter(self.model_class.phase == phase_filter)

        model_instances = query.order_by(asc(self.model_class.trading_day)).all()
        return [self._to_session_status(instance) for instance in model_instances]

    def get_open_sessions(self) -> List[SessionStatus]:
        """예측 접수 중인 세션들 조회"""
        model_instances = (
            self.db.query(self.model_class)
            .filter(self.model_class.phase == PhaseEnum.OPEN)
            .order_by(desc(self.model_class.trading_day))
            .all()
        )

        return [self._to_session_status(instance) for instance in model_instances]

    def get_settling_sessions(self) -> List[SessionStatus]:
        """정산 중인 세션들 조회"""
        model_instances = (
            self.db.query(self.model_class)
            .filter(self.model_class.phase == PhaseEnum.SETTLING)
            .order_by(desc(self.model_class.trading_day))
            .all()
        )

        return [self._to_session_status(instance) for instance in model_instances]

    def session_exists(self, trading_day: date) -> bool:
        """특정 날짜의 세션 존재 여부 확인"""
        return self.exists(filters={"trading_day": trading_day})

    def is_prediction_active(self, trading_day: date) -> bool:
        """예측 접수 활성 상태 확인"""
        session = self.get_current_session()

        if trading_day:
            session = self.get_session_by_date(trading_day)

        return session and session.is_prediction_open if session else False

    def is_settlement_in_progress(self, trading_day: date) -> bool:
        """정산 진행 중 여부 확인"""
        session = self.get_current_session()

        if trading_day:
            session = self.get_session_by_date(trading_day)

        return session and session.is_settling if session else False
