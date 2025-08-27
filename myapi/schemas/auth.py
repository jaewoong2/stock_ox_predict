
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
