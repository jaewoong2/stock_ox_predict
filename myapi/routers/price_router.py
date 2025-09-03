from typing import Any
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, status
from dependency_injector.wiring import inject
from myapi.core.auth_middleware import get_current_active_user, require_admin
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.services.price_service import PriceService
from myapi.deps import get_price_service


router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/current/{symbol}", response_model=BaseResponse)
@inject
async def get_current_stock_price(
    symbol: str = Path(..., pattern=r"^[A-Z]{1,5}$"),
    _current_user: UserSchema = Depends(
        get_current_active_user
    ),  # Authentication required
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """특정 종목의 현재 가격을 조회합니다."""
    try:
        async with price_service as service:
            price = await service.get_current_price(symbol.upper())
            return BaseResponse(success=True, data={"price": price.model_dump()})

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch current price for {symbol}: {str(e)}",
        )


@router.get("/universe/{trading_day}", response_model=BaseResponse)
@inject
async def get_universe_current_prices(
    trading_day: str,
    _current_user: UserSchema = Depends(
        get_current_active_user
    ),  # Authentication required
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """오늘의 유니버스 모든 종목의 현재 가격을 조회합니다."""
    try:
        day = date.fromisoformat(trading_day)
        async with price_service as service:
            universe_prices = await service.get_universe_current_prices(day)
            return BaseResponse(
                success=True, data={"universe_prices": universe_prices.model_dump()}
            )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch universe prices: {str(e)}",
        )


@router.get("/eod/{symbol}/{trading_day}", response_model=BaseResponse)
@inject
async def get_eod_price(
    symbol: str = Path(..., pattern=r"^[A-Z]{1,5}$"),
    trading_day: str = Path(...),
    _current_user: UserSchema = Depends(
        get_current_active_user
    ),  # Authentication required
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """특정 종목의 EOD(장 마감) 가격을 조회합니다."""
    try:
        day = date.fromisoformat(trading_day)
        async with price_service as service:
            eod_price = await service.get_eod_price(symbol.upper(), day)
            return BaseResponse(
                success=True, data={"eod_price": eod_price.model_dump()}
            )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch EOD price: {str(e)}",
        )


@router.get("/admin/validate-settlement/{trading_day}", response_model=BaseResponse)
@inject
async def validate_settlement_prices(
    trading_day: str,
    _current_user: UserSchema = Depends(
        get_current_active_user
    ),  # Admin authentication required
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """정산을 위한 가격 검증을 수행합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        async with price_service as service:
            settlement_data = await service.validate_settlement_prices(day)
            return BaseResponse(
                success=True,
                data={
                    "settlement_data": [data.model_dump() for data in settlement_data]
                },
            )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate settlement prices: {str(e)}",
        )


@router.post("/admin/compare-prediction", response_model=BaseResponse)
@inject
async def compare_prediction_with_outcome(
    symbol: str,
    trading_day: str,
    predicted_direction: str,
    _current_user: UserSchema = Depends(
        get_current_active_user
    ),  # Admin authentication required
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """예측과 실제 결과를 비교합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        if predicted_direction.upper() not in ["UP", "DOWN"]:
            return BaseResponse(
                success=False,
                error=Error(
                    code=ErrorCode.INVALID_CREDENTIALS,
                    message="predicted_direction must be 'UP' or 'DOWN'",
                ),
            )

        async with price_service as service:
            comparison = await service.compare_prediction_with_outcome(
                symbol.upper(), day, predicted_direction
            )
            return BaseResponse(
                success=True, data={"comparison": comparison.model_dump()}
            )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare prediction: {str(e)}",
        )


@router.post("/collect-eod/{trading_day}", response_model=BaseResponse)
@inject
async def collect_eod_data(
    trading_day: str,
    _current_user: UserSchema = Depends(require_admin),  # Admin authentication required
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """
    지정된 거래일의 EOD(End of Day) 가격 데이터를 수집합니다. (관리자 전용)
    Yahoo Finance API를 통해 전일 유니버스의 모든 종목에 대한 EOD 데이터를 수집하고 DB에 저장합니다.
    """
    try:
        day = date.fromisoformat(trading_day)
        async with price_service as service:
            collection_result = await service.collect_eod_data_for_universe(day)
            return BaseResponse(
                success=True,
                data={
                    "trading_day": trading_day,
                    "total_symbols": collection_result.total_symbols,
                    "successful_collections": collection_result.successful_collections,
                    "failed_collections": collection_result.failed_collections,
                    "collection_details": [detail.model_dump() for detail in collection_result.details]
                }
            )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, 
                message="Invalid date format"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to collect EOD data for {trading_day}: {str(e)}",
        )
