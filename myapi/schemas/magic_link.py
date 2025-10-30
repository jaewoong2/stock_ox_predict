from pydantic import BaseModel, EmailStr, AnyHttpUrl
from typing import Optional


class MagicLinkRequest(BaseModel):
    email: EmailStr
    redirect_url: Optional[str] = None


class MagicLinkResponse(BaseModel):
    success: bool
    message: str


class MagicLinkVerifyRequest(BaseModel):
    token: str


class MagicLinkVerifyCodeRequest(BaseModel):
    """Request schema for verifying 6-digit code"""
    email: EmailStr
    code: str  # 6-digit numeric string
