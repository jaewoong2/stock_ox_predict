"""
포인트 시스템 API 라우터

이 파일은 포인트 시스템의 모든 HTTP API 엔드포인트를 정의합니다:

사용자용 엔드포인트:
- GET /points/balance: 내 포인트 잔액 조회
- GET /points/ledger: 내 포인트 거래 내역
- GET /points/ledger/date-range: 날짜 범위별 거래 내역
- GET /points/earned/{trading_day}: 특정일 획득 포인트
- GET /points/integrity/my: 내 포인트 정합성 검증

관리자용 엔드포인트:
- POST /points/admin/add: 포인트 추가
- POST /points/admin/deduct: 포인트 차감
- POST /points/admin/adjust: 포인트 조정
- GET /points/admin/balance/{user_id}: 사용자 잔액 조회
- GET /points/admin/ledger/{user_id}: 사용자 거래 내역
- GET /points/admin/integrity/*: 정합성 검증 관리
- GET /points/admin/stats/daily: 일별 통계

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
    DailyPointsIntegrityResponse,
    PointsEarnedResponse,
    DailyPointsStatsResponse,
    AffordabilityResponse,
)
from myapi.core.exceptions import (
    ValidationError,
    InsufficientBalanceError,
)
import logging

logger = logging.getLogger(__name__)

# 포인트 관련 API 라우터 - /points 경로 하에 모든 엔드포인트 그룹화
router = APIRouter(prefix="/points", tags=["points"])


@router.get("/balance", response_model=PointsBalanceResponse)
@inject
async def get_my_balance(
    current_user: UserSchema = Depends(get_current_active_user),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsBalanceResponse:
    """
    내 포인트 잔액 조회 - 인증된 사용자의 현재 포인트 잔액

    인증 필요: Bearer 토큰
    권한: 일반 사용자
    
    Returns:
        PointsBalanceResponse: 현재 포인트 잔액 정보
        
    HTTP Status:
        200: 성공적으로 잔액 조회
        401: 인증 실패 또는 잘못된 토큰
        500: 내부 서버 오류
    
    성능:
        - O(1) 성능 (balance_after 필드 사용)
        - 인덱스를 통한 빠른 조회
    """
    try:
        user_id = current_user.id
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
    current_user: UserSchema = Depends(get_current_active_user),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsLedgerResponse:
    """
    내 포인트 거래 내역 조회 - 페이징을 통한 거래 내역 조회

    인증 필요: Bearer 토큰
    권한: 일반 사용자
    
    Query Parameters:
        limit: 한 페이지에 조회할 항목 수 (1-100, 기본: 50)
        offset: 건너뛸 항목 수 (기본: 0)
        
    Returns:
        PointsLedgerResponse: 거래 내역 및 페이징 정보
        - balance: 현재 잔액
        - entries: 거래 내역 리스트 (최신순)
        - total_count: 전체 거래 건수
        - has_next: 다음 페이지 존재 여부
        
    HTTP Status:
        200: 성공적으로 거래 내역 조회
        401: 인증 실패
        500: 내부 서버 오류
    
    사용 예시:
        GET /points/ledger?limit=20&offset=0  # 처음 20개 항목
        GET /points/ledger?limit=10&offset=20 # 21-30번째 항목
    """
    try:
        user_id = current_user.id
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
    current_user: UserSchema = Depends(get_current_active_user),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> List[PointsLedgerEntry]:
    """날짜 범위별 포인트 거래 내역 조회

    지정된 날짜 범위의 포인트 거래 내역을 조회합니다.
    """
    try:
        user_id = current_user.id
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


@router.get("/earned/{trading_day}", response_model=PointsEarnedResponse)
@inject
async def get_points_earned_today(
    trading_day: date = Path(..., description="거래일 (YYYY-MM-DD)"),
    current_user: UserSchema = Depends(get_current_active_user),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsEarnedResponse:
    """특정일 획득 포인트 조회

    사용자가 특정일에 획득한 포인트 총합을 조회합니다.
    """
    try:
        user_id = current_user.id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user token")

        earned_points = point_service.get_user_points_earned_today(user_id, trading_day)
        return PointsEarnedResponse(
            user_id=user_id, trading_day=trading_day.isoformat(), points_earned=earned_points
        )
    except Exception as e:
        logger.error(f"Failed to get points earned today: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve points earned")


@router.get("/integrity/my", response_model=PointsIntegrityCheckResponse)
@inject
async def verify_my_integrity(
    current_user: UserSchema = Depends(get_current_active_user),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsIntegrityCheckResponse:
    """내 포인트 정합성 검증

    현재 사용자의 포인트 정합성을 검증합니다.
    """
    try:
        user_id = current_user.id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user token")

        integrity_result = point_service.verify_user_integrity(user_id)
        return integrity_result
    except Exception as e:
        logger.error(f"Failed to verify user integrity: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify integrity")


# ============================================================================
# 관리자 전용 엔드포인트 - Admin Only Endpoints
# ============================================================================
# 모든 관리자 엔드포인트는 is_admin=True 권한이 필요합니다.
# 사용자의 포인트를 직접 조작하거나 시스템 전체 정보에 접근할 수 있습니다.

@router.post("/admin/add", response_model=PointsTransactionResponse)
@inject
async def admin_add_points(
    request: PointsTransactionRequest,
    user_id: int = Query(..., description="대상 사용자 ID"),
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsTransactionResponse:
    """
    관리자용 포인트 추가 - 특정 사용자에게 포인트 지급

    인증 필요: Bearer 토큰
    권한: 관리자 (is_admin=True)
    
    Query Parameters:
        user_id: 포인트를 추가할 대상 사용자 ID
        
    Request Body:
        PointsTransactionRequest:
            - points: 추가할 포인트 수 (양수)
            - reason: 추가 사유
            - ref_id: 중복 방지용 고유 ID
            - trading_day: 거래일 (선택사항)
            - symbol: 관련 심볼 (선택사항)
            
    Returns:
        PointsTransactionResponse: 거래 결과
        - success: 성공 여부
        - transaction_id: 거래 ID
        - balance_after: 거래 후 잔액
        - message: 결과 메시지
        
    HTTP Status:
        200: 성공적으로 포인트 추가
        400: 잘못된 요청 또는 유효성 검증 실패
        403: 관리자 권한 없음
        500: 내부 서버 오류
        
    멱등성:
        - 동일한 ref_id로 여러 번 호출시 한 번만 처리
        - 기존 거래가 있으면 기존 결과 반환
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨
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
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsTransactionResponse:
    """포인트 차감 (관리자 전용)

    특정 사용자의 포인트를 차감합니다.
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨

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
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsTransactionResponse:
    """포인트 조정 (관리자 전용)

    특정 사용자의 포인트를 조정합니다. 양수면 추가, 음수면 차감됩니다.
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨

        admin_id = current_user.id
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
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsBalanceResponse:
    """사용자 포인트 잔액 조회 (관리자 전용)

    특정 사용자의 포인트 잔액을 조회합니다.
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨

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
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsLedgerResponse:
    """사용자 포인트 거래 내역 조회 (관리자 전용)

    특정 사용자의 포인트 거래 내역을 조회합니다.
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨

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
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsIntegrityCheckResponse:
    """사용자 포인트 정합성 검증 (관리자 전용)

    특정 사용자의 포인트 정합성을 검증합니다.
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨

        integrity_result = point_service.verify_user_integrity(user_id)
        return integrity_result
    except Exception as e:
        logger.error(f"Failed to verify user integrity: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify integrity")


@router.get("/admin/integrity/global", response_model=PointsIntegrityCheckResponse)
@inject
async def admin_verify_global_integrity(
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> PointsIntegrityCheckResponse:
    """
    전체 포인트 정합성 검증 - 시스템 전체의 포인트 무결성 검사

    인증 필요: Bearer 토큰
    권한: 관리자 (is_admin=True)
    
    검증 내용:
    1. 모든 사용자의 최신 잔액 합계
    2. 모든 거래의 포인트 변동량 총합
    3. 두 값의 일치 여부 확인
    
    Returns:
        PointsIntegrityCheckResponse:
        - status: "OK" 또는 "MISMATCH"
        - total_balance_from_latest: 최신 잔액들의 합
        - total_deltas: 모든 변동량의 합
        - user_count: 전체 사용자 수
        - total_entries: 전체 거래 건수
        
    HTTP Status:
        200: 검증 완료
        403: 관리자 권한 없음
        500: 검증 중 오류 발생
        
    주의사항:
        - 대량 데이터에서는 시간이 오래 걸릴 수 있음
        - 정기적인 모니터링 용도로 사용 권장
        - MISMATCH 발생 시 시스템 점검 필요
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨

        integrity_result = point_service.verify_global_integrity()
        return integrity_result
    except Exception as e:
        logger.error(f"Failed to verify global integrity: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify global integrity")


