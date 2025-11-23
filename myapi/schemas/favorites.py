"""
Favorites Schemas

Pydantic models for user favorites/watchlist API responses and requests.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional


class FavoriteBase(BaseModel):
    """Base schema for favorite"""
    user_id: int
    symbol: str


class FavoriteTickerInfo(BaseModel):
    """
    Favorite ticker with detailed information.
    Used in list responses with ticker metadata.
    """
    symbol: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., description="Company/ticker name")
    market_category: Optional[str] = Field(None, description="Market category")
    is_etf: bool = Field(False, description="Whether this is an ETF")
    added_at: datetime = Field(..., description="When user added to favorites")

    class Config:
        from_attributes = True


class AddFavoriteRequest(BaseModel):
    """Request body for adding a favorite (optional, can use path param instead)"""
    symbol: str = Field(..., description="Ticker symbol to add to favorites")


class UserFavoritesResponse(BaseModel):
    """Response containing user's list of favorites"""
    user_id: int
    favorites: List[FavoriteTickerInfo]
    total_count: int

    class Config:
        from_attributes = True


class FavoriteCheckResponse(BaseModel):
    """Response for checking if a symbol is favorited"""
    symbol: str
    is_favorited: bool

    class Config:
        from_attributes = True


class FavoriteSchema(BaseModel):
    """
    Basic favorite schema matching database model.
    Used for repository layer conversions.
    """
    user_id: int
    symbol: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
