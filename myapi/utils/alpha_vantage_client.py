"""
Alpha Vantage API 클라이언트

yfinance가 실패할 때 사용하는 fallback API 클라이언트입니다.
무료 tier: 일 500회 요청 제한
"""

import asyncio
import logging
import os
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, Deque

import httpx
from myapi.schemas.price import StockPrice

logger = logging.getLogger(__name__)


class AlphaVantageClient:
    """Alpha Vantage API 클라이언트"""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Alpha Vantage API 키. 없으면 환경변수에서 조회
        """
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            logger.warning(
                "Alpha Vantage API key not found. Set ALPHA_VANTAGE_API_KEY environment variable."
            )
        # 요청 제한 관리를 위한 동시성/쿨다운 제어
        # Alpha Vantage 무료 플랜: 분당 5회 제한
        self._semaphore = asyncio.Semaphore(5)
        self._rate_limit_lock = asyncio.Lock()
        self._recent_request_times: Deque[datetime] = deque(maxlen=5)

        # HTTP 클라이언트 재사용 (연결 풀 유지)
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()
        self._timeout = httpx.Timeout(10.0, connect=5.0)

    async def get_intraday_price(
        self, symbol: str, interval: str = "15min"
    ) -> Optional[StockPrice]:
        """
        Alpha Vantage에서 intraday 가격 조회

        Args:
            symbol: 주식 심볼
            interval: 시간 간격 (1min, 5min, 15min, 30min, 60min)

        Returns:
            Optional[StockPrice]: 성공시 가격 정보, 실패시 None
        """
        if not self.api_key:
            logger.warning("Alpha Vantage API key not available")
            return None

        try:
            async with self._semaphore:
                await self._throttle()

                params = {
                    "function": "TIME_SERIES_INTRADAY",
                    "symbol": symbol,
                    "interval": interval,
                    "apikey": self.api_key,
                    "outputsize": "compact",  # 최근 100개 데이터포인트만
                }

                client = await self._get_client()
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                return self._parse_intraday_response(data, symbol)

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Alpha Vantage HTTP error for %s: %s (status=%s)",
                symbol,
                exc.response.text,
                exc.response.status_code,
            )
            return None
        except httpx.RequestError as exc:
            logger.error("Alpha Vantage request error for %s: %s", symbol, exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.error(
                "Alpha Vantage intraday request failed for %s: %s", symbol, exc
            )
            return None

    async def get_daily_price(self, symbol: str) -> Optional[StockPrice]:
        """
        Alpha Vantage에서 일일 가격 조회

        Args:
            symbol: 주식 심볼

        Returns:
            Optional[StockPrice]: 성공시 가격 정보, 실패시 None
        """
        if not self.api_key:
            logger.warning("Alpha Vantage API key not available")
            return None

        try:
            async with self._semaphore:
                await self._throttle()

                params = {
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "apikey": self.api_key,
                    "outputsize": "compact",
                }

                client = await self._get_client()
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                return self._parse_daily_response(data, symbol)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Alpha Vantage HTTP error for %s (daily): %s (status=%s)",
                symbol,
                exc.response.text,
                exc.response.status_code,
            )
            return None
        except httpx.RequestError as exc:
            logger.error("Alpha Vantage request error for %s (daily): %s", symbol, exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.error(
                "Alpha Vantage daily request failed for %s: %s", symbol, exc
            )
            return None

    async def aclose(self) -> None:
        """Close underlying HTTP client (call on application shutdown)."""
        async with self._client_lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create and return a shared AsyncClient."""
        async with self._client_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=self._timeout)
            return self._client

    async def _throttle(self) -> None:
        """Respect Alpha Vantage's 5-requests-per-minute rate limit."""
        async with self._rate_limit_lock:
            now = datetime.now(timezone.utc)
            if self._recent_request_times and len(self._recent_request_times) == self._recent_request_times.maxlen:
                oldest = self._recent_request_times[0]
                elapsed = (now - oldest).total_seconds()
                cooldown = max(0.0, 60.0 - elapsed)
                if cooldown > 0:
                    await asyncio.sleep(cooldown)
                    now = datetime.now(timezone.utc)

            self._recent_request_times.append(now)

    def _parse_intraday_response(
        self, data: Dict[str, Any], symbol: str
    ) -> Optional[StockPrice]:
        """Alpha Vantage intraday 응답 파싱"""
        try:
            # 오류 메시지 체크
            if "Error Message" in data:
                logger.error(
                    f"Alpha Vantage error for {symbol}: {data['Error Message']}"
                )
                return None

            if "Note" in data:
                logger.warning(f"Alpha Vantage rate limit for {symbol}: {data['Note']}")
                return None

            # 시계열 데이터 키 찾기
            time_series_key = None
            for key in data.keys():
                if "Time Series" in key:
                    time_series_key = key
                    break

            if not time_series_key or time_series_key not in data:
                logger.error(f"No time series data found for {symbol}")
                return None

            time_series = data[time_series_key]
            if not time_series:
                logger.error(f"Empty time series data for {symbol}")
                return None

            # 최신 2개 데이터포인트 가져오기
            sorted_times = sorted(time_series.keys(), reverse=True)
            if len(sorted_times) < 2:
                logger.error(
                    f"Insufficient data points for {symbol}: {len(sorted_times)}"
                )
                return None

            latest_time = sorted_times[0]
            previous_time = sorted_times[1]

            latest_data = time_series[latest_time]
            previous_data = time_series[previous_time]

            # 가격 데이터 추출
            current_price = Decimal(latest_data["4. close"])
            previous_close = Decimal(previous_data["4. close"])

            change = current_price - previous_close
            change_percent = (
                (change / previous_close) * 100 if previous_close else Decimal("0")
            )

            return StockPrice(
                symbol=symbol,
                current_price=current_price,
                previous_close=previous_close,
                change=change,
                change_percent=change_percent,
                volume=int(float(latest_data["5. volume"])),
                market_status="ALPHA_VANTAGE_INTRADAY",
                last_updated=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(
                f"Failed to parse Alpha Vantage intraday response for {symbol}: {e}"
            )
            return None

    def _parse_daily_response(
        self, data: Dict[str, Any], symbol: str
    ) -> Optional[StockPrice]:
        """Alpha Vantage daily 응답 파싱"""
        try:
            # 오류 메시지 체크
            if "Error Message" in data:
                logger.error(
                    f"Alpha Vantage error for {symbol}: {data['Error Message']}"
                )
                return None

            if "Note" in data:
                logger.warning(f"Alpha Vantage rate limit for {symbol}: {data['Note']}")
                return None

            # 시계열 데이터 확인
            if "Time Series (Daily)" not in data:
                logger.error(f"No daily time series data found for {symbol}")
                return None

            time_series = data["Time Series (Daily)"]
            if not time_series:
                logger.error(f"Empty daily time series data for {symbol}")
                return None

            # 최신 2개 데이터포인트 가져오기
            sorted_dates = sorted(time_series.keys(), reverse=True)
            if len(sorted_dates) < 2:
                logger.error(
                    f"Insufficient daily data points for {symbol}: {len(sorted_dates)}"
                )
                return None

            latest_date = sorted_dates[0]
            previous_date = sorted_dates[1]

            latest_data = time_series[latest_date]
            previous_data = time_series[previous_date]

            # 가격 데이터 추출
            current_price = Decimal(latest_data["4. close"])
            previous_close = Decimal(previous_data["4. close"])

            change = current_price - previous_close
            change_percent = (
                (change / previous_close) * 100 if previous_close else Decimal("0")
            )

            return StockPrice(
                symbol=symbol,
                current_price=current_price,
                previous_close=previous_close,
                change=change,
                change_percent=change_percent,
                volume=int(float(latest_data["5. volume"])),
                market_status="ALPHA_VANTAGE_DAILY",
                last_updated=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(
                f"Failed to parse Alpha Vantage daily response for {symbol}: {e}"
            )
            return None


# 글로벌 인스턴스
alpha_vantage_client = AlphaVantageClient()
