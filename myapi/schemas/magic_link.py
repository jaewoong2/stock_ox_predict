from pydantic import BaseModel, EmailStr, AnyHttpUrl
from typing import Optional


class MagicLinkRequest(BaseModel):
    email: EmailStr
    redirect_url: Optional[AnyHttpUrl] = None


class MagicLinkResponse(BaseModel):
    success: bool
    message: str


class MagicLinkVerifyRequest(BaseModel):
    token: str
