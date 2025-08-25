from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from dependency_injector.wiring import inject, Provide

from myapi.containers import Container
from myapi.core.auth_middleware import (
    get_current_user_optional,
    get_current_active_user,
)
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse
from myapi.schemas.universe import UniverseUpdate
from myapi.services.universe_service import UniverseService


router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("/today", response_model=BaseResponse)
@inject
def get_today_universe(
    _user: Optional[UserSchema] = Depends(get_current_user_optional),
    service: UniverseService = Depends(Provide[Container.services.universe_service]),
) -> Any:
    """
    오늘의 유니버스(종목 리스트)를 조회합니다.

    Args:
        _user (Optional[UserSchema]): 현재 사용자 정보 (인증되지 않아도 접근 가능)
        service (UniverseService): 유니버스 서비스

    Returns:
        BaseResponse: 오늘의 유니버스 정보
    """
    try:
        res = service.get_today_universe()
        return BaseResponse(
            success=True,
            data={"universe": res.model_dump()} if res else {"universe": None},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fetch universe failed",
        )


@router.post("/upsert", response_model=BaseResponse)
@inject
def upsert_universe(
    payload: UniverseUpdate,
    _current_user: UserSchema = Depends(get_current_active_user),
    service: UniverseService = Depends(Provide[Container.services.universe_service]),
) -> Any:
    """
    특정 날짜의 유니버스를 생성하거나 업데이트합니다. (관리자용)

    Args:
        payload (UniverseUpdate): 업데이트할 유니버스 정보 (trading_day, symbols)
        _current_user (UserSchema): 현재 활성 사용자 정보 (인증 필요)
        service (UniverseService): 유니버스 서비스

    Returns:
        BaseResponse: 생성/업데이트된 유니버스 정보
    """
    try:
        res = service.upsert_universe(payload)
        return BaseResponse(success=True, data={"universe": res.model_dump()})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upsert universe failed",
        )
