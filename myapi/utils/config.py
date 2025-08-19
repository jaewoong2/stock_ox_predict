"""Application configuration and logging utilities."""

import json
import logging
import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import inspect


class Settings(BaseSettings):
    """Base settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file="myapi/.env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    ENVIRONMENT: str = Field(default="development")
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_DEFAULT_REGION: str = "ap-northeast-2"
    AWS_S3_ACCESS_KEY_ID: str = ""
    AWS_S3_SECRET_ACCESS_KEY: str = ""
    AWS_S3_DEFAULT_REGION: str = "ap-northeast-2"
    DATABASE_URL: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
    )
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])


class DevelopmentSettings(Settings):
    DEBUG: bool = True


class StagingSettings(Settings):
    DEBUG: bool = False


class ProductionSettings(Settings):
    DEBUG: bool = False


ENVIRONMENTS: dict[str, type[Settings]] = {
    "development": DevelopmentSettings,
    "staging": StagingSettings,
    "production": ProductionSettings,
}


@lru_cache
def get_settings() -> Settings:
    """Return settings instance based on ENVIRONMENT variable."""

    env = os.getenv("ENVIRONMENT", "development").lower()
    settings_cls = ENVIRONMENTS.get(env, DevelopmentSettings)
    return settings_cls()


def row_to_dict(row) -> dict:
    """Convert SQLAlchemy row to dictionary."""

    return {key: getattr(row, key) for key in inspect(row).attrs.keys()}


class JsonFormatter(logging.Formatter):
    """Simple JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        log_record = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(log_record)


def init_logging() -> None:
    """Initialize application-wide structured logging."""

    logger = logging.getLogger()
    if logger.hasHandlers():
        logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("✅ Logging initialized!")

