import logging
import time
from fastapi import Request, Response
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Use the myapi logger so it goes to the JSON handler
logger = logging.getLogger("myapi")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.time()
        method = request.method
        url = str(request.url)
        client = request.client.host if request.client else "-"

        logger.info(f"[Request] {method} {url} from {client}")
        try:
            response = await call_next(request)
        except HTTPException as http_exc:
            # Log HTTP exceptions; escalate 5xx as errors
            if http_exc.status_code >= 500:
                logger.error(
                    f"[HTTPException] {method} {url} from {client} -> {http_exc.status_code}: {http_exc.detail}"
                )
            else:
                logger.warning(
                    f"[HTTPException] {method} {url} from {client} -> {http_exc.status_code}: {http_exc.detail}"
                )
            raise
        except Exception:
            # Log unexpected exceptions with full traceback
            logger.exception(f"[Unhandled Error] {method} {url} from {client}")
            raise

        duration_ms = (time.time() - start) * 1000
        if response.status_code >= 500:
            logger.error(
                f"[Response] {method} {url} from {client} -> {response.status_code} in {duration_ms:.1f}ms"
            )
        elif response.status_code >= 400:
            logger.warning(
                f"[Response] {method} {url} from {client} -> {response.status_code} in {duration_ms:.1f}ms"
            )
        else:
            logger.info(
                f"[Response] {method} {url} from {client} -> {response.status_code} in {duration_ms:.1f}ms"
            )
        return response
