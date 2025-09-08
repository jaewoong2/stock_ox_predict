from typing import Optional
from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from myapi.config import settings
from myapi.models.user import UserRole
from myapi.database.session import get_db
from myapi.services.auth_service import AuthService
from myapi.schemas.user import User as UserSchema
from myapi.core.exceptions import AuthenticationError

# JWT Bearer 토큰 스킴
security = HTTPBearer(auto_error=False)


def _extract_bearer_from_internal_header(request: Request) -> Optional[str]:
    """Extract JWT from an internal header used behind AWS Function URL.

    We cannot use the standard Authorization header when calling Lambda Function URL
    with IAM auth (SigV4), so callers can send JWT via `settings.INTERNAL_AUTH_HEADER`.
    Expected format: `Bearer <token>`.
    """
    hdr_name = settings.INTERNAL_AUTH_HEADER.lower()
    raw = request.headers.get(hdr_name)
    if not raw:
        return None
    try:
        parts = raw.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    except Exception:
        pass
    return None


def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[UserSchema]:
    """선택적 사용자 인증 - 토큰이 없거나 유효하지 않아도 None 반환"""
    token: Optional[str] = None
    # 1) Prefer internal header (used when Function URL IAM auth occupies Authorization)
    internal_token = _extract_bearer_from_internal_header(request)
    if internal_token:
        token = internal_token
    elif credentials:
        token = credentials.credentials
    else:
        return None

    auth_service = AuthService(db, settings=settings)
    try:
        user = auth_service.get_current_user(token)
        return user
    except Exception:
        return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> UserSchema:
    """필수 사용자 인증 - 유효한 토큰이 필요함"""
    # 1) Prefer internal header (used when Function URL IAM auth occupies Authorization)
    token: Optional[str] = _extract_bearer_from_internal_header(request)
    if not token:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = credentials.credentials

    auth_service = AuthService(db, settings=settings)

    try:
        user = auth_service.get_current_user(token)
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


def require_admin(
    current_user: UserSchema = Depends(get_current_active_user),
) -> UserSchema:
    """관리자 권한이 필요한 엔드포인트용 의존성"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_role(required_role: UserRole):
    """특정 역할 이상의 권한이 필요한 엔드포인트용 의존성 팩토리"""

    def _require_role(
        current_user: UserSchema = Depends(get_current_active_user),
    ) -> UserSchema:
        if not UserRole.has_permission(current_user.role, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' or higher required",
            )
        return current_user

    return _require_role


def require_premium(
    current_user: UserSchema = Depends(get_current_active_user),
) -> UserSchema:
    """프리미엄 이상 권한이 필요한 엔드포인트용 의존성"""
    if not current_user.is_premium_or_above:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium access required",
        )
    return current_user


def require_super_admin(
    current_user: UserSchema = Depends(get_current_active_user),
) -> UserSchema:
    """최고 관리자 권한이 필요한 엔드포인트용 의존성"""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return current_user


# Legacy compatibility - 기존 코드와의 호환성을 위해
verify_bearer_token = get_current_user
verify_bearer_token_optional = get_current_user_optional
