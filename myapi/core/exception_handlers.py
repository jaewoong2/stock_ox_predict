import logging
import traceback
from typing import Any, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

from .exceptions import InternalServerError

logger = logging.getLogger("myapi")


def _request_context(request: Request) -> Dict[str, Any]:
    client = request.client.host if request.client else "-"
    return {
        "method": request.method,
        "url": str(request.url),
        "client": client,
    }


async def handle_base_api_exception(request, exc):
    ctx = _request_context(request)
    if getattr(exc, "status_code", 500) >= 500:
        logger.error(
            f"[BaseAPIException] {ctx['method']} {ctx['url']} from {ctx['client']} -> {exc.status_code}: {exc.detail}"
        )
    else:
        logger.warning(
            f"[BaseAPIException] {ctx['method']} {ctx['url']} from {ctx['client']} -> {exc.status_code}: {exc.detail}"
        )
    return JSONResponse(status_code=exc.status_code, content=exc.detail)  # type: ignore[arg-type]


async def handle_http_exception(request, exc):
    ctx = _request_context(request)

    # 에러 메시지 + 스택 트레이스 포맷팅
    error_msg = f"[HTTPException] {ctx['method']} {ctx['url']} from {ctx['client']} -> {exc.status_code}: {exc.detail}"

    if getattr(exc, "status_code", 500) >= 500:
        # 500번대 에러는 스택 트레이스 포함
        tb_str = ''.join(traceback.format_tb(exc.__traceback__))
        logger.error(f"{error_msg}\n\nStack Trace:\n{tb_str}")
    else:
        logger.warning(error_msg)
    # If detail is already structured (e.g., from BaseAPIException), pass through; else normalize
    if isinstance(exc.detail, dict) and "error" in exc.detail:  # type: ignore[truthy-bool]
        content = exc.detail  # type: ignore[assignment]
    else:
        content = {
            "success": False,
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            },
        }
    return JSONResponse(status_code=exc.status_code, content=content)


async def handle_validation_error(request, exc):
    ctx = _request_context(request)
    logger.warning(
        f"[ValidationError] {ctx['method']} {ctx['url']} from {ctx['client']} -> 422: {exc.errors()}"
    )
    content = {
        "success": False,
        "error": {
            "code": "VALIDATION_001",
            "message": "Validation failed",
            "details": {"errors": exc.errors()},
        },
    }
    return JSONResponse(status_code=422, content=content)


async def handle_unexpected_error(request, exc):
    ctx = _request_context(request)

    # 전체 스택 트레이스 포함
    tb_str = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(
        f"\n{'=' * 80}\n"
        f"[Unhandled Error] {ctx['method']} {ctx['url']} from {ctx['client']}\n"
        f"Exception Type: {type(exc).__name__}\n"
        f"Exception Message: {str(exc)}\n\n"
        f"Full Stack Trace:\n{tb_str}"
        f"{'=' * 80}"
    )

    internal = InternalServerError()
    return JSONResponse(status_code=internal.status_code, content=internal.detail)  # type: ignore[arg-type]
