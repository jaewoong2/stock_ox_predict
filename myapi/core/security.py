from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, ValidationError

from myapi.database.session import get_db
from myapi.config import settings
from myapi.repositories.user_repository import UserRepository
from sqlalchemy.orm import Session


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


# Security scheme
security = HTTPBearer()


class TokenPayload(BaseModel):
    user_id: int
    sub: EmailStr  # subject, typically user's email


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """JWT 토큰을 검증하고 user_id를 반환합니다."""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        token_data = TokenPayload.model_validate(payload)
        return token_data.user_id
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    user_id: int = Depends(verify_token), db: Session = Depends(get_db)
):
    """현재 인증된 사용자 정보 조회"""
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


def admin_required(current_user=Depends(get_current_user)):
    """관리자 권한 확인"""
    # 관리자 역할 확인 (User 모델에 is_admin 필드가 있다고 가정)
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return current_user
