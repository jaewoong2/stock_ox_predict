from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from dependency_injector.wiring import inject, Provide

from myapi.containers import Container
from myapi.core.auth_middleware import (
    get_current_user_optional,
    get_current_active_user,
)
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.session import SessionToday
from myapi.services.session_service import SessionService


router = APIRouter(prefix="/session", tags=["session"])


@router.get("/today", response_model=BaseResponse)
@inject
def get_today_session(
    _user: Optional[UserSchema] = Depends(get_current_user_optional),  # optional
    service: SessionService = Depends(Provide[Container.services.session_service]),
) -> Any:
    """
    오늘의 세션 정보를 조회합니다.

    Args:
        _user (Optional[UserSchema]): 현재 사용자 정보 (인증되지 않아도 접근 가능)
        service (SessionService): 세션 서비스

    Returns:
        BaseResponse: 오늘의 세션 정보 (trading_day, phase 등)
    """
    try:
        today = service.get_today()
        if not today:
            return BaseResponse(success=True, data={"session": None})
        return BaseResponse(success=True, data={"session": today.model_dump()})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fetch session failed",
        )


# Internal-ish endpoints (should be admin-protected in production)
@router.post("/flip-to-predict", response_model=BaseResponse)
@inject
def flip_to_predict(
    _current_user: UserSchema = Depends(get_current_active_user),
    service: SessionService = Depends(Provide[Container.services.session_service]),
) -> Any:
    try:
        status_obj = service.open_predictions()
        return BaseResponse(
            success=True,
            data={"status": status_obj.model_dump() if status_obj else None},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Flip to predict failed",
        )


@router.post("/cutoff", response_model=BaseResponse)
@inject
def cutoff_predictions(
    _current_user: UserSchema = Depends(get_current_active_user),
    service: SessionService = Depends(Provide[Container.services.session_service]),
) -> Any:
    try:
        status_obj = service.close_predictions()
        return BaseResponse(
            success=True,
            data={"status": status_obj.model_dump() if status_obj else None},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cutoff failed"
        )
