"""Range prediction service - handles price range prediction business logic."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Optional, Tuple, Set

from sqlalchemy.orm import Session

from myapi.config import Settings
from myapi.core.exceptions import BusinessLogicError, NotFoundError, ValidationError
from myapi.models.prediction import Prediction as PredictionModel, StatusEnum
from myapi.repositories.cooldown_repository import CooldownRepository
from myapi.repositories.range_prediction_repository import RangePredictionRepository
from myapi.schemas.auth import ErrorCode
from myapi.schemas.range_prediction import (
    RangePredictionCreate,
    RangePredictionListResponse,
    RangePredictionResponse,
    RangePredictionUpdate,
)
from myapi.services.base_prediction_service import BasePredictionService
from myapi.services.binance_service import BinanceAPIError, BinanceService
from myapi.services.point_service import PointService
from myapi.utils.timezone_utils import get_current_kst_date, get_kst_now, to_utc


@dataclass
class RangePredictionError(Exception):
    """Custom error for range predictions."""

    status_code: int
    error_code: ErrorCode
    message: str
    details: Optional[Dict] = None

    def __str__(self) -> str:
        return self.message


class SettlementDataUnavailable(Exception):
    """Settlement price data not available yet."""


class RangePredictionService(BasePredictionService):
    """
    Service for RANGE type predictions (price_low/price_high).

    Asset-agnostic design - symbol validation handled via config.
    """

    INTERVAL = "1h"

    def __init__(
        self,
        db: Session,
        settings: Settings,
        binance_service: BinanceService,
        allowed_symbols: Optional[Set[str]] = None,
    ):
        """
        Initialize RANGE prediction service.

        Args:
            db: Database session
            settings: Application settings
            binance_service: Binance API service
            allowed_symbols: Set of allowed symbols (None = allow all)
        """
        super().__init__(db, settings)
        self.repo = RangePredictionRepository(db)
        self.cooldown_repo = CooldownRepository(db)
        self.binance_service = binance_service
        self.point_service = PointService(db)
        self.allowed_symbols = allowed_symbols

    def _validate_symbol(self, symbol: str) -> None:
        """Validate symbol against allowed list."""
        if self.allowed_symbols and symbol not in self.allowed_symbols:
            raise RangePredictionError(
                status_code=400,
                error_code=ErrorCode.SYMBOL_NOT_ALLOWED,
                message="허용되지 않은 심볼입니다.",
            )

    def _get_current_hour_window_ms(self) -> Tuple[int, int]:
        """
        Get next hour time window (KST) in UTC ms.

        Returns:
            Tuple of (open_time_ms, close_time_ms)
        """
        now_kst = get_kst_now()
        open_kst = now_kst.replace(minute=0, second=0, microsecond=0) + timedelta(
            hours=1
        )
        close_kst = open_kst + timedelta(hours=1)

        open_ms = int(to_utc(open_kst).timestamp() * 1000)
        close_ms = int(to_utc(close_kst).timestamp() * 1000)
        return open_ms, close_ms

    async def create_prediction(
        self, user_id: int, payload: RangePredictionCreate
    ) -> RangePredictionResponse:
        """Create new RANGE prediction."""
        symbol = payload.symbol.upper()
        trading_day = get_current_kst_date()

        # Validate symbol
        self._validate_symbol(symbol)

        # Validate range
        if payload.price_low >= payload.price_high:
            raise RangePredictionError(
                status_code=400,
                error_code=ErrorCode.INVALID_RANGE,
                message="price_low must be less than price_high",
            )

        # Get time window
        target_open_ms, target_close_ms = self._get_current_hour_window_ms()

        # Check for duplicate
        if self.repo.prediction_exists(user_id, target_open_ms):
            raise RangePredictionError(
                status_code=409,
                error_code=ErrorCode.DUPLICATE_PREDICTION,
                message="동일한 시간대 예측이 이미 존재합니다.",
            )

        # Check slots
        stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
        if stats.available_predictions <= 0:
            active_cd = self.cooldown_repo.get_active_timer(user_id, trading_day)
            raise RangePredictionError(
                status_code=403 if active_cd else 429,
                error_code=(
                    ErrorCode.COOLDOWN_ACTIVE if active_cd else ErrorCode.NO_SLOTS
                ),
                message=(
                    "쿨다운 진행 중입니다."
                    if active_cd
                    else "사용 가능한 슬롯이 없습니다."
                ),
                details={"remaining": stats.available_predictions},
            )

        # Consume slot
        updated_stats = self.stats_repo.consume_available_prediction(
            user_id, trading_day, amount=1
        )
        if updated_stats.available_predictions >= stats.available_predictions:
            raise RangePredictionError(
                status_code=429,
                error_code=ErrorCode.NO_SLOTS,
                message="슬롯 차감 중 오류가 발생했습니다.",
            )

        # Create prediction with duplicate handling
        submitted_at = datetime.now(timezone.utc)
        try:
            created = self.repo.create_prediction(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                price_low=payload.price_low,
                price_high=payload.price_high,
                target_open_time_ms=target_open_ms,
                target_close_time_ms=target_close_ms,
                submitted_at=submitted_at,
            )
            if not created:
                raise RuntimeError("예측 생성에 실패했습니다.")
        except Exception as exc:
            # Check if it's a duplicate constraint violation
            error_msg = str(exc)
            if (
                "uq_predictions_range" in error_msg
                or "duplicate key" in error_msg.lower()
            ):
                # Refund the slot that was consumed
                self._refund_slot(user_id, trading_day, symbol)

                # Try to get and update existing prediction
                existing = self.repo.get_existing_prediction(user_id, target_open_ms)

                if (
                    existing
                    and existing.status == StatusEnum.PENDING
                    and existing.locked_at is None
                ):
                    # Update existing prediction instead of creating new
                    updated = self.repo.update_existing_prediction(
                        existing.id,
                        price_low=payload.price_low,
                        price_high=payload.price_high,
                        submitted_at=submitted_at,
                    )
                    if updated:
                        return updated

                # If we can't update, raise proper error
                raise RangePredictionError(
                    status_code=409,
                    error_code=ErrorCode.DUPLICATE_PREDICTION,
                    message="동일한 시간대 예측이 이미 존재하며 수정할 수 없습니다.",
                )

            # For other exceptions, refund and re-raise
            self._refund_slot(user_id, trading_day, symbol)
            if isinstance(exc, RangePredictionError):
                raise

            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                error_message=f"Failed to create range prediction: {str(exc)}",
                prediction_details=payload.model_dump(),
            )
            raise

        # Trigger cooldown
        self._check_and_trigger_cooldown(user_id, trading_day)

        return created

    async def update_range_prediction(
        self,
        user_id: int,
        prediction_id: int,
        payload: RangePredictionUpdate,
    ) -> RangePredictionResponse:
        """
        Update RANGE prediction bounds.

        Similar to DirectionPredictionService.update_prediction.

        Args:
            user_id: User ID
            prediction_id: Prediction ID
            payload: Update payload

        Returns:
            Updated prediction

        Raises:
            NotFoundError: Prediction not found
            BusinessLogicError: Cannot modify (ownership/status/locked)
            ValidationError: Invalid update data
        """
        # Get prediction for ownership verification
        model = self.repo.get_user_prediction(user_id, prediction_id)

        if not model:
            raise NotFoundError("Prediction not found")

        # Check ownership
        if int(str(model.user_id)) != int(user_id):
            raise BusinessLogicError(
                error_code="FORBIDDEN_PREDICTION",
                message="Cannot modify another user's prediction",
            )

        # Check status
        if model.status != StatusEnum.PENDING:
            raise BusinessLogicError(
                error_code="PREDICTION_LOCKED",
                message="Only pending predictions can be updated",
            )

        # Check if locked
        if getattr(model, "locked_at", None) is not None:
            raise BusinessLogicError(
                error_code="PREDICTION_LOCKED",
                message="Prediction has been locked for settlement",
            )

        # Validate range
        price_low = (
            payload.price_low if payload.price_low is not None else model.price_low
        )
        price_high = (
            payload.price_high if payload.price_high is not None else model.price_high
        )

        if price_low >= price_high:
            raise ValidationError("price_low must be less than price_high")

        # Update
        updated = self.repo.update_range_bounds(
            prediction_id,
            price_low=payload.price_low,
            price_high=payload.price_high,
        )

        if not updated:
            raise ValidationError("Failed to update prediction")

        return updated

    async def list_user_predictions(
        self,
        user_id: int,
        symbol: Optional[str],
        *,
        limit: int,
        offset: int,
    ) -> RangePredictionListResponse:
        """List user's RANGE predictions."""
        normalized_symbol = symbol.upper() if symbol else None
        if normalized_symbol:
            self._validate_symbol(normalized_symbol)

        return self.repo.list_user_predictions(
            user_id=user_id,
            symbol=normalized_symbol,
            limit=limit,
            offset=offset,
        )

    async def settle_due_predictions(
        self, *, now_ms: Optional[int] = None
    ) -> Dict[str, int]:
        """Settle RANGE predictions that are due."""
        now_ms = now_ms or int(time.time() * 1000)

        pending = self.repo.get_pending_for_settlement(now_ms=now_ms)
        result = {
            "processed": 0,
            "correct": 0,
            "incorrect": 0,
            "skipped": 0,
            "failed": 0,
        }

        for prediction in pending:
            try:
                settlement_price = await self._fetch_settlement_price(prediction)
                status = self._determine_outcome(prediction, settlement_price)
                points = (
                    self.settings.CORRECT_PREDICTION_POINTS
                    if status == StatusEnum.CORRECT
                    else 0
                )
                updated = self.repo.update_status(
                    prediction.id,
                    status,
                    settlement_price=settlement_price,
                    points_earned=points,
                )
                if updated:
                    result["processed"] += 1
                    if status == StatusEnum.CORRECT:
                        result["correct"] += 1
                    else:
                        result["incorrect"] += 1

                if status == StatusEnum.CORRECT:
                    self.point_service.award_prediction_points(
                        user_id=prediction.user_id,
                        prediction_id=prediction.id,
                        points=points,
                        trading_day=prediction.trading_day,
                        symbol=prediction.symbol,
                    )
            except SettlementDataUnavailable:
                result["skipped"] += 1
            except BinanceAPIError as exc:
                result["failed"] += 1
                self.error_log_service.log_prediction_error(
                    user_id=prediction.user_id,
                    trading_day=prediction.trading_day,
                    symbol=prediction.symbol,
                    error_message=f"정산 실패(Binance): {exc.message}",
                    prediction_details={"prediction_id": prediction.id},
                )
            except Exception as exc:
                result["failed"] += 1
                self.error_log_service.log_prediction_error(
                    user_id=prediction.user_id,
                    trading_day=prediction.trading_day,
                    symbol=prediction.symbol,
                    error_message=f"정산 실패: {str(exc)}",
                    prediction_details={"prediction_id": prediction.id},
                )

        return result

    async def _fetch_settlement_price(
        self, prediction: RangePredictionResponse
    ) -> Decimal:
        """Fetch settlement price from target candle."""
        klines, _ = await self.binance_service.fetch_klines(
            symbol=prediction.symbol,
            interval=self.INTERVAL,
            limit=1,
            start_time=prediction.target_open_time_ms,
            end_time=prediction.target_close_time_ms,
        )
        if not klines.klines:
            raise SettlementDataUnavailable("타겟 캔들이 아직 준비되지 않았습니다.")

        candle = klines.klines[0]
        if candle.openTime > prediction.target_open_time_ms + 500:
            raise SettlementDataUnavailable("캔들이 아직 준비되지 않았습니다.")

        return Decimal(str(candle.open))

    def _determine_outcome(
        self, prediction: RangePredictionResponse, settlement_price: Decimal
    ) -> StatusEnum:
        """Determine if prediction was correct."""
        low = prediction.price_low
        high = prediction.price_high

        if low <= settlement_price <= high:
            return StatusEnum.CORRECT
        return StatusEnum.INCORRECT
