"""
광고 해제 시스템 API 라우터

이 파일은 광고 시청을 통한 예측 슬롯 해제 시스템의 모든 HTTP API 엔드포인트를 정의합니다:

사용자용 엔드포인트:
- POST /ads/watch-complete: 광고 시청 완료 처리
- POST /ads/unlock-slot: 쿨다운을 통한 슬롯 해제
- GET /ads/available-slots: 사용 가능한 슬롯 정보 조회
- GET /ads/history: 내 광고 해제 히스토리

관리자용 엔드포인트:
- GET /ads/admin/stats/{trading_day}: 일별 광고 해제 통계
- GET /ads/admin/user-history/{user_id}: 특정 사용자 히스토리

인증 및 권한:
- 모든 엔드포인트는 Bearer 토큰 인증 필요
- 관리자 엔드포인트는 is_admin=True 권한 필요
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import List
from datetime import date
from dependency_injector.wiring import inject, Provide

from myapi.core.auth_middleware import verify_bearer_token, require_admin, get_current_active_user
from myapi.schemas.user import User as UserSchema
from myapi.services.ad_unlock_service import AdUnlockService
from myapi.containers import Container
from myapi.schemas.ad_unlock import (
    AdUnlockCreate,
    AdUnlockResponse,
    AdUnlockHistory,
    SlotIncreaseRequest,
    SlotIncreaseResponse,
    AvailableSlotsResponse,
    AdUnlockStatsResponse,
    AdWatchCompleteRequest,
    AdWatchCompleteResponse,
    UnlockMethod
)
from myapi.core.exceptions import (
    ValidationError,
    BusinessLogicError,
)
import logging

logger = logging.getLogger(__name__)

# 광고 해제 관련 API 라우터 - /ads 경로 하에 모든 엔드포인트 그룹화
router = APIRouter(prefix="/ads", tags=["advertisements"])


@router.post("/watch-complete", response_model=AdWatchCompleteResponse)
@inject
async def watch_ad_complete(
    request: AdWatchCompleteRequest,
    current_user: UserSchema = Depends(get_current_active_user),
    ad_unlock_service: AdUnlockService = Depends(Provide[Container.services.ad_unlock_service]),
) -> AdWatchCompleteResponse:
    """
    광고 시청 완료 처리 - 광고를 시청한 후 예측 슬롯을 해제합니다

    인증 필요: Bearer 토큰
    권한: 일반 사용자
    
    비즈니스 규칙:
    - 일일 광고 시청 제한: 10회
    - 광고 1회 시청 = 예측 슬롯 1개 추가
    - 예측 세션 시간 내에서만 사용 가능
    
    Args:
        request: 광고 시청 완료 요청 (선택적 매개변수 포함)
        
    Returns:
        AdWatchCompleteResponse: 광고 시청 완료 결과
        
    HTTP Status:
        200: 성공적으로 슬롯 해제 완료
        400: 일일 제한 도달 또는 유효하지 않은 요청
        401: 인증 실패 또는 잘못된 토큰
        500: 내부 서버 오류
    
    비즈니스 로직:
        1. 일일 광고 시청 제한 확인
        2. 광고 시청 기록 생성
        3. 예측 슬롯 증가
        4. 결과 반환
    """
    try:
        logger.info(f"User {current_user.id} attempting to complete ad watch")
        
        response = ad_unlock_service.watch_ad_complete(
            user_id=current_user.id,
            request=request
        )
        
        if response.success:
            logger.info(
                f"User {current_user.id} successfully completed ad watch, "
                f"unlocked {response.slots_unlocked} slots"
            )
        else:
            logger.warning(
                f"User {current_user.id} ad watch failed: {response.message}"
            )
        
        return response
        
    except ValidationError as e:
        logger.error(f"Validation error in ad watch completion: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except BusinessLogicError as e:
        logger.error(f"Business logic error in ad watch completion: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in ad watch completion: {str(e)}")
        raise HTTPException(status_code=500, detail="광고 시청 처리 중 오류가 발생했습니다.")


@router.post("/unlock-slot", response_model=SlotIncreaseResponse)
@inject
async def unlock_slot_by_cooldown(
    current_user: UserSchema = Depends(get_current_active_user),
    ad_unlock_service: AdUnlockService = Depends(Provide[Container.services.ad_unlock_service]),
) -> SlotIncreaseResponse:
    """
    쿨다운을 통한 슬롯 해제 - 쿨다운 시간을 기다린 후 예측 슬롯을 해제합니다

    인증 필요: Bearer 토큰
    권한: 일반 사용자
    
    비즈니스 규칙:
    - 일일 쿨다운 제한: 5회
    - 쿨다운 대기 시간: 60분
    - 쿨다운 1회 사용 = 예측 슬롯 1개 추가
    
    Returns:
        SlotIncreaseResponse: 슬롯 해제 결과
        
    HTTP Status:
        200: 성공적으로 슬롯 해제 완료
        400: 쿨다운 대기 중이거나 일일 제한 도달
        401: 인증 실패 또는 잘못된 토큰
        500: 내부 서버 오류
    
    비즈니스 로직:
        1. 일일 쿨다운 제한 확인
        2. 쿨다운 대기 시간 확인
        3. 쿨다운 해제 기록 생성
        4. 예측 슬롯 증가
    """
    try:
        logger.info(f"User {current_user.id} attempting to unlock slot by cooldown")
        
        response = ad_unlock_service.unlock_slot_by_cooldown(
            user_id=current_user.id
        )
        
        if response.success:
            logger.info(
                f"User {current_user.id} successfully unlocked slot by cooldown, "
                f"unlocked {response.unlocked_slots} slots"
            )
        else:
            logger.warning(
                f"User {current_user.id} cooldown unlock failed: {response.message}"
            )
        
        return response
        
    except ValidationError as e:
        logger.error(f"Validation error in cooldown unlock: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except BusinessLogicError as e:
        logger.error(f"Business logic error in cooldown unlock: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in cooldown unlock: {str(e)}")
        raise HTTPException(status_code=500, detail="쿨다운 슬롯 해제 중 오류가 발생했습니다.")


@router.get("/available-slots", response_model=AvailableSlotsResponse)
@inject
async def get_available_slots_info(
    current_user: UserSchema = Depends(get_current_active_user),
    ad_unlock_service: AdUnlockService = Depends(Provide[Container.services.ad_unlock_service]),
) -> AvailableSlotsResponse:
    """
    사용 가능한 슬롯 정보 조회 - 현재 예측 현황과 해제 가능 상태를 조회합니다

    인증 필요: Bearer 토큰
    권한: 일반 사용자
    
    Returns:
        AvailableSlotsResponse: 현재 슬롯 현황 및 해제 가능성 정보
        
    HTTP Status:
        200: 성공적으로 정보 조회
        401: 인증 실패 또는 잘못된 토큰
        500: 내부 서버 오류
    
    응답 정보:
        - 현재 최대 예측 수
        - 이미 만든 예측 수
        - 남은 예측 가능 수
        - 광고/쿨다운 해제 가능 여부
        - 오늘의 해제 사용 현황
    """
    try:
        logger.info(f"User {current_user.id} retrieving available slots info")
        
        response = ad_unlock_service.get_available_slots_info(
            user_id=current_user.id
        )
        
        logger.info(
            f"User {current_user.id} slots info: "
            f"max={response.current_max_predictions}, "
            f"made={response.predictions_made}, "
            f"available={response.available_predictions}"
        )
        
        return response
        
    except ValidationError as e:
        logger.error(f"Validation error in getting available slots: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in getting available slots: {str(e)}")
        raise HTTPException(status_code=500, detail="슬롯 정보 조회 중 오류가 발생했습니다.")


@router.get("/history", response_model=List[AdUnlockHistory])
@inject
async def get_my_unlock_history(
    limit: int = Query(30, ge=1, le=90, description="조회할 최대 일수"),
    current_user: UserSchema = Depends(get_current_active_user),
    ad_unlock_service: AdUnlockService = Depends(Provide[Container.services.ad_unlock_service]),
) -> List[AdUnlockHistory]:
    """
    내 광고 해제 히스토리 조회 - 사용자의 광고 해제 사용 내역을 일별로 조회합니다

    인증 필요: Bearer 토큰
    권한: 일반 사용자
    
    Args:
        limit: 조회할 최대 일수 (기본값: 30일, 최대: 90일)
        
    Returns:
        List[AdUnlockHistory]: 일별 광고 해제 히스토리 목록
        
    HTTP Status:
        200: 성공적으로 히스토리 조회
        401: 인증 실패 또는 잘못된 토큰
        500: 내부 서버 오류
    
    응답 정보:
        - 일별 총 해제 슬롯 수
        - 광고 시청/쿨다운별 해제 수
        - 상세 해제 기록 목록
    """
    try:
        logger.info(f"User {current_user.id} retrieving unlock history (limit: {limit})")
        
        history = ad_unlock_service.get_user_unlock_history(
            user_id=current_user.id,
            limit=limit
        )
        
        logger.info(f"User {current_user.id} retrieved {len(history)} days of unlock history")
        
        return history
        
    except ValidationError as e:
        logger.error(f"Validation error in getting unlock history: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in getting unlock history: {str(e)}")
        raise HTTPException(status_code=500, detail="해제 히스토리 조회 중 오류가 발생했습니다.")


# 관리자용 엔드포인트
@router.get("/admin/stats/{trading_day}", response_model=AdUnlockStatsResponse)
@inject
async def get_daily_unlock_stats(
    trading_day: date = Path(..., description="조회할 거래일"),
    current_user: UserSchema = Depends(require_admin),
    ad_unlock_service: AdUnlockService = Depends(Provide[Container.services.ad_unlock_service]),
) -> AdUnlockStatsResponse:
    """
    일별 광고 해제 통계 조회 (관리자 전용) - 특정 날짜의 전체 광고 해제 통계를 조회합니다

    인증 필요: Bearer 토큰 + 관리자 권한
    권한: 관리자만 접근 가능
    
    Args:
        trading_day: 조회할 거래일
        
    Returns:
        AdUnlockStatsResponse: 일별 광고 해제 통계
        
    HTTP Status:
        200: 성공적으로 통계 조회
        401: 인증 실패 또는 관리자 권한 없음
        500: 내부 서버 오류
    
    응답 정보:
        - 총 해제 슬롯 수
        - 해제한 사용자 수
        - 방법별 상세 통계 (광고/쿨다운)
    """
    try:
        logger.info(f"Admin {current_user.id} retrieving daily unlock stats for {trading_day}")
        
        stats = ad_unlock_service.get_daily_stats(trading_day)
        
        logger.info(
            f"Admin {current_user.id} retrieved stats for {trading_day}: "
            f"total_unlocks={stats.total_unlocks}, unique_users={stats.unique_users}"
        )
        
        return stats
        
    except ValidationError as e:
        logger.error(f"Validation error in getting daily stats: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in getting daily stats: {str(e)}")
        raise HTTPException(status_code=500, detail="일일 통계 조회 중 오류가 발생했습니다.")


@router.get("/admin/user-history/{user_id}", response_model=List[AdUnlockHistory])
@inject
async def get_user_unlock_history_admin(
    user_id: int = Path(..., description="조회할 사용자 ID"),
    limit: int = Query(30, ge=1, le=90, description="조회할 최대 일수"),
    current_user: UserSchema = Depends(require_admin),
    ad_unlock_service: AdUnlockService = Depends(Provide[Container.services.ad_unlock_service]),
) -> List[AdUnlockHistory]:
    """
    특정 사용자 광고 해제 히스토리 조회 (관리자 전용)

    인증 필요: Bearer 토큰 + 관리자 권한
    권한: 관리자만 접근 가능
    
    Args:
        user_id: 조회할 사용자 ID
        limit: 조회할 최대 일수
        
    Returns:
        List[AdUnlockHistory]: 해당 사용자의 광고 해제 히스토리
        
    HTTP Status:
        200: 성공적으로 히스토리 조회
        401: 인증 실패 또는 관리자 권한 없음
        404: 사용자를 찾을 수 없음
        500: 내부 서버 오류
    """
    try:
        logger.info(f"Admin {current_user.id} retrieving unlock history for user {user_id}")
        
        history = ad_unlock_service.get_user_unlock_history(
            user_id=user_id,
            limit=limit
        )
        
        logger.info(
            f"Admin {current_user.id} retrieved {len(history)} days of "
            f"unlock history for user {user_id}"
        )
        
        return history
        
    except ValidationError as e:
        logger.error(f"Validation error in admin getting unlock history: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in admin getting unlock history: {str(e)}")
        raise HTTPException(status_code=500, detail="해제 히스토리 조회 중 오류가 발생했습니다.")