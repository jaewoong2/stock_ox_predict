from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum

from myapi.models.user import UserRole
from myapi.schemas.pagination import PaginatedResponse


class AuthProvider(str, Enum):
    LOCAL = "local"
    GOOGLE = "google"
    KAKAO = "kakao"


class User(BaseModel):
    id: int
    email: EmailStr
    nickname: str
    auth_provider: AuthProvider
    created_at: datetime
    last_login_at: Optional[datetime] = None
    is_active: bool = True
    role: UserRole = UserRole.USER

    class Config:
        from_attributes = True

    @property
    def is_admin(self) -> bool:
        """Backward compatibility property"""
        return UserRole.is_admin(self.role)

    @property
    def is_premium_or_above(self) -> bool:
        """Check if user has premium or higher privileges"""
        return UserRole.is_premium_or_above(self.role)


class UserProfile(BaseModel):
    user_id: int
    email: EmailStr
    nickname: str
    auth_provider: AuthProvider
    created_at: datetime
    is_oauth_user: bool

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    nickname: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[EmailStr] = None

    @field_validator("nickname")
    @classmethod
    def nickname_must_not_be_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip() == "":
            raise ValueError("Nickname cannot be empty")
        return v


class UserStats(BaseModel):
    total_users: int
    active_users: int
    oauth_users: int
    local_users: int


class UserProfileWithPoints(BaseModel):
    user_profile: UserProfile
    points_balance: int
    last_updated: datetime

    class Config:
        from_attributes = True


class UserFinancialSummary(BaseModel):
    user_id: int
    current_balance: int
    points_earned_today: int
    can_make_predictions: bool
    summary_date: str

    class Config:
        from_attributes = True


class UserListItem(BaseModel):
    """사용자 목록용 간소한 정보"""
    id: int
    nickname: str
    auth_provider: AuthProvider
    created_at: datetime

    class Config:
        from_attributes = True


class UserListResult(BaseModel):
    """사용자 목록 결과"""
    users: List[UserListItem]
    count: int


class UserSearchItem(BaseModel):
    """사용자 검색용 간소한 정보"""
    id: int
    nickname: str
    auth_provider: AuthProvider

    class Config:
        from_attributes = True


class UserSearchResult(BaseModel):
    """사용자 검색 결과"""
    users: List[UserSearchItem]
    count: int


class AffordabilityCheck(BaseModel):
    """지불 가능 여부 확인"""
    amount: int
    can_afford: bool
    current_balance: int
    shortfall: int = 0  # 부족한 포인트
