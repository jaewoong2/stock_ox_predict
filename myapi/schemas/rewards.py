from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class RewardItem(BaseModel):
    """리워드 아이템"""

    sku: str = Field(..., description="상품 고유 코드")
    title: str = Field(..., description="상품명")
    cost_points: int = Field(..., description="필요 포인트")
    stock: int = Field(..., description="재고 수량")
    vendor: str = Field(..., description="벤더명")
    is_available: bool = Field(..., description="구매 가능 여부")
    description: Optional[str] = Field(None, description="상품 설명")
    image_url: Optional[str] = Field(None, description="상품 이미지 URL")

    class Config:
        from_attributes = True


class RewardCatalogResponse(BaseModel):
    """리워드 카탈로그 응답"""

    rewards: List[RewardItem] = Field(..., description="리워드 목록")
    total_count: int = Field(..., description="총 상품 수")

    class Config:
        from_attributes = True


class RewardRedemptionRequest(BaseModel):
    """리워드 교환 요청"""

    sku: str = Field(..., min_length=1, description="교환할 리워드 SKU")
    delivery_info: Optional[Dict[str, Any]] = Field(None, description="배송/발급 정보")

    class Config:
        from_attributes = True


class RewardRedemptionResponse(BaseModel):
    """리워드 교환 응답"""

    success: bool = Field(..., description="교환 성공 여부")
    redemption_id: str = Field(..., description="교환 ID")
    status: str = Field(..., description="교환 상태")
    message: str = Field(..., description="응답 메시지")
    cost_points: int = Field(..., description="사용된 포인트")
    issued_at: Optional[str] = Field(None, description="발급 완료 시간")

    class Config:
        from_attributes = True


class RewardRedemptionHistory(BaseModel):
    """리워드 교환 내역"""

    redemption_id: str = Field(..., description="교환 ID")
    sku: str = Field(..., description="상품 SKU")
    title: str = Field(..., description="상품명")
    cost_points: int = Field(..., description="사용된 포인트")
    status: str = Field(..., description="교환 상태")
    requested_at: str = Field(..., description="교환 요청 시간")
    issued_at: Optional[str] = Field(None, description="발급 완료 시간")
    vendor: Optional[str] = Field(None, description="벤더명")

    class Config:
        from_attributes = True


class RewardRedemptionHistoryResponse(BaseModel):
    """리워드 교환 내역 응답"""

    history: List[RewardRedemptionHistory] = Field(..., description="교환 내역 목록")
    total_count: int = Field(..., description="총 교환 건수")
    has_next: bool = Field(..., description="다음 페이지 존재 여부")

    class Config:
        from_attributes = True


class AdminRewardCreateRequest(BaseModel):
    """관리자용 리워드 생성 요청"""

    sku: str = Field(..., min_length=1, max_length=50, description="상품 고유 코드")
    title: str = Field(..., min_length=1, max_length=200, description="상품명")
    cost_points: int = Field(..., gt=0, description="필요 포인트")
    stock: int = Field(..., ge=0, description="초기 재고")
    vendor: str = Field(..., min_length=1, max_length=50, description="벤더명")
    description: Optional[str] = Field(None, max_length=1000, description="상품 설명")

    class Config:
        from_attributes = True


class AdminStockUpdateRequest(BaseModel):
    """관리자용 재고 업데이트 요청"""

    sku: str = Field(..., min_length=1, description="상품 SKU")
    new_stock: int = Field(..., ge=0, description="새로운 재고 수량")

    class Config:
        from_attributes = True


class DeleteResultResponse(BaseModel):
    success: bool
    message: str


class RewardsInventoryResponse(BaseModel):
    """리워드 인벤토리 응답 스키마"""

    sku: str
    title: str
    cost_points: int
    stock: int
    reserved: int
    vendor: str
    available_stock: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class RewardsRedemptionResponse(BaseModel):
    """리워드 교환 응답 스키마"""

    id: int
    user_id: int
    sku: str
    cost_points: int
    status: str
    vendor_code: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class InventorySummary(BaseModel):
    total_items: int
    total_stock: int
    total_reserved: int
    available_stock: int

    class Config:
        from_attributes = True


class RedemptionStats(BaseModel):
    total_redemptions: int
    issued_redemptions: int
    pending_redemptions: int
    failed_redemptions: int
    total_points_spent: int

    class Config:
        from_attributes = True


class AdminRewardsStatsResponse(BaseModel):
    inventory: InventorySummary
    redemptions: RedemptionStats

    class Config:
        from_attributes = True


class RewardsInventorySnapshot(BaseModel):
    """RewardsInventory ORM -> typed snapshot DTO"""

    sku: str
    title: str
    cost_points: int
    stock: int
    reserved: int
    vendor: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RewardsRedemptionSnapshot(BaseModel):
    """RewardsRedemption ORM -> typed snapshot DTO"""

    id: int
    user_id: int
    sku: str
    cost_points: int
    status: Any = None  # Enum in ORM; mapped to str at use sites
    vendor_code: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== 마이페이지용 응답 스키마 ====================


class AvailableRewardResponse(BaseModel):
    """사용 가능한 리워드"""

    redemption_id: int = Field(..., description="교환 ID")
    sku: str = Field(..., description="상품 SKU")
    title: str = Field(..., description="상품명")
    reward_type: str = Field(..., description="리워드 타입")
    image_url: Optional[str] = Field(None, description="상품 이미지 URL")
    description: Optional[str] = Field(None, description="상품 설명")
    purchased_at: str = Field(..., description="구매 시간")
    can_use_now: bool = Field(..., description="현재 사용 가능 여부")

    class Config:
        from_attributes = True


class UsedRewardResponse(BaseModel):
    """사용 완료된 리워드"""

    redemption_id: int = Field(..., description="교환 ID")
    sku: str = Field(..., description="상품 SKU")
    title: str = Field(..., description="상품명")
    reward_type: str = Field(..., description="리워드 타입")
    used_at: str = Field(..., description="사용 시간")
    cost_points: int = Field(..., description="사용된 포인트")

    class Config:
        from_attributes = True


class RewardsSummaryResponse(BaseModel):
    """마이페이지 리워드 요약"""

    available_rewards: List[AvailableRewardResponse] = Field(
        ..., description="사용 가능한 리워드 목록"
    )
    used_rewards: List[UsedRewardResponse] = Field(
        ..., description="사용 완료된 리워드 목록"
    )
    pending_rewards: List[RewardRedemptionHistory] = Field(
        ..., description="관리자 처리 대기 중 리워드"
    )
    total_points_spent: int = Field(..., description="총 사용된 포인트")

    class Config:
        from_attributes = True


class RewardActivationResponse(BaseModel):
    """리워드 활성화 결과"""

    success: bool = Field(..., description="활성화 성공 여부")
    message: str = Field(..., description="응답 메시지")
    redemption_id: int = Field(..., description="교환 ID")
    reward_type: str = Field(..., description="리워드 타입")
    activation_result: Dict[str, Any] = Field(..., description="활성화 결과 상세 정보")

    class Config:
        from_attributes = True


class RewardCancellationResponse(BaseModel):
    """리워드 취소 결과"""

    success: bool = Field(..., description="취소 성공 여부")
    message: str = Field(..., description="응답 메시지")
    redemption_id: int = Field(..., description="교환 ID")

    class Config:
        from_attributes = True
