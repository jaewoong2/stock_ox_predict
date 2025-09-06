from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone, timedelta
import os
from decimal import Decimal
from typing import List, Optional, cast

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

from myapi.core.exceptions import ValidationError, NotFoundError, ServiceException
from myapi.repositories.active_universe_repository import ActiveUniverseRepository
from myapi.repositories.price_repository import PriceRepository
from myapi.repositories.session_repository import SessionRepository
from myapi.repositories.prediction_repository import PredictionRepository
from myapi.models.prediction import StatusEnum as PredictionStatusEnum
from myapi.schemas.price import (
    StockPrice,
    EODPrice,
    PriceComparisonResult,
    UniversePriceResponse,
    SettlementPriceData,
    EODCollectionResult,
    EODCollectionDetail,
)
from myapi.services.error_log_service import ErrorLogService
from myapi.utils.yf_cache import configure_yfinance_cache


class PriceService:
    """주식 가격 조회 및 정산 검증 서비스"""

    def __init__(self, db: Session):
        self.db = db
        self.universe_repo = ActiveUniverseRepository(db)
        self.price_repo = PriceRepository(db)
        self.session_repo = SessionRepository(db)
        self.pred_repo = PredictionRepository(db)
        self.error_log_service = ErrorLogService(db)
        self.current_price_cache = {}
        self.eod_price_cache = {}
        self.cache_ttl = timedelta(seconds=60)  # 60초 TTL
        # Configure yfinance caches with Lambda/ MPLCONFIGDIR aware fallback
        configure_yfinance_cache()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # yfinance는 별도의 연결 종료가 필요 없음
        pass

    async def get_current_price(self, symbol: str) -> StockPrice:
        """특정 종목의 현재 가격을 조회합니다.
        우선순위: 메모리 캐시 → DB(universe) → yfinance 초기 수집 후 DB 저장.
        """
        # 캐시 확인
        now = datetime.now(timezone.utc)
        if symbol in self.current_price_cache:
            cached_data, timestamp = self.current_price_cache[symbol]
            if now - timestamp < self.cache_ttl:
                return cached_data

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
                # 캐시에 저장 후 반환
                self.current_price_cache[symbol] = (price_data, now)
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

            # 캐시에 저장 후 반환
            self.current_price_cache[symbol] = (price_data, now)
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

    async def get_universe_current_prices(
        self, trading_day: Optional[date] = None
    ) -> UniversePriceResponse:
        """오늘의 유니버스 모든 종목의 현재 가격을 조회합니다."""
        if not trading_day:
            # 현재 세션의 거래일을 우선 사용 (KST 일관성)
            try:
                session = self.session_repo.get_current_session()
                if session:
                    trading_day = session.trading_day
                else:
                    # 세션이 없으면 KST 기준 오늘의 거래일 사용
                    from myapi.utils.market_hours import USMarketHours

                    trading_day = USMarketHours.get_kst_trading_day()
            except Exception:
                from myapi.utils.market_hours import USMarketHours

                trading_day = USMarketHours.get_kst_trading_day()

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
            # 유니버스 전체 가격 조회 실패 에러 로깅
            failed_symbols = [
                universe_item.symbol for universe_item in universe_symbols
            ]
            self.error_log_service.log_eod_fetch_error(
                trading_day=trading_day,
                provider="yfinance",
                failed_symbols=failed_symbols,
                error_message="Failed to fetch any valid current prices for universe",
                retry_count=0,
            )
            raise ServiceException("Failed to fetch any valid prices")

        return UniversePriceResponse(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            prices=valid_prices,
            last_updated=datetime.now(timezone.utc),
        )

    async def get_eod_price(self, symbol: str, trading_day: date) -> EODPrice:
        """
        특정 종목의 특정 날짜 EOD 가격을 조회합니다.
        1. 캐시 확인
        2. DB에서 조회 (이미 수집된 데이터 우선 사용)
        3. 없으면 Yahoo Finance API 호출
        """
        # 1. 캐시 확인 (EOD 데이터는 날짜별로 불변)
        cache_key = (symbol, trading_day)
        if cache_key in self.eod_price_cache:
            return self.eod_price_cache[cache_key]

        # 2. DB에서 이미 수집된 데이터 확인 (우선순위)
        try:
            db_price = self.price_repo.get_eod_price(symbol, trading_day)
            if db_price:
                # 캐시에 저장
                self.eod_price_cache[cache_key] = db_price
                return db_price
        except Exception:
            # DB 조회 실패해도 API 호출로 fallback
            pass

        # 3. DB에 없으면 Yahoo Finance API 호출
        try:
            ticker = yf.Ticker(symbol)
            price_data = await self._get_eod_price_with_yf(ticker, symbol, trading_day)

            # 캐시에 저장
            self.eod_price_cache[cache_key] = price_data
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
        """yfinance를 사용해 EOD 가격 조회 (전일 종가 로직 개선)"""
        loop = asyncio.get_event_loop()

        # 안정적인 전일 종가 확보를 위해 5일치 데이터 조회
        start_date = trading_day - timedelta(days=5)
        end_date = trading_day + timedelta(days=1)

        def fetch_history() -> pd.DataFrame:
            return ticker.history(start=start_date, end=end_date, interval="1d")

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
                    open_price=float(eod_price.open_price),
                    high_price=float(eod_price.high),
                    low_price=float(eod_price.low),
                    close_price=float(eod_price.close_price),
                    previous_close=float(eod_price.previous_close),
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
