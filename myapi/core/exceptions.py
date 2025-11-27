from fastapi import HTTPException, status
from typing import Optional, Dict, Any

class BaseAPIException(HTTPException):
    """Base exception for API errors"""
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        
        super().__init__(
            status_code=status_code,
            detail={
                "success": False,
                "error": {
                    "code": error_code,
                    "message": message,
                    "details": self.details
                }
            }
        )

    def __str__(self) -> str:  # Ensure str(e) returns the human message
        return self.message

class AuthenticationError(BaseAPIException):
    """Authentication related errors"""
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_001",
            message=message,
            details=details
        )

class AuthorizationError(BaseAPIException):
    """Authorization related errors"""
    def __init__(self, message: str = "Access forbidden", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="AUTH_002",
            message=message,
            details=details
        )

class OAuthError(BaseAPIException):
    """OAuth related errors"""
    def __init__(self, message: str = "OAuth error", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="OAUTH_001",
            message=message,
            details=details
        )

class ValidationError(BaseAPIException):
    """Validation errors"""
    def __init__(self, message: str = "Validation failed", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_001",
            message=message,
            details=details
        )

class RateLimitError(BaseAPIException):
    """Rate limiting errors"""
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_001",
            message=message,
            details=details
        )

class BusinessLogicError(BaseAPIException):
    """Business logic errors"""
    def __init__(self, error_code: str, message: str, details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=error_code,
            message=message,
            details=details
        )

class NotFoundError(BaseAPIException):
    """Resource not found errors"""
    def __init__(self, message: str = "Resource not found", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND_001",
            message=message,
            details=details
        )

class ConflictError(BaseAPIException):
    """Resource conflict errors"""
    def __init__(self, message: str = "Resource conflict", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT_001",
            message=message,
            details=details
        )

class InternalServerError(BaseAPIException):
    """Internal server errors"""
    def __init__(self, message: str = "Internal server error", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_001",
            message=message,
            details=details
        )

class InsufficientBalanceError(BaseAPIException):
    """Insufficient balance errors"""
    def __init__(self, message: str = "Insufficient balance", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="BALANCE_001",
            message=message,
            details=details
        )

class NonTradingDayError(BaseAPIException):
    """Non-trading day validation errors"""
    def __init__(self, requested_date: str, day_type: str, next_trading_day: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="NON_TRADING_DAY",
            message=f"{requested_date} is not a US trading day ({day_type})",
            details={
                "requested_date": requested_date,
                "day_type": day_type,
                "next_trading_day": next_trading_day
            }
        )

class ServiceException(Exception):
    """Base exception for service layer errors"""
    pass
