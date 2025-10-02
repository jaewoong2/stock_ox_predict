from pydantic import BaseModel, EmailStr
from typing import Optional


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkResponse(BaseModel):
    success: bool
    message: str


class MagicLinkVerifyRequest(BaseModel):
    token: str
