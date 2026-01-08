"""Direction prediction repository - handles UP/DOWN predictions."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import and_, asc, case, desc, func, Numeric
from sqlalchemy.orm import Session

from myapi.config import settings
from myapi.models.prediction import (
    ChoiceEnum,
    Prediction as PredictionModel,
    PredictionTypeEnum,
    StatusEnum,
)
from myapi.models.ticker_reference import TickerReference
from myapi.repositories.base_prediction_repository import BasePredictionRepository
from myapi.schemas.prediction import (
    PredictionResponse,
    PredictionStats,
    PredictionStatus,
    PredictionSummary,
    UserPredictionsResponse,
)


class DirectionPredictionRepository(BasePredictionRepository[PredictionResponse]):
    """Repository for DIRECTION type predictions (UP/DOWN)."""

    def __init__(self, db: Session):
        super().__init__(
            schema_class=PredictionResponse,
            db=db,
            prediction_type=PredictionTypeEnum.DIRECTION,
        )

    def create_prediction(
        self,
        user_id: int,
        trading_day: date,
        symbol: str,
        choice: ChoiceEnum,
        submitted_at: datetime,
    ) -> Optional[PredictionResponse]:
        """Create new DIRECTION prediction."""
        submitted_at = datetime.now(timezone.utc)

        return self.create(
            user_id=user_id,
            trading_day=trading_day,
            symbol=symbol,
            prediction_type=PredictionTypeEnum.DIRECTION,
            choice=choice,
            status=StatusEnum.PENDING,
            submitted_at=submitted_at,
            points_earned=0,
        )

    def update_prediction_choice(
        self, prediction_id: int, new_choice: ChoiceEnum
    ) -> Optional[PredictionResponse]:
        """Update prediction choice (only allowed within modification window)."""
        return self.update(
            prediction_id, choice=new_choice, updated_at=datetime.now(timezone.utc)
        )

    def get_user_predictions_for_day(
        self, user_id: int, trading_day: date
    ) -> UserPredictionsResponse:
        """Get user's predictions for a specific trading day."""
        self._ensure_clean_session()
        model_instances = (
            self._filter_by_type(
                self.model_class.user_id == user_id,
                self.model_class.trading_day == trading_day,
            )
            .order_by(asc(self.model_class.submitted_at))
            .all()
        )

        predictions = [
            p
            for p in (self._to_schema(instance) for instance in model_instances)
            if p is not None
        ]

        total_predictions = len(predictions)
        completed_predictions = sum(
            1 for p in predictions if p.status != PredictionStatus.PENDING
        )
        pending_predictions = total_predictions - completed_predictions

        return UserPredictionsResponse(
            trading_day=trading_day,
            predictions=predictions,
            total_predictions=total_predictions,
            completed_predictions=completed_predictions,
            pending_predictions=pending_predictions,
        )

    def get_predictions_by_symbol_and_date(
        self, symbol: str, trading_day: date, status_filter: Optional[StatusEnum] = None
    ) -> List[PredictionResponse]:
        """Get all predictions for a symbol and date."""
        self._ensure_clean_session()
        filters = [
            self.model_class.symbol == symbol,
            self.model_class.trading_day == trading_day,
        ]

        if status_filter:
            filters.append(self.model_class.status == status_filter)

        model_instances = (
            self._filter_by_type(*filters)
            .order_by(asc(self.model_class.submitted_at))
            .all()
        )

        return [
            p
            for p in (self._to_schema(instance) for instance in model_instances)
            if p is not None
        ]

    def prediction_exists(self, user_id: int, trading_day: date, symbol: str) -> bool:
        """Check if DIRECTION prediction exists for user/day/symbol."""
        return super().prediction_exists(user_id, trading_day, symbol=symbol)

    def lock_predictions_for_settlement(self, trading_day: date) -> int:
        """Lock predictions for settlement (make them immutable)."""
        self._ensure_clean_session()
        locked_count = (
            self._filter_by_type(
                self.model_class.trading_day == trading_day,
                self.model_class.status == StatusEnum.PENDING,
                self.model_class.locked_at.is_(None),
            )
            .update(
                {"locked_at": datetime.now(timezone.utc)}, synchronize_session=False
            )
        )

        self.db.commit()
        return locked_count

    def update_prediction_status(
        self,
        prediction_id: int,
        status: StatusEnum,
        points_earned: int = 0,
        settlement_price: Optional[Decimal] = None,
        *,
        commit: bool = True,
    ) -> Optional[PredictionResponse]:
        """Update prediction status and points earned."""
        updates = {
            "status": status,
            "points_earned": points_earned,
            "updated_at": datetime.now(timezone.utc),
        }
        if settlement_price is not None:
            updates["settlement_price"] = settlement_price

        return self.update(prediction_id, commit=commit, **updates)

    def bulk_update_predictions_status(
        self,
        trading_day: date,
        symbol: str,
        correct_choice: ChoiceEnum,
        points_per_correct: int = 10,
        settlement_price: Optional[Decimal] = None,
    ) -> Tuple[int, int]:
        """Bulk update predictions status for settlement."""
        self._ensure_clean_session()
        correct_updates = {
            PredictionModel.status: StatusEnum.CORRECT,
            PredictionModel.points_earned: points_per_correct,
            PredictionModel.updated_at: datetime.now(timezone.utc),
        }
        incorrect_updates = {
            PredictionModel.status: StatusEnum.INCORRECT,
            PredictionModel.points_earned: 0,
            PredictionModel.updated_at: datetime.now(timezone.utc),
        }
        if settlement_price is not None:
            correct_updates[PredictionModel.settlement_price] = settlement_price
            incorrect_updates[PredictionModel.settlement_price] = settlement_price

        # Update correct predictions
        correct_count = (
            self._filter_by_type(
                self.model_class.trading_day == trading_day,
                self.model_class.symbol == symbol,
                self.model_class.choice == correct_choice,
                self.model_class.status == StatusEnum.PENDING,
            )
            .update(correct_updates, synchronize_session=False)
        )

        # Update incorrect predictions
        incorrect_count = (
            self._filter_by_type(
                self.model_class.trading_day == trading_day,
                self.model_class.symbol == symbol,
                self.model_class.choice != correct_choice,
                self.model_class.status == StatusEnum.PENDING,
            )
            .update(incorrect_updates, synchronize_session=False)
        )

        self.db.flush()
        self.db.commit()
        return correct_count, incorrect_count

    def get_prediction_stats(self, trading_day: date) -> PredictionStats:
        """Get prediction statistics for a trading day."""
        self._ensure_clean_session()
        stats = (
            self.db.query(
                func.count(self.model_class.id).label("total"),
                func.sum(
                    func.case([(self.model_class.choice == ChoiceEnum.UP, 1)], else_=0)
                ).label("up_count"),
                func.sum(
                    func.case(
                        [(self.model_class.choice == ChoiceEnum.DOWN, 1)], else_=0
                    )
                ).label("down_count"),
                func.sum(
                    func.case(
                        [(self.model_class.status == StatusEnum.CORRECT, 1)], else_=0
                    )
                ).label("correct_count"),
                func.sum(self.model_class.points_earned).label("total_points"),
            )
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.prediction_type == PredictionTypeEnum.DIRECTION,
                )
            )
            .first()
        )

        if not stats:
            return PredictionStats(
                trading_day=trading_day,
                total_predictions=0,
                up_predictions=0,
                down_predictions=0,
                correct_predictions=0,
                accuracy_rate=0.0,
                points_distributed=0,
            )

        total = stats.total or 0
        up_count = stats.up_count or 0
        down_count = stats.down_count or 0
        correct_count = stats.correct_count or 0
        total_points = stats.total_points or 0

        accuracy_rate = (correct_count / total * 100) if total > 0 else 0.0

        return PredictionStats(
            trading_day=trading_day,
            total_predictions=total,
            up_predictions=up_count,
            down_predictions=down_count,
            correct_predictions=correct_count,
            accuracy_rate=accuracy_rate,
            points_distributed=total_points,
        )

    def get_user_prediction_summary(
        self, user_id: int, trading_day: date
    ) -> PredictionSummary:
        """Get user's prediction summary for a trading day."""
        self._ensure_clean_session()
        stats = (
            self.db.query(
                func.count(self.model_class.id).label("total"),
                func.sum(
                    func.case(
                        [(self.model_class.status == StatusEnum.CORRECT, 1)], else_=0
                    )
                ).label("correct"),
                func.sum(
                    func.case(
                        [(self.model_class.status == StatusEnum.INCORRECT, 1)], else_=0
                    )
                ).label("incorrect"),
                func.sum(
                    func.case(
                        [(self.model_class.status == StatusEnum.PENDING, 1)], else_=0
                    )
                ).label("pending"),
                func.sum(self.model_class.points_earned).label("total_points"),
            )
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                    self.model_class.prediction_type == PredictionTypeEnum.DIRECTION,
                )
            )
            .first()
        )

        if not stats:
            return PredictionSummary(
                user_id=user_id,
                trading_day=trading_day,
                total_submitted=0,
                correct_count=0,
                incorrect_count=0,
                pending_count=0,
                accuracy_rate=0.0,
                total_points_earned=0,
            )

        total = stats.total or 0
        correct = stats.correct or 0
        incorrect = stats.incorrect or 0
        pending = stats.pending or 0
        total_points = stats.total_points or 0

        accuracy_rate = (
            (correct / (correct + incorrect) * 100)
            if (correct + incorrect) > 0
            else 0.0
        )

        return PredictionSummary(
            user_id=user_id,
            trading_day=trading_day,
            total_submitted=total,
            correct_count=correct,
            incorrect_count=incorrect,
            pending_count=pending,
            accuracy_rate=accuracy_rate,
            total_points_earned=total_points,
        )

    def get_pending_predictions_for_settlement(
        self, trading_day: date
    ) -> List[PredictionResponse]:
        """Get pending predictions for settlement."""
        model_instances = (
            self._filter_by_type(
                self.model_class.trading_day == trading_day,
                self.model_class.status == StatusEnum.PENDING,
            )
            .order_by(asc(self.model_class.symbol), asc(self.model_class.submitted_at))
            .all()
        )
        return [
            p
            for p in (self._to_schema(instance) for instance in model_instances)
            if p is not None
        ]

    def cancel_prediction(
        self, prediction_id: int, *, commit: bool = True
    ) -> Optional[PredictionResponse]:
        """Cancel prediction."""
        return self.update_prediction_status(
            prediction_id, StatusEnum.CANCELLED, commit=commit
        )

    def get_user_prediction_history_by_month(
        self, user_id: int, month_start: date, month_end: date
    ) -> List[PredictionResponse]:
        """Get user's prediction history for a month."""
        model_instances = (
            self.db.query(self.model_class)
            .filter(
                self.model_class.user_id == user_id,
                self.model_class.trading_day >= month_start,
                self.model_class.trading_day <= month_end,
                self.model_class.prediction_type == PredictionTypeEnum.DIRECTION,
            )
            .order_by(
                desc(self.model_class.trading_day),
                desc(self.model_class.submitted_at),
            )
            .all()
        )

        return [
            p
            for p in (self._to_schema(instance) for instance in model_instances)
            if p is not None
        ]

    def get_user_prediction_history(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> List[PredictionResponse]:
        """Get user's prediction history (latest first)."""

        model_instances = (
            self.db.query(
                self.model_class,
                TickerReference.name,
                TickerReference.market_category,
                TickerReference.is_etf,
                TickerReference.exchange,
            )
            .join(TickerReference, TickerReference.symbol == self.model_class.symbol)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.prediction_type == PredictionTypeEnum.DIRECTION,
                )
            )
            .order_by(
                desc(self.model_class.trading_day), desc(self.model_class.submitted_at)
            )
            .limit(limit)
            .offset(offset)
            .all()
        )

        response_list = []
        for prediction, name, market_category, is_etf, exchange in model_instances:
            predict = self._to_schema(prediction)
            if predict is None:
                continue

            pred_dict = predict.model_dump()
            pred_dict.update(
                {
                    "ticker_name": name,
                    "ticker_market_category": market_category,
                    "ticker_is_etf": is_etf,
                    "ticker_exchange": exchange,
                }
            )
            response_list.append(PredictionResponse(**pred_dict))

        return response_list

    def count_predictions_by_date(self, trading_day: date) -> int:
        """Count total predictions for a trading day."""
        return (
            self._filter_by_type(
                self.model_class.trading_day == trading_day,
            )
            .count()
        )

    def count_predictions_by_date_and_status(
        self, trading_day: date, status: StatusEnum
    ) -> int:
        """Count predictions by date and status."""
        return (
            self._filter_by_type(
                self.model_class.trading_day == trading_day,
                self.model_class.status == status,
            )
            .count()
        )

    def count_user_predictions(self, user_id: int) -> int:
        """Count user's total predictions."""
        return (
            self._filter_by_type(
                self.model_class.user_id == user_id,
            )
            .count()
        )

    def get_most_long_predictions(
        self, trading_day: date, limit: int = 5
    ) -> List[Tuple[str, int, Optional[float], Optional[float]]]:
        """
        Get TOP N symbols with most UP predictions.
        
        Returns:
            List[Tuple[ticker, count, win_rate, avg_profit]]
        """
        self._ensure_clean_session()

        long_stats = (
            self.db.query(
                self.model_class.symbol.label("ticker"),
                func.count(self.model_class.id).label("prediction_count"),
                func.cast(
                    func.sum(
                        case(
                            (self.model_class.status == StatusEnum.CORRECT, 1),
                            else_=0,
                        )
                    )
                    * 100.0
                    / func.nullif(
                        func.sum(
                            case(
                                (
                                    self.model_class.status.in_(
                                        [StatusEnum.CORRECT, StatusEnum.INCORRECT]
                                    ),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    Numeric(10, 2),
                ).label("win_rate"),
                func.cast(
                    func.avg(
                        case(
                            (
                                self.model_class.status.in_(
                                    [StatusEnum.CORRECT, StatusEnum.INCORRECT]
                                ),
                                self.model_class.points_earned,
                            ),
                            else_=None,
                        )
                    ),
                    Numeric(10, 2),
                ).label("avg_profit"),
            )
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.choice == ChoiceEnum.UP,
                    self.model_class.prediction_type == PredictionTypeEnum.DIRECTION,
                )
            )
            .group_by(self.model_class.symbol)
            .order_by(desc("prediction_count"))
            .limit(limit)
            .all()
        )

        return [
            (
                str(row.ticker),
                int(row.prediction_count),
                float(row.win_rate) if row.win_rate is not None else None,
                float(row.avg_profit) if row.avg_profit is not None else None,
            )
            for row in long_stats
        ]

    def get_most_short_predictions(
        self, trading_day: date, limit: int = 5
    ) -> List[Tuple[str, int, Optional[float], Optional[float]]]:
        """
        Get TOP N symbols with most DOWN predictions.
        
        Returns:
            List[Tuple[ticker, count, win_rate, avg_profit]]
        """
        self._ensure_clean_session()

        short_stats = (
            self.db.query(
                self.model_class.symbol.label("ticker"),
                func.count(self.model_class.id).label("prediction_count"),
                func.cast(
                    func.sum(
                        case(
                            (self.model_class.status == StatusEnum.CORRECT, 1),
                            else_=0,
                        )
                    )
                    * 100.0
                    / func.nullif(
                        func.sum(
                            case(
                                (
                                    self.model_class.status.in_(
                                        [StatusEnum.CORRECT, StatusEnum.INCORRECT]
                                    ),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    Numeric(10, 2),
                ).label("win_rate"),
                func.cast(
                    func.avg(
                        case(
                            (
                                self.model_class.status.in_(
                                    [StatusEnum.CORRECT, StatusEnum.INCORRECT]
                                ),
                                self.model_class.points_earned,
                            ),
                            else_=None,
                        )
                    ),
                    Numeric(10, 2),
                ).label("avg_profit"),
            )
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.choice == ChoiceEnum.DOWN,
                    self.model_class.prediction_type == PredictionTypeEnum.DIRECTION,
                )
            )
            .group_by(self.model_class.symbol)
            .order_by(desc("prediction_count"))
            .limit(limit)
            .all()
        )

        return [
            (
                str(row.ticker),
                int(row.prediction_count),
                float(row.win_rate) if row.win_rate is not None else None,
                float(row.avg_profit) if row.avg_profit is not None else None,
            )
            for row in short_stats
        ]

