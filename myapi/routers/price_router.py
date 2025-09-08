from typing import Any
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, status
from dependency_injector.wiring import inject
from myapi.core.auth_middleware import get_current_active_user, require_admin
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.price import SettlementPriceData
from myapi.services.price_service import PriceService
from myapi.deps import get_price_service
from myapi.core.exceptions import NotFoundError


router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/current/{symbol}", response_model=BaseResponse)
@inject
async def get_current_stock_price(
    symbol: str = Path(..., pattern=r"^[A-Z]{1,5}$"),
    _current_user: UserSchema = Depends(get_current_active_user),
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """특정 종목의 현재 가격을 스냅샷(DB)에서 조회합니다."""
    price = price_service.get_current_price_snapshot(symbol.upper())
    return BaseResponse(success=True, data={"price": price.model_dump()})


@router.get("/universe/{trading_day}", response_model=BaseResponse)
@inject
async def get_universe_current_prices(
    trading_day: str,
    _current_user: UserSchema = Depends(get_current_active_user),
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """유니버스 현재 가격을 스냅샷(DB)에서 조회합니다."""
    try:
        day = date.fromisoformat(trading_day)
        universe_prices = price_service.get_universe_current_prices_snapshot(day)
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


@router.get("/eod/{symbol}/{trading_day}", response_model=BaseResponse)
@inject
async def get_eod_price(
    symbol: str = Path(..., pattern=r"^[A-Z]{1,5}$"),
    trading_day: str = Path(...),
    _current_user: UserSchema = Depends(get_current_active_user),
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """특정 종목의 EOD(장 마감) 가격을 스냅샷(DB)에서 조회합니다."""
    try:
        day = date.fromisoformat(trading_day)
        eod_price = price_service.get_eod_price_snapshot(symbol.upper(), day)
        return BaseResponse(success=True, data={"eod_price": eod_price.model_dump()})
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )


@router.get("/admin/validate-settlement/{trading_day}", response_model=BaseResponse)
@inject
async def validate_settlement_prices(
    trading_day: str,
    _current_user: UserSchema = Depends(get_current_active_user),
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """정산을 위한 가격 검증을 수행합니다. (관리자 전용, 스냅샷만 사용)"""
    try:
        day = date.fromisoformat(trading_day)
        eod_prices = price_service.get_universe_eod_prices_snapshot(day)
        # Reuse existing transformation logic on snapshot data
        settlement_data = []
        for e in eod_prices:
            price_movement = price_service._calculate_price_movement(e.close_price, e.previous_close)
            change_percent = price_service._calculate_change_percent(e.close_price, e.previous_close)
            is_valid, void_reason = price_service._validate_price_for_settlement(e)
            settlement_data.append(
                SettlementPriceData(
                    symbol=e.symbol,
                    trading_date=e.trading_date,
                    settlement_price=e.close_price,
                    reference_price=e.previous_close,
                    price_movement=price_movement,
                    change_percent=change_percent,
                    is_valid_settlement=is_valid,
                    void_reason=void_reason,
                )
            )
        return BaseResponse(
            success=True,
            data={"settlement_data": [data.model_dump() for data in settlement_data]},
        )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
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


@router.post("/admin/compare-prediction/by-id", response_model=BaseResponse)
@inject
async def compare_prediction_with_outcome_by_id(
    prediction_id: int,
    _current_user: UserSchema = Depends(require_admin),  # Admin authentication required
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """특정 예측 ID를 기준으로 스냅샷 가격 대비 결과를 비교합니다. (관리자 전용)"""
    try:
        async with price_service as service:
            comparison = await service.compare_prediction_with_outcome_by_id(
                prediction_id
            )
            return BaseResponse(
                success=True, data={"comparison": comparison.model_dump()}
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare prediction by id: {str(e)}",
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
    except NotFoundError as e:
        # Universe 미존재 등 정합성 이슈는 409로 매핑
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{str(e)}. Ensure universe is set for the trading day before collecting EOD.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to collect EOD data for {trading_day}: {str(e)}",
        )
