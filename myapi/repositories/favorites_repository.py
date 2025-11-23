"""
Favorites Repository

CRITICAL: All methods return Pydantic schemas, NEVER SQLAlchemy models.
Follows the strict repository pattern defined in CLAUDE.md.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from myapi.models.user_favorites import UserFavorite
from myapi.models.ticker_reference import TickerReference
from myapi.schemas.favorites import (
    FavoriteSchema,
    FavoriteTickerInfo,
)
from myapi.repositories.base import BaseRepository


class FavoritesRepository(BaseRepository[UserFavorite, FavoriteSchema]):
    """
    Repository for user favorites operations.

    All methods return Pydantic schemas following the repository pattern:
    Database (SQLAlchemy models) → Repository (converts to schemas) → Service/Router
    """

    def __init__(self, db: Session):
        super().__init__(
            model_class=UserFavorite,
            schema_class=FavoriteSchema,
            db=db
        )

    def get_user_favorites(
        self,
        user_id: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[FavoriteTickerInfo]:
        """
        Get all favorites for a user with ticker information.

        Returns: List of FavoriteTickerInfo (Pydantic schema)
        """
        self._ensure_clean_session()

        # Join favorites with ticker reference to get ticker details
        query = (
            self.db.query(
                UserFavorite.symbol,
                UserFavorite.created_at,
                TickerReference.name,
                TickerReference.market_category,
                TickerReference.is_etf,
            )
            .join(
                TickerReference,
                UserFavorite.symbol == TickerReference.symbol
            )
            .filter(UserFavorite.user_id == user_id)
            .order_by(UserFavorite.created_at.desc())
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        results = query.all()

        # Convert query results to Pydantic schemas
        favorites = []
        for row in results:
            favorite = FavoriteTickerInfo(
                symbol=row.symbol,
                name=row.name,
                market_category=row.market_category,
                is_etf=row.is_etf,
                added_at=row.created_at,
            )
            favorites.append(favorite)

        return favorites

    def add_favorite(self, user_id: int, symbol: str) -> Optional[FavoriteSchema]:
        """
        Add a ticker to user's favorites.

        Returns: FavoriteSchema (Pydantic schema) if successful
        """
        self._ensure_clean_session()

        # Check if already exists
        if self.is_favorited(user_id, symbol):
            # Already favorited, return existing
            return self.get_favorite(user_id, symbol)

        # Create new favorite using base class method (returns schema)
        return self.create(user_id=user_id, symbol=symbol, commit=True)

    def remove_favorite(self, user_id: int, symbol: str) -> bool:
        """
        Remove a ticker from user's favorites.

        Returns: True if removed, False if not found
        """
        self._ensure_clean_session()

        favorite = (
            self.db.query(UserFavorite)
            .filter(
                and_(
                    UserFavorite.user_id == user_id,
                    UserFavorite.symbol == symbol
                )
            )
            .first()
        )

        if not favorite:
            return False

        try:
            self.db.delete(favorite)
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def is_favorited(self, user_id: int, symbol: str) -> bool:
        """
        Check if a ticker is in user's favorites.

        Returns: True if favorited, False otherwise
        """
        return self.exists({"user_id": user_id, "symbol": symbol})

    def get_favorite(self, user_id: int, symbol: str) -> Optional[FavoriteSchema]:
        """
        Get a specific favorite record.

        Returns: FavoriteSchema (Pydantic schema) if found
        """
        self._ensure_clean_session()

        favorite = (
            self.db.query(UserFavorite)
            .filter(
                and_(
                    UserFavorite.user_id == user_id,
                    UserFavorite.symbol == symbol
                )
            )
            .first()
        )

        return self._to_schema(favorite)

    def get_favorites_count(self, user_id: int) -> int:
        """
        Get total count of favorites for a user.

        Returns: Count as integer
        """
        return self.count({"user_id": user_id})

    def get_all_favorited_symbols(self, user_id: int) -> List[str]:
        """
        Get list of all favorited symbols for a user (simple list).

        Returns: List of symbol strings
        """
        self._ensure_clean_session()

        results = (
            self.db.query(UserFavorite.symbol)
            .filter(UserFavorite.user_id == user_id)
            .all()
        )

        return [row.symbol for row in results]
