from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

from myapi.core.exceptions import ValidationError, NotFoundError, ServiceException
from myapi.repositories.active_universe_repository import ActiveUniverseRepository
from myapi.schemas.price import (
    StockPrice,
    EODPrice,
    PriceComparisonResult,
    UniversePriceResponse,
    SettlementPriceData,
)


class PriceService:
    """주식 가격 조회 및 정산 검증 서비스"""

    def __init__(self, db: Session):
        self.db = db
        self.universe_repo = ActiveUniverseRepository(db)
        self.current_price_cache = {}
        self.eod_price_cache = {}
        self.cache_ttl = timedelta(seconds=60)  # 60초 TTL

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # yfinance는 별도의 연결 종료가 필요 없음
        pass

    async def get_current_price(self, symbol: str) -> StockPrice:
        """특정 종목의 현재 가격을 조회합니다. 캐싱을 적용합니다."""
        # 캐시 확인
        now = datetime.now(timezone.utc)
        if symbol in self.current_price_cache:
            cached_data, timestamp = self.current_price_cache[symbol]
            if now - timestamp < self.cache_ttl:
                return cached_data

        try:
            # yfinance를 사용한 실시간 가격 조회
            ticker = yf.Ticker(symbol)
            price_data = await self._get_current_price_with_yf(ticker, symbol)

            # 캐시에 저장
            self.current_price_cache[symbol] = (price_data, now)
            return price_data
        except Exception as e:
            raise ServiceException(
                f"Failed to fetch current price for {symbol}: {str(e)}"
            )

    async def get_universe_current_prices(
        self, trading_day: Optional[date] = None
    ) -> UniversePriceResponse:
        """오늘의 유니버스 모든 종목의 현재 가격을 조회합니다."""
        if not trading_day:
            trading_day = date.today()

        # 오늘의 유니버스 종목 조회
        universe_symbols = self.universe_repo.get_universe_for_date(trading_day)
        if not universe_symbols:
            raise NotFoundError(f"No universe found for {trading_day}")

        # 병렬로 모든 종목 가격 조회
        tasks = [self.get_current_price(symbol.symbol) for symbol in universe_symbols]
        prices = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외 발생한 항목들 필터링
        valid_prices = [price for price in prices if isinstance(price, StockPrice)]

        if not valid_prices:
            raise ServiceException("Failed to fetch any valid prices")

        return UniversePriceResponse(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            prices=valid_prices,
            last_updated=datetime.now(timezone.utc),
            market_status=self._determine_market_status(),
        )

    async def get_eod_price(self, symbol: str, trading_day: date) -> EODPrice:
        """특정 종목의 특정 날짜 EOD 가격을 조회합니다. 캐싱을 적용합니다."""
        # 캐시 확인 (EOD 데이터는 날짜별로 불변)
        cache_key = (symbol, trading_day)
        if cache_key in self.eod_price_cache:
            return self.eod_price_cache[cache_key]

        try:
            ticker = yf.Ticker(symbol)
            price_data = await self._get_eod_price_with_yf(ticker, symbol, trading_day)

            # 캐시에 저장
            self.eod_price_cache[cache_key] = price_data
            return price_data
        except Exception as e:
            raise ServiceException(
                f"Failed to fetch EOD price for {symbol} on {trading_day}: {str(e)}"
            )

    async def get_universe_eod_prices(self, trading_day: date) -> List[EODPrice]:
        """오늘의 유니버스 모든 종목의 EOD 가격을 조회합니다."""
        universe_symbols = self.universe_repo.get_universe_for_date(trading_day)
        if not universe_symbols:
            raise NotFoundError(f"No universe found for {trading_day}")

        # 병렬로 모든 종목 EOD 가격 조회
        tasks = [
            self.get_eod_price(symbol.symbol, trading_day)
            for symbol in universe_symbols
        ]
        prices = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외 발생한 항목들 필터링
        valid_prices = [price for price in prices if isinstance(price, EODPrice)]
        return valid_prices

    async def validate_settlement_prices(
        self, trading_day: date
    ) -> List[SettlementPriceData]:
        """정산을 위한 가격 검증을 수행합니다."""
        eod_prices = await self.get_universe_eod_prices(trading_day)
        settlement_data = []

        for eod_price in eod_prices:
            # 가격 움직임 계산
            price_movement = self._calculate_price_movement(
                eod_price.close_price, eod_price.previous_close
            )

            # 변동률 계산
            change_percent = self._calculate_change_percent(
                eod_price.close_price, eod_price.previous_close
            )

            # 정산 유효성 검증
            is_valid, void_reason = self._validate_price_for_settlement(eod_price)

            settlement_data.append(
                SettlementPriceData(
                    symbol=eod_price.symbol,
                    trading_date=eod_price.trading_date,
                    settlement_price=eod_price.close_price,
                    reference_price=eod_price.previous_close,
                    price_movement=price_movement,
                    change_percent=change_percent,
                    is_valid_settlement=is_valid,
                    void_reason=void_reason,
                )
            )

        return settlement_data

    async def compare_prediction_with_outcome(
        self, symbol: str, trading_day: date, predicted_direction: str
    ) -> PriceComparisonResult:
        """예측과 실제 결과를 비교합니다."""
        try:
            eod_price = await self.get_eod_price(symbol, trading_day)

            # 실제 가격 움직임 계산
            actual_movement = self._calculate_price_movement(
                eod_price.close_price, eod_price.previous_close
            )

            # 예측 결과 판정
            prediction_outcome = (
                "CORRECT"
                if predicted_direction.upper() == actual_movement
                else "INCORRECT"
            )

            change_percent = self._calculate_change_percent(
                eod_price.close_price, eod_price.previous_close
            )

            return PriceComparisonResult(
                symbol=symbol,
                trading_date=trading_day.strftime("%Y-%m-%d"),
                current_price=eod_price.close_price,
                previous_price=eod_price.previous_close,
                price_movement=actual_movement,
                change_percent=change_percent,
                prediction_outcome=prediction_outcome,
            )

        except Exception as e:
            raise ServiceException(
                f"Failed to compare prediction for {symbol}: {str(e)}"
            )

    # Private helper methods
    async def _get_current_price_with_yf(
        self, ticker: yf.Ticker, symbol: str
    ) -> StockPrice:
        """yfinance를 사용해 실시간 가격 조회"""
        loop = asyncio.get_event_loop()

        # blocking I/O를 async로 실행
        def fetch_info():
            info = ticker.info
            return info

        info = await loop.run_in_executor(None, fetch_info)

        if not info or "regularMarketPrice" not in info:
            raise ValidationError(f"No current price data available for {symbol}")

        current_price = Decimal(str(info["regularMarketPrice"]))
        previous_close = Decimal(str(info.get("previousClose", current_price)))
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
            volume=info.get("volume"),
            market_status=info.get("marketState", "UNKNOWN"),
            last_updated=datetime.now(timezone.utc),
        )

    async def _get_eod_price_with_yf(
        self, ticker: yf.Ticker, symbol: str, trading_day: date
    ) -> EODPrice:
        """yfinance를 사용해 EOD 가격 조회"""
        loop = asyncio.get_event_loop()

        # 역사적 데이터 가져오기 (2일 범위로 조회해 전일 종가 포함)
        end_date = trading_day + timedelta(days=1)
        start_date = trading_day - timedelta(days=1)

        def fetch_history():
            return ticker.history(start=start_date, end=end_date, interval="1d")

        hist = await loop.run_in_executor(None, fetch_history)

        if hist.empty or trading_day.strftime("%Y-%m-%d") not in pd.to_datetime(
            hist.index
        ).strftime("%Y-%m-%d"):
            raise ValidationError(
                f"No EOD data available for {symbol} on {trading_day}"
            )

        # 해당 날짜의 데이터 찾기
        target_date_str = trading_day.strftime("%Y-%m-%d")
        matching_rows = hist[
            pd.to_datetime(hist.index).strftime("%Y-%m-%d") == target_date_str
        ]

        if matching_rows.empty:
            raise ValidationError(
                f"No EOD data available for {symbol} on {trading_day}"
            )

        row = matching_rows.iloc[0]

        close_price = Decimal(str(row["Close"]))
        open_price = Decimal(str(row["Open"]))
        high_price = Decimal(str(row["High"]))
        low_price = Decimal(str(row["Low"]))
        volume = int(row["Volume"])

        # 이전 역사 데이터에서 전일 종가 찾기
        if len(hist) > 1:
            previous_close = Decimal(str(hist.iloc[0]["Close"]))
        else:
            # 이전 데이터가 없으면 시가를 전일 종가로 사용
            previous_close = open_price

        change = close_price - previous_close
        change_percent = (
            (change / previous_close) * 100 if previous_close else Decimal("0")
        )

        return EODPrice(
            symbol=symbol,
            trading_date=trading_day.strftime("%Y-%m-%d"),
            close_price=close_price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            high=high_price,
            low=low_price,
            open_price=open_price,
            volume=volume,
            fetched_at=datetime.now(timezone.utc),
        )

    def _calculate_price_movement(self, current: Decimal, previous: Decimal) -> str:
        """가격 움직임 계산 (UP/DOWN/FLAT)"""
        if current > previous:
            return "UP"
        elif current < previous:
            return "DOWN"
        else:
            return "FLAT"

    def _calculate_change_percent(self, current: Decimal, previous: Decimal) -> Decimal:
        """변동률 계산"""
        if previous == 0:
            return Decimal("0")
        return ((current - previous) / previous) * 100

    def _validate_price_for_settlement(
        self, eod_price: EODPrice
    ) -> tuple[bool, Optional[str]]:
        """정산용 가격 유효성 검증"""
        # 기본 검증: 가격이 0이 아니고 합리적인 범위 내에 있는지
        if eod_price.close_price <= 0:
            return False, "Invalid close price (<=0)"

        # 비정상적인 변동률 체크 (예: 50% 이상 변동)
        if abs(eod_price.change_percent) > 50:
            return False, f"Abnormal price movement: {eod_price.change_percent}%"

        # 거래량 체크
        if eod_price.volume == 0:
            return False, "No trading volume"

        return True, None

    def _determine_market_status(self) -> str:
        """현재 시장 상태 판정"""
        # 간단한 구현 - 실제로는 시간대와 거래소 일정을 고려해야 함
        now = datetime.now(timezone.utc)
        hour = now.hour

        # 미국 동부 시간 기준 대략적인 장 시간 (UTC 기준)
        if 14 <= hour < 21:  # 9:30 AM - 4:00 PM EST
            return "OPEN"
        elif 9 <= hour < 14:  # Pre-market
            return "PRE_MARKET"
        elif 21 <= hour <= 23:  # After-hours
            return "AFTER_HOURS"
        else:
            return "CLOSED"
