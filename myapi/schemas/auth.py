
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from enum import Enum

class ErrorCode(str, Enum):
    # Auth related
    UNAUTHORIZED = "AUTH_001"
    FORBIDDEN = "AUTH_002"
    TOKEN_EXPIRED = "AUTH_003"
    INVALID_CREDENTIALS = "AUTH_004"
    
    # OAuth related
    OAUTH_INVALID_CODE = "OAUTH_001"
    OAUTH_STATE_MISMATCH = "OAUTH_002"
    OAUTH_PROVIDER_ERROR = "OAUTH_003"
    
    # User related
    USER_ALREADY_EXISTS = "USER_001"
    USER_NOT_FOUND = "USER_002"

class Error(BaseModel):
    code: ErrorCode
    message: str
    details: Optional[dict] = None

class BaseResponse(BaseModel):
    success: bool = True
    data: Optional[dict] = None
    error: Optional[Error] = None
    meta: Optional[dict] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[EmailStr] = None
    user_id: Optional[int] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=2, max_length=50)
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v
    
    @field_validator('nickname')
    @classmethod
    def validate_nickname(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Nickname cannot be empty')
        if any(char in v for char in ['<', '>', '"', "'"]):
            raise ValueError('Nickname contains invalid characters')
        return v.strip()

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class OAuthCallbackRequest(BaseModel):
    provider: str = Field(pattern="^(google|kakao)$")
    code: str
    state: str
    redirect_uri: str

class OAuthLoginResponse(BaseModel):
    user_id: int
    token: str
    nickname: str
    is_new_user: bool
