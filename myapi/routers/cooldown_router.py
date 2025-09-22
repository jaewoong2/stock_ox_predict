from fastapi import APIRouter, Depends, HTTPException
from dependency_injector.wiring import inject
from myapi.core.auth_middleware import get_current_active_user
from myapi.schemas.user import User as UserSchema
from myapi.schemas.cooldown import SlotRefillMessage, CooldownStatusResponse
from myapi.services.cooldown_service import CooldownService
from myapi.deps import get_cooldown_service
from myapi.core.exceptions import ValidationError, BusinessLogicError
from myapi.utils.timezone_utils import get_current_kst_date
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cooldown", tags=["cooldown"])


@router.get("/status", response_model=CooldownStatusResponse)
@inject
async def get_cooldown_status(
    current_user: UserSchema = Depends(get_current_active_user),
    cooldown_service: CooldownService = Depends(get_cooldown_service),
) -> CooldownStatusResponse:
    """
    사용자의 현재 쿨다운 상태 조회

    인증 필요: Bearer 토큰
    권한: 일반 사용자

    Returns:
        CooldownStatusResponse: 쿨다운 상태 정보
    """
    try:
        current_date = get_current_kst_date()
        return cooldown_service.get_cooldown_status(current_user.id, current_date)

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error getting cooldown status: {str(e)}")
        raise HTTPException(
            status_code=500, detail="쿨다운 상태 조회 중 오류가 발생했습니다."
        )


@router.post("/cancel")
@inject
async def cancel_cooldown(
    current_user: UserSchema = Depends(get_current_active_user),
    cooldown_service: CooldownService = Depends(get_cooldown_service),
) -> dict:
    """
    활성 쿨다운 취소 (사용자 요청 시)

    인증 필요: Bearer 토큰
    권한: 일반 사용자

    Returns:
        dict: 취소 결과
    """
    try:
        current_date = get_current_kst_date()
        success = cooldown_service.cancel_active_cooldown(current_user.id, current_date)

        if success:
            return {"success": True, "message": "쿨다운이 취소되었습니다."}
        else:
            return {"success": False, "message": "취소할 활성 쿨다운이 없습니다."}

    except Exception as e:
        logger.error(f"Failed to cancel cooldown for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="쿨다운 취소 중 오류가 발생했습니다."
        )


@router.post("/handle-slot-refill")
@inject
async def handle_slot_refill_message(
    message: SlotRefillMessage,
    cooldown_service: CooldownService = Depends(get_cooldown_service),
) -> dict:
    """
    EventBridge Scheduler Lambda 콜백: 쿨다운 완료 후 슬롯 충전 처리

    이 엔드포인트는 AWS Lambda(스케줄러 트리거)를 통해 내부 인증 헤더와 함께 호출됩니다.
    직접 사용자 호출용이 아닙니다.

    Args:
        message: 슬롯 충전 메시지

    Returns:
        dict: 처리 결과
    """
    try:
        logger.info(
            f"Processing slot refill message: timer_id={message.timer_id}, user_id={message.user_id}"
        )

        success = await cooldown_service.handle_cooldown_completion(message.timer_id)

        if success:
            return {
                "success": True,
                "message": f"Slot refill completed for timer {message.timer_id}",
                "timer_id": message.timer_id,
                "user_id": message.user_id,
            }
        else:
            return {
                "success": False,
                "message": f"Slot refill failed for timer {message.timer_id}",
                "timer_id": message.timer_id,
                "user_id": message.user_id,
            }

    except Exception as e:
        logger.error(f"Failed to handle slot refill message: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"슬롯 충전 처리 중 오류가 발생했습니다: {str(e)}"
        )
