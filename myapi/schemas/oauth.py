from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class OAuthTokenResponse(BaseModel):
    access_token: str
    token_type: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    id_token: Optional[str] = None
    scope: Optional[str] = None
    raw: Optional[Dict[str, Any]] = Field(default=None, description="Provider raw payload")


class OAuthUserInfo(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    verified_email: Optional[bool] = None

