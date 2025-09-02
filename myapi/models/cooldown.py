from sqlalchemy import Column, Integer, String, Date, ForeignKey, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from myapi.models.base import Base


class CooldownTimer(Base):
    """
    자동 쿨다운 타이머 모델
    
    예측 슬롯이 임계값 이하일 때 자동으로 생성되어
    EventBridge를 통해 일정 시간 후 슬롯을 충전하는 타이머를 관리합니다.
    """
    __tablename__ = "cooldown_timers"
    __table_args__ = {"schema": "crypto"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, 
        ForeignKey("crypto.users.id"), 
        nullable=False,
        comment="타이머를 소유한 사용자 ID"
    )
    trading_day = Column(
        Date, 
        nullable=False,
        comment="타이머가 생성된 거래일"
    )
    started_at = Column(
        TIMESTAMP(timezone=True), 
        nullable=False, 
        server_default=func.now(),
        comment="쿨다운 타이머 시작 시간"
    )
    scheduled_at = Column(
        TIMESTAMP(timezone=True), 
        nullable=False,
        comment="슬롯 충전 예정 시간 (started_at + cooldown_minutes)"
    )
    status = Column(
        String(20), 
        nullable=False, 
        default="ACTIVE",
        comment="타이머 상태: ACTIVE, COMPLETED, CANCELLED, FAILED"
    )
    eventbridge_rule_arn = Column(
        String(500),
        nullable=True,
        comment="AWS EventBridge 규칙 ARN (스케줄 취소용)"
    )
    slots_to_refill = Column(
        Integer,
        nullable=False,
        default=1,
        comment="충전할 슬롯 개수"
    )
    created_at = Column(
        TIMESTAMP(timezone=True), 
        nullable=False, 
        server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), 
        nullable=False, 
        server_default=func.now(),
        onupdate=func.now()
    )