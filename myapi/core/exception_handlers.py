import logging
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
    logger.warning(
        f"[BaseAPIException] {ctx['method']} {ctx['url']} from {ctx['client']} -> {exc.status_code}: {exc.detail}"
    )
    return JSONResponse(status_code=exc.status_code, content=exc.detail)  # type: ignore[arg-type]


async def handle_http_exception(request, exc):
    ctx = _request_context(request)
    logger.warning(
        f"[HTTPException] {ctx['method']} {ctx['url']} from {ctx['client']} -> {exc.status_code}: {exc.detail}"
    )
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
    logger.exception(
        f"[Unhandled Error] {ctx['method']} {ctx['url']} from {ctx['client']}"
    )
    internal = InternalServerError()
    return JSONResponse(status_code=internal.status_code, content=internal.detail)  # type: ignore[arg-type]
