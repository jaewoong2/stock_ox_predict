from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
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