@router.get("/admin/stats/daily/{trading_day}", response_model=DailyPointsStatsResponse)
@inject
async def get_daily_points_stats(
    trading_day: date = Path(..., description="거래일 (YYYY-MM-DD)"),
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> DailyPointsStatsResponse:
    """일별 포인트 통계 (관리자 전용)

    특정일의 포인트 지급 통계를 조회합니다.
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨

        total_awarded = point_service.get_total_points_awarded_today(trading_day)

        return DailyPointsStatsResponse(
            trading_day=trading_day.isoformat(), total_points_awarded=total_awarded
        )
    except Exception as e:
        logger.error(f"Failed to get daily points stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve daily stats")


@router.get("/admin/check-affordability/{user_id}/{amount}", response_model=AffordabilityResponse)
@inject
async def check_user_affordability(
    user_id: int = Path(..., description="확인할 사용자 ID"),
    amount: int = Path(..., description="확인할 포인트 금액"),
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> AffordabilityResponse:
    """사용자 지불 능력 확인 (관리자 전용)

    특정 사용자가 지정된 포인트를 지불할 수 있는지 확인합니다.
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨

        can_afford = point_service.can_afford(user_id, amount)
        current_balance = point_service.get_user_balance(user_id).balance

        return AffordabilityResponse(
            user_id=user_id,
            amount=amount,
            can_afford=can_afford,
            current_balance=current_balance,
            shortfall=max(0, amount - current_balance) if not can_afford else 0,
        )
    except Exception as e:
        logger.error(f"Failed to check affordability: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check affordability")


@router.get(
    "/admin/integrity/daily/{trading_day}",
    response_model=DailyPointsIntegrityResponse,
)
@inject
async def verify_daily_points_integrity(
    trading_day: date = Path(..., description="검증할 거래일 (YYYY-MM-DD)"),
    current_user: UserSchema = Depends(require_admin),
    point_service: PointService = Depends(Provide[Container.services.point_service]),
) -> DailyPointsIntegrityResponse:
    """
    일별 포인트 정합성 검증 (관리자 전용)
    
    특정일의 포인트 거래 내역을 분석하여 정합성을 검증합니다.
    
    인증 필요: Bearer 토큰
    권한: 관리자 (is_admin=True)
    
    Returns:
        dict: 일별 포인트 정합성 검증 결과
        - trading_day: 검증 대상 날짜
        - total_transactions: 총 거래 건수
        - total_points_delta: 총 포인트 변동량
        - total_points_awarded: 총 지급 포인트  
        - total_points_deducted: 총 차감 포인트
        - prediction_award_count: 예측 보상 건수
        - prediction_points_total: 예측 보상 총 포인트
        - status: 검증 상태
        
    HTTP Status:
        200: 검증 완료
        403: 관리자 권한 없음
        500: 검증 중 오류 발생
        
    사용 예시:
        GET /points/admin/integrity/daily/2025-08-28
    """
    try:
        # 관리자 권한은 require_admin에서 이미 확인됨
        
        integrity_result = point_service.verify_daily_integrity(trading_day)
        return integrity_result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to verify daily points integrity: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify daily points integrity")
