"""
레이트 리밋 미들웨어
FastAPI 미들웨어로 API 레이트 제한 적용
"""

import time
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session

from myapi.database.session import get_db_contextlib
from myapi.services.rate_limit_service import RateLimitService
from myapi.schemas.auth import BaseResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """레이트 리밋 미들웨어"""

    def __init__(self, app, exclude_paths: Optional[list] = None):
        super().__init__(app)

        # 레이트 리밋을 적용하지 않을 경로들
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

        # 경로별 레이트 리밋 설정
        self.path_limits = {
            "/v1/predictions": "predictions_submit",
            "/v1/points/balance": "points_balance",
            "/v1/rewards/catalog": "rewards_catalog",
            "/v1/rewards/redeem": "rewards_redeem",
        }

        # 메서드별 추가 제한
        self.method_limits = {
            "POST": {
                "/v1/predictions": ["predictions_submit", "predictions_submit_hourly"],
                "/v1/rewards/redeem": ["rewards_redeem"],
            }
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """요청 처리"""

        # 제외 경로 확인
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # IP 주소 추출
        ip_address = self._get_client_ip(request)

        # 사용자 ID 추출 (JWT 토큰에서)
        user_id = self._get_user_id_from_request(request)

        try:
            with get_db_contextlib() as db:
                rate_limit_service = RateLimitService(db)

                # 글로벌 IP 제한 확인
                if not await self._check_global_ip_limit(
                    rate_limit_service, ip_address
                ):
                    return self._create_rate_limit_response(
                        "IP 주소당 요청 한도를 초과했습니다"
                    )

                # 글로벌 사용자 제한 확인 (로그인된 사용자)
                if user_id and not await self._check_global_user_limit(
                    rate_limit_service, user_id
                ):
                    return self._create_rate_limit_response(
                        "사용자당 요청 한도를 초과했습니다"
                    )

                # 엔드포인트별 제한 확인
                if not await self._check_endpoint_limits(
                    rate_limit_service, request, user_id, ip_address
                ):
                    return self._create_rate_limit_response(
                        "API 요청 한도를 초과했습니다"
                    )

        except Exception as e:
            # 레이트 리밋 서비스 오류 시 요청 허용 (fail-open)
            pass

        # 응답에 레이트 리밋 헤더 추가
        response = await call_next(request)

        # 레이트 리밋 정보를 응답 헤더에 추가
        try:
            with get_db_contextlib() as db:
                rate_limit_service = RateLimitService(db)
                await self._add_rate_limit_headers(
                    response, rate_limit_service, request, user_id, ip_address
                )
        except:
            pass

        return response

    async def _check_global_ip_limit(
        self, rate_limit_service: RateLimitService, ip_address: str
    ) -> bool:
        """글로벌 IP 제한 확인"""
        key = rate_limit_service.create_rate_limit_key("global", ip_address=ip_address)
        allowed, _ = rate_limit_service.check_rate_limit(
            key, "global_per_ip", ip_address=ip_address
        )
        return allowed

    async def _check_global_user_limit(
        self, rate_limit_service: RateLimitService, user_id: int
    ) -> bool:
        """글로벌 사용자 제한 확인"""
        key = rate_limit_service.create_rate_limit_key("global", user_id=user_id)
        allowed, _ = rate_limit_service.check_rate_limit(
            key, "global_per_user", user_id=user_id
        )
        return allowed

    async def _check_endpoint_limits(
        self,
        rate_limit_service: RateLimitService,
        request: Request,
        user_id: Optional[int],
        ip_address: str,
    ) -> bool:
        """엔드포인트별 제한 확인"""
        path = request.url.path
        method = request.method

        # 경로 기반 제한 확인
        for path_prefix, limit_type in self.path_limits.items():
            if path.startswith(path_prefix):
                key = rate_limit_service.create_rate_limit_key(
                    path_prefix, user_id=user_id, ip_address=ip_address
                )
                allowed, _ = rate_limit_service.check_rate_limit(
                    key, limit_type, user_id=user_id, ip_address=ip_address
                )
                if not allowed:
                    return False

        # 메서드별 추가 제한 확인
        if method in self.method_limits:
            for path_prefix, limit_types in self.method_limits[method].items():
                if path.startswith(path_prefix):
                    for limit_type in limit_types:
                        key = rate_limit_service.create_rate_limit_key(
                            f"{method}_{path_prefix}",
                            user_id=user_id,
                            ip_address=ip_address,
                        )
                        allowed, _ = rate_limit_service.check_rate_limit(
                            key, limit_type, user_id=user_id, ip_address=ip_address
                        )
                        if not allowed:
                            return False

        return True

    async def _add_rate_limit_headers(
        self,
        response: Response,
        rate_limit_service: RateLimitService,
        request: Request,
        user_id: Optional[int],
        ip_address: str,
    ):
        """응답에 레이트 리밋 헤더 추가"""
        path = request.url.path

        # 주요 엔드포인트에 대한 헤더 추가
        for path_prefix, limit_type in self.path_limits.items():
            if path.startswith(path_prefix):
                key = rate_limit_service.create_rate_limit_key(
                    path_prefix, user_id=user_id, ip_address=ip_address
                )
                _, limit_info = rate_limit_service.check_rate_limit(
                    key, limit_type, user_id=user_id, ip_address=ip_address
                )

                response.headers["X-RateLimit-Remaining"] = str(
                    limit_info.get("remaining", 0)
                )
                response.headers["X-RateLimit-Reset"] = str(
                    limit_info.get("reset_at", 0)
                )
                if limit_info.get("retry_after", 0) > 0:
                    response.headers["Retry-After"] = str(limit_info["retry_after"])
                break

    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 주소 추출"""
        # 프록시 환경에서 실제 IP 추출
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        x_real_ip = request.headers.get("X-Real-IP")
        if x_real_ip:
            return x_real_ip

        return request.client.host if request.client else "unknown"

    def _get_user_id_from_request(self, request: Request) -> Optional[int]:
        """요청에서 사용자 ID 추출 (JWT 토큰에서)"""
        try:
            # request.state에서 현재 사용자 정보 추출 (인증 미들웨어에서 설정)
            if hasattr(request.state, "current_user"):
                return request.state.current_user.id
        except:
            pass
        return None

    def _create_rate_limit_response(self, message: str) -> JSONResponse:
        """레이트 리밋 에러 응답 생성"""
        response_data = BaseResponse(
            success=False,
            error={
                "code": "RATE_LIMITED",
                "message": message,
                "details": {"retry_after": 60},  # 기본 1분 후 재시도
            },
        )

        return JSONResponse(
            status_code=429,
            content=response_data.dict(),
            headers={"Retry-After": "60", "X-RateLimit-Remaining": "0"},
        )


# 레이트 리밋 데코레이터
def rate_limit(limit_type: str, custom_key: Optional[str] = None):
    """레이트 리밋 데코레이터"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # FastAPI dependency로 구현하는 것이 더 적절
            # 여기서는 기본 구현만 제공
            return await func(*args, **kwargs)

        return wrapper

    return decorator
