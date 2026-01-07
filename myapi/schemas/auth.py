
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

    # Favorites related
    FAVORITES_LIST_ERROR = "FAVORITES_001"
    FAVORITES_ADD_ERROR = "FAVORITES_002"
    FAVORITES_REMOVE_ERROR = "FAVORITES_003"
    FAVORITES_CHECK_ERROR = "FAVORITES_004"
    FAVORITES_SYMBOLS_ERROR = "FAVORITES_005"

    # Binance related
    BINANCE_INVALID_PARAMS = "BINANCE_INVALID_PARAMS"
    BINANCE_RATE_LIMIT = "BINANCE_RATE_LIMIT"
    BINANCE_SERVICE_UNAVAILABLE = "BINANCE_SERVICE_UNAVAILABLE"
    BINANCE_TIMEOUT = "BINANCE_TIMEOUT"
    BINANCE_UNKNOWN_ERROR = "BINANCE_UNKNOWN_ERROR"

    # Crypto band prediction related
    NO_SLOTS = "NO_SLOTS"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    DUPLICATE_PREDICTION = "DUPLICATE_PREDICTION"
    PREDICTION_CLOSED = "PREDICTION_CLOSED"
    SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
    INVALID_ROW = "INVALID_ROW"
    INVALID_INTERVAL = "INVALID_INTERVAL"
    PREDICTION_NOT_FOUND = "PREDICTION_NOT_FOUND"

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
