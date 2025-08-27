from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from myapi.logging_config import setup_logging

setup_logging()

from myapi.config import settings
from myapi.core.logging_middleware import LoggingMiddleware
from myapi.routers import auth_router, user_router
from myapi.routers import (
    prediction_router,
    session_router,
    universe_router,
    batch_router,
)
from myapi.routers import price_router, settlement_router
from myapi.routers import reward_router, point_router, ad_unlock_router
from myapi.containers import Container

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="O/X Prediction API",
        version="1.0.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    )

    app.container = Container()  # type: ignore

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://ai.bamtoly.com",
            "https://ox-universe.bamtoly.com",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(LoggingMiddleware)

    # Routers
    app.include_router(auth_router.router, prefix=settings.API_V1_STR)
    app.include_router(user_router.router, prefix=settings.API_V1_STR)
    app.include_router(prediction_router.router, prefix=settings.API_V1_STR)
    app.include_router(price_router.router, prefix=settings.API_V1_STR)
    app.include_router(settlement_router.router, prefix=settings.API_V1_STR)
    app.include_router(session_router.router, prefix=settings.API_V1_STR)
    app.include_router(universe_router.router, prefix=settings.API_V1_STR)
    app.include_router(batch_router.router, prefix=settings.API_V1_STR)
    app.include_router(reward_router.router, prefix=settings.API_V1_STR)
    app.include_router(point_router.router, prefix=settings.API_V1_STR)
    app.include_router(ad_unlock_router.router, prefix=settings.API_V1_STR)

    return app


app = create_app()


# Lambda handler for AWS Lambda deployment
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    # Mangum not available, skip Lambda handler
    handler = None


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
