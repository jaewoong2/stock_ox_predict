from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging

from myapi.config import settings
from myapi.database.connection import engine
from myapi.middleware.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="O/X Prediction API",
        version="1.0.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate Limiting Middleware
    app.add_middleware(
        RateLimitMiddleware,
        exclude_paths=["/health", "/docs", "/openapi.json", "/redoc", "/metrics"],
    )

    # app.add_middleware(LoggingMiddleware) # This will be added later

    return app


app = create_app()
