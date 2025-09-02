from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date
from enum import Enum


class UnlockMethod(str, Enum):
    """광고 해제 방법 열거형"""
    AD = "AD"
    COOLDOWN = "COOLDOWN"


class AdUnlockCreate(BaseModel):
    """광고 시청 완료 요청 스키마"""
    
    method: UnlockMethod = Field(..., description="해제 방법 (AD 또는 COOLDOWN)")
    unlocked_slots: int = Field(1, ge=1, le=5, description="해제할 슬롯 수 (기본값: 1)")
    
    class Config:
        from_attributes = True


class AdUnlockResponse(BaseModel):
    """광고 시청 기록 응답 스키마"""
    
    id: int = Field(..., description="광고 해제 기록 ID")
    user_id: int = Field(..., description="사용자 ID")
    trading_day: date = Field(..., description="거래일")
    method: str = Field(..., description="해제 방법")
    unlocked_slots: int = Field(..., description="해제된 슬롯 수")
    
    class Config:
        from_attributes = True


class AdUnlockHistory(BaseModel):
    """사용자 광고 시청 히스토리"""
    
    trading_day: date = Field(..., description="거래일")
    total_unlocks: int = Field(..., description="총 해제 슬롯 수")
    ad_unlocks: int = Field(..., description="광고 시청으로 해제한 슬롯 수")
    cooldown_unlocks: int = Field(..., description="쿨다운으로 해제한 슬롯 수")
    records: List[AdUnlockResponse] = Field(..., description="상세 기록 목록")
    
    class Config:
        from_attributes = True


class SlotIncreaseRequest(BaseModel):
    """슬롯 증가 요청 스키마"""
    
    method: UnlockMethod = Field(..., description="해제 방법 (AD 또는 COOLDOWN)")
    
    class Config:
        from_attributes = True


class SlotIncreaseResponse(BaseModel):
    """슬롯 증가 응답 스키마"""
    
    success: bool = Field(..., description="성공 여부")
    message: str = Field(..., description="응답 메시지")
    available_predictions: int = Field(..., description="현재 가용 슬롯 수")
    unlocked_slots: int = Field(..., description="해제된 슬롯 수")
    method_used: str = Field(..., description="사용된 해제 방법")
    
    class Config:
        from_attributes = True


class AvailableSlotsResponse(BaseModel):
    """사용 가능한 슬롯 조회 응답"""
    
    predictions_made: int = Field(..., description="이미 만든 예측 수")
    available_predictions: int = Field(..., description="남은 예측 가능 수")
    can_unlock_by_ad: bool = Field(..., description="광고로 슬롯 해제 가능 여부")
    can_unlock_by_cooldown: bool = Field(..., description="쿨다운으로 슬롯 해제 가능 여부")
    today_ad_unlocks: int = Field(..., description="오늘 광고로 해제한 슬롯 수")
    today_cooldown_unlocks: int = Field(..., description="오늘 쿨다운으로 해제한 슬롯 수")
    
    class Config:
        from_attributes = True


class AdUnlockStatsResponse(BaseModel):
    """광고 해제 통계 응답"""
    
    trading_day: date = Field(..., description="거래일")
    total_unlocks: int = Field(..., description="총 해제 슬롯 수")
    unique_users: int = Field(..., description="해제한 사용자 수")
    method_breakdown: Dict[str, Any] = Field(..., description="방법별 통계")
    
    class Config:
        from_attributes = True


class AdWatchCompleteRequest(BaseModel):
    """광고 시청 완료 처리 요청"""
    
    ad_id: Optional[str] = Field(None, description="광고 ID (추후 확장용)")
    duration: Optional[int] = Field(None, description="시청 시간 (초)")
    
    class Config:
        from_attributes = True


class AdWatchCompleteResponse(BaseModel):
    """광고 시청 완료 처리 응답"""
    
    success: bool = Field(..., description="성공 여부")
    message: str = Field(..., description="응답 메시지")
    slots_unlocked: int = Field(..., description="해제된 슬롯 수")
    available_predictions: int = Field(..., description="현재 가용 슬롯 수")
    
    class Config:
        from_attributes = True
