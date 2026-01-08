"""Base service for prediction operations with common business logic."""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from myapi.config import Settings
from myapi.core.exceptions import RateLimitError
from myapi.repositories.prediction_repository import UserDailyStatsRepository
from myapi.services.cooldown_service import CooldownService
from myapi.services.error_log_service import ErrorLogService


class BasePredictionService:
    """
    Base service for prediction operations.
    
    Provides common business logic for:
    - Slot management (check, consume, refund)
    - Cooldown triggering
    - Error logging
    
    Subclasses (DirectionPredictionService, RangePredictionService) inherit this.
    """

    def __init__(self, db: Session, settings: Settings):
        """
        Initialize base prediction service.
        
        Args:
            db: Database session
            settings: Application settings
        """
        self.db = db
        self.settings = settings
        self.stats_repo = UserDailyStatsRepository(db)
        self.error_log_service = ErrorLogService(db)

    def _check_slots(self, user_id: int, trading_day: date) -> None:
        """
        Check if user has available prediction slots.
        
        Args:
            user_id: User ID
            trading_day: Trading day
            
        Raises:
            RateLimitError: If no slots available
        """
        if not self.stats_repo.can_make_prediction(user_id, trading_day):
            remaining = self.stats_repo.get_remaining_predictions(user_id, trading_day)
            raise RateLimitError(
                message="Daily prediction limit reached",
                details={"remaining": remaining},
            )

    def _consume_slot(self, user_id: int, trading_day: date) -> None:
        """
        Consume one prediction slot atomically.
        
        Args:
            user_id: User ID
            trading_day: Trading day
            
        Raises:
            RateLimitError: If slot consumption fails (race condition)
        """
        stats_before = self.stats_repo.get_or_create_user_daily_stats(
            user_id, trading_day
        )

        if stats_before.available_predictions <= 0:
            raise RateLimitError(
                message="Daily prediction limit reached",
                details={"remaining": 0},
            )

        stats_after = self.stats_repo.consume_available_prediction(
            user_id, trading_day, amount=1
        )

        # Verify slot was actually consumed
        if stats_after.available_predictions != max(
            0, stats_before.available_predictions - 1
        ):
            remaining = self.stats_repo.get_remaining_predictions(user_id, trading_day)
            raise RateLimitError(
                message="Daily prediction limit reached",
                details={"remaining": remaining},
            )

    def _refund_slot(
        self, user_id: int, trading_day: date, symbol: str, reason: str = ""
    ) -> None:
        """
        Refund prediction slot on error.
        
        Args:
            user_id: User ID
            trading_day: Trading day
            symbol: Symbol being predicted
            reason: Reason for refund (for logging)
        """
        try:
            self.stats_repo.refund_prediction(user_id, trading_day, amount=1)
        except Exception as exc:
            # Log refund failure but don't raise
            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                error_message=f"Slot refund failed: {str(exc)}. Reason: {reason}",
                prediction_details=None,
            )

    def _check_and_trigger_cooldown(self, user_id: int, trading_day: date) -> None:
        """
        Check if cooldown should be triggered and start it if needed.
        
        Cooldown is triggered when available slots fall below threshold.
        
        Args:
            user_id: User ID
            trading_day: Trading day
        """
        try:
            stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
            available_slots = max(0, stats.available_predictions)

            # Trigger cooldown if below threshold and no active cooldown
            if available_slots < self.settings.COOLDOWN_TRIGGER_THRESHOLD:
                cooldown_service = CooldownService(self.db, self.settings)
                active = cooldown_service.cooldown_repo.get_active_timer(
                    user_id, trading_day
                )
                if not active:
                    cooldown_service.start_auto_cooldown_sync(user_id, trading_day)
        except Exception as exc:
            # Log cooldown failure but don't raise (non-critical)
            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol="",
                error_message=f"Cooldown trigger failed: {str(exc)}",
                prediction_details=None,
            )

    def should_cancel_cooldown(self, available_slots: int) -> bool:
        """
        Check if cooldown should be canceled.
        
        Cooldown is only needed when slots are below threshold.
        
        Args:
            available_slots: Current available slots
            
        Returns:
            True if cooldown should be canceled
        """
        return available_slots >= self.settings.COOLDOWN_TRIGGER_THRESHOLD

