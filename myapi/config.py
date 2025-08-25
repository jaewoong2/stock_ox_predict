from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "OX Prediction API"
    PROJECT_NAME: str = "OX Predict API"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database
    POSTGRES_HOST: str = ""
    POSTGRES_PORT: int = 5432
    POSTGRES_USERNAME: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DATABASE: str = ""
    POSTGRES_SCHEMA: str = "crypto"

    # Legacy Database URL (will be constructed from POSTGRES_* vars)
    DATABASE_URL: Optional[str] = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    @property
    def database_url(self) -> str:
        """Construct database URL from individual components"""
        from urllib.parse import quote_plus

        if self.DATABASE_URL:
            return self.DATABASE_URL

        # URL encode the password to handle special characters
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        return f"postgresql+psycopg2://{self.POSTGRES_USERNAME}:{encoded_password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"

    # Security
    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # For compatibility

    # OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    KAKAO_CLIENT_ID: str = ""
    KAKAO_CLIENT_SECRET: str = ""
    OAUTH_STATE_EXPIRE_MINUTES: int = 10

    # External APIs
    ALPHA_VANTAGE_API_KEY: str = "demo"  # Default demo key
    EOD_FETCH_RETRY_COUNT: int = 3

    # AWS
    AWS_REGION: str = "ap-northeast-2"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    SQS_ENDPOINT_URL: Optional[str] = None

    # Queue Names and URLs
    SQS_EOD_FETCH_QUEUE: str = "ox-eod-fetch"
    SQS_SETTLEMENT_QUEUE: str = "ox-settlement"
    SQS_POINTS_AWARD_QUEUE: str = "ox-points-award"

    # Queue URLs (for compatibility)
    SQS_EOD_FETCH_QUEUE_URL: Optional[str] = None
    SQS_SETTLEMENT_COMPUTE_QUEUE_URL: Optional[str] = None
    SQS_POINTS_AWARD_QUEUE_URL: Optional[str] = None

    # Business Rules
    POINTS_WIN_REWARD: int = 100
    POINTS_VOID_REWARD: int = 0
    BASE_PREDICTION_SLOTS: int = 3
    MAX_AD_SLOTS: int = 7
    COOLDOWN_MINUTES: int = 5

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    DEFAULT_RATE_LIMIT: int = 100

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "https://yourapp.com"]

    # Timezone
    TIMEZONE: str = "Asia/Seoul"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env


settings = Settings()
