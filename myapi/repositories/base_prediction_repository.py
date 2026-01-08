"""Base repository for prediction-related operations with common query helpers."""

from datetime import date
from typing import Optional, TypeVar, Generic, Type, Any

from sqlalchemy import and_
from sqlalchemy.orm import Session
from pydantic import BaseModel

from myapi.models.prediction import Prediction as PredictionModel, PredictionTypeEnum
from myapi.repositories.base import BaseRepository

SchemaType = TypeVar("SchemaType", bound=BaseModel)


class BasePredictionRepository(
    BaseRepository[PredictionModel, SchemaType], Generic[SchemaType]
):
    """
    Base repository for prediction operations.
    
    Provides common query helpers and type filtering for DIRECTION/RANGE predictions.
    Subclasses should specify their prediction_type in __init__.
    """

    def __init__(
        self,
        schema_class: Type[SchemaType],
        db: Session,
        prediction_type: PredictionTypeEnum,
    ):
        """
        Initialize base prediction repository.
        
        Args:
            schema_class: Pydantic schema class for response
            db: Database session
            prediction_type: Type of prediction (DIRECTION or RANGE)
        """
        super().__init__(PredictionModel, schema_class, db)
        self.prediction_type = prediction_type

    def _build_base_query(self):
        """Build base query with prediction type filter."""
        return self.db.query(self.model_class).filter(
            self.model_class.prediction_type == self.prediction_type
        )

    def _filter_by_type(self, *additional_filters):
        """
        Create a query with prediction type filter and additional filters.
        
        Args:
            *additional_filters: Additional SQLAlchemy filter conditions
            
        Returns:
            Query object with all filters applied
        """
        return self.db.query(self.model_class).filter(
            and_(
                self.model_class.prediction_type == self.prediction_type,
                *additional_filters,
            )
        )

    def get_by_id(self, id: int) -> Optional[SchemaType]:
        """Get prediction by ID (filtered by prediction type)."""
        self._ensure_clean_session()
        model_instance = self._filter_by_type(self.model_class.id == id).first()
        return self._to_schema(model_instance)

    def prediction_exists(
        self, user_id: int, trading_day: date, **kwargs
    ) -> bool:
        """
        Check if prediction exists for user on trading day.
        
        Args:
            user_id: User ID
            trading_day: Trading day
            **kwargs: Additional filters (e.g., symbol, target_open_time_ms)
            
        Returns:
            True if prediction exists
        """
        self._ensure_clean_session()
        filters = [
            self.model_class.user_id == user_id,
            self.model_class.trading_day == trading_day,
        ]

        # Add additional filters from kwargs
        for key, value in kwargs.items():
            if hasattr(self.model_class, key):
                filters.append(getattr(self.model_class, key) == value)

        return self._filter_by_type(*filters).first() is not None

    def get_user_prediction(
        self, user_id: int, prediction_id: int
    ) -> Optional[PredictionModel]:
        """
        Get prediction model for ownership verification.
        
        Returns raw model (not schema) for internal use in services.
        
        Args:
            user_id: User ID
            prediction_id: Prediction ID
            
        Returns:
            PredictionModel instance or None
        """
        self._ensure_clean_session()
        return self._filter_by_type(
            self.model_class.id == prediction_id,
            self.model_class.user_id == user_id,
        ).first()

