"""
ErrorLog 관련 Pydantic 스키마

시스템 에러 및 실패 상황 추적을 위한 스키마 정의
"""

from datetime import date, datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from enum import Enum


class ErrorTypeEnum(str, Enum):
    """에러 타입 정의"""
    SETTLEMENT_FAILED = "SETTLEMENT_FAILED"
    EOD_FETCH_FAILED = "EOD_FETCH_FAILED" 
    BATCH_FAILED = "BATCH_FAILED"
    PREDICTION_FAILED = "PREDICTION_FAILED"
    POINT_TRANSACTION_FAILED = "POINT_TRANSACTION_FAILED"
    REWARD_REDEMPTION_FAILED = "REWARD_REDEMPTION_FAILED"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class ErrorLogCreate(BaseModel):
    """에러 로그 생성 요청 스키마"""
    check_type: ErrorTypeEnum
    trading_day: Optional[date] = None
    details: Dict[str, Any]
    
    class Config:
        json_encoders = {
            date: lambda v: v.isoformat() if v else None
        }


class ErrorLogResponse(BaseModel):
    """에러 로그 응답 스키마"""
    id: int
    check_type: str
    trading_day: Optional[date]
    status: str
    details: Dict[str, Any]
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat() if v else None
        }


class ErrorLogFilter(BaseModel):
    """에러 로그 필터링 조건"""
    check_type: Optional[ErrorTypeEnum] = None
    trading_day: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    limit: Optional[int] = 50
    offset: Optional[int] = 0


class ErrorLogStats(BaseModel):
    """에러 통계 응답"""
    total_errors: int
    errors_by_type: Dict[str, int]
    errors_by_date: Dict[str, int]
    most_frequent_error: Optional[str]
    latest_error: Optional[ErrorLogResponse]


class ErrorLogSummary(BaseModel):
    """일별 에러 요약"""
    trading_day: date
    total_errors: int
    error_types: List[str]
    critical_errors: int
    resolved_errors: int = 0  # 향후 확장용


class BatchErrorContext(BaseModel):
    """배치 작업 에러 컨텍스트"""
    batch_type: str
    stage: str
    execution_time: str
    retry_count: Optional[int] = 0


class SettlementErrorContext(BaseModel):
    """정산 에러 컨텍스트"""
    failed_symbols: List[str]
    total_symbols: int
    context: str = "Daily settlement"


class EODFetchErrorContext(BaseModel):
    """EOD 데이터 수집 에러 컨텍스트"""
    provider: str
    failed_symbols: List[str]
    retry_count: int = 0
    rate_limit_hit: bool = False


class APIErrorContext(BaseModel):
    """외부 API 에러 컨텍스트"""
    api_endpoint: str
    response_code: Optional[int]
    response_message: Optional[str]
    request_data: Optional[Dict[str, Any]] = None