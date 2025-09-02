from datetime import date, datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from myapi.models.cooldown import CooldownTimer
from myapi.repositories.base import BaseRepository
from myapi.schemas.cooldown import CooldownTimerSchema


class CooldownRepository(BaseRepository[CooldownTimer, CooldownTimerSchema]):
    """쿨다운 타이머 데이터 접근 계층"""

    def __init__(self, db: Session):
        super().__init__(CooldownTimer, CooldownTimerSchema, db)

    def create_cooldown_timer(
        self,
        user_id: int,
        trading_day: date,
        scheduled_at: datetime,
        slots_to_refill: int = 1,
    ) -> Optional[CooldownTimerSchema]:
        """새로운 쿨다운 타이머 생성"""
        return self.create(
            user_id=user_id,
            trading_day=trading_day,
            scheduled_at=scheduled_at,
            status="ACTIVE",
            slots_to_refill=slots_to_refill,
        )

    def get_active_timer(
        self, user_id: int, trading_day: date
    ) -> Optional[CooldownTimerSchema]:
        """
        사용자의 활성 쿨다운 타이머 조회

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            Optional[CooldownTimerSchema]: 활성 타이머 (없으면 None)
        """
        model_instance = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                    self.model_class.status == "ACTIVE",
                )
            )
            .first()
        )
        return self._to_schema(model_instance)

    def update_timer_arn(self, timer_id: int, eventbridge_rule_arn: str) -> bool:
        """
        타이머에 EventBridge 규칙 ARN 업데이트

        Args:
            timer_id: 타이머 ID
            eventbridge_rule_arn: EventBridge 규칙 ARN

        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            updated_count = (
                self.db.query(self.model_class)
                .filter(self.model_class.id == timer_id)
                .update(
                    {self.model_class.eventbridge_rule_arn: eventbridge_rule_arn},
                    synchronize_session=False,
                )
            )
            self.db.flush()
            self.db.commit()
            return updated_count > 0
        except Exception:
            self.db.rollback()
            return False

    def complete_timer(self, timer_id: int) -> bool:
        """
        타이머를 완료 상태로 변경

        Args:
            timer_id: 타이머 ID

        Returns:
            bool: 완료 처리 성공 여부
        """
        try:
            updated_count = (
                self.db.query(self.model_class)
                .filter(
                    and_(
                        self.model_class.id == timer_id,
                        self.model_class.status == "ACTIVE",
                    )
                )
                .update(
                    {self.model_class.status: "COMPLETED"}, synchronize_session=False
                )
            )
            self.db.flush()
            self.db.commit()
            return updated_count > 0
        except Exception:
            self.db.rollback()
            return False

    def cancel_timer(self, timer_id: int) -> bool:
        """
        타이머를 취소 상태로 변경

        Args:
            timer_id: 타이머 ID

        Returns:
            bool: 취소 처리 성공 여부
        """
        try:
            updated_count = (
                self.db.query(self.model_class)
                .filter(
                    and_(
                        self.model_class.id == timer_id,
                        self.model_class.status == "ACTIVE",
                    )
                )
                .update(
                    {self.model_class.status: "CANCELLED"}, synchronize_session=False
                )
            )
            self.db.flush()
            self.db.commit()
            return updated_count > 0
        except Exception:
            self.db.rollback()
            return False

    def get_timers_by_status(
        self, status: str, trading_day: Optional[date] = None, limit: int = 100
    ) -> List[CooldownTimerSchema]:
        """
        상태별 타이머 목록 조회

        Args:
            status: 타이머 상태
            trading_day: 거래일 (선택사항)
            limit: 조회 제한 수

        Returns:
            List[CooldownTimerSchema]: 타이머 목록
        """
        query = self.db.query(self.model_class).filter(
            self.model_class.status == status
        )

        if trading_day:
            query = query.filter(self.model_class.trading_day == trading_day)

        model_instances = (
            query.order_by(desc(self.model_class.created_at)).limit(limit).all()
        )
        results: List[CooldownTimerSchema] = []
        for instance in model_instances:
            schema = self._to_schema(instance)
            if schema is not None:
                results.append(schema)
        return results

    def count_daily_timers(self, user_id: int, trading_day: date) -> int:
        """
        사용자의 일일 타이머 생성 수 조회

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            int: 일일 타이머 생성 수
        """
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                )
            )
            .count()
        )
