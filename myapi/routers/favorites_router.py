"""
Favorites Router

API endpoints for user favorites/watchlist management.
"""

from typing import Any, Optional
from fastapi import APIRouter, Depends, Query
import logging

from myapi.services.favorites_service import FavoritesService
from myapi.core.auth_middleware import get_current_active_user
from myapi.core.exceptions import (
    NotFoundError,
    ValidationError,
    ConflictError,
)
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from dependency_injector.wiring import inject
from myapi.deps import get_favorites_service


router = APIRouter(prefix="/favorites", tags=["favorites"])
logger = logging.getLogger(__name__)


@router.get("", response_model=BaseResponse)
@inject
def get_my_favorites(
    current_user: UserSchema = Depends(get_current_active_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
    limit: Optional[int] = Query(
        100, ge=1, le=500, description="Maximum number of results"
    ),
    offset: Optional[int] = Query(0, ge=0, description="Number of results to skip"),
) -> Any:
    """
    Get current user's favorite tickers.

    Returns paginated list of favorited stocks with ticker details.
    """
    try:
        favorites_response = favorites_service.get_user_favorites(
            user_id=current_user.id, limit=limit, offset=offset
        )

        # Type-safe handling of Optional[int]
        limit_val = limit or 100
        offset_val = offset or 0

        return BaseResponse(
            success=True,
            data=favorites_response.model_dump(),
            meta={
                "limit": limit_val,
                "offset": offset_val,
                "total_count": favorites_response.total_count,
                "has_next": (offset_val + limit_val) < favorites_response.total_count,
            },
        )
    except Exception as e:
        logger.error(f"Error getting favorites for user {current_user.id}: {e}")
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.FAVORITES_LIST_ERROR, message=str(e))
        )


@router.post("/{symbol}", response_model=BaseResponse)
@inject
def add_favorite(
    symbol: str,
    current_user: UserSchema = Depends(get_current_active_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
) -> Any:
    """
    Add a ticker to favorites.

    Args:
        symbol: Stock ticker symbol (e.g., AAPL, GOOGL)
    """
    try:
        favorite_info = favorites_service.add_favorite(
            user_id=current_user.id, symbol=symbol
        )

        logger.info(f"User {current_user.id} added favorite: {symbol}")

        return BaseResponse(
            success=True,
            data=favorite_info.model_dump(),
            meta={"message": f"Successfully added {symbol} to favorites"},
        )
    except NotFoundError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.USER_NOT_FOUND, message=str(e))
        )
    except ConflictError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.USER_ALREADY_EXISTS, message=str(e))
        )
    except ValidationError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.USER_NOT_FOUND, message=str(e))
        )
    except Exception as e:
        logger.error(f"Error adding favorite {symbol} for user {current_user.id}: {e}")
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.FAVORITES_ADD_ERROR, message="Failed to add favorite"),
        )


@router.delete("/{symbol}", response_model=BaseResponse)
@inject
def remove_favorite(
    symbol: str,
    current_user: UserSchema = Depends(get_current_active_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
) -> Any:
    """
    Remove a ticker from favorites.

    Args:
        symbol: Stock ticker symbol to remove
    """
    try:
        favorites_service.remove_favorite(user_id=current_user.id, symbol=symbol)

        logger.info(f"User {current_user.id} removed favorite: {symbol}")

        return BaseResponse(
            success=True,
            data={"symbol": symbol},
            meta={"message": f"Successfully removed {symbol} from favorites"},
        )
    except NotFoundError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.USER_NOT_FOUND, message=str(e))
        )
    except ValidationError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.USER_NOT_FOUND, message=str(e))
        )
    except Exception as e:
        logger.error(
            f"Error removing favorite {symbol} for user {current_user.id}: {e}"
        )
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.FAVORITES_REMOVE_ERROR, message="Failed to remove favorite"),
        )


@router.get("/check/{symbol}", response_model=BaseResponse)
@inject
def check_favorite(
    symbol: str,
    current_user: UserSchema = Depends(get_current_active_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
) -> Any:
    """
    Check if a ticker is in user's favorites.

    Args:
        symbol: Stock ticker symbol to check

    Returns:
        Boolean indicating if the symbol is favorited
    """
    try:
        check_response = favorites_service.check_favorite(
            user_id=current_user.id, symbol=symbol
        )

        return BaseResponse(success=True, data=check_response.model_dump())
    except Exception as e:
        logger.error(
            f"Error checking favorite {symbol} for user {current_user.id}: {e}"
        )
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.FAVORITES_CHECK_ERROR,
                message="Failed to check favorite status"
            ),
        )


@router.get("/symbols/list", response_model=BaseResponse)
@inject
def get_favorite_symbols(
    current_user: UserSchema = Depends(get_current_active_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
) -> Any:
    """
    Get simple list of favorited ticker symbols.

    Returns just the symbol strings without additional ticker metadata.
    Useful for quick checks or dropdown lists.
    """
    try:
        symbols = favorites_service.get_favorited_symbols(current_user.id)

        return BaseResponse(
            success=True, data={"symbols": symbols, "count": len(symbols)}
        )
    except Exception as e:
        logger.error(f"Error getting favorite symbols for user {current_user.id}: {e}")
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.FAVORITES_SYMBOLS_ERROR,
                message="Failed to get favorite symbols"
            ),
        )
