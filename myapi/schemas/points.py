from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class PointsBalanceResponse(BaseModel):
    """포인트 잔액 응답"""

    balance: int = Field(..., description="현재 포인트 잔액")

    class Config:
        from_attributes = True


class PointsLedgerEntry(BaseModel):
    """포인트 원장 항목"""

    id: int = Field(..., description="원장 항목 ID")
    transaction_type: str = Field(..., description="트랜잭션 타입")
    delta_points: int = Field(..., description="포인트 변화량")
    balance_after: int = Field(..., description="트랜잭션 후 잔액")
    reason: str = Field(..., description="트랜잭션 사유")
    ref_id: Optional[str] = Field(None, description="참조 ID")
    created_at: str = Field(..., description="생성 시간")

    class Config:
        from_attributes = True


class PointsLedgerResponse(BaseModel):
    """포인트 원장 조회 응답"""

    balance: int = Field(..., description="현재 잔액")
    entries: List[PointsLedgerEntry] = Field(..., description="원장 항목 목록")
    total_count: int = Field(..., description="전체 항목 수")
    has_next: bool = Field(..., description="다음 페이지 존재 여부")

    class Config:
        from_attributes = True


class PointsTransactionRequest(BaseModel):
    """포인트 트랜잭션 요청"""

    amount: int = Field(..., gt=0, description="포인트 금액")
    reason: str = Field(..., min_length=1, max_length=255, description="트랜잭션 사유")
    ref_id: Optional[str] = Field(None, max_length=100, description="참조 ID")

    class Config:
        from_attributes = True


class PointsTransactionResponse(BaseModel):
    """포인트 트랜잭션 응답"""

    success: bool = Field(..., description="성공 여부")
    transaction_id: Optional[int] = Field(None, description="트랜잭션 ID")
    delta_points: int = Field(..., description="포인트 변화량")
    balance_after: int = Field(..., description="트랜잭션 후 잔액")
    message: str = Field(..., description="응답 메시지")

    class Config:
        from_attributes = True


class AdminPointsAdjustmentRequest(BaseModel):
    """관리자 포인트 조정 요청"""

    user_id: int = Field(..., gt=0, description="사용자 ID")
    amount: int = Field(..., description="조정할 포인트 (양수: 추가, 음수: 차감)")
    reason: str = Field(..., min_length=1, max_length=255, description="조정 사유")

    class Config:
        from_attributes = True


class PointsIntegrityCheckResponse(BaseModel):
    """포인트 정합성 검증 응답"""

    status: str = Field(..., description="검증 상태 (OK, MISMATCH)")
    user_id: Optional[int] = Field(None, description="사용자 ID (단일 사용자 검증 시)")
    calculated_balance: Optional[int] = Field(None, description="계산된 잔액")
    recorded_balance: Optional[int] = Field(None, description="기록된 잔액")
    total_balance_from_latest: Optional[int] = Field(None, description="최신 잔액 합계")
    total_deltas: Optional[int] = Field(None, description="전체 델타 합계")
    user_count: Optional[int] = Field(None, description="사용자 수")
    total_entries: Optional[int] = Field(None, description="전체 항목 수")
    entry_count: Optional[int] = Field(None, description="항목 수")
    error: Optional[str] = Field(None, description="오류 메시지")
    entry_id: Optional[int] = Field(None, description="오류 발생 항목 ID")
    verified_at: Optional[str] = Field(None, description="검증 시간")

    class Config:
        from_attributes = True
