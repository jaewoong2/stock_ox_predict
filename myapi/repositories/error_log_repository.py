"""
ErrorLog Repository

시스템 에러 및 실패 상황 추적을 위한 데이터 액세스 계층
"""

from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_

from myapi.repositories.base import BaseRepository
from myapi.models.internal import ErrorLog
from myapi.schemas.error_log import (
    ErrorLogResponse, 
    ErrorLogFilter, 
    ErrorLogStats,
    ErrorLogSummary
)


class ErrorLogRepository(BaseRepository[ErrorLog, ErrorLogResponse]):
    """ErrorLog 전용 Repository"""

    def __init__(self, db: Session):
        super().__init__(ErrorLog, ErrorLogResponse, db)

    def create_error_log(
        self, 
        check_type: str, 
        trading_day: Optional[date], 
        details: Dict[str, Any]
    ) -> ErrorLogResponse:
        """에러 로그 생성"""
        try:
            error_log = ErrorLog(
                check_type=check_type,
                trading_day=trading_day,
                status="FAILED",
                details=details
            )
            
            self.db.add(error_log)
            self.db.flush()
            self.db.commit()
            
            return ErrorLogResponse.model_validate(error_log)
        
        except Exception as e:
            self.db.rollback()
            raise Exception(f"Failed to create error log: {str(e)}")

    def get_recent_errors(
        self, 
        limit: int = 50,
        check_type: Optional[str] = None
    ) -> List[ErrorLogResponse]:
        """최근 에러 로그 조회"""
        query = self.db.query(ErrorLog).order_by(desc(ErrorLog.created_at))
        
        if check_type:
            query = query.filter(ErrorLog.check_type == check_type)
        
        query = query.limit(limit)
        error_logs = query.all()
        
        return [ErrorLogResponse.model_validate(log) for log in error_logs]

    def get_errors_by_filter(self, filter_params: ErrorLogFilter) -> List[ErrorLogResponse]:
        """필터링된 에러 로그 조회"""
        query = self.db.query(ErrorLog)
        
        # 필터 조건 적용
        if filter_params.check_type:
            query = query.filter(ErrorLog.check_type == filter_params.check_type.value)
        
        if filter_params.trading_day:
            query = query.filter(ErrorLog.trading_day == filter_params.trading_day)
        
        if filter_params.start_date:
            query = query.filter(ErrorLog.created_at >= filter_params.start_date)
        
        if filter_params.end_date:
            query = query.filter(ErrorLog.created_at <= filter_params.end_date)
        
        # 정렬 및 페이징
        query = query.order_by(desc(ErrorLog.created_at))
        query = query.offset(filter_params.offset or 0)
        query = query.limit(filter_params.limit or 50)
        
        error_logs = query.all()
        return [ErrorLogResponse.model_validate(log) for log in error_logs]

    def get_errors_by_trading_day(self, trading_day: date) -> List[ErrorLogResponse]:
        """특정 거래일의 에러 조회"""
        error_logs = (
            self.db.query(ErrorLog)
            .filter(ErrorLog.trading_day == trading_day)
            .order_by(desc(ErrorLog.created_at))
            .all()
        )
        
        return [ErrorLogResponse.model_validate(log) for log in error_logs]

    def get_error_stats(self, days: int = 7) -> ErrorLogStats:
        """에러 통계 조회"""
        # 최근 N일간의 에러 조회
        from datetime import timedelta
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)
        
        # 총 에러 수
        total_errors = (
            self.db.query(func.count(ErrorLog.id))
            .filter(
                and_(
                    func.date(ErrorLog.created_at) >= start_date,
                    func.date(ErrorLog.created_at) <= end_date
                )
            )
            .scalar() or 0
        )
        
        # 타입별 에러 수
        type_stats = (
            self.db.query(ErrorLog.check_type, func.count(ErrorLog.id))
            .filter(
                and_(
                    func.date(ErrorLog.created_at) >= start_date,
                    func.date(ErrorLog.created_at) <= end_date
                )
            )
            .group_by(ErrorLog.check_type)
            .all()
        )
        
        errors_by_type = {check_type: count for check_type, count in type_stats}
        
        # 일별 에러 수
        date_stats = (
            self.db.query(
                func.date(ErrorLog.created_at).label('error_date'),
                func.count(ErrorLog.id)
            )
            .filter(
                and_(
                    func.date(ErrorLog.created_at) >= start_date,
                    func.date(ErrorLog.created_at) <= end_date
                )
            )
            .group_by(func.date(ErrorLog.created_at))
            .all()
        )
        
        errors_by_date = {str(error_date): count for error_date, count in date_stats}
        
        # 가장 빈번한 에러
        most_frequent_error = None
        if errors_by_type:
            most_frequent_error = max(errors_by_type.items(), key=lambda x: x[1])[0]
        
        # 최신 에러
        latest_error_log = (
            self.db.query(ErrorLog)
            .order_by(desc(ErrorLog.created_at))
            .first()
        )
        
        latest_error = None
        if latest_error_log:
            latest_error = ErrorLogResponse.model_validate(latest_error_log)
        
        return ErrorLogStats(
            total_errors=total_errors,
            errors_by_type=errors_by_type,
            errors_by_date=errors_by_date,
            most_frequent_error=most_frequent_error,
            latest_error=latest_error
        )

    def get_daily_error_summary(self, trading_day: date) -> ErrorLogSummary:
        """일별 에러 요약"""
        errors = self.get_errors_by_trading_day(trading_day)
        
        error_types = list(set([error.check_type for error in errors]))
        critical_types = [
            "SETTLEMENT_FAILED", 
            "DATABASE_ERROR", 
            "BATCH_FAILED"
        ]
        
        critical_errors = len([
            error for error in errors 
            if error.check_type in critical_types
        ])
        
        return ErrorLogSummary(
            trading_day=trading_day,
            total_errors=len(errors),
            error_types=error_types,
            critical_errors=critical_errors
        )

    def count_errors_by_type(self, check_type: str, days: int = 1) -> int:
        """특정 타입의 에러 수 조회"""
        from datetime import timedelta
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)
        
        count = (
            self.db.query(func.count(ErrorLog.id))
            .filter(
                and_(
                    ErrorLog.check_type == check_type,
                    func.date(ErrorLog.created_at) >= start_date
                )
            )
            .scalar() or 0
        )
        
        return count

    def delete_old_errors(self, days_to_keep: int = 30) -> int:
        """오래된 에러 로그 삭제 (정리용)"""
        cutoff_date = datetime.now(timezone.utc).date()
        
        try:
            deleted_count = (
                self.db.query(ErrorLog)
                .filter(func.date(ErrorLog.created_at) < cutoff_date)
                .delete(synchronize_session=False)
            )
            
            self.db.commit()
            return deleted_count
            
        except Exception as e:
            self.db.rollback()
            raise Exception(f"Failed to delete old error logs: {str(e)}")