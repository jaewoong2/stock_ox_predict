from typing import Any, List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status, Query
from dependency_injector.wiring import inject

from myapi.core.auth_middleware import require_admin, verify_bearer_token
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.core.exceptions import NotFoundError
from myapi.schemas.prediction import PredictionChoice
from myapi.services.settlement_service import SettlementService
from myapi.deps import get_settlement_service


router = APIRouter(prefix="/admin/settlement", tags=["settlement"])

# 일반 사용자용 정산 상태 조회 라우터 (읽기 전용)
public_router = APIRouter(prefix="/settlement", tags=["settlement-public"])


@router.post("/settle-day/{trading_day}", response_model=BaseResponse)
@inject
async def settle_day(
    trading_day: str,
    _current_user: UserSchema = Depends(require_admin),  # Admin authentication required
    settlement_service: SettlementService = Depends(get_settlement_service),
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
    except NotFoundError as e:
        # 정산 대상 데이터 부재 (EOD/Universe 등) → 409로 매핑
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{str(e)}. Ensure EOD prices and universe exist for the trading day.",
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
    _current_user: UserSchema = Depends(require_admin),  # Admin authentication required
    settlement_service: SettlementService = Depends(get_settlement_service),
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
    _current_user: UserSchema = Depends(require_admin),  # Admin authentication required
    settlement_service: SettlementService = Depends(get_settlement_service),
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


# ============================================================================
# 정산 상태 조회 API - 일반 사용자도 접근 가능 (읽기 전용)
# ============================================================================


@public_router.get("/status/{trading_day}", response_model=BaseResponse)
@inject
async def get_settlement_status(
    trading_day: str,
    _current_user: UserSchema = Depends(verify_bearer_token),  # 일반 사용자 인증
    settlement_service: SettlementService = Depends(get_settlement_service),
) -> Any:
    """특정 거래일의 정산 진행 상태를 조회합니다. (인증된 사용자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        status_data = await settlement_service.get_settlement_status(day)
        return BaseResponse(success=True, data={"settlement_status": status_data})
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
            detail=f"Failed to get settlement status: {str(e)}",
        )


# ============================================================================
# 정산 재시도 API - 관리자 전용
# ============================================================================


@router.post("/retry/{trading_day}", response_model=BaseResponse)
@inject
async def retry_settlement(
    trading_day: str,
    symbols: Optional[List[str]] = Query(
        None, description="재시도할 종목 목록 (없으면 모든 PENDING 종목)"
    ),
    _current_user: UserSchema = Depends(require_admin),  # 관리자 권한 필요
    settlement_service: SettlementService = Depends(get_settlement_service),
) -> Any:
    """실패했거나 PENDING 상태인 예측들의 정산을 재시도합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        retry_result = await settlement_service.retry_settlement(day, symbols or [])
        return BaseResponse(success=True, data={"retry_result": retry_result})
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
            detail=f"Failed to retry settlement: {str(e)}",
        )
