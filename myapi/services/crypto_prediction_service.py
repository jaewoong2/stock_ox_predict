from __future__ import annotations
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from myapi.config import Settings
from myapi.repositories.cooldown_repository import CooldownRepository
from myapi.repositories.crypto_prediction_repository import (
    CryptoBandPredictionRepository,
)
from myapi.repositories.prediction_repository import UserDailyStatsRepository
from myapi.schemas.auth import ErrorCode
from myapi.schemas.crypto_prediction import (
    CryptoBandPredictionCreate,
    CryptoBandPredictionListResponse,
    CryptoBandPredictionSchema,
    CryptoBandPredictionStatus,
)
from myapi.services.binance_service import BinanceAPIError, BinanceService
from myapi.services.cooldown_service import CooldownService
from myapi.services.error_log_service import ErrorLogService
from myapi.utils.timezone_utils import get_current_kst_date


@dataclass
class CryptoPredictionError(Exception):
    status_code: int
    error_code: ErrorCode
    message: str
    details: Optional[Dict] = None

    def __str__(self) -> str:
        return self.message


class SettlementDataUnavailable(Exception):
    """정산에 필요한 가격 데이터가 준비되지 않은 경우."""


class CryptoPredictionService:
    """BTC 가격 밴드 예측 서비스."""

    ALLOWED_SYMBOLS = {"BTCUSDT"}
    ALLOWED_INTERVALS = {"1h"}
    FUTURE_COL = 0
    SETTLEMENT_MAX_ATTEMPTS = 3
    # row 3는 명확한 정의가 없으므로 1(-1%~1%)과 동일하게 취급하여 확장성 확보
    ROW_TO_PCT: Dict[int, Tuple[Optional[Decimal], Optional[Decimal]]] = {
        0: (Decimal("0.01"), None),  # 상승: +1% 이상
        1: (Decimal("-0.01"), Decimal("0.01")),  # 횡보: -1% ~ +1%
        2: (None, Decimal("-0.01")),  # 하락: -1% 이하
        3: (Decimal("-0.01"), Decimal("0.01")),
    }

    def __init__(
        self,
        db: Session,
        settings: Settings,
        binance_service: BinanceService,
    ):
        self.db = db
        self.settings = settings
        self.repo = CryptoBandPredictionRepository(db)
        self.stats_repo = UserDailyStatsRepository(db)
        self.cooldown_repo = CooldownRepository(db)
        self.binance_service = binance_service
        self.error_log_service = ErrorLogService(db)

    async def create_prediction(
        self, user_id: int, payload: CryptoBandPredictionCreate
    ) -> CryptoBandPredictionSchema:
        symbol = payload.symbol.upper()
        interval = payload.interval.lower()
        trading_day = get_current_kst_date()

        self._validate_request(symbol, interval, payload)

        if self.repo.prediction_exists(user_id, payload.target_open_time_ms, payload.row):
            raise CryptoPredictionError(
                status_code=409,
                error_code=ErrorCode.DUPLICATE_PREDICTION,
                message="동일한 시간/밴드 조합 예측이 이미 존재합니다.",
            )

        stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
        if stats.available_predictions <= 0:
            active_cd = self.cooldown_repo.get_active_timer(user_id, trading_day)
            raise CryptoPredictionError(
                status_code=403 if active_cd else 429,
                error_code=ErrorCode.COOLDOWN_ACTIVE if active_cd else ErrorCode.NO_SLOTS,
                message="쿨다운 진행 중입니다." if active_cd else "사용 가능한 슬롯이 없습니다.",
                details={"remaining": stats.available_predictions},
            )

        # 슬롯 차감
        updated_stats = self.stats_repo.consume_available_prediction(
            user_id, trading_day, amount=1
        )
        if updated_stats.available_predictions >= stats.available_predictions:
            raise CryptoPredictionError(
                status_code=429,
                error_code=ErrorCode.NO_SLOTS,
                message="슬롯 차감 중 오류가 발생했습니다.",
            )

        try:
            p0 = await self._fetch_reference_price(symbol, interval)
            pct_low, pct_high = self.ROW_TO_PCT[payload.row]
            band_price_low, band_price_high = self._calculate_band_prices(
                p0, pct_low, pct_high
            )

            created = self.repo.create_prediction(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                interval=interval,
                future_col=self.FUTURE_COL,
                row=payload.row,
                target_open_time_ms=payload.target_open_time_ms,
                target_close_time_ms=payload.target_close_time_ms,
                p0=p0,
                band_pct_low=pct_low,
                band_pct_high=pct_high,
                band_price_low=band_price_low,
                band_price_high=band_price_high,
            )
            if not created:
                raise RuntimeError("예측 생성에 실패했습니다.")
        except CryptoPredictionError:
            self._refund_slot_safe(user_id, trading_day)
            raise
        except BinanceAPIError as exc:
            self._refund_slot_safe(user_id, trading_day)
            raise CryptoPredictionError(
                status_code=exc.status_code,
                error_code=exc.error_code,
                message=exc.message,
            ) from exc
        except Exception as exc:
            self._refund_slot_safe(user_id, trading_day)
            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                error_message=f"Failed to create crypto prediction: {str(exc)}",
                prediction_details=payload.model_dump(),
            )
            raise

        self._maybe_trigger_cooldown(user_id, trading_day)
        return created

    def _validate_symbol_interval(self, symbol: str, interval: str) -> None:
        if symbol not in self.ALLOWED_SYMBOLS:
            raise CryptoPredictionError(
                status_code=400,
                error_code=ErrorCode.SYMBOL_NOT_ALLOWED,
                message="허용되지 않은 심볼입니다.",
            )
        if interval not in self.ALLOWED_INTERVALS:
            raise CryptoPredictionError(
                status_code=400,
                error_code=ErrorCode.INVALID_INTERVAL,
                message="지원하지 않는 interval 입니다. (현재 1h만 허용)",
            )

    def _validate_request(
        self, symbol: str, interval: str, payload: CryptoBandPredictionCreate
    ) -> None:
        self._validate_symbol_interval(symbol, interval)
        if payload.row not in self.ROW_TO_PCT:
            raise CryptoPredictionError(
                status_code=400,
                error_code=ErrorCode.INVALID_ROW,
                message="지원하지 않는 row 입니다.",
            )
        if payload.target_close_time_ms <= payload.target_open_time_ms:
            raise CryptoPredictionError(
                status_code=400,
                error_code=ErrorCode.PREDICTION_CLOSED,
                message="종료 시간이 시작 시간보다 같거나 빠릅니다.",
            )
        now_ms = int(time.time() * 1000)
        if now_ms >= payload.target_open_time_ms:
            raise CryptoPredictionError(
                status_code=400,
                error_code=ErrorCode.PREDICTION_CLOSED,
                message="이미 마감된 캔들에 대한 예측은 생성할 수 없습니다.",
            )
        # 1h 윈도우 검증 (±1분 허용)
        expected_gap = 3_600_000
        actual_gap = payload.target_close_time_ms - payload.target_open_time_ms
        if abs(actual_gap - expected_gap) > 60_000:
            raise CryptoPredictionError(
                status_code=400,
                error_code=ErrorCode.INVALID_INTERVAL,
                message="타겟 캔들 길이가 1시간이 아닙니다.",
                details={"expected_ms": expected_gap, "actual_ms": actual_gap},
            )

    async def _fetch_reference_price(self, symbol: str, interval: str) -> Decimal:
        """가장 최근 확정된 캔들 종가를 기준가로 사용."""
        klines, _ = await self.binance_service.fetch_klines(
            symbol=symbol, interval=interval, limit=2
        )
        if not klines.klines:
            raise CryptoPredictionError(
                status_code=500,
                error_code=ErrorCode.BINANCE_UNKNOWN_ERROR,
                message="기준가를 계산할 수 없습니다.",
            )

        latest = klines.klines[-1]
        now_ms = int(time.time() * 1000)
        if latest.closeTime > now_ms and len(klines.klines) > 1:
            latest = klines.klines[-2]

        return Decimal(str(latest.close))

    def _calculate_band_prices(
        self,
        p0: Decimal,
        pct_low: Optional[Decimal],
        pct_high: Optional[Decimal],
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        one = Decimal("1")
        low_price = (
            (p0 * (one + pct_low)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            if pct_low is not None
            else None
        )
        high_price = (
            (p0 * (one + pct_high)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            if pct_high is not None
            else None
        )
        return low_price, high_price

    def _refund_slot_safe(self, user_id: int, trading_day: date) -> None:
        try:
            self.stats_repo.refund_prediction(user_id, trading_day, amount=1)
        except Exception as exc:
            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol="BTCUSDT",
                error_message=f"슬롯 환불 실패: {str(exc)}",
                prediction_details=None,
            )

    def _maybe_trigger_cooldown(self, user_id: int, trading_day: date) -> None:
        try:
            stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
            if stats.available_predictions < self.settings.COOLDOWN_TRIGGER_THRESHOLD:
                cooldown_service = CooldownService(self.db, self.settings)
                active = cooldown_service.cooldown_repo.get_active_timer(
                    user_id, trading_day
                )
                if not active:
                    cooldown_service.start_auto_cooldown_sync(user_id, trading_day)
        except Exception as exc:
            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol="BTCUSDT",
                error_message=f"쿨다운 트리거 실패: {str(exc)}",
                prediction_details=None,
            )

    async def list_user_predictions(
        self,
        user_id: int,
        symbol: str,
        interval: str,
        *,
        limit: int,
        offset: int,
    ) -> CryptoBandPredictionListResponse:
        normalized_symbol = symbol.upper()
        normalized_interval = interval.lower()
        self._validate_symbol_interval(normalized_symbol, normalized_interval)
        return self.repo.list_user_predictions(
            user_id=user_id,
            symbol=normalized_symbol,
            interval=normalized_interval,
            limit=limit,
            offset=offset,
        )

    async def settle_due_predictions(
        self, *, now_ms: Optional[int] = None, max_attempts: Optional[int] = None
    ) -> Dict[str, int]:
        """기한이 지난 예측을 정산."""
        now_ms = now_ms or int(time.time() * 1000)
        max_attempts = max_attempts or self.SETTLEMENT_MAX_ATTEMPTS

        pending = self.repo.get_pending_for_settlement(
            now_ms=now_ms, max_attempts=max_attempts
        )
        result = {"processed": 0, "won": 0, "lost": 0, "failed": 0}

        for prediction in pending:
            next_attempt = prediction.settlement_attempts + 1
            mark_error = next_attempt >= max_attempts
            try:
                settlement_price = await self._fetch_settlement_price(prediction)
                status = self._determine_outcome(prediction, settlement_price)
                updated = self.repo.update_status(
                    prediction.id,
                    status,
                    settlement_price=settlement_price,
                    last_error=None,
                )
                if updated:
                    result["processed"] += 1
                    if status == CryptoBandPredictionStatus.WON:
                        result["won"] += 1
                    elif status == CryptoBandPredictionStatus.LOST:
                        result["lost"] += 1
            except SettlementDataUnavailable as exc:
                self.repo.mark_attempt_failed(
                    prediction.id, last_error=str(exc), mark_error=mark_error
                )
                result["failed"] += 1
            except BinanceAPIError as exc:
                self.repo.mark_attempt_failed(
                    prediction.id, last_error=exc.message, mark_error=mark_error
                )
                result["failed"] += 1
            except Exception as exc:
                self.repo.mark_attempt_failed(
                    prediction.id, last_error=str(exc), mark_error=mark_error
                )
                self.error_log_service.log_prediction_error(
                    user_id=prediction.user_id,
                    trading_day=prediction.trading_day,
                    symbol=prediction.symbol,
                    error_message=f"정산 실패: {str(exc)}",
                    prediction_details={"prediction_id": prediction.id},
                )
                result["failed"] += 1

        return result

    async def _fetch_settlement_price(
        self, prediction: CryptoBandPredictionSchema
    ) -> Decimal:
        """타겟 캔들의 종가 조회."""
        klines, _ = await self.binance_service.fetch_klines(
            symbol=prediction.symbol,
            interval=prediction.interval,
            limit=1,
            start_time=prediction.target_open_time_ms,
            end_time=prediction.target_close_time_ms,
        )
        if not klines.klines:
            raise SettlementDataUnavailable("타겟 캔들이 아직 준비되지 않았습니다.")

        candle = klines.klines[0]
        if candle.closeTime < prediction.target_close_time_ms - 500:
            raise SettlementDataUnavailable("캔들이 아직 마감되지 않았습니다.")

        return Decimal(str(candle.close))

    def _determine_outcome(
        self, prediction: CryptoBandPredictionSchema, settlement_price: Decimal
    ) -> CryptoBandPredictionStatus:
        low = prediction.band_price_low
        high = prediction.band_price_high

        if low is not None and high is not None:
            return (
                CryptoBandPredictionStatus.WON
                if low <= settlement_price <= high
                else CryptoBandPredictionStatus.LOST
            )
        if low is not None:
            return (
                CryptoBandPredictionStatus.WON
                if settlement_price >= low
                else CryptoBandPredictionStatus.LOST
            )
        if high is not None:
            return (
                CryptoBandPredictionStatus.WON
                if settlement_price <= high
                else CryptoBandPredictionStatus.LOST
            )

        return CryptoBandPredictionStatus.ERROR
