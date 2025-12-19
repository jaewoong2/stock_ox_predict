from click import Option
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from typing import List, Optional
from dependency_injector.wiring import inject

from myapi.database.session import get_db
from myapi.core.auth_middleware import verify_bearer_token, require_admin
from myapi.schemas.user import User as UserSchema
from myapi.services.reward_service import RewardService
from myapi.deps import get_reward_service
from myapi.schemas.rewards import (
    DeleteResultResponse,
    RewardCatalogResponse,
    RewardItem,
    RewardRedemptionRequest,
    RewardRedemptionResponse,
    RewardRedemptionHistoryResponse,
    AdminRewardCreateRequest,
    AdminStockUpdateRequest,
    RewardsInventoryResponse,
    AdminRewardsStatsResponse,
    RewardsSummaryResponse,
    RewardActivationResponse,
    RewardCancellationResponse,
)
from myapi.schemas.pagination import PaginationLimits
from myapi.core.exceptions import (
    ValidationError,
    NotFoundError,
    InsufficientBalanceError,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rewards", tags=["rewards"])


@router.get("/catalog", response_model=RewardCatalogResponse)
@inject
async def get_reward_catalog(
    available_only: bool = Query(True, description="재고 있는 상품만 조회"),
    reward_service: RewardService = Depends(get_reward_service),
) -> RewardCatalogResponse:
    """리워드 카탈로그 조회

    사용 가능한 리워드 상품 목록을 조회합니다.
    """
    try:
        catalog = reward_service.get_reward_catalog(available_only=available_only)
        return catalog
    except Exception as e:
        logger.error(f"Failed to get reward catalog: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve reward catalog")


@router.get("/catalog/{sku}", response_model=Optional[RewardItem])
@inject
async def get_reward_by_sku(
    sku: str = Path(..., description="리워드 SKU"),
    reward_service: RewardService = Depends(get_reward_service),
):
    """SKU로 리워드 상품 조회

    특정 SKU의 리워드 상품 정보를 조회합니다.
    """
    try:
        reward = reward_service.get_reward_by_sku(sku)
        return reward
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get reward {sku}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve reward")


@router.post("/redeem", response_model=RewardRedemptionResponse)
@inject
async def redeem_reward(
    request: RewardRedemptionRequest,
    current_user: UserSchema = Depends(verify_bearer_token),
    reward_service: RewardService = Depends(get_reward_service),
) -> RewardRedemptionResponse:
    """리워드 교환

    사용자가 포인트를 사용하여 리워드를 교환합니다.
    """
    try:
        user_id = current_user.id

        result = reward_service.redeem_reward(user_id, request)
        return result
    except InsufficientBalanceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to redeem reward: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process redemption")


@router.get("/my-redemptions", response_model=RewardRedemptionHistoryResponse)
@inject
async def get_my_redemption_history(
    limit: int = Query(
        PaginationLimits.REWARDS_HISTORY["default"],
        ge=PaginationLimits.REWARDS_HISTORY["min"],
        le=PaginationLimits.REWARDS_HISTORY["max"],
        description="페이지 크기",
    ),
    offset: int = Query(0, ge=0, description="오프셋"),
    current_user: UserSchema = Depends(verify_bearer_token),
    reward_service: RewardService = Depends(get_reward_service),
) -> RewardRedemptionHistoryResponse:
    """내 교환 내역 조회

    현재 사용자의 리워드 교환 내역을 조회합니다.
    """
    try:
        user_id = current_user.id

        history = reward_service.get_user_redemption_history(
            user_id=user_id, limit=limit, offset=offset
        )
        return history
    except Exception as e:
        logger.error(f"Failed to get redemption history: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve redemption history"
        )


# 관리자 전용 엔드포인트
@router.post("/admin/items", response_model=RewardsInventoryResponse)
@inject
async def create_reward_item(
    request: AdminRewardCreateRequest,
    current_user: UserSchema = Depends(require_admin),
    reward_service: RewardService = Depends(get_reward_service),
) -> RewardsInventoryResponse:
    """리워드 아이템 생성 (관리자 전용)

    새로운 리워드 상품을 생성합니다.
    """
    try:
        reward = reward_service.create_reward_item(request)
        return reward
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create reward item: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create reward item")


@router.put(
    "/admin/items/{sku}/stock", response_model=Optional[RewardsInventoryResponse]
)
@inject
async def update_reward_stock(
    sku: str = Path(..., description="리워드 SKU"),
    new_stock: int = Query(..., ge=0, description="새로운 재고 수량"),
    current_user: UserSchema = Depends(require_admin),
    reward_service: RewardService = Depends(get_reward_service),
):
    """리워드 재고 업데이트 (관리자 전용)

    리워드 상품의 재고를 업데이트합니다.
    """
    try:
        request = AdminStockUpdateRequest(sku=sku, new_stock=new_stock)
        updated_reward = reward_service.update_reward_stock(request)
        return updated_reward
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update reward stock: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update reward stock")


@router.delete("/admin/items/{sku}", response_model=DeleteResultResponse)
@inject
async def delete_reward_item(
    sku: str = Path(..., description="삭제할 리워드 SKU"),
    current_user: UserSchema = Depends(require_admin),
    reward_service: RewardService = Depends(get_reward_service),
) -> DeleteResultResponse:
    """리워드 아이템 삭제 (관리자 전용)

    리워드 상품을 삭제합니다. 진행 중인 교환이 있으면 삭제할 수 없습니다.
    """
    try:
        success = reward_service.delete_reward_item(sku)
        return DeleteResultResponse(
            success=success, message=f"Reward '{sku}' deleted successfully"
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete reward item: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete reward item")


@router.get("/admin/stats", response_model=AdminRewardsStatsResponse)
@inject
async def get_admin_stats(
    current_user: UserSchema = Depends(require_admin),
    reward_service: RewardService = Depends(get_reward_service),
) -> AdminRewardsStatsResponse:
    """관리자용 리워드 통계

    리워드 인벤토리 요약과 교환 통계를 조회합니다.
    """
    try:
        inventory_summary = reward_service.get_inventory_summary()
        redemption_stats = reward_service.get_redemption_stats()

        return AdminRewardsStatsResponse(
            inventory=inventory_summary, redemptions=redemption_stats
        )
    except Exception as e:
        logger.error(f"Failed to get admin stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


@router.get("/admin/pending-redemptions")
@inject
async def get_pending_redemptions(
    limit: int = Query(100, ge=1, le=500, description="조회할 최대 건수"),
    current_user: UserSchema = Depends(require_admin),
    reward_service: RewardService = Depends(get_reward_service),
) -> List:
    """대기 중인 교환 요청 조회 (관리자 전용)

    처리 대기 중인 리워드 교환 요청을 조회합니다.
    """
    try:
        pending_redemptions = reward_service.get_pending_redemptions(limit=limit)
        return pending_redemptions
    except Exception as e:
        logger.error(f"Failed to get pending redemptions: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve pending redemptions"
        )


from pydantic import BaseModel


class UpdateRedemptionStatusResponse(BaseModel):
    success: bool
    message: str


@router.put(
    "/admin/redemptions/{redemption_id}/status",
    response_model=UpdateRedemptionStatusResponse,
)
@inject
async def update_redemption_status(
    redemption_id: int = Path(..., description="교환 요청 ID"),
    new_status: str = Query(..., description="새로운 상태 (ISSUED, CANCELLED, FAILED)"),
    vendor_code: Optional[str] = Query(None, description="벤더 코드 (발급 완료시)"),
    current_user: UserSchema = Depends(require_admin),
    reward_service: RewardService = Depends(get_reward_service),
) -> UpdateRedemptionStatusResponse:
    """교환 요청 상태 업데이트 (관리자 전용)

    교환 요청의 상태를 수동으로 업데이트합니다.
    """
    try:
        success = reward_service.process_redemption_manually(
            redemption_id=redemption_id,
            new_status=new_status,
            vendor_code=vendor_code or "",
        )

        return UpdateRedemptionStatusResponse(
            success=success,
            message=f"Redemption {redemption_id} status updated to {new_status}",
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update redemption status: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to update redemption status"
        )


# ==================== 마이페이지용 엔드포인트 ====================


@router.get("/my-summary", response_model=RewardsSummaryResponse)
@inject
async def get_my_rewards_summary(
    current_user: UserSchema = Depends(verify_bearer_token),
    reward_service: RewardService = Depends(get_reward_service),
) -> RewardsSummaryResponse:
    """마이페이지: 리워드 전체 요약

    사용자의 사용 가능한 리워드, 사용 완료된 리워드, 대기 중인 리워드를 모두 조회합니다.
    """
    try:
        user_id = current_user.id
        summary = reward_service.get_user_rewards_summary(user_id)
        return summary
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get rewards summary: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve rewards summary"
        )


@router.post("/activate/{redemption_id}", response_model=RewardActivationResponse)
@inject
async def activate_reward(
    redemption_id: int = Path(..., description="교환 ID"),
    current_user: UserSchema = Depends(verify_bearer_token),
    reward_service: RewardService = Depends(get_reward_service),
) -> RewardActivationResponse:
    """리워드 사용하기 (통합 엔드포인트)

    사용자가 구매한 리워드를 실제로 사용합니다.
    SKU 타입에 따라 슬롯 리프레시, 기프티콘 발급, 포인트 지급 등의 액션이 실행됩니다.
    """
    try:
        user_id = current_user.id
        result = await reward_service.activate_reward(user_id, redemption_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to activate reward: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to activate reward")


@router.post("/cancel/{redemption_id}", response_model=RewardCancellationResponse)
@inject
async def cancel_reward(
    redemption_id: int = Path(..., description="교환 ID"),
    current_user: UserSchema = Depends(verify_bearer_token),
    reward_service: RewardService = Depends(get_reward_service),
) -> RewardCancellationResponse:
    """리워드 취소하기

    사용자가 구매한 리워드를 취소하고 포인트를 환불받습니다.
    AVAILABLE 상태의 리워드만 취소 가능합니다.
    """
    try:
        user_id = current_user.id
        result = await reward_service.cancel_reward(user_id, redemption_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to cancel reward: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to cancel reward")
