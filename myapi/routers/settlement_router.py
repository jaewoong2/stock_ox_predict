from typing import Any
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from dependency_injector.wiring import inject, Provide

from myapi.containers import Container
from myapi.core.auth_middleware import require_admin
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.prediction import PredictionChoice
from myapi.services.settlement_service import SettlementService


router = APIRouter(prefix="/admin/settlement", tags=["settlement"])


@router.post("/settle-day/{trading_day}", response_model=BaseResponse)
@inject
async def settle_day(
    trading_day: str,
    _current_user: UserSchema = Depends(
        require_admin
    ),  # Admin authentication required
    settlement_service: SettlementService = Depends(
        Provide[Container.services.settlement_service]
    ),
) -> Any:
    """특정 거래일의 모든 예측을 자동으로 정산합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        result = await settlement_service.validate_and_settle_day(day)
        return BaseResponse(success=True, data={"settlement_result": result})
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
            detail=f"Failed to settle day: {str(e)}",
        )


@router.get("/summary/{trading_day}", response_model=BaseResponse)
@inject
async def get_settlement_summary(
    trading_day: str,
    _current_user: UserSchema = Depends(
        require_admin
    ),  # Admin authentication required
    settlement_service: SettlementService = Depends(
        Provide[Container.services.settlement_service]
    ),
) -> Any:
    """특정 거래일의 정산 요약 정보를 조회합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        summary = await settlement_service.get_settlement_summary(day)
        return BaseResponse(success=True, data={"settlement_summary": summary})
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
            detail=f"Failed to get settlement summary: {str(e)}",
        )


@router.post("/manual-settle", response_model=BaseResponse)
@inject
async def manual_settle_symbol(
    trading_day: str,
    symbol: str,
    correct_choice: PredictionChoice,
    override_price_validation: bool = False,
    _current_user: UserSchema = Depends(
        require_admin
    ),  # Admin authentication required
    settlement_service: SettlementService = Depends(
        Provide[Container.services.settlement_service]
    ),
):
    """특정 종목에 대해 수동으로 정산을 수행합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        result = await settlement_service.manual_settle_symbol(
            day, symbol.upper(), correct_choice, override_price_validation
        )
        return BaseResponse(success=True, data={"manual_settlement": result})
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
            detail=f"Failed to manually settle symbol: {str(e)}",
        )
