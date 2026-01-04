import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from myapi.deps import get_binance_service
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.binance import BinanceKlinesResponse
from myapi.services.binance_service import (
    ALLOWED_INTERVALS,
    BinanceAPIError,
    BinanceService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/binance", tags=["binance"])


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    """Parse optional string query parameter to int."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise BinanceAPIError(
            status_code=400,
            error_code=ErrorCode.BINANCE_INVALID_PARAMS,
            message="startTime/endTime은 정수(Unix ms)여야 합니다.",
        ) from exc


def _error_response(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=BaseResponse(
            success=False, data=None, error=Error(code=code, message=message), meta=None
        ).model_dump(),
    )


@router.get("/klines", response_model=BaseResponse)
async def get_binance_klines(
    symbol: Optional[str] = Query(
        default=None, description="바이낸스 거래쌍 심볼 (예: BTCUSDT)"
    ),
    interval: Optional[str] = Query(
        default=None, description="캔들 간격 (1m, 5m, 15m, 1h, 4h, 1d)"
    ),
    limit: Optional[str] = Query(
        default="60", description="조회 캔들 개수 (기본 60, 최대 1000)"
    ),
    start_time: Optional[str] = Query(
        default=None, alias="startTime", description="시작 시간 (Unix timestamp ms)"
    ),
    end_time: Optional[str] = Query(
        default=None, alias="endTime", description="종료 시간 (Unix timestamp ms)"
    ),
    binance_service: BinanceService = Depends(get_binance_service),
) -> Any:
    """바이낸스 Klines API 프록시"""
    if not symbol or not interval:
        return _error_response(
            400,
            ErrorCode.BINANCE_INVALID_PARAMS,
            "잘못된 요청입니다. symbol 또는 interval을 확인해주세요.",
        )

    normalized_symbol = symbol.strip().upper()
    normalized_interval = interval.strip()

    if normalized_interval not in ALLOWED_INTERVALS:
        return _error_response(
            400,
            ErrorCode.BINANCE_INVALID_PARAMS,
            "잘못된 요청입니다. interval 값을 확인해주세요.",
        )

    try:
        limit_value = int(limit) if limit is not None else 60
    except (TypeError, ValueError):
        return _error_response(
            400,
            ErrorCode.BINANCE_INVALID_PARAMS,
            "limit은 숫자여야 합니다.",
        )

    if limit_value < 1 or limit_value > 1000:
        return _error_response(
            400,
            ErrorCode.BINANCE_INVALID_PARAMS,
            "limit은 1 이상 1000 이하만 허용됩니다.",
        )

    try:
        start_ts = _parse_optional_int(start_time)
        end_ts = _parse_optional_int(end_time)
    except BinanceAPIError as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message)

    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        return _error_response(
            400,
            ErrorCode.BINANCE_INVALID_PARAMS,
            "startTime은 endTime보다 클 수 없습니다.",
        )

    try:
        klines: BinanceKlinesResponse
        meta: dict[str, int]
        klines, meta = await binance_service.fetch_klines(
            symbol=normalized_symbol,
            interval=normalized_interval,
            limit=limit_value,
            start_time=start_ts,
            end_time=end_ts,
        )
        return BaseResponse(
            success=True,
            data=klines.model_dump(),
            error=None,
            meta=meta,
        )
    except BinanceAPIError as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected Binance Klines error: %s", exc)
        return _error_response(
            500,
            ErrorCode.BINANCE_UNKNOWN_ERROR,
            "데이터를 불러오는 중 문제가 발생했습니다.",
        )
