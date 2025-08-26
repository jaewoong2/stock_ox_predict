import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            logger.info(f"[Request]: {request.method} {request.url}")
            return await call_next(request)
        except Exception as e:
            logger.error(f"[Error]: {e}", exc_info=True)
            raise e
