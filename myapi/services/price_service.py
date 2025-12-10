from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone, timedelta
import logging
import os
from decimal import Decimal
from typing import Any, List, Optional, cast

import pandas as pd
import yfinance as yf
from sqlalchemy import desc
from sqlalchemy.orm import Session

from myapi.core.exceptions import ValidationError, NotFoundError, ServiceException
from myapi.repositories.active_universe_repository import ActiveUniverseRepository
from myapi.repositories.price_repository import PriceRepository
from myapi.repositories.session_repository import SessionRepository
from myapi.repositories.prediction_repository import PredictionRepository
from myapi.schemas.price import (
    StockPrice,
    EODPrice,
    PriceComparisonResult,
    UniversePriceResponse,
    SettlementPriceData,
    EODCollectionResult,
    EODCollectionDetail,
    TradingDayPriceSummary,
    EODPriceSnapshot,
    CurrentPriceSnapshot,
)
from myapi.schemas.error_log import ErrorTypeEnum
from myapi.services.error_log_service import ErrorLogService
from myapi.schemas.universe import ActiveUniverseSnapshot
from myapi.utils.yf_cache import configure_yfinance_cache
from myapi.utils.alpha_vantage_client import alpha_vantage_client

logger = logging.getLogger(__name__)


class PriceService:
    """주식 가격 조회 및 정산 검증 서비스"""

    def __init__(self, db: Session):
        self.db = db
        self.universe_repo = ActiveUniverseRepository(db)
        self.price_repo = PriceRepository(db)
        self.session_repo = SessionRepository(db)
        self.pred_repo = PredictionRepository(db)
        self.error_log_service = ErrorLogService(db)
        # Configure yfinance caches with Lambda/ MPLCONFIGDIR aware fallback
        configure_yfinance_cache()
        # Limit concurrent outbound yfinance calls (avoid saturation)
        self._yf_semaphore = asyncio.Semaphore(5)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # yfinance는 별도의 연결 종료가 필요 없음
        pass

    async def get_current_price(self, symbol: str) -> StockPrice:
        """특정 종목의 현재 가격을 조회합니다.
        우선순위: 메모리 캐시 → DB(universe) → yfinance 초기 수집 후 DB 저장.
        """
        now = datetime.now(timezone.utc)

        # DB(universe)에서 시도: 오늘(현재 세션) 유니버스에 가격이 있으면 그걸 사용
        try:
            session = self.session_repo.get_current_session()
            trading_day = session.trading_day if session else date.today()

            uni_item = self.universe_repo.get_universe_item_model(trading_day, symbol)
            if uni_item and uni_item.current_price is not None:
                # DB 스냅샷을 StockPrice로 변환
                price_data = StockPrice(
                    symbol=symbol,
                    current_price=Decimal(str(uni_item.current_price)),
                    previous_close=(
                        Decimal(str(uni_item.previous_close))
                        if uni_item.previous_close is not None
                        else Decimal("0")
                    ),
                    change=(
                        Decimal(str(uni_item.change_amount))
                        if uni_item.change_amount is not None
                        else Decimal("0")
                    ),
                    change_percent=(
                        Decimal(str(uni_item.change_percent))
                        if uni_item.change_percent is not None
                        else Decimal("0")
                    ),
                    volume=uni_item.volume if uni_item.volume is not None else None,  # type: ignore
                    market_status=(
                        str(uni_item.market_status)
                        if uni_item.market_status is not None
                        else "UNKNOWN"
                    ),
                    last_updated=uni_item.last_price_updated if uni_item.last_price_updated is not None else now,  # type: ignore
                )
                return price_data
        except Exception:
            # DB 조회 실패해도 이후 단계 진행
            pass

        # DB에 없거나(또는 오늘의 유니버스가 아니라면) 최초 1회 yfinance 조회 후 저장
        try:
            ticker = yf.Ticker(symbol)
            price_data = await self._get_current_price_with_yf(ticker, symbol)

            # 유니버스에 해당 심볼이 있으면 가격을 저장 (없으면 저장 안 함)
            try:
                session = self.session_repo.get_current_session()
                trading_day = session.trading_day if session else date.today()
                if self.universe_repo.symbol_exists_in_universe(trading_day, symbol):
                    self.universe_repo.update_symbol_price(
                        trading_day, symbol, price_data
                    )
            except Exception:
                # 저장 실패는 무시하고 계속 진행
                pass

            return price_data
        except Exception as e:
            # 실시간 가격 조회 실패 에러 로깅
            self.error_log_service.log_api_error(
                api_endpoint=f"yfinance.Ticker({symbol}).info",
                error_message=str(e),
                trading_day=date.today(),
            )
            raise ServiceException(
                f"Failed to fetch current price for {symbol}: {str(e)}"
            )

    # Note: Universe current-price reads are handled by snapshot-only helpers.

    async def refresh_symbol_price(
        self, symbol: str, trading_day: Optional[date] = None
    ) -> StockPrice:
        """
        단일 심볼의 현재가를 yfinance로 강제 갱신하고 DB(universe)에 반영합니다.
        읽기는 최소화하고, 업데이트 목적의 경량 경로로 사용합니다.
        """
        # 거래일 결정
        if trading_day is None:
            try:
                session = self.session_repo.get_current_session()
                trading_day = session.trading_day if session else date.today()
            except Exception:
                from myapi.utils.market_hours import USMarketHours

                trading_day = USMarketHours.get_kst_trading_day()

        # yfinance로 강제 조회
        ticker = yf.Ticker(symbol)
        price_data = await self._get_current_price_with_yf(ticker, symbol)

        # 유니버스에 존재할 때만 저장
        try:
            if self.universe_repo.symbol_exists_in_universe(trading_day, symbol):
                self.universe_repo.update_symbol_price(trading_day, symbol, price_data)
        except Exception:
            # 저장 실패는 무시 (다음 주기에서 재시도)
            pass

        return price_data

    async def save_intraday_price(
        self, symbol: str, interval: str = "15m", period: str = "1d"
    ) -> StockPrice:
        """
        특정 종목의 intraday 가격을 조회합니다 (15분봉 등).

        Args:
            symbol: 종목 코드
            interval: 봉 간격 (1m, 5m, 15m, 30m, 1h, 1d)
            period: 조회 기간 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        """
        ticker = yf.Ticker(symbol)
        price_data = await self._get_intraday_price_with_yf(
            ticker, symbol, interval, period
        )

        # 유니버스에 존재할 때만 저장
        try:
            session = self.session_repo.get_current_session()
            trading_day = session.trading_day if session else date.today()
            if self.universe_repo.symbol_exists_in_universe(trading_day, symbol):
                self.universe_repo.update_symbol_price(trading_day, symbol, price_data)
        except Exception:
            # 저장 실패는 무시 (다음 주기에서 재시도)
            pass

        return price_data

    async def refresh_universe_prices(
        self, trading_day: Optional[date] = None
    ) -> UniversePriceResponse:
        """
        유니버스 전체에 대해 현재가를 yfinance로 강제 갱신하고 DB에 반영합니다.
        배치/관리자 갱신용 경로.
        """
        # 거래일 결정
        if trading_day is None:
            try:
                session = self.session_repo.get_current_session()
                trading_day = session.trading_day if session else date.today()
            except Exception:
                from myapi.utils.market_hours import USMarketHours

                trading_day = USMarketHours.get_kst_trading_day()

        universe_symbols = self.universe_repo.get_universe_for_date(trading_day)

        if not universe_symbols:
            raise NotFoundError(f"No universe found for {trading_day}")

        tasks = [
            self.refresh_symbol_price(item.symbol, trading_day)
            for item in universe_symbols
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid = [r for r in results if isinstance(r, StockPrice)]

        if not valid:
            raise ServiceException("Failed to refresh any prices for universe")

        return UniversePriceResponse(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            prices=valid,
            last_updated=datetime.now(timezone.utc),
        )

    async def refresh_universe_prices_intraday(
        self, trading_day: Optional[date] = None, interval: str = "15m"
    ) -> UniversePriceResponse:
        """
        유니버스 전체에 대해 intraday 가격(15분봉 등)을 갱신합니다.
        """
        # 거래일 결정
        if trading_day is None:
            try:
                session = self.session_repo.get_current_session()
                trading_day = session.trading_day if session else date.today()
            except Exception:
                from myapi.utils.market_hours import USMarketHours

                trading_day = USMarketHours.get_kst_trading_day()

        universe_symbols = self.universe_repo.get_universe_for_date(trading_day)

        if not universe_symbols:
            raise NotFoundError(f"No universe found for {trading_day}")

        tasks = [
            self.save_intraday_price(item.symbol, interval=interval)
            for item in universe_symbols
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, StockPrice)]

        if not valid:
            raise ServiceException(
                f"Failed to refresh any intraday prices for universe with interval {interval}"
            )

        return UniversePriceResponse(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            prices=valid,
            last_updated=datetime.now(timezone.utc),
        )

    async def get_eod_price(self, symbol: str, trading_day: date) -> EODPrice:
        """
        특정 종목의 특정 날짜 EOD 가격을 조회합니다.
        1. 캐시 확인
        2. DB에서 조회 (이미 수집된 데이터 우선 사용)
        3. 없으면 Yahoo Finance API 호출
        """
        # 1. DB에서 이미 수집된 데이터 확인 (우선순위)
        try:
            db_price = self.price_repo.get_eod_price(symbol, trading_day)
            if db_price:
                return db_price
        except Exception:
            # DB 조회 실패해도 API 호출로 fallback
            pass

        # 2. DB에 없으면 Yahoo Finance API 호출
        try:
            ticker = yf.Ticker(symbol)
            price_data = await self._get_eod_price_with_yf(ticker, symbol, trading_day)
            return price_data
        except Exception as e:
            # EOD 가격 조회 실패 에러 로깅
            self.error_log_service.log_eod_fetch_error(
                trading_day=trading_day,
                provider="yfinance",
                failed_symbols=[symbol],
                error_message=str(e),
                retry_count=0,
            )
            raise ServiceException(
                f"Failed to fetch EOD price for {symbol} on {trading_day}: {str(e)}"
            )

    async def get_universe_eod_prices(self, trading_day: date) -> List[EODPrice]:
        """
        오늘의 유니버스 모든 종목의 EOD 가격을 조회합니다.
        DB에서 batch 조회 → 없는 것만 API 호출로 효율적 처리
        """
        universe_symbols = self.universe_repo.get_universe_for_date(trading_day)
        if not universe_symbols:
            raise NotFoundError(f"No universe found for {trading_day}")

        symbols = [sym.symbol for sym in universe_symbols]

        # DB에서 이미 저장된 EOD 데이터를 batch로 조회 (효율적)
        try:
            db_prices = self.price_repo.get_eod_prices_for_symbols(symbols, trading_day)
            db_symbols = {price.symbol for price in db_prices}

            # DB에 없는 종목들만 API 호출
            missing_symbols = [sym for sym in symbols if sym not in db_symbols]

            if missing_symbols:
                # 누락된 종목만 병렬 API 호출
                tasks = [
                    self.get_eod_price(symbol, trading_day)
                    for symbol in missing_symbols
                ]
                api_prices = await asyncio.gather(*tasks, return_exceptions=True)
                valid_api_prices = [
                    price for price in api_prices if isinstance(price, EODPrice)
                ]

                # DB 데이터 + API 데이터 합쳐서 반환
                return db_prices + valid_api_prices
            else:
                # 모든 데이터가 DB에 있음
                return db_prices

        except Exception:
            # DB 조회 실패 시 fallback to 기존 방식
            tasks = [self.get_eod_price(symbol, trading_day) for symbol in symbols]
            prices = await asyncio.gather(*tasks, return_exceptions=True)
            valid_prices = [price for price in prices if isinstance(price, EODPrice)]
            return valid_prices

    async def validate_settlement_prices(
        self, trading_day: date
    ) -> List[SettlementPriceData]:
        """
        정산을 위한 가격 검증을 수행합니다.

        - 예측 시점 스냅샷 가격(snapshot)과 EOD 종가를 비교 가능한지 여부를 추가로 검증합니다.
          (스냅샷 가격이 있는 경우 0보다 커야 하며, 없다면 전일 종가로 비교 가능해야 함)
        """
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

            # 1차: EOD 데이터 자체 유효성 검증
            is_valid, void_reason = self._validate_price_for_settlement(eod_price)

            # 스냅샷 존재/품질에 대한 판단은 예측별로 Settlement 단계에서 처리 (심볼 전체 VOID 방지)

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
                prediction_id=None,
                base_price_source="previous_close",
            )

        except Exception as e:
            raise ServiceException(
                f"Failed to compare prediction for {symbol}: {str(e)}"
            )

    async def compare_prediction_with_outcome_by_id(
        self, prediction_id: int
    ) -> PriceComparisonResult:
        """특정 예측 ID를 기준으로 스냅샷 가격 대비 EOD 결과를 비교합니다."""
        try:
            pred = self.pred_repo.get_by_id(prediction_id)
            if pred is None:
                raise NotFoundError(f"Prediction not found: {prediction_id}")

            # EOD 가격 조회
            eod_price = await self.get_eod_price(pred.symbol, pred.trading_day)

            # 기준 가격: 스냅샷 우선, 없으면 전일 종가
            snap = getattr(pred, "prediction_price", None)
            if snap is not None:
                base_price: Decimal = cast(Decimal, snap)
                base_src = "snapshot"
            else:
                base_price = eod_price.previous_close
                base_src = "previous_close"

            # 실제 가격 움직임 계산 (정산 종가 vs 기준가)
            actual_movement = self._calculate_price_movement(
                eod_price.close_price, base_price
            )

            # 예측 결과 판정
            prediction_outcome = (
                "CORRECT"
                if pred.choice.value.upper() == actual_movement
                else "INCORRECT"
            )

            change_percent = self._calculate_change_percent(
                eod_price.close_price, base_price
            )

            return PriceComparisonResult(
                symbol=pred.symbol,
                trading_date=pred.trading_day.strftime("%Y-%m-%d"),
                current_price=eod_price.close_price,
                previous_price=base_price,
                price_movement=actual_movement,
                change_percent=change_percent,
                prediction_outcome=prediction_outcome,
                prediction_id=pred.id,
                base_price_source=base_src,
            )
        except Exception as e:
            raise ServiceException(
                f"Failed to compare prediction by id {prediction_id}: {str(e)}"
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

        # Offload blocking call with concurrency guard
        async with self._yf_semaphore:
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

    # Snapshot-only helpers (no yfinance)
    def get_current_price_snapshot(
        self, symbol: str, trading_day: Optional[date] = None
    ) -> StockPrice:
        """ActiveUniverse snapshot only. Raises NotFoundError if missing."""
        if trading_day is None:
            try:
                session = self.session_repo.get_current_session()
                trading_day = session.trading_day if session else date.today()
            except Exception:
                from myapi.utils.market_hours import USMarketHours

                trading_day = USMarketHours.get_kst_trading_day()

        uni_item = self.universe_repo.get_universe_item_model(trading_day, symbol)
        if (
            not uni_item
            or uni_item.current_price is None
            or uni_item.previous_close is None
        ):
            raise NotFoundError(
                message="SNAPSHOT_NOT_AVAILABLE",
                details={
                    "resource": "current_price",
                    "symbol": symbol,
                    "trading_day": str(trading_day),
                },
            )
        return StockPrice(
            symbol=symbol,
            current_price=Decimal(str(uni_item.current_price)),
            previous_close=Decimal(str(uni_item.previous_close)),
            change=(
                Decimal(str(uni_item.change_amount))
                if uni_item.change_amount is not None
                else Decimal("0")
            ),
            change_percent=(
                Decimal(str(uni_item.change_percent))
                if uni_item.change_percent is not None
                else Decimal("0")
            ),
            volume=uni_item.volume if uni_item.volume is not None else None,  # type: ignore
            market_status=(
                str(uni_item.market_status)
                if uni_item.market_status is not None
                else "UNKNOWN"
            ),
            last_updated=uni_item.last_price_updated if uni_item.last_price_updated is not None else datetime.now(timezone.utc),  # type: ignore
        )

    def get_universe_current_prices_snapshot(
        self, trading_day: Optional[date] = None
    ) -> UniversePriceResponse:
        """ActiveUniverse snapshots only. Raises NotFoundError if any missing."""
        if trading_day is None:
            try:
                session = self.session_repo.get_current_session()
                trading_day = session.trading_day if session else date.today()
            except Exception:
                from myapi.utils.market_hours import USMarketHours

                trading_day = USMarketHours.get_kst_trading_day()

        universe_models = self.universe_repo.get_universe_models_for_date(trading_day)
        if not universe_models:
            raise NotFoundError(
                message="SNAPSHOT_NOT_AVAILABLE",
                details={"resource": "universe", "trading_day": str(trading_day)},
            )

        prices: list[StockPrice] = []
        missing: list[str] = []
        for m in universe_models:
            snap = ActiveUniverseSnapshot.model_validate(m)
            if snap.current_price is None or snap.previous_close is None:
                missing.append(snap.symbol)
                continue
            prices.append(
                StockPrice(
                    symbol=snap.symbol,
                    current_price=Decimal(str(snap.current_price)),
                    previous_close=Decimal(str(snap.previous_close)),
                    change=(
                        Decimal(str(snap.change_amount))
                        if snap.change_amount is not None
                        else Decimal("0")
                    ),
                    change_percent=(
                        Decimal(str(snap.change_percent))
                        if snap.change_percent is not None
                        else Decimal("0")
                    ),
                    volume=snap.volume if snap.volume is not None else None,  # type: ignore
                    market_status=(
                        snap.market_status
                        if snap.market_status is not None
                        else "UNKNOWN"
                    ),
                    last_updated=snap.last_price_updated if snap.last_price_updated is not None else datetime.now(timezone.utc),  # type: ignore
                )
            )

        if missing:
            raise NotFoundError(
                message="SNAPSHOT_NOT_AVAILABLE",
                details={
                    "resource": "current_price",
                    "trading_day": str(trading_day),
                    "missing_count": len(missing),
                },
            )

        return UniversePriceResponse(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            prices=prices,
            last_updated=datetime.now(timezone.utc),
        )

    def get_trading_day_price_summary(
        self,
        trading_day: Optional[date] = None,
        symbols: Optional[List[str]] = None,
    ) -> List[TradingDayPriceSummary]:
        """
        거래일 가격 요약 조회 (종가 + 현재가)

        Returns:
            - 금일 종가 (전일 대비 변동)
            - 현재가 (금일 종가 대비 변동)

        Args:
            trading_day: 거래일 (기본값: 현재 KST 거래일)
            symbols: 조회할 심볼 리스트 (기본값: 전체 유니버스)

        Raises:
            NotFoundError: 데이터가 없는 경우
        """
        # 1. trading_day 기본값 설정
        if trading_day is None:
            try:
                session = self.session_repo.get_current_session()
                trading_day = session.trading_day if session else date.today()
            except Exception:
                from myapi.utils.market_hours import USMarketHours

                trading_day = USMarketHours.get_kst_trading_day()

        # 2. EOD 가격 데이터 조회 및 변환
        from myapi.utils.market_hours import USMarketHours

        prev_trading_day = USMarketHours.get_prev_trading_day(trading_day)

        if symbols:
            eod_models = self.price_repo.get_eod_prices_for_symbols(
                symbols=symbols, trading_date=prev_trading_day
            )
        else:
            eod_models = self.price_repo.get_eod_prices_for_date(prev_trading_day)

        # 3. 현재가 데이터 조회 및 변환
        universe_models = self.universe_repo.get_universe_models_for_date(trading_day)
        if not universe_models:
            raise NotFoundError(
                message="UNIVERSE_DATA_NOT_AVAILABLE",
                details={
                    "resource": "active_universe",
                    "trading_day": str(trading_day),
                },
            )

        # 4. DB 모델을 타입 안전한 스냅샷으로 변환
        eod_map = {
            eod.symbol: EODPriceSnapshot.from_db_model(eod) for eod in eod_models
        }

        current_map = {
            str(model.symbol): CurrentPriceSnapshot.from_db_model(model)
            for model in universe_models
            if model.current_price is not None  # 현재가가 있는 것만
        }

        # 5. EOD + 현재가 결합하여 요약 데이터 생성
        summaries: List[TradingDayPriceSummary] = []
        symbol_seq_map: dict[str, int] = {}  # 정렬용 seq 맵

        for symbol, current_snap in current_map.items():
            # seq 저장 (정렬용)
            symbol_seq_map[symbol] = current_snap.seq

            # EOD 데이터 조회 또는 폴백 생성
            eod_snap = eod_map.get(symbol)

            if not eod_snap:
                # EOD 데이터 없음 → 폴백 값 사용 (0으로 채워서 나중에 업데이트 가능)
                logger.warning(
                    "No EOD data for symbol %s on previous trading day %s - using fallback values",
                    symbol,
                    prev_trading_day,
                )
                eod_snap = EODPriceSnapshot(
                    symbol=symbol,
                    close_price=current_snap.current_price,  # Baseline
                    previous_close=current_snap.current_price,  # Baseline
                    change_amount=Decimal("0"),  # No change data
                    change_percent=Decimal("0"),  # No change data
                )

            # 현재가 변동 계산 (현재가 - 금일 종가)
            current_change_amount = current_snap.current_price - eod_snap.close_price
            current_change_percent = (
                (current_change_amount / eod_snap.close_price * 100)
                if eod_snap.close_price != 0
                else Decimal("0")
            )

            summaries.append(
                TradingDayPriceSummary(
                    symbol=symbol,
                    trading_day=trading_day.strftime("%Y-%m-%d"),
                    # 종가 정보 (전일 대비)
                    closing_price=eod_snap.close_price,
                    previous_close=eod_snap.previous_close,
                    close_change_amount=eod_snap.change_amount,
                    close_change_percent=eod_snap.change_percent,
                    # 현재가 정보 (종가 대비)
                    current_price=current_snap.current_price,
                    current_change_amount=current_change_amount,
                    current_change_percent=current_change_percent,
                    market_status=current_snap.market_status,
                    last_price_updated=current_snap.last_price_updated,
                )
            )

        # 6. 정렬 (seq 순서대로) - 타입 안전
        summaries.sort(key=lambda x: symbol_seq_map.get(x.symbol, 9999))

        return summaries

    def get_eod_price_snapshot(self, symbol: str, trading_day: date) -> EODPrice:
        """EOD from DB only. Raises NotFoundError if missing."""
        db_price = self.price_repo.get_eod_price(symbol, trading_day)
        if not db_price:
            raise NotFoundError(
                message="SNAPSHOT_NOT_AVAILABLE",
                details={
                    "resource": "eod_price",
                    "symbol": symbol,
                    "trading_day": str(trading_day),
                },
            )
        return db_price

    def get_universe_eod_prices_snapshot(self, trading_day: date) -> list[EODPrice]:
        """Universe EOD from DB only. Raises NotFoundError if missing."""
        universe_symbols = self.universe_repo.get_universe_for_date(trading_day)
        if not universe_symbols:
            raise NotFoundError(
                message="SNAPSHOT_NOT_AVAILABLE",
                details={"resource": "universe", "trading_day": str(trading_day)},
            )
        symbols = [s.symbol for s in universe_symbols]
        prices = self.price_repo.get_eod_prices_for_symbols(symbols, trading_day)
        if not prices or len(prices) < len(symbols):
            raise NotFoundError(
                message="SNAPSHOT_NOT_AVAILABLE",
                details={
                    "resource": "eod_price",
                    "trading_day": str(trading_day),
                    "expected": len(symbols),
                    "found": len(prices),
                },
            )
        return prices

    async def _get_eod_price_with_yf(
        self, ticker: yf.Ticker, symbol: str, trading_day: date
    ) -> EODPrice:
        """yfinance를 사용해 EOD 가격 조회 (전일 종가 로직 개선)"""
        loop = asyncio.get_event_loop()

        # 안정적인 전일 종가 확보를 위해 5일치 데이터 조회
        start_date = trading_day - timedelta(days=2)
        end_date = trading_day + timedelta(days=1)

        def fetch_history() -> pd.DataFrame:
            return ticker.history(start=start_date, end=end_date, interval="1d")

        # Offload blocking call with concurrency guard
        async with self._yf_semaphore:
            hist: pd.DataFrame = await loop.run_in_executor(None, fetch_history)

        if hist.empty:
            raise ValidationError(
                f"No history data available for {symbol} near {trading_day}"
            )

        hist.index = pd.Index([d.date() for d in pd.to_datetime(hist.index)])

        # 해당 거래일의 데이터 찾기
        try:
            row_data = hist.loc[trading_day]
            # 중복 인덱스가 있을 경우 DataFrame이 반환되므로 첫 번째 행을 사용
            if isinstance(row_data, pd.DataFrame):
                row = row_data.iloc[0]
            else:
                row = row_data
        except KeyError:
            raise ValidationError(
                f"No EOD data available for {symbol} on {trading_day}"
            )

        # 전일 종가 찾기
        try:
            # trading_day 이전의 마지막 행을 찾음
            previous_day_row = hist.loc[: trading_day - timedelta(days=1)].iloc[-1]
            previous_close = Decimal(str(previous_day_row["Close"]))
        except IndexError:
            # 이전 데이터가 없으면 시가를 전일 종가로 사용 (IPO 등의 경우)
            previous_close = Decimal(str(row["Open"]))

        close_price = Decimal(str(row["Close"]))
        open_price = Decimal(str(row["Open"]))
        high_price = Decimal(str(row["High"]))
        low_price = Decimal(str(row["Low"]))
        volume = int(row["Volume"])

        change = close_price - previous_close
        change_percent = (
            (change / previous_close) * 100 if previous_close else Decimal("0")
        )

        return EODPrice(
            symbol=symbol,
            trading_date=trading_day.strftime("%Y-%m-%d"),
            close_price=close_price,
            previous_close=previous_close,
            change_amount=change,
            change_percent=change_percent,
            high=high_price,
            low=low_price,
            open_price=open_price,
            volume=volume,
            fetched_at=datetime.now(timezone.utc),
        )

    async def _get_intraday_price_with_yf(
        self, ticker: yf.Ticker, symbol: str, interval: str = "15m", period: str = "1d"
    ) -> StockPrice:
        """
        yfinance를 사용해 intraday 가격 조회 (15분봉 등)

        오류 처리 및 Fallback 순서:
        1. yfinance 시도
        2. Alpha Vantage API 시도 (무료 tier: 일 500회)
        3. 캐시된 universe 데이터 조회
        4. EOD 데이터 기반 추정

        봉(Candle) 개념:
        - 현재 시간 10:35분, 30분봉 기준
        - 10:00~10:30: 완료된 봉 (latest_row)
        - 10:30~11:00: 진행 중인 봉 (보통 데이터에 포함 안됨)
        - 09:30~10:00: 이전 완료된 봉 (previous_row)

        비교 방식:
        - current_price: 가장 최근 완료된 봉의 종가
        - previous_close: 그 이전 봉의 종가
        - 시간 흐름에 따른 연속적 가격 변화를 추적
        """
        try:
            loop = asyncio.get_event_loop()

            def fetch_intraday() -> pd.DataFrame:
                # prepost=True로 프리/애프터마켓 포함
                return ticker.history(period=period, interval=interval, prepost=True)

            # Offload blocking call with concurrency guard
            async with self._yf_semaphore:
                hist: pd.DataFrame = await loop.run_in_executor(None, fetch_intraday)

            if hist.empty:
                # yfinance에서 데이터를 가져올 수 없는 경우 Alpha Vantage 시도
                logger.warning(f"No yfinance data for {symbol}, trying Alpha Vantage")
                alpha_vantage_price = await self._get_intraday_price_with_alpha_vantage(
                    symbol, interval
                )
                if alpha_vantage_price:
                    return alpha_vantage_price
                else:
                    # Alpha Vantage도 실패하면 기존 fallback 체인 시도
                    return await self._get_fallback_intraday_price(
                        symbol, interval, period
                    )

            # 최소 2개 이상의 봉이 필요 (현재 봉과 이전 봉 비교를 위해)
            if len(hist) < 2:
                logger.warning(
                    f"Insufficient yfinance data for {symbol}: {len(hist)} candles, trying Alpha Vantage"
                )
                alpha_vantage_price = await self._get_intraday_price_with_alpha_vantage(
                    symbol, interval
                )
                if alpha_vantage_price:
                    return alpha_vantage_price
                else:
                    # Alpha Vantage도 실패하면 기존 fallback 체인 시도
                    return await self._get_fallback_intraday_price(
                        symbol, interval, period
                    )

            latest_row = hist.iloc[-1]
            previous_row = hist.iloc[-2]

            current_price = Decimal(str(latest_row["Close"]))
            previous_close = Decimal(str(previous_row["Close"]))

            # 봉 간 가격 변화 계산
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
                volume=latest_row.get("Volume"),
                market_status="INTRADAY",
                last_updated=datetime.now(timezone.utc),
            )

        except Exception as e:
            error_msg = str(e).lower()
            if "delisted" in error_msg or "no price data found" in error_msg:
                logger.error(
                    f"Symbol {symbol} appears to be delisted: {e}, trying Alpha Vantage"
                )
            else:
                logger.error(
                    f"Unexpected yfinance error for {symbol}: {e}, trying Alpha Vantage"
                )

            # yfinance 오류 시 Alpha Vantage 시도
            alpha_vantage_price = await self._get_intraday_price_with_alpha_vantage(
                symbol, interval
            )
            if alpha_vantage_price:
                return alpha_vantage_price
            else:
                # Alpha Vantage도 실패하면 기존 fallback 체인 시도
                return await self._get_fallback_intraday_price(symbol, interval, period)

    async def _get_intraday_price_with_alpha_vantage(
        self, symbol: str, interval: str = "15m"
    ) -> Optional[StockPrice]:
        """
        Alpha Vantage API를 사용해 intraday 가격 조회 (yfinance fallback)

        yfinance 간격을 Alpha Vantage 형식으로 변환:
        - "15m" -> "15min"
        - "30m" -> "30min"
        - "1h" -> "60min"

        Args:
            symbol: 주식 심볼
            interval: yfinance 형식 간격

        Returns:
            Optional[StockPrice]: 성공시 가격 정보, 실패시 None
        """
        try:
            # yfinance 간격을 Alpha Vantage 형식으로 변환
            av_interval_map = {
                "1m": "1min",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "1h": "60min",
            }

            av_interval = av_interval_map.get(interval, "15min")
            logger.info(
                f"Trying Alpha Vantage for {symbol} with interval {av_interval}"
            )

            # Alpha Vantage API 호출
            price_data = await alpha_vantage_client.get_intraday_price(
                symbol, av_interval
            )

            if price_data:
                logger.info(f"Successfully retrieved Alpha Vantage data for {symbol}")
                return price_data
            else:
                logger.warning(f"Alpha Vantage returned no data for {symbol}")
                return None

        except Exception as e:
            logger.error(f"Alpha Vantage intraday request failed for {symbol}: {e}")
            return None

    async def _get_fallback_intraday_price(
        self, symbol: str, interval: str = "15m", period: str = "1d"
    ) -> StockPrice:
        """
        yfinance와 Alpha Vantage 모두 실패했을 때 사용하는 최종 fallback 메소드

        Fallback 전략:
        1. 캐시된 universe 데이터 조회 (24시간 이내)
        2. EOD 데이터를 기반으로 추정값 생성
        3. 모든 방법이 실패하면 심볼을 비활성화 상태로 마킹 후 오류 발생

        Args:
            symbol: 주식 심볼
            interval: 봉 간격 (사용안함)
            period: 기간 (사용안함)

        Returns:
            StockPrice: 추정된 또는 캐시된 가격 정보

        Raises:
            ValidationError: 모든 fallback 방법이 실패한 경우
        """
        logger.info(f"Attempting final fallback price retrieval for {symbol}")

        try:
            # 1. 최근 캐시된 universe 데이터 조회 시도
            cached_price = await self._get_cached_intraday_price(symbol)
            if cached_price:
                logger.info(f"Using cached universe data for {symbol}")
                return cached_price

            # 2. EOD 데이터 기반 추정 시도
            estimated_price = await self._estimate_intraday_from_eod(symbol)
            if estimated_price:
                logger.info(f"Using EOD-based estimation for {symbol}")
                return estimated_price

            # 3. 모든 방법 실패 - 심볼 비활성화 고려
            await self._handle_unavailable_symbol(symbol)

            raise ValidationError(
                f"Unable to retrieve price data for {symbol} through any method. "
                f"Symbol may be delisted or temporarily unavailable."
            )

        except Exception as e:
            logger.error(f"Final fallback price retrieval failed for {symbol}: {e}")
            raise ValidationError(
                f"All price retrieval methods failed for {symbol}: {str(e)}"
            )

    async def _get_cached_intraday_price(self, symbol: str) -> Optional[StockPrice]:
        """
        최근 캐시된 intraday 가격 데이터 조회

        현재 시스템에서는 intraday 데이터를 별도로 저장하지 않으므로,
        universe 테이블에서 최근 가격 정보를 조회합니다.

        Args:
            symbol: 주식 심볼

        Returns:
            Optional[StockPrice]: 캐시된 가격 정보 (최근 데이터), 없으면 None
        """
        try:
            # universe에서 최근 가격 정보 조회 시도
            session = self.session_repo.get_current_session()
            trading_day = session.trading_day if session else date.today()

            uni_item = self.universe_repo.get_universe_item_model(trading_day, symbol)
            if uni_item:
                current_price_raw = getattr(uni_item, "current_price", None)
                previous_close_raw = getattr(uni_item, "previous_close", None)
                last_price_updated_value = cast(
                    Optional[datetime], getattr(uni_item, "last_price_updated", None)
                )

                if (
                    current_price_raw is not None
                    and previous_close_raw is not None
                    and last_price_updated_value is not None
                ):
                    # 24시간 이내 데이터인지 확인
                    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
                    if last_price_updated_value >= cutoff_time:
                        change_amount_raw = getattr(uni_item, "change_amount", None)
                        change_percent_raw = getattr(uni_item, "change_percent", None)
                        volume_raw: Any = getattr(uni_item, "volume", None)

                        return StockPrice(
                            symbol=symbol,
                            current_price=Decimal(str(current_price_raw)),
                            previous_close=Decimal(str(previous_close_raw)),
                            change=(
                                Decimal(str(change_amount_raw))
                                if change_amount_raw is not None
                                else Decimal("0")
                            ),
                            change_percent=(
                                Decimal(str(change_percent_raw))
                                if change_percent_raw is not None
                                else Decimal("0")
                            ),
                            volume=(
                                int(volume_raw) if volume_raw is not None else None
                            ),
                            market_status="CACHED_UNIVERSE",
                            last_updated=cast(datetime, last_price_updated_value),
                        )

            return None

        except Exception as e:
            logger.warning(f"Failed to retrieve cached universe data for {symbol}: {e}")
            return None

    async def _estimate_intraday_from_eod(self, symbol: str) -> Optional[StockPrice]:
        """
        EOD 데이터를 기반으로 intraday 가격 추정

        전략:
        - 최근 2일의 EOD 데이터 사용
        - 변동성을 고려한 추정값 생성
        - 시장 상황에 따른 조정

        Args:
            symbol: 주식 심볼

        Returns:
            Optional[StockPrice]: 추정된 가격 정보, 실패시 None
        """
        try:
            # price_repo를 통해 최근 EOD 데이터 조회
            cutoff_date = date.today() - timedelta(days=3)

            # 최근 2일의 EOD 데이터 조회
            # 해당 심볼의 최근 2일 데이터 조회
            # 기존 repository를 활용하여 EOD 데이터 조회
            try:
                # 최근 EOD 가격 조회 (전체 리스트에서 해당 심볼 필터링)
                all_recent_prices = self.price_repo.get_latest_eod_prices(limit=100)
                symbol_prices = [p for p in all_recent_prices if p.symbol == symbol]
                latest_prices = symbol_prices[:2] if len(symbol_prices) >= 2 else []
            except Exception:
                latest_prices = []

            if len(latest_prices) < 2:
                logger.warning(f"Insufficient EOD data for estimation: {symbol}")
                return None

            latest_eod = latest_prices[0]
            previous_eod = latest_prices[1]

            # 추정값 생성 (현재는 단순히 최신 EOD 가격 사용)
            # 향후 더 정교한 추정 로직 추가 가능
            estimated_price = latest_eod.close_price
            estimated_previous = previous_eod.close_price

            change = estimated_price - estimated_previous
            change_percent = (
                (change / estimated_previous) * 100
                if estimated_previous
                else Decimal("0")
            )

            return StockPrice(
                symbol=symbol,
                current_price=estimated_price,
                previous_close=estimated_previous,
                change=change,
                change_percent=change_percent,
                volume=latest_eod.volume,
                market_status="ESTIMATED_FROM_EOD",
                last_updated=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.warning(
                f"Failed to estimate intraday price from EOD for {symbol}: {e}"
            )
            return None

    async def _handle_unavailable_symbol(self, symbol: str) -> None:
        """
        지속적으로 데이터를 가져올 수 없는 심볼 처리

        - 에러 로그 기록
        - universe에서 일시적 비활성화 고려 (optional)
        - 알림 시스템 연동 (optional)

        Args:
            symbol: 처리할 심볼
        """
        try:
            # 에러 로그 기록
            error_context = {
                "action": "price_retrieval_failed",
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "all_methods_failed": True,
                "attempted_sources": [
                    "yfinance",
                    "alpha_vantage",
                    "cached_universe",
                    "eod_estimation",
                ],
            }

            self.error_log_service.log_generic_error(
                check_type=ErrorTypeEnum.EXTERNAL_API_ERROR,
                error_message=f"All price retrieval methods failed for symbol {symbol}",
                details=error_context,
                trading_day=date.today(),
            )

            logger.warning(f"Symbol {symbol} marked as unavailable in error logs")

            # TODO: 향후 구현 고려사항
            # - universe 테이블에서 심볼 일시 비활성화
            # - 관리자 알림 시스템 연동
            # - 자동 재시도 스케줄링

        except Exception as e:
            logger.error(f"Failed to handle unavailable symbol {symbol}: {e}")

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

    async def collect_eod_data_for_universe(
        self, trading_day: date
    ) -> EODCollectionResult:
        """
        지정된 거래일의 유니버스에 대한 모든 EOD 데이터를 수집하고 저장합니다.

        Args:
            trading_day: 데이터를 수집할 거래일

        Returns:
            EODCollectionResult: 수집 결과 및 상세 정보
        """
        # 해당 거래일의 유니버스 조회
        universe_symbols = self.universe_repo.get_universe_for_date(trading_day)
        if not universe_symbols:
            raise NotFoundError(f"No universe found for {trading_day}")

        total_symbols = len(universe_symbols)
        collection_details = []
        successful_collections = 0
        failed_collections = 0

        # 각 종목에 대해 EOD 데이터 수집 및 저장
        for universe_symbol in universe_symbols:
            symbol = universe_symbol.symbol
            detail = EODCollectionDetail(
                symbol=symbol, success=False, error_message=None, eod_data=None
            )

            try:
                # EOD 데이터 조회
                eod_price = await self.get_eod_price(symbol, trading_day)

                # Repository를 통해 DB에 저장
                self.price_repo.save_eod_price(
                    symbol=symbol,
                    trading_date=trading_day,
                    open_price=eod_price.open_price,
                    high_price=eod_price.high,
                    low_price=eod_price.low,
                    close_price=eod_price.close_price,
                    previous_close=eod_price.previous_close,
                    volume=eod_price.volume,
                    data_source="yfinance",
                )

                detail.success = True
                detail.eod_data = eod_price
                successful_collections += 1

            except Exception as e:
                detail.success = False
                detail.error_message = str(e)
                failed_collections += 1

                # EOD 데이터 수집 실패 에러 로깅
                self.error_log_service.log_eod_fetch_error(
                    trading_day=trading_day,
                    provider="yfinance",
                    failed_symbols=[symbol],
                    error_message=str(e),
                    retry_count=0,
                )

            collection_details.append(detail)

        return EODCollectionResult(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            total_symbols=total_symbols,
            successful_collections=successful_collections,
            failed_collections=failed_collections,
            details=collection_details,
        )
