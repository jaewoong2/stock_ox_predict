"""Range prediction repository - handles price range predictions."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from myapi.models.prediction import PredictionTypeEnum, StatusEnum
from myapi.repositories.base_prediction_repository import BasePredictionRepository
from myapi.schemas.range_prediction import (
    RangePredictionListResponse,
    RangePredictionResponse,
)


class RangePredictionRepository(BasePredictionRepository[RangePredictionResponse]):
    """Repository for RANGE type predictions (price_low/price_high)."""

    def __init__(self, db: Session):
        super().__init__(
            schema_class=RangePredictionResponse,
            db=db,
            prediction_type=PredictionTypeEnum.RANGE,
        )

    def prediction_exists(self, user_id: int, target_open_time_ms: int) -> bool:
        """Check if RANGE prediction exists for user and time window."""
        return super().prediction_exists(
            user_id,
            trading_day=date.min,  # Not used for RANGE (uses target_open_time_ms)
            target_open_time_ms=target_open_time_ms,
        )

    def get_existing_prediction(
        self, user_id: int, target_open_time_ms: int
    ) -> Optional[RangePredictionResponse]:
        """
        Get existing RANGE prediction for user and time window.

        Args:
            user_id: User ID
            target_open_time_ms: Target candle open time in milliseconds

        Returns:
            Existing prediction or None
        """
        self._ensure_clean_session()
        instance = self._filter_by_type(
            self.model_class.user_id == user_id,
            self.model_class.target_open_time_ms == target_open_time_ms,
        ).first()
        return self._to_schema(instance)

    def create_prediction(
        self,
        *,
        user_id: int,
        trading_day: date,
        symbol: str,
        price_low: Decimal,
        price_high: Decimal,
        target_open_time_ms: int,
        target_close_time_ms: int,
        submitted_at: datetime,
    ) -> Optional[RangePredictionResponse]:
        """Create new RANGE prediction."""
        return self.create(
            user_id=user_id,
            trading_day=trading_day,
            symbol=symbol,
            prediction_type=PredictionTypeEnum.RANGE,
            status=StatusEnum.PENDING,
            price_low=price_low,
            price_high=price_high,
            target_open_time_ms=target_open_time_ms,
            target_close_time_ms=target_close_time_ms,
            submitted_at=submitted_at,
            points_earned=0,
        )

    def update_existing_prediction(
        self,
        prediction_id: int,
        *,
        price_low: Decimal,
        price_high: Decimal,
        submitted_at: datetime,
    ) -> Optional[RangePredictionResponse]:
        """
        Update existing RANGE prediction (when duplicate detected).

        Only updates if prediction is still PENDING and not locked.

        Args:
            prediction_id: Prediction ID
            price_low: New lower bound
            price_high: New upper bound
            submitted_at: New submission time

        Returns:
            Updated prediction or None if not updatable
        """
        self._ensure_clean_session()
        instance = self._filter_by_type(
            self.model_class.id == prediction_id,
            self.model_class.status == StatusEnum.PENDING,
            self.model_class.locked_at.is_(None),
        ).first()

        if not instance:
            return None

        instance.price_low = price_low
        instance.price_high = price_high
        instance.submitted_at = submitted_at
        instance.updated_at = datetime.now(timezone.utc)

        try:
            self.db.flush()
            self.db.refresh(instance)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return self._to_schema(instance)

    def update_range_bounds(
        self,
        prediction_id: int,
        price_low: Optional[Decimal] = None,
        price_high: Optional[Decimal] = None,
    ) -> Optional[RangePredictionResponse]:
        """
        Update RANGE prediction bounds.
        
        Only allowed for PENDING predictions that are not locked.
        Similar to DirectionPredictionRepository.update_prediction_choice.
        
        Args:
            prediction_id: Prediction ID
            price_low: New lower bound (optional)
            price_high: New upper bound (optional)
            
        Returns:
            Updated prediction or None if not found
        """
        updates = {"updated_at": datetime.now(timezone.utc)}

        if price_low is not None:
            updates["price_low"] = price_low
        if price_high is not None:
            updates["price_high"] = price_high

        return self.update(prediction_id, **updates)

    def list_user_predictions(
        self,
        user_id: int,
        symbol: Optional[str],
        *,
        limit: int,
        offset: int,
    ) -> RangePredictionListResponse:
        """List user's RANGE predictions (latest first)."""
        self._ensure_clean_session()

        filters = [self.model_class.user_id == user_id]
        if symbol:
            filters.append(self.model_class.symbol == symbol)

        query = self._filter_by_type(*filters).order_by(
            desc(self.model_class.submitted_at)
        )

        total_count = query.count()
        items = query.limit(limit + 1).offset(offset).all()

        schemas: List[RangePredictionResponse] = [
            schema for schema in (self._to_schema(item) for item in items) if schema
        ]
        has_next = len(schemas) > limit
        predictions = schemas[:limit]

        return RangePredictionListResponse(
            predictions=predictions,
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_next=has_next,
        )

    def get_pending_for_settlement(
        self, *, now_ms: int, limit: int = 200
    ) -> List[RangePredictionResponse]:
        """Get pending RANGE predictions ready for settlement."""
        self._ensure_clean_session()
        items = (
            self._filter_by_type(
                self.model_class.status == StatusEnum.PENDING,
                self.model_class.target_open_time_ms <= now_ms,
            )
            .order_by(self.model_class.target_open_time_ms)
            .limit(limit)
            .all()
        )
        return [schema for schema in (self._to_schema(item) for item in items) if schema]

    def update_status(
        self,
        prediction_id: int,
        status: StatusEnum,
        *,
        settlement_price: Decimal,
        points_earned: int,
    ) -> Optional[RangePredictionResponse]:
        """Update RANGE prediction status (for settlement)."""
        self._ensure_clean_session()
        instance = self._filter_by_type(self.model_class.id == prediction_id).first()

        if not instance:
            return None

        instance.status = status
        instance.settlement_price = settlement_price
        instance.points_earned = points_earned
        instance.updated_at = datetime.now(timezone.utc)

        try:
            self.db.flush()
            self.db.refresh(instance)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return self._to_schema(instance)

