from datetime import date
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
    오늘의 유니버스(종목 리스트)를 현재 가격 스냅샷과 함께 조회합니다.
    스냅샷이 없는 경우 서비스에서 오류를 발생시키며, 전역 예외 핸들러가 응답 형식을 표준화합니다.
    """
    res = await service.get_today_universe_with_prices()
    return BaseResponse(
        success=True,
        data={"universe": res.model_dump()} if res else {"universe": None},
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


@router.post("/refresh-prices", response_model=BaseResponse)
@inject
async def refresh_today_universe_prices(
    trading_day: str,
    interval: Optional[str] = "realtime",  # realtime, 30m, 1h 등
    _current_user: UserSchema = Depends(
        get_current_active_user
    ),  # or require_admin if stricter
    service: UniverseService = Depends(get_universe_service),
) -> Any:
    """
    오늘의 유니버스 종목들에 대한 가격을 수집하고 DB에 반영합니다.
    interval에 따라 실시간 또는 봉 데이터를 선택할 수 있습니다.
    
    Args:
        trading_day: 거래일 (YYYY-MM-DD)
        interval: 가격 조회 방식
            - "realtime": 실시간 가격 조회 (기존 방식)
            - "30m", "1h" 등: intraday 봉 데이터 조회 (배치용)
    """
    try:
        if interval == "realtime":
            res = await service.refresh_today_prices(
                trading_day=date.fromisoformat(trading_day)
            )
        else:
            res = await service.refresh_today_prices_intraday(
                trading_day=date.fromisoformat(trading_day),
                interval=interval or "30m"  # None인 경우 기본값 사용
            )
        return BaseResponse(
            success=True,
            data={"universe_prices": res.model_dump() if res else None},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Refresh universe prices failed with interval {interval}",
        )


@router.get("/snapshot/status", response_model=BaseResponse)
@inject
def get_universe_snapshot_status(
    trading_day: Optional[str] = None,
    _user: Optional[UserSchema] = Depends(get_current_user_optional),
    service: UniverseService = Depends(get_universe_service),
) -> Any:
    """유니버스 스냅샷 상태 요약 (누락 카운트, 최근 갱신 시각)."""
    day = None
    if trading_day:
        day = date.fromisoformat(trading_day)
    status_data = service.get_universe_snapshot_status(day)
    return BaseResponse(success=True, data={"snapshot_status": status_data})
