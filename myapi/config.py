from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="myapi/.env",
        env_file_encoding="utf-8",
        extra="allow",
    )
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

    # Main SQS FIFO Queue URL
    SQS_MAIN_QUEUE_URL: str = (
        "https://sqs.ap-northeast-2.amazonaws.com/849441246713/ox.fifo"
    )

    # Business Rules
    POINTS_VOID_REWARD: int = 0
    BASE_PREDICTION_SLOTS: int = 3
    MAX_AD_SLOTS: int = 7
    COOLDOWN_MINUTES: int = 5

    # Point Management
    CORRECT_PREDICTION_POINTS: int = 100  # 정답 예측 시 지급 포인트
    PREDICTION_FEE_POINTS: int = 10  # 예측 수수료
    SIGNUP_BONUS_POINTS: int = 1000  # 신규 가입 보너스 포인트
    VOID_REFUND_ENABLED: bool = True  # VOID 처리 시 수수료 환불 여부
    FLAT_PRICE_POLICY: str = (
        "ALL_WRONG"  # FLAT 가격일 때 처리 정책: ALL_WRONG | ALL_CORRECT | VOID
    )
    SETTLEMENT_TIMEOUT_MINUTES: int = 30  # 정산 작업 타임아웃 (분)

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    DEFAULT_RATE_LIMIT: int = 100

    # Timezone
    TIMEZONE: str = "Asia/Seoul"
    AUTH_TOKEN: str = ""

    AWS_SQS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SQS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_SQS_REGION: str = "ap-northeast-2"


settings = Settings()
