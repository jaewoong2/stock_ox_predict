from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from myapi.services.user_service import UserService
from myapi.core.auth_middleware import (
    get_current_active_user,
    get_current_user_optional,
    require_admin,
)
from myapi.core.exceptions import NotFoundError, ValidationError
from myapi.schemas.user import User as UserSchema, UserProfile, UserStats, UserUpdate
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.points import PointsBalanceResponse, PointsLedgerResponse
import logging
from dependency_injector.wiring import inject, Provide
from myapi.containers import Container

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


@router.get("/me", response_model=BaseResponse)
def get_current_user_profile(
    current_user: UserSchema = Depends(get_current_active_user),
) -> Any:
    """현재 사용자 프로필 조회"""
    return BaseResponse(
        success=True,
        data={
            "id": current_user.id,
            "email": current_user.email,
            "nickname": current_user.nickname,
            "auth_provider": current_user.auth_provider,
            "created_at": current_user.created_at.isoformat(),
            "last_login_at": (
                current_user.last_login_at.isoformat()
                if current_user.last_login_at
                else None
            ),
            "is_active": current_user.is_active,
        },
    )


@router.put("/me", response_model=BaseResponse)
@inject
def update_current_user_profile(
    update_data: UserUpdate,
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """현재 사용자 프로필 업데이트"""
    try:
        updated_user = user_service.update_user_profile(current_user.id, update_data)

        if not updated_user:
            raise NotFoundError("User not found")

        return BaseResponse(
            success=True,
            data={
                "id": updated_user.id,
                "email": updated_user.email,
                "nickname": updated_user.nickname,
                "auth_provider": updated_user.auth_provider,
            },
        )
    except ValidationError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=str(e)),
        )
    except Exception as e:
        logger.error(f"Profile update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update failed",
        )


