"""Direction prediction service - handles UP/DOWN prediction business logic."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import List, Optional, Tuple, cast

from sqlalchemy.orm import Session

from myapi.config import Settings
from myapi.core.exceptions import (
    BusinessLogicError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from myapi.models.prediction import (
    ChoiceEnum,
    Prediction as PredictionModel,
    PredictionTypeEnum,
    StatusEnum,
)
from myapi.repositories.active_universe_repository import ActiveUniverseRepository
from myapi.repositories.direction_prediction_repository import (
    DirectionPredictionRepository,
)
from myapi.repositories.price_repository import PriceRepository
from myapi.repositories.session_repository import SessionRepository
from myapi.schemas.prediction import (
    MostLongPredictionItem,
    MostShortPredictionItem,
    PredictHistoryMonth,
    PredictionChoice,
    PredictionCreate,
    PredictionResponse,
    PredictionStats,
    PredictionStatus,
    PredictionSummary,
    PredictionTrendsResponse,
    PredictionUpdate,
    UserPredictionsResponse,
)
from myapi.schemas.universe import ActiveUniverseSnapshot
from myapi.services.base_prediction_service import BasePredictionService
from myapi.utils.date_utils import to_date


class DirectionPredictionService(BasePredictionService):
    """Service for DIRECTION type predictions (UP/DOWN)."""

    def __init__(self, db: Session, settings: Settings):
        super().__init__(db, settings)
        self.pred_repo = DirectionPredictionRepository(db)
        self.universe_repo = ActiveUniverseRepository(db)
        self.session_repo = SessionRepository(db)
        self.price_repo = PriceRepository(db)

    def _safe_transaction(self, operation):
        """Safe transaction execution helper."""
        try:
            result = operation()
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def submit_prediction(
        self, user_id: int, trading_day: date, payload: PredictionCreate
    ) -> PredictionResponse:
        """Submit new DIRECTION prediction."""
        # Check session state
        session = self.session_repo.get_session_by_date(trading_day)
        if not session:
            session = self.session_repo.get_current_session()
        if not session or not session.is_prediction_open:
            raise BusinessLogicError(
                error_code="PREDICTION_CLOSED",
                message="Predictions are not open for this trading day.",
                details={
                    "trading_day": trading_day.isoformat(),
                    "code": "PREDICTION_CLOSED",
                },
            )

        # Use server-managed trading day
        trading_day = session.trading_day
        symbol = payload.symbol.upper()

        # Validate symbol in universe
        if not self.universe_repo.symbol_exists_in_universe(trading_day, symbol):
            raise NotFoundError(
                message=f"Symbol not available for predictions: {symbol}"
            )

        # Check for duplicate
        if self.pred_repo.prediction_exists(user_id, trading_day, symbol):
            raise ConflictError("Prediction already submitted for this symbol")

        # Check and consume slot
        self._check_slots(user_id, trading_day)
        self._consume_slot(user_id, trading_day)

        # Create prediction
        choice = ChoiceEnum(payload.choice.value)
        now = datetime.now(timezone.utc)
        model: Optional[PredictionModel] = None

        try:
            # Get price snapshot
            uni_item = self.universe_repo.get_universe_item_model(trading_day, symbol)
            snap_price = None
            snap_at = None
            price_source = None

            if uni_item:
                snap = ActiveUniverseSnapshot.model_validate(uni_item)
                if snap.current_price is not None:
                    snap_price = snap.current_price
                    snap_at = snap.last_price_updated or now
                    price_source = "universe"

            def _create():
                instance = PredictionModel(
                    user_id=user_id,
                    trading_day=trading_day,
                    symbol=symbol,
                    prediction_type=PredictionTypeEnum.DIRECTION,
                    choice=choice,
                    status=StatusEnum.PENDING,
                    submitted_at=now,
                    points_earned=0,
                    prediction_price=snap_price,
                    prediction_price_at=snap_at,
                    prediction_price_source=price_source,
                )
                self.db.add(instance)
                return instance

            model = self._safe_transaction(_create)
        except Exception as e:
            # Refund slot on error
            self._refund_slot(
                user_id, trading_day, symbol, reason=f"Prediction creation failed: {str(e)}"
            )
            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                error_message=f"Failed to create prediction: {str(e)}",
                prediction_details={"choice": payload.choice.value},
            )
            raise

        # Convert to schema
        created = self.pred_repo._to_schema(model)

        # Trigger cooldown if needed
        self._check_and_trigger_cooldown(user_id, trading_day)

        if not created:
            raise ValidationError("Failed to create prediction")

        return created

    def update_prediction(
        self, user_id: int, prediction_id: int, payload: PredictionUpdate
    ) -> PredictionResponse:
        """Update DIRECTION prediction choice."""
        # Get prediction for ownership verification
        model: Optional[PredictionModel] = (
            self.db.query(PredictionModel)
            .filter(
                PredictionModel.id == prediction_id,
                PredictionModel.prediction_type == PredictionTypeEnum.DIRECTION,
            )
            .first()
        )

        if not model:
            raise NotFoundError("Prediction not found")

        if int(str(model.user_id)) != int(user_id):
            raise BusinessLogicError(
                error_code="FORBIDDEN_PREDICTION",
                message="Cannot modify another user's prediction",
            )

        model_status = cast(StatusEnum, model.status)
        if model_status != StatusEnum.PENDING:
            raise BusinessLogicError(
                error_code="PREDICTION_LOCKED",
                message="Only pending predictions can be updated",
            )

        if getattr(model, "locked_at", None) is not None:
            raise BusinessLogicError(
                error_code="PREDICTION_LOCKED",
                message="Prediction has been locked for settlement",
            )

        new_choice = ChoiceEnum(payload.choice.value)
        updated = self.pred_repo.update_prediction_choice(prediction_id, new_choice)

        if not updated:
            raise ValidationError("Failed to update prediction")

        return updated

    # Query methods
    def get_user_predictions_for_day(
        self, user_id: int, trading_day: date
    ) -> UserPredictionsResponse:
        """Get user's predictions for a trading day."""
        return self.pred_repo.get_user_predictions_for_day(user_id, trading_day)

    def get_predictions_by_symbol_and_date(
        self, symbol: str, trading_day: date, status_filter: Optional[StatusEnum] = None
    ) -> List[PredictionResponse]:
        """Get predictions by symbol and date."""
        return self.pred_repo.get_predictions_by_symbol_and_date(
            symbol=symbol.upper(),
            trading_day=trading_day,
            status_filter=status_filter or StatusEnum.PENDING,
        )

    def get_prediction_stats(self, trading_day: date) -> PredictionStats:
        """Get prediction statistics."""
        return self.pred_repo.get_prediction_stats(trading_day)

    def get_user_prediction_summary(
        self, user_id: int, trading_day: date
    ) -> PredictionSummary:
        """Get user's prediction summary."""
        return self.pred_repo.get_user_prediction_summary(user_id, trading_day)

    def get_user_prediction_history(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> List[PredictionResponse]:
        """Get user's prediction history."""
        return self.pred_repo.get_user_prediction_history(
            user_id, limit=limit, offset=offset
        )

    def get_user_prediction_history_by_month(
        self, user_id: int, month: str
    ) -> PredictHistoryMonth:
        """Get user's prediction history for a month."""
        normalized = month.replace("-", "")
        if not normalized.isdigit() or len(normalized) not in (6, 8):
            raise ValueError(
                "월 파라미터는 YYYYMM, YYYYMMDD 또는 YYYY-MM-DD 형식이어야 합니다."
            )

        year = int(normalized[:4])
        month_int = int(normalized[4:6])
        if month_int < 1 or month_int > 12:
            raise ValueError(
                "월 파라미터는 YYYYMM, YYYYMMDD 또는 YYYY-MM-DD 형식이어야 합니다."
            )

        last_day = monthrange(year, month_int)[1]
        month_start = date(year, month_int, 1)
        month_end = date(year, month_int, last_day)

        history = self.pred_repo.get_user_prediction_history_by_month(
            user_id, month_start, month_end
        )

        total_points = sum(pred.points_earned or 0 for pred in history)
        total_correct = sum(
            1 for pred in history if pred.status == PredictionStatus.CORRECT
        )
        total_incorrect = sum(
            1 for pred in history if pred.status == PredictionStatus.INCORRECT
        )
        total_predictions = len(history)
        total_pending = sum(
            1 for pred in history if pred.status == PredictionStatus.PENDING
        )

        return PredictHistoryMonth(
            month=f"{year:04d}{month_int:02d}",
            total_points=total_points,
            total_correct=total_correct,
            total_incorrect=total_incorrect,
            total_predictions=total_predictions,
            total_pending=total_pending,
        )

    def get_user_prediction_history_paginated(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> Tuple[List[PredictionResponse], int, bool]:
        """Get user's prediction history with pagination."""
        if limit > 100:
            limit = 100

        predictions = self.pred_repo.get_user_prediction_history(
            user_id, limit=limit + 1, offset=offset
        )

        has_next = len(predictions) > limit
        if has_next:
            predictions = predictions[:limit]

        total_count = self.pred_repo.count_user_predictions(user_id)

        return predictions, total_count, has_next

    # Settlement methods
    def lock_predictions_for_settlement(self, trading_day: date) -> int:
        """Lock predictions for settlement."""
        return self.pred_repo.lock_predictions_for_settlement(trading_day)

    def bulk_update_predictions_status(
        self,
        trading_day: date,
        symbol: str,
        correct_choice: PredictionChoice,
        points_per_correct: int = 10,
    ) -> Tuple[int, int]:
        """Bulk update prediction status for settlement."""
        return self.pred_repo.bulk_update_predictions_status(
            trading_day=trading_day,
            symbol=symbol.upper(),
            correct_choice=ChoiceEnum(correct_choice.value),
            points_per_correct=points_per_correct,
        )

    def get_pending_predictions_for_settlement(
        self, trading_day: date
    ) -> List[PredictionResponse]:
        """Get pending predictions for settlement."""
        return self.pred_repo.get_pending_predictions_for_settlement(trading_day)

    # Trends
    def get_prediction_trends(
        self, trading_day: date, limit: int = 5
    ) -> PredictionTrendsResponse:
        """Get prediction trends (most long/short predicted symbols)."""
        limit = max(1, min(limit, 10))

        # Get most long predictions
        long_data = self.pred_repo.get_most_long_predictions(trading_day, limit)

        # Get most short predictions
        short_data = self.pred_repo.get_most_short_predictions(trading_day, limit)

        # Get price info
        all_tickers = set(
            [ticker for ticker, _, _, _ in long_data]
            + [ticker for ticker, _, _, _ in short_data]
        )

        price_map = {}
        for ticker in all_tickers:
            try:
                price_data = self.price_repo.get_eod_price(ticker, trading_day)
                if price_data:
                    price_map[ticker] = {
                        "last_price": price_data.close_price,
                        "change_percent": price_data.change_percent,
                    }
            except Exception:
                pass

        # Get company names
        company_name_map = {}
        for ticker in all_tickers:
            try:
                universe_item_model = self.universe_repo.get_universe_item_model(
                    trading_day, ticker
                )
                if universe_item_model and hasattr(universe_item_model, "company_name"):
                    company_name_map[ticker] = universe_item_model.company_name
            except Exception:
                pass

        # Build response items
        most_long_items = []
        for ticker, count, win_rate, avg_profit in long_data:
            price_info = price_map.get(ticker, {})
            most_long_items.append(
                MostLongPredictionItem(
                    ticker=ticker,
                    company_name=company_name_map.get(ticker),
                    count=count,
                    win_rate=win_rate,
                    avg_profit=avg_profit,
                    last_price=price_info.get("last_price"),
                    change_percent=(
                        price_info.get("change_percent")
                        if price_info.get("change_percent") is not None
                        else None
                    ),
                )
            )

        most_short_items = []
        for ticker, count, win_rate, avg_profit in short_data:
            price_info = price_map.get(ticker, {})
            most_short_items.append(
                MostShortPredictionItem(
                    ticker=ticker,
                    company_name=company_name_map.get(ticker),
                    count=count,
                    win_rate=win_rate,
                    avg_profit=avg_profit,
                    last_price=price_info.get("last_price"),
                    change_percent=(
                        price_info.get("change_percent")
                        if price_info.get("change_percent") is not None
                        else None
                    ),
                )
            )

        return PredictionTrendsResponse(
            most_long_predictions=most_long_items,
            most_short_predictions=most_short_items,
            updated_at=datetime.now(timezone.utc),
        )

    # Slot management (exposed methods)
    def get_remaining_predictions(self, user_id: int, trading_day: date) -> int:
        """Get remaining prediction slots."""
        return self.stats_repo.get_remaining_predictions(user_id, trading_day)

    async def increase_max_predictions(
        self, user_id: int, trading_day: date, additional_slots: int = 1
    ) -> None:
        """Increase max prediction slots."""
        if additional_slots <= 0:
            raise ValidationError("additional_slots must be positive")
        await self.stats_repo.increase_max_predictions(
            user_id, trading_day, additional_slots
        )

