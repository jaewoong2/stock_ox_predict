
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from typing import Optional
from enum import Enum

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

    class Config:
        from_attributes = True

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
    
    @field_validator('nickname')
    @classmethod
    def nickname_must_not_be_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip() == '':
            raise ValueError('Nickname cannot be empty')
        return v

class UserStats(BaseModel):
    total_users: int
    active_users: int
    oauth_users: int
    local_users: int