@router.get("/{user_id}", response_model=BaseResponse)
@inject
def get_user_by_id(
    user_id: int,
    current_user: UserSchema = Depends(get_current_user_optional),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """사용자 ID로 프로필 조회 (공개 정보만)"""
    try:
        user_profile = user_service.get_user_profile(user_id)

        if not user_profile:
            raise NotFoundError("User not found")

        # 공개 정보만 반환
        return BaseResponse(
            success=True,
            data={
                "user_id": user_profile.user_id,
                "nickname": user_profile.nickname,
                "auth_provider": user_profile.auth_provider,
                "created_at": user_profile.created_at.isoformat(),
                "is_oauth_user": user_profile.is_oauth_user,
            },
        )
    except NotFoundError as e:
        return BaseResponse(
            success=False, error=Error(code=ErrorCode.USER_NOT_FOUND, message=str(e))
        )
    except Exception as e:
        logger.error(f"User profile fetch error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User profile fetch failed",
        )


@router.get("/", response_model=BaseResponse)
@inject
def get_users_list(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """활성 사용자 목록 조회 (인증 필요)"""
    try:
        users = user_service.get_active_users(limit=limit, offset=offset)

        users_data = []
        for user in users:
            users_data.append(
                {
                    "id": user.id,
                    "nickname": user.nickname,
                    "auth_provider": user.auth_provider,
                    "created_at": user.created_at.isoformat(),
                }
            )

        return BaseResponse(
            success=True,
            data={"users": users_data, "count": len(users_data)},
            meta={"limit": limit, "offset": offset},
        )
    except Exception as e:
        logger.error(f"Users list fetch error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Users list fetch failed",
        )


@router.get("/search/nickname", response_model=BaseResponse)
@inject
def search_users_by_nickname(
    q: str = Query(..., min_length=2, max_length=50),
    limit: int = Query(20, ge=1, le=50),
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """닉네임으로 사용자 검색"""
    try:
        users = user_service.search_users_by_nickname(q, limit=limit)

        users_data = []
        for user in users:
            users_data.append(
                {
                    "id": user.id,
                    "nickname": user.nickname,
                    "auth_provider": user.auth_provider,
                }
            )

        return BaseResponse(
            success=True,
            data={"users": users_data, "count": len(users_data)},
            meta={"query": q, "limit": limit},
        )
    except ValidationError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=str(e)),
        )
    except Exception as e:
        logger.error(f"User search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User search failed",
        )


@router.get("/stats/overview", response_model=BaseResponse)
@inject
def get_user_stats(
    current_user: UserSchema = Depends(require_admin),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """사용자 통계 조회 (관리자 권한 필요)"""
    try:
        stats = user_service.get_user_stats()

        return BaseResponse(
            success=True,
            data={
                "total_users": stats.total_users,
                "active_users": stats.active_users,
                "oauth_users": stats.oauth_users,
                "local_users": stats.local_users,
            },
        )
    except Exception as e:
        logger.error(f"User stats fetch error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User stats fetch failed",
        )


@router.post("/validate/email", response_model=BaseResponse)
@inject
def validate_email_availability(
    email: str,
    current_user: UserSchema = Depends(get_current_user_optional),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """이메일 사용 가능 여부 확인"""
    try:
        exclude_user_id = current_user.id if current_user else None
        is_available = user_service.validate_email_availability(email, exclude_user_id)

        return BaseResponse(
            success=True, data={"email": email, "is_available": is_available}
        )
    except Exception as e:
        logger.error(f"Email validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email validation failed",
        )


@router.post("/validate/nickname", response_model=BaseResponse)
@inject
def validate_nickname_availability(
    nickname: str,
    current_user: UserSchema = Depends(get_current_user_optional),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """닉네임 사용 가능 여부 확인"""
    try:
        exclude_user_id = current_user.id if current_user else None
        is_available = user_service.validate_nickname_availability(
            nickname, exclude_user_id
        )

        return BaseResponse(
            success=True, data={"nickname": nickname, "is_available": is_available}
        )
    except Exception as e:
        logger.error(f"Nickname validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nickname validation failed",
        )


@router.delete("/me", response_model=BaseResponse)
@inject
def deactivate_current_user(
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """현재 사용자 계정 비활성화"""
    try:
        deactivated_user = user_service.deactivate_user(current_user.id)

        if not deactivated_user:
            raise NotFoundError("User not found")

        return BaseResponse(
            success=True,
            data={
                "message": "User account deactivated successfully",
                "user_id": deactivated_user.id,
            },
        )
    except ValidationError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=str(e)),
        )
    except Exception as e:
        logger.error(f"User deactivation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User deactivation failed",
        )


# 포인트 관련 엔드포인트들
@router.get("/me/points/balance", response_model=BaseResponse)
@inject
def get_my_points_balance(
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """내 포인트 잔액 조회"""
    try:
        balance = user_service.get_user_points_balance(current_user.id)

        return BaseResponse(
            success=True, data={"balance": balance.balance, "user_id": current_user.id}
        )
    except Exception as e:
        logger.error(f"Points balance fetch error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve points balance",
        )


@router.get("/me/points/ledger", response_model=BaseResponse)
@inject
def get_my_points_ledger(
    limit: int = Query(50, ge=1, le=100, description="페이지 크기"),
    offset: int = Query(0, ge=0, description="오프셋"),
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """내 포인트 거래 내역 조회"""
    try:
        ledger = user_service.get_user_points_ledger(
            current_user.id, limit=limit, offset=offset
        )

        return BaseResponse(
            success=True,
            data={
                "balance": ledger.balance,
                "entries": [entry.model_dump() for entry in ledger.entries],
                "total_count": ledger.total_count,
                "has_next": ledger.has_next,
            },
        )
    except Exception as e:
        logger.error(f"Points ledger fetch error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve points ledger",
        )


@router.get("/me/profile-with-points", response_model=BaseResponse)
@inject
def get_my_profile_with_points(
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
):
    """포인트 정보를 포함한 내 프로필 조회"""
    try:
        profile_with_points = user_service.get_user_profile_with_points(current_user.id)

        if not profile_with_points:
            raise NotFoundError("User not found")

        return BaseResponse(success=True, data=profile_with_points.model_dump())
    except Exception as e:
        logger.error(f"Profile with points fetch error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve profile with points",
        )


@router.get("/me/financial-summary", response_model=BaseResponse)
@inject
def get_my_financial_summary(
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """내 재정 요약 정보 조회"""
    try:
        summary = user_service.get_user_financial_summary(current_user.id)

        return BaseResponse(success=True, data=summary.model_dump())
    except Exception as e:
        logger.error(f"Financial summary fetch error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve financial summary",
        )


@router.get("/me/can-afford/{amount}", response_model=BaseResponse)
@inject
def check_if_i_can_afford(
    amount: int,
    current_user: UserSchema = Depends(get_current_active_user),
    user_service: UserService = Depends(Provide[Container.services.user_service]),
) -> Any:
    """특정 포인트를 지불할 수 있는지 확인"""
    try:
        can_afford = user_service.can_user_afford(current_user.id, amount)
        current_balance = user_service.get_user_points_balance(current_user.id)

        return BaseResponse(
            success=True,
            data={
                "amount": amount,
                "can_afford": can_afford,
                "current_balance": current_balance.balance,
                "shortfall": (
                    max(0, amount - current_balance.balance) if not can_afford else 0
                ),
            },
        )
    except Exception as e:
        logger.error(f"Affordability check error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check affordability",
        )
