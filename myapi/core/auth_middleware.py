from typing import Optional
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from myapi.database.session import get_db
from myapi.services.auth_service import AuthService
from myapi.schemas.user import User as UserSchema
from myapi.core.exceptions import AuthenticationError

# JWT Bearer 토큰 스킴
security = HTTPBearer(auto_error=False)


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[UserSchema]:
    """선택적 사용자 인증 - 토큰이 없거나 유효하지 않아도 None 반환"""
    if not credentials:
        return None

    auth_service = AuthService(db)
    try:
        user = auth_service.get_current_user(credentials.credentials)
        return user
    except Exception:
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> UserSchema:
    """필수 사용자 인증 - 유효한 토큰이 필요함"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = AuthService(db)
    try:
        user = auth_service.get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_active_user(
    current_user: UserSchema = Depends(get_current_user),
) -> UserSchema:
    """활성 사용자만 허용"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )
    return current_user


# Legacy compatibility - 기존 코드와의 호환성을 위해
verify_bearer_token = get_current_user
verify_bearer_token_optional = get_current_user_optional