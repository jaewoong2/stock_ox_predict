from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional, List

T = TypeVar('T')


class PaginationParams(BaseModel):
    """기본 페이지네이션 파라미터"""
    limit: Optional[int] = Field(None, ge=1, description="페이지당 항목 수")
    offset: Optional[int] = Field(0, ge=0, description="시작 오프셋")


class PaginationMeta(BaseModel):
    """페이지네이션 메타 정보"""
    limit: int
    offset: int
    total_count: Optional[int] = None
    has_next: Optional[bool] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """BaseResponse를 래핑하는 페이지네이션 응답"""
    success: bool = True
    data: Optional[T] = None
    meta: Optional[PaginationMeta] = None


class DirectPaginatedResponse(BaseModel, Generic[T]):
    """직접 응답하는 페이지네이션"""
    data: List[T]
    total_count: int
    has_next: bool
    limit: int
    offset: int


# 엔드포인트별 페이지네이션 제한
class PaginationLimits:
    PREDICTIONS_HISTORY = {"min": 1, "max": 100, "default": 50}
    POINTS_LEDGER = {"min": 1, "max": 100, "default": 50}
    REWARDS_HISTORY = {"min": 1, "max": 100, "default": 50}
    USER_LIST = {"min": 1, "max": 100, "default": 20}
    USER_SEARCH = {"min": 1, "max": 50, "default": 20}