from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import List
from datetime import date
from dependency_injector.wiring import inject, Provide

from myapi.core.auth_middleware import verify_bearer_token
from myapi.services.point_service import PointService
from myapi.containers import Container
from myapi.schemas.points import (
    PointsBalanceResponse,
    PointsLedgerEntry,
    PointsLedgerResponse,
    PointsTransactionRequest,
    PointsTransactionResponse,
    AdminPointsAdjustmentRequest,
    PointsIntegrityCheckResponse,
)
from myapi.core.exceptions import (
    ValidationError,
    InsufficientBalanceError,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/points", tags=["points"])


@router.get("/balance", response_model=PointsBalanceResponse)
@inject
async def get_my_balance(
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsBalanceResponse:
    """내 포인트 잔액 조회

    현재 사용자의 포인트 잔액을 조회합니다.
    """
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user token")

        balance = point_service.get_user_balance(user_id)
        return balance
    except Exception as e:
        logger.error(f"Failed to get balance for user: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve balance")


@router.get("/ledger", response_model=PointsLedgerResponse)
@inject
async def get_my_ledger(
    limit: int = Query(50, ge=1, le=100, description="페이지 크기"),
    offset: int = Query(0, ge=0, description="오프셋"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsLedgerResponse:
    """내 포인트 거래 내역 조회

    현재 사용자의 포인트 거래 내역을 페이징으로 조회합니다.
    """
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user token")

        ledger = point_service.get_user_ledger(
            user_id=user_id, limit=limit, offset=offset
        )
        return ledger
    except Exception as e:
        logger.error(f"Failed to get ledger for user: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ledger")


@router.get("/ledger/date-range", response_model=List[PointsLedgerEntry])
@inject
async def get_ledger_by_date_range(
    start_date: date = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> List[PointsLedgerEntry]:
    """날짜 범위별 포인트 거래 내역 조회

    지정된 날짜 범위의 포인트 거래 내역을 조회합니다.
    """
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user token")

        transactions = point_service.get_transactions_by_date_range(
            user_id=user_id, start_date=start_date, end_date=end_date
        )
        return transactions
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get transactions by date range: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve transactions")


@router.get("/earned/{trading_day}")
@inject
async def get_points_earned_today(
    trading_day: date = Path(..., description="거래일 (YYYY-MM-DD)"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> dict:
    """특정일 획득 포인트 조회

    사용자가 특정일에 획득한 포인트 총합을 조회합니다.
    """
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user token")

        earned_points = point_service.get_user_points_earned_today(user_id, trading_day)
        return {
            "user_id": user_id,
            "trading_day": trading_day.isoformat(),
            "points_earned": earned_points,
        }
    except Exception as e:
        logger.error(f"Failed to get points earned today: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve points earned")


@router.get("/integrity/my", response_model=PointsIntegrityCheckResponse)
@inject
async def verify_my_integrity(
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsIntegrityCheckResponse:
    """내 포인트 정합성 검증

    현재 사용자의 포인트 정합성을 검증합니다.
    """
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user token")

        integrity_result = point_service.verify_user_integrity(user_id)
        return integrity_result
    except Exception as e:
        logger.error(f"Failed to verify user integrity: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify integrity")


# 관리자 전용 엔드포인트
@router.post("/admin/add", response_model=PointsTransactionResponse)
@inject
async def admin_add_points(
    request: PointsTransactionRequest,
    user_id: int = Query(..., description="대상 사용자 ID"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsTransactionResponse:
    """포인트 추가 (관리자 전용)

    특정 사용자에게 포인트를 추가합니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        result = point_service.add_points(user_id=user_id, request=request)
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add points: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to add points")


@router.post("/admin/deduct", response_model=PointsTransactionResponse)
@inject
async def admin_deduct_points(
    request: PointsTransactionRequest,
    user_id: int = Query(..., description="대상 사용자 ID"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsTransactionResponse:
    """포인트 차감 (관리자 전용)

    특정 사용자의 포인트를 차감합니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        result = point_service.deduct_points(user_id=user_id, request=request)
        return result
    except InsufficientBalanceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to deduct points: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to deduct points")


@router.post("/admin/adjust", response_model=PointsTransactionResponse)
@inject
async def admin_adjust_points(
    request: AdminPointsAdjustmentRequest,
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsTransactionResponse:
    """포인트 조정 (관리자 전용)

    특정 사용자의 포인트를 조정합니다. 양수면 추가, 음수면 차감됩니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        admin_id = current_user.get("user_id")
        if not admin_id:
            raise HTTPException(status_code=401, detail="Invalid admin token")

        result = point_service.admin_adjust_points(admin_id=admin_id, request=request)
        return result
    except InsufficientBalanceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to adjust points: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to adjust points")


@router.get("/admin/balance/{user_id}", response_model=PointsBalanceResponse)
@inject
async def admin_get_user_balance(
    user_id: int = Path(..., description="조회할 사용자 ID"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsBalanceResponse:
    """사용자 포인트 잔액 조회 (관리자 전용)

    특정 사용자의 포인트 잔액을 조회합니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        balance = point_service.get_user_balance(user_id)
        return balance
    except Exception as e:
        logger.error(f"Failed to get balance for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve balance")


@router.get("/admin/ledger/{user_id}", response_model=PointsLedgerResponse)
@inject
async def admin_get_user_ledger(
    user_id: int = Path(..., description="조회할 사용자 ID"),
    limit: int = Query(50, ge=1, le=100, description="페이지 크기"),
    offset: int = Query(0, ge=0, description="오프셋"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsLedgerResponse:
    """사용자 포인트 거래 내역 조회 (관리자 전용)

    특정 사용자의 포인트 거래 내역을 조회합니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        ledger = point_service.get_user_ledger(
            user_id=user_id, limit=limit, offset=offset
        )
        return ledger
    except Exception as e:
        logger.error(f"Failed to get ledger for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ledger")


@router.get("/admin/integrity/{user_id}", response_model=PointsIntegrityCheckResponse)
@inject
async def admin_verify_user_integrity(
    user_id: int = Path(..., description="검증할 사용자 ID"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsIntegrityCheckResponse:
    """사용자 포인트 정합성 검증 (관리자 전용)

    특정 사용자의 포인트 정합성을 검증합니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        integrity_result = point_service.verify_user_integrity(user_id)
        return integrity_result
    except Exception as e:
        logger.error(f"Failed to verify user integrity: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify integrity")


@router.get("/admin/integrity/global", response_model=PointsIntegrityCheckResponse)
@inject
async def admin_verify_global_integrity(
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsIntegrityCheckResponse:
    """전체 포인트 정합성 검증 (관리자 전용)

    전체 시스템의 포인트 정합성을 검증합니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        integrity_result = point_service.verify_global_integrity()
        return integrity_result
    except Exception as e:
        logger.error(f"Failed to verify global integrity: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify global integrity")


@router.get("/admin/stats/daily/{trading_day}")
@inject
async def get_daily_points_stats(
    trading_day: date = Path(..., description="거래일 (YYYY-MM-DD)"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> dict:
    """일별 포인트 통계 (관리자 전용)

    특정일의 포인트 지급 통계를 조회합니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        total_awarded = point_service.get_total_points_awarded_today(trading_day)

        return {
            "trading_day": trading_day.isoformat(),
            "total_points_awarded": total_awarded,
        }
    except Exception as e:
        logger.error(f"Failed to get daily points stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve daily stats")


@router.get("/admin/check-affordability/{user_id}/{amount}")
@inject
async def check_user_affordability(
    user_id: int = Path(..., description="확인할 사용자 ID"),
    amount: int = Path(..., description="확인할 포인트 금액"),
    current_user: dict = Depends(verify_bearer_token),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> dict:
    """사용자 지불 능력 확인 (관리자 전용)

    특정 사용자가 지정된 포인트를 지불할 수 있는지 확인합니다.
    """
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

        can_afford = point_service.can_afford(user_id, amount)
        current_balance = point_service.get_user_balance(user_id).balance

        return {
            "user_id": user_id,
            "amount": amount,
            "can_afford": can_afford,
            "current_balance": current_balance,
            "shortfall": max(0, amount - current_balance) if not can_afford else 0,
        }
    except Exception as e:
        logger.error(f"Failed to check affordability: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check affordability")
