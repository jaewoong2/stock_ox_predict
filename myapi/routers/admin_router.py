"""
Admin Router

관리자 전용 API 엔드포인트
- 에러 로그 조회 및 모니터링
- 시스템 상태 확인
"""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from myapi.database.session import get_db
from myapi.core.security import admin_required
from myapi.services.error_log_service import ErrorLogService
from myapi.schemas.error_log import (
    ErrorLogResponse,
    ErrorLogFilter,
    ErrorLogStats,
    ErrorLogSummary,
    ErrorTypeEnum,
)
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin"])


def get_error_log_service(db: Session = Depends(get_db)) -> ErrorLogService:
    """ErrorLogService 의존성 주입"""
    return ErrorLogService(db)


@router.get("/errors/recent", response_model=List[ErrorLogResponse])
async def get_recent_errors(
    limit: int = Query(50, ge=1, le=100, description="조회할 에러 개수"),
    check_type: Optional[ErrorTypeEnum] = Query(None, description="에러 타입 필터"),
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """최근 에러 로그 조회"""
    try:
        errors = error_service.get_recent_errors(limit=limit, check_type=check_type)
        return errors
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch recent errors: {str(e)}"
        )


@router.get("/errors/stats", response_model=ErrorLogStats)
async def get_error_stats(
    days: int = Query(7, ge=1, le=30, description="통계 기간 (일)"),
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """에러 통계 조회"""
    try:
        stats = error_service.get_error_stats(days=days)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch error stats: {str(e)}"
        )


@router.get("/errors/trading-day/{trading_day}", response_model=List[ErrorLogResponse])
async def get_errors_by_trading_day(
    trading_day: date,
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """특정 거래일의 에러 조회"""
    try:
        errors = error_service.get_errors_by_trading_day(trading_day)
        return errors
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch errors for {trading_day}: {str(e)}",
        )


@router.get("/errors/summary/{trading_day}", response_model=ErrorLogSummary)
async def get_daily_error_summary(
    trading_day: date,
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """일별 에러 요약"""
    try:
        summary = error_service.get_daily_error_summary(trading_day)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch error summary for {trading_day}: {str(e)}",
        )


@router.get("/errors/critical", response_model=List[ErrorLogResponse])
async def get_critical_errors(
    days: int = Query(1, ge=1, le=7, description="조회 기간 (일)"),
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """중요한 에러만 조회"""
    try:
        errors = error_service.get_critical_errors(days=days)
        return errors
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch critical errors: {str(e)}"
        )


@router.post("/errors/filter", response_model=List[ErrorLogResponse])
async def filter_errors(
    filter_params: ErrorLogFilter,
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """필터링된 에러 조회"""
    try:
        errors = error_service.get_errors_by_filter(filter_params)
        return errors
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to filter errors: {str(e)}"
        )


class ErrorTrendingResponse(BaseModel):
    error_type: str
    is_trending: bool
    today_count: int
    threshold: int
    message: str


@router.get("/errors/trending/{error_type}", response_model=ErrorTrendingResponse)
async def check_error_trending(
    error_type: ErrorTypeEnum,
    threshold: int = Query(5, ge=1, le=50, description="급증 임계값"),
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """특정 에러 급증 여부 확인"""
    try:
        is_trending = error_service.is_error_trending(error_type, threshold=threshold)
        count = error_service.count_errors_by_type(error_type, days=1)

        return ErrorTrendingResponse(
            error_type=error_type.value,
            is_trending=is_trending,
            today_count=count,
            threshold=threshold,
            message=("⚠️ Trending" if is_trending else "✅ Normal"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to check trending: {str(e)}"
        )


@router.get("/system/health")
async def system_health_check(
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """시스템 헬스 체크"""
    try:
        health_info = error_service.health_check()
        return health_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


class CleanupResultResponse(BaseModel):
    success: bool
    deleted_count: int
    days_kept: int
    message: str


@router.delete("/errors/cleanup", response_model=CleanupResultResponse)
async def cleanup_old_errors(
    days_to_keep: int = Query(30, ge=7, le=365, description="보관할 일수"),
    current_user=Depends(admin_required),
    error_service: ErrorLogService = Depends(get_error_log_service),
):
    """오래된 에러 로그 정리"""
    try:
        deleted_count = error_service.cleanup_old_errors(days_to_keep=days_to_keep)
        return CleanupResultResponse(
            success=True,
            deleted_count=deleted_count,
            days_kept=days_to_keep,
            message=f"Successfully deleted {deleted_count} old error logs",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to cleanup errors: {str(e)}"
        )
