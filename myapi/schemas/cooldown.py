from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class CooldownTimerCreateSchema(BaseModel):
    """쿨다운 타이머 생성 스키마"""
    user_id: int = Field(..., description="사용자 ID")
    trading_day: date = Field(..., description="거래일")
    scheduled_at: datetime = Field(..., description="스케줄된 실행 시간")
    status: str = Field(default="ACTIVE", description="타이머 상태")
    slots_to_refill: int = Field(default=1, description="충전할 슬롯 수")


class CooldownTimerSchema(BaseModel):
    """쿨다운 타이머 응답 스키마"""
    id: int = Field(..., description="타이머 ID")
    user_id: int = Field(..., description="사용자 ID")
    trading_day: date = Field(..., description="거래일")
    started_at: datetime = Field(..., description="시작 시간")
    scheduled_at: datetime = Field(..., description="스케줄된 실행 시간")
    status: str = Field(..., description="타이머 상태")
    eventbridge_rule_arn: Optional[str] = Field(None, description="EventBridge 규칙 ARN")
    slots_to_refill: int = Field(..., description="충전할 슬롯 수")
    created_at: datetime = Field(..., description="생성 시간")
    updated_at: datetime = Field(..., description="수정 시간")

    class Config:
        from_attributes = True


class SlotRefillMessage(BaseModel):
    """슬롯 충전 SQS 메시지 스키마"""
    user_id: int = Field(..., description="사용자 ID")
    timer_id: int = Field(..., description="타이머 ID")
    trading_day: str = Field(..., description="거래일 (ISO 형식)")
    slots_to_refill: int = Field(default=1, description="충전할 슬롯 수")
    message_type: str = Field(default="SLOT_REFILL", description="메시지 타입")


class CooldownStatusResponse(BaseModel):
    """쿨다운 상태 응답 스키마"""
    has_active_cooldown: bool = Field(..., description="활성 쿨다운 여부")
    next_refill_at: Optional[datetime] = Field(None, description="다음 충전 시간")
    daily_timer_count: int = Field(..., description="오늘 생성된 타이머 수")
    remaining_timer_quota: int = Field(..., description="남은 타이머 생성 가능 수")