"""
ErrorLog Service

시스템 에러 및 실패 상황 추적을 위한 비즈니스 로직 서비스
"""

from datetime import date
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from myapi.repositories.error_log_repository import ErrorLogRepository
from myapi.schemas.error_log import (
    ErrorLogResponse,
    ErrorLogFilter,
    ErrorLogStats,
    ErrorLogSummary,
    ErrorTypeEnum,
    BatchErrorContext,
    SettlementErrorContext,
    EODFetchErrorContext,
    APIErrorContext,
)
from myapi.schemas.health import HealthCheckResponse


class ErrorLogService:
    """ErrorLog 통합 관리 서비스"""

    def __init__(self, db: Session):
        self.db = db
        self.repo = ErrorLogRepository(db)

    # ============================================================================
    # 에러 로그 생성 메서드들 (타입별로 편의 메서드 제공)
    # ============================================================================

    def log_settlement_error(
        self,
        trading_day: date,
        failed_symbols: List[str],
        total_symbols: int,
        error_message: str,
        context: str = "Daily settlement",
    ) -> ErrorLogResponse:
        """정산 실패 에러 로그"""
        details = SettlementErrorContext(
            failed_symbols=failed_symbols, total_symbols=total_symbols, context=context
        ).model_dump()
        details["error_message"] = error_message

        return self.repo.create_error_log(
            check_type=ErrorTypeEnum.SETTLEMENT_FAILED.value,
            trading_day=trading_day,
            details=details,
        )

    def log_eod_fetch_error(
        self,
        trading_day: date,
        provider: str,
        failed_symbols: List[str],
        error_message: str,
        retry_count: int = 0,
        rate_limit_hit: bool = False,
    ) -> ErrorLogResponse:
        """EOD 데이터 수집 실패 에러 로그"""
        details = EODFetchErrorContext(
            provider=provider,
            failed_symbols=failed_symbols,
            retry_count=retry_count,
            rate_limit_hit=rate_limit_hit,
        ).model_dump()
        details["error_message"] = error_message

        return self.repo.create_error_log(
            check_type=ErrorTypeEnum.EOD_FETCH_FAILED.value,
            trading_day=trading_day,
            details=details,
        )

    def log_batch_error(
        self,
        trading_day: Optional[date],
        batch_type: str,
        stage: str,
        execution_time: str,
        error_message: str,
        retry_count: int = 0,
    ) -> ErrorLogResponse:
        """배치 작업 실패 에러 로그"""
        details = BatchErrorContext(
            batch_type=batch_type,
            stage=stage,
            execution_time=execution_time,
            retry_count=retry_count,
        ).model_dump()
        details["error_message"] = error_message

        return self.repo.create_error_log(
            check_type=ErrorTypeEnum.BATCH_FAILED.value,
            trading_day=trading_day,
            details=details,
        )

    def log_api_error(
        self,
        api_endpoint: str,
        error_message: str,
        response_code: Optional[int] = None,
        response_message: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        trading_day: Optional[date] = None,
    ) -> ErrorLogResponse:
        """외부 API 에러 로그"""
        details = APIErrorContext(
            api_endpoint=api_endpoint,
            response_code=response_code,
            response_message=response_message,
            request_data=request_data,
        ).model_dump()
        details["error_message"] = error_message

        return self.repo.create_error_log(
            check_type=ErrorTypeEnum.EXTERNAL_API_ERROR.value,
            trading_day=trading_day,
            details=details,
        )

    def log_database_error(
        self,
        error_message: str,
        operation: str,
        table_name: Optional[str] = None,
        query_details: Optional[Dict[str, Any]] = None,
        trading_day: Optional[date] = None,
    ) -> ErrorLogResponse:
        """데이터베이스 에러 로그"""
        details = {
            "operation": operation,
            "table_name": table_name,
            "query_details": query_details,
            "error_message": error_message,
        }

        return self.repo.create_error_log(
            check_type=ErrorTypeEnum.DATABASE_ERROR.value,
            trading_day=trading_day,
            details=details,
        )

    def log_prediction_error(
        self,
        user_id: int,
        trading_day: date,
        symbol: str,
        error_message: str,
        prediction_details: Optional[Dict[str, Any]] = None,
    ) -> ErrorLogResponse:
        """예측 관련 에러 로그"""
        details = {
            "user_id": user_id,
            "symbol": symbol,
            "prediction_details": prediction_details,
            "error_message": error_message,
        }

        return self.repo.create_error_log(
            check_type=ErrorTypeEnum.PREDICTION_FAILED.value,
            trading_day=trading_day,
            details=details,
        )

    def log_point_transaction_error(
        self,
        user_id: int,
        transaction_type: str,
        amount: int,
        error_message: str,
        ref_id: Optional[str] = None,
        trading_day: Optional[date] = None,
    ) -> ErrorLogResponse:
        """포인트 거래 에러 로그"""
        details = {
            "user_id": user_id,
            "transaction_type": transaction_type,
            "amount": amount,
            "ref_id": ref_id,
            "error_message": error_message,
        }

        return self.repo.create_error_log(
            check_type=ErrorTypeEnum.POINT_TRANSACTION_FAILED.value,
            trading_day=trading_day,
            details=details,
        )

    def log_reward_redemption_error(
        self,
        user_id: int,
        sku: str,
        cost_points: int,
        error_message: str,
        redemption_details: Optional[Dict[str, Any]] = None,
        trading_day: Optional[date] = None,
    ) -> ErrorLogResponse:
        """리워드 교환 에러 로그"""
        details = {
            "user_id": user_id,
            "sku": sku,
            "cost_points": cost_points,
            "redemption_details": redemption_details,
            "error_message": error_message,
        }

        return self.repo.create_error_log(
            check_type=ErrorTypeEnum.REWARD_REDEMPTION_FAILED.value,
            trading_day=trading_day,
            details=details,
        )

    def log_generic_error(
        self,
        check_type: ErrorTypeEnum,
        error_message: str,
        details: Dict[str, Any],
        trading_day: Optional[date] = None,
    ) -> ErrorLogResponse:
        """범용 에러 로그 (기타 에러들)"""
        error_details = details.copy()
        error_details["error_message"] = error_message

        return self.repo.create_error_log(
            check_type=check_type.value, trading_day=trading_day, details=error_details
        )

    # ============================================================================
    # 에러 조회 및 분석 메서드들
    # ============================================================================

    def get_recent_errors(
        self, limit: int = 50, check_type: Optional[ErrorTypeEnum] = None
    ) -> List[ErrorLogResponse]:
        """최근 에러 조회"""
        type_filter = check_type.value if check_type else None
        return self.repo.get_recent_errors(limit=limit, check_type=type_filter)

    def get_errors_by_filter(
        self, filter_params: ErrorLogFilter
    ) -> List[ErrorLogResponse]:
        """필터링된 에러 조회"""
        return self.repo.get_errors_by_filter(filter_params)

    def get_errors_by_trading_day(self, trading_day: date) -> List[ErrorLogResponse]:
        """특정 거래일의 에러 조회"""
        return self.repo.get_errors_by_trading_day(trading_day)

    def get_error_stats(self, days: int = 7) -> ErrorLogStats:
        """에러 통계 조회"""
        return self.repo.get_error_stats(days=days)

    def get_daily_error_summary(self, trading_day: date) -> ErrorLogSummary:
        """일별 에러 요약"""
        return self.repo.get_daily_error_summary(trading_day)

    def get_critical_errors(self, days: int = 1) -> List[ErrorLogResponse]:
        """중요한 에러만 조회"""
        critical_types = [
            ErrorTypeEnum.SETTLEMENT_FAILED,
            ErrorTypeEnum.BATCH_FAILED,
            ErrorTypeEnum.DATABASE_ERROR,
        ]

        all_errors = []
        for error_type in critical_types:
            filter_params = ErrorLogFilter(check_type=error_type, limit=20)
            errors = self.get_errors_by_filter(filter_params)
            all_errors.extend(errors)

        # 시간순 정렬
        all_errors.sort(key=lambda x: x.created_at, reverse=True)
        return all_errors

    def count_errors_by_type(self, check_type: ErrorTypeEnum, days: int = 1) -> int:
        """특정 타입의 에러 수 조회"""
        return self.repo.count_errors_by_type(check_type.value, days=days)

    def is_error_trending(self, check_type: ErrorTypeEnum, threshold: int = 5) -> bool:
        """특정 에러가 급증하고 있는지 확인"""
        today_count = self.count_errors_by_type(check_type, days=1)
        return today_count >= threshold

    # ============================================================================
    # 유지보수 및 관리 메서드들
    # ============================================================================

    def cleanup_old_errors(self, days_to_keep: int = 30) -> int:
        """오래된 에러 로그 정리"""
        return self.repo.delete_old_errors(days_to_keep=days_to_keep)

    def health_check(self) -> HealthCheckResponse:
        """에러 로그 시스템 헬스 체크"""
        try:
            recent_errors = self.get_recent_errors(limit=1)
            error_stats = self.get_error_stats(days=1)

            return HealthCheckResponse(
                status="healthy",
                total_errors_today=error_stats.total_errors,
                system_operational=True,
                last_error_logged=(
                    recent_errors[0].created_at if recent_errors else None
                ),
            )
        except Exception as e:
            return HealthCheckResponse(
                status="unhealthy", error=str(e), system_operational=False
            )
