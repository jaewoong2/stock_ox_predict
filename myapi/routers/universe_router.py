from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from dependency_injector.wiring import inject

from myapi.core.tickers import get_default_tickers
from myapi.core.auth_middleware import (
    get_current_user_optional,
    get_current_active_user,
)
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse
from myapi.schemas.universe import UniverseUpdate
from myapi.services.universe_service import UniverseService
from myapi.utils.market_hours import USMarketHours
import logging
from myapi.deps import get_universe_service


router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("/today", response_model=BaseResponse)
@inject
def get_today_universe(
    _user: Optional[UserSchema] = Depends(get_current_user_optional),
    service: UniverseService = Depends(get_universe_service),
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


@router.get("/today/with-prices", response_model=BaseResponse)
@inject
async def get_today_universe_with_prices(
    _user: Optional[UserSchema] = Depends(get_current_user_optional),
    service: UniverseService = Depends(get_universe_service),
) -> Any:
    """
    오늘의 유니버스(종목 리스트)를 현재 가격 정보와 함께 조회합니다.
    사용자가 예측하기 전에 시장 상황을 파악할 수 있도록 가격과 변동률을 제공합니다.

    Args:
        _user (Optional[UserSchema]): 현재 사용자 정보 (인증되지 않아도 접근 가능)
        service (UniverseService): 유니버스 서비스

    Returns:
        BaseResponse: 가격 정보가 포함된 오늘의 유니버스 정보
    """
    try:
        res = await service.get_today_universe_with_prices()
        return BaseResponse(
            success=True,
            data={"universe": res.model_dump()} if res else {"universe": None},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fetch universe with prices failed",
        )


@router.post("/upsert", response_model=BaseResponse)
@inject
def upsert_universe(
    payload: UniverseUpdate,
    _current_user: UserSchema = Depends(get_current_active_user),
    service: UniverseService = Depends(get_universe_service),
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
        symbols = payload.symbols
        # 빈 리스트/None 모두 기본 티커로 대체
        if not symbols:
            symbols = get_default_tickers()

        # trading_day 유효성 검증/로그
        try:
            trg_day = payload.trading_day
            day = None
            if trg_day:
                from datetime import date as _date
                day = _date.fromisoformat(trg_day)
        except Exception:
            # FastAPI validation이 잡겠지만 방어
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid trading_day format",
            )

        try:
            logger = logging.getLogger(__name__)
            today_trading_day = USMarketHours.get_kst_trading_day()
            if day:
                if day > today_trading_day:
                    logger.warning(
                        f"Universe upsert for future date {day} requested; proceeding"
                    )
                if not USMarketHours.is_us_trading_day(day):
                    logger.warning(
                        f"Universe upsert for non-trading day {day}; proceeding"
                    )
        except Exception:
            pass

        res = service.upsert_universe(
            UniverseUpdate(
                symbols=symbols,
                trading_day=payload.trading_day,
            )
        )
        return BaseResponse(success=True, data={"universe": res.model_dump()})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upsert universe failed",
        )
