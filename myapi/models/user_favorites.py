"""
User Favorites Model

Junction table for many-to-many relationship between users and tickers.
Allows users to create a watchlist of favorite stocks.
"""

from sqlalchemy import Column, BigInteger, String, ForeignKey
from sqlalchemy.schema import PrimaryKeyConstraint
from myapi.models.base import BaseModel


class UserFavorite(BaseModel):
    """
    User's favorite tickers/stocks.

    Composite primary key ensures:
    - One user can have many favorite tickers
    - One ticker can be favorited by many users
    - No duplicate favorites per user
    """

    __tablename__ = "user_favorites"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "symbol", name="pk_user_favorites"),
        {"schema": "crypto"},
    )

    user_id = Column(
        BigInteger,
        ForeignKey("crypto.users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to user who favorited the ticker",
    )

    symbol = Column(
        String,
        ForeignKey("crypto.tickers_reference.symbol", ondelete="CASCADE"),
        nullable=False,
        comment="Stock ticker symbol (e.g., AAPL, GOOGL)",
    )

    # created_at, updated_at inherited from BaseModel's TimestampMixin
