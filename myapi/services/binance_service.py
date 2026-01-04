from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import httpx

from myapi.config import Settings
from myapi.schemas.auth import ErrorCode
from myapi.schemas.binance import BinanceKline, BinanceKlinesResponse

logger = logging.getLogger(__name__)

ALLOWED_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}


class BinanceAPIError(Exception):
    """바이낸스 API 연동 중 발생한 오류를 표현합니다."""

    def __init__(self, status_code: int, error_code: ErrorCode, message: str):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(message)


class BinanceService:
    """바이낸스 Klines 조회 서비스"""

    _KLINES_PATH = "/api/v3/klines"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = settings.BINANCE_API_BASE_URL.rstrip("/")
        self._timeout = httpx.Timeout(settings.BINANCE_TIMEOUT_SECONDS, connect=5.0)
        self._api_key = settings.BINANCE_API_KEY

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Tuple[BinanceKlinesResponse, Dict[str, int]]:
        """바이낸스 Klines 데이터를 조회하고 스키마로 변환합니다."""
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        headers = {}
        if self._api_key:
            # Public endpoint지만 API Key가 제공되면 헤더에 추가
            headers["X-MBX-APIKEY"] = self._api_key

        started_at = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.get(
                    self._KLINES_PATH, params=params, headers=headers
                )
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        except httpx.TimeoutException as exc:
            raise BinanceAPIError(
                status_code=504,
                error_code=ErrorCode.BINANCE_TIMEOUT,
                message="요청 시간이 초과되었습니다.",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Binance request error: %s", exc)
            raise BinanceAPIError(
                status_code=503,
                error_code=ErrorCode.BINANCE_SERVICE_UNAVAILABLE,
                message="바이낸스 서비스가 일시적으로 불안정합니다.",
            ) from exc

        if response.status_code == 429:
            raise BinanceAPIError(
                status_code=429,
                error_code=ErrorCode.BINANCE_RATE_LIMIT,
                message="너무 많은 요청이 발생했습니다. 잠시 후 다시 시도해주세요.",
            )
        if response.status_code == 400:
            raise BinanceAPIError(
                status_code=400,
                error_code=ErrorCode.BINANCE_INVALID_PARAMS,
                message="잘못된 요청입니다. symbol 또는 interval을 확인해주세요.",
            )
        if response.status_code >= 500:
            raise BinanceAPIError(
                status_code=503,
                error_code=ErrorCode.BINANCE_SERVICE_UNAVAILABLE,
                message="바이낸스 서비스가 일시적으로 불안정합니다.",
            )

        try:
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise BinanceAPIError(
                status_code=500,
                error_code=ErrorCode.BINANCE_UNKNOWN_ERROR,
                message="데이터를 불러오는 중 문제가 발생했습니다.",
            ) from exc
        except ValueError as exc:
            raise BinanceAPIError(
                status_code=500,
                error_code=ErrorCode.BINANCE_UNKNOWN_ERROR,
                message="바이낸스 응답을 파싱하는 중 문제가 발생했습니다.",
            ) from exc

        try:
            klines = [self._transform_kline(item) for item in payload]
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Binance response transform failed: %s", exc)
            raise BinanceAPIError(
                status_code=500,
                error_code=ErrorCode.BINANCE_UNKNOWN_ERROR,
                message="바이낸스 응답을 변환하는 중 문제가 발생했습니다.",
            ) from exc

        response_data = BinanceKlinesResponse(
            klines=klines, symbol=symbol.upper(), interval=interval, count=len(klines)
        )
        meta = {"binanceResponseTime": elapsed_ms}
        return response_data, meta

    def _transform_kline(self, kline: list) -> BinanceKline:
        """바이낸스 배열 응답을 스키마 객체로 변환합니다."""
        if len(kline) < 11:
            raise ValueError("Kline payload has insufficient fields")

        return BinanceKline(
            openTime=int(kline[0]),
            open=str(kline[1]),
            high=str(kline[2]),
            low=str(kline[3]),
            close=str(kline[4]),
            volume=str(kline[5]),
            closeTime=int(kline[6]),
            quoteAssetVolume=str(kline[7]),
            numberOfTrades=int(kline[8]),
            takerBuyBaseAssetVolume=str(kline[9]),
            takerBuyQuoteAssetVolume=str(kline[10]),
        )
