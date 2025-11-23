"""
Favorites Service

Business logic layer for user favorites/watchlist.
Validates ticker symbols and manages favorites operations.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
import logging

from myapi.repositories.favorites_repository import FavoritesRepository
from myapi.schemas.favorites import (
    FavoriteTickerInfo,
    UserFavoritesResponse,
    FavoriteCheckResponse,
)
from myapi.core.exceptions import (
    ValidationError,
    NotFoundError,
    ConflictError,
)
from myapi.models.ticker_reference import TickerReference

logger = logging.getLogger(__name__)


class FavoritesService:
    """
    Service layer for favorites management.

    Handles:
    - Ticker symbol validation
    - Duplicate favorite prevention
    - Business logic for favorites operations
    """

    def __init__(self, db: Session):
        self.db = db
        self.favorites_repo = FavoritesRepository(db)

    def _validate_ticker_exists(self, symbol: str) -> None:
        """
        Validate that a ticker symbol exists in the reference table.

        Args:
            symbol: Ticker symbol to validate

        Raises:
            NotFoundError: If ticker symbol doesn't exist
        """
        ticker = (
            self.db.query(TickerReference)
            .filter(TickerReference.symbol == symbol)
            .first()
        )

        if not ticker:
            raise NotFoundError(
                f"Ticker symbol '{symbol}' not found in our database",
                details={"symbol": symbol}
            )

    def get_user_favorites(
        self,
        user_id: int,
        limit: Optional[int] = 100,
        offset: Optional[int] = 0
    ) -> UserFavoritesResponse:
        """
        Get all favorites for a user with pagination.

        Args:
            user_id: User ID
            limit: Maximum number of results (default: 100, max: 500)
            offset: Number of results to skip (default: 0)

        Returns:
            UserFavoritesResponse with list of favorites and total count
        """
        # Enforce reasonable limits
        if limit and limit > 500:
            limit = 500

        favorites = self.favorites_repo.get_user_favorites(
            user_id=user_id,
            limit=limit,
            offset=offset
        )

        total_count = self.favorites_repo.get_favorites_count(user_id)

        return UserFavoritesResponse(
            user_id=user_id,
            favorites=favorites,
            total_count=total_count
        )

    def add_favorite(self, user_id: int, symbol: str) -> FavoriteTickerInfo:
        """
        Add a ticker to user's favorites.

        Args:
            user_id: User ID
            symbol: Ticker symbol to add

        Returns:
            FavoriteTickerInfo of the added favorite

        Raises:
            NotFoundError: If ticker symbol doesn't exist
            ConflictError: If ticker is already favorited
        """
        # Normalize symbol to uppercase
        symbol = symbol.upper()

        # Validate ticker exists
        self._validate_ticker_exists(symbol)

        # Check if already favorited
        if self.favorites_repo.is_favorited(user_id, symbol):
            raise ConflictError(
                f"Ticker '{symbol}' is already in your favorites",
                details={"symbol": symbol}
            )

        # Add to favorites
        favorite_schema = self.favorites_repo.add_favorite(user_id, symbol)

        if not favorite_schema:
            raise ValidationError("Failed to add favorite")

        # Get full favorite info with ticker details
        favorites = self.favorites_repo.get_user_favorites(
            user_id=user_id,
            limit=1,
            offset=0
        )

        # Filter to get the one we just added
        for fav in favorites:
            if fav.symbol == symbol:
                return fav

        # Fallback: create basic response (shouldn't reach here)
        ticker = (
            self.db.query(TickerReference)
            .filter(TickerReference.symbol == symbol)
            .first()
        )

        return FavoriteTickerInfo(
            symbol=symbol,
            name=ticker.name if ticker else symbol,
            market_category=ticker.market_category if ticker else None,
            is_etf=ticker.is_etf if ticker else False,
            added_at=favorite_schema.created_at
        )

    def remove_favorite(self, user_id: int, symbol: str) -> bool:
        """
        Remove a ticker from user's favorites.

        Args:
            user_id: User ID
            symbol: Ticker symbol to remove

        Returns:
            True if removed successfully

        Raises:
            NotFoundError: If ticker is not in favorites
        """
        # Normalize symbol to uppercase
        symbol = symbol.upper()

        # Check if favorited
        if not self.favorites_repo.is_favorited(user_id, symbol):
            raise NotFoundError(
                f"Ticker '{symbol}' is not in your favorites",
                details={"symbol": symbol}
            )

        # Remove from favorites
        success = self.favorites_repo.remove_favorite(user_id, symbol)

        if not success:
            raise ValidationError("Failed to remove favorite")

        logger.info(f"User {user_id} removed favorite: {symbol}")
        return True

    def check_favorite(self, user_id: int, symbol: str) -> FavoriteCheckResponse:
        """
        Check if a ticker is in user's favorites.

        Args:
            user_id: User ID
            symbol: Ticker symbol to check

        Returns:
            FavoriteCheckResponse indicating if favorited
        """
        # Normalize symbol to uppercase
        symbol = symbol.upper()

        is_favorited = self.favorites_repo.is_favorited(user_id, symbol)

        return FavoriteCheckResponse(
            symbol=symbol,
            is_favorited=is_favorited
        )

    def get_favorited_symbols(self, user_id: int) -> List[str]:
        """
        Get simple list of favorited symbol strings.

        Args:
            user_id: User ID

        Returns:
            List of symbol strings
        """
        return self.favorites_repo.get_all_favorited_symbols(user_id)
