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
    DB_POOL_SIZE: int = 5  # 동시 연결 수를 줄임
    DB_MAX_OVERFLOW: int = 10  # 최대 오버플로우도 줄임

    @property
    def database_url(self) -> str:
        """Construct database URL from individual components"""

        # URL encode the password to handle special characters
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        return f"postgresql+psycopg://{self.POSTGRES_USERNAME}:{encoded_password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"

    # Security
    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 1 day
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # For compatibility

    # OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    KAKAO_CLIENT_ID: str = ""
    KAKAO_CLIENT_SECRET: str = ""
    APPLE_CLIENT_ID: str = ""
    APPLE_TEAM_ID: str = ""
    APPLE_KEY_ID: str = ""
    APPLE_PRIVATE_KEY: str = ""
    OAUTH_STATE_EXPIRE_MINUTES: int = 10

    # Magic Link
    MAGIC_LINK_EXPIRE_MINUTES: int = 15
    # API Base URL (쿨다운 콜백 등에 사용)
    API_BASE_URL: str = ""
    API_BASE_URL_LOCAL: Optional[str] = None
    API_BASE_URL_PROD: Optional[str] = None

    # Magic Link
    MAGIC_LINK_BASE_URL: str = ""
    MAGIC_LINK_BASE_URL_LOCAL: Optional[str] = None
    MAGIC_LINK_BASE_URL_PROD: Optional[str] = None
    MAGIC_LINK_CLIENT_REDIRECT_URL: str = ""
    MAGIC_LINK_CLIENT_REDIRECT_URL_LOCAL: Optional[str] = None
    MAGIC_LINK_CLIENT_REDIRECT_URL_PROD: Optional[str] = None
    SES_FROM_EMAIL: str = ""
    # Common Job API (Function URL)
    JOB_API_BASE_URL: str = ""
    JOB_API_AUTH_TOKEN: Optional[str] = None
    JOB_API_APP_ID: Optional[str] = None
    JOB_API_TIMEOUT_SEC: int = 10
    JOB_API_USE_SIGV4: bool = False

    # External APIs
    ALPHA_VANTAGE_API_KEY: str = "demo"  # Default demo key
    EOD_FETCH_RETRY_COUNT: int = 3
    BINANCE_API_BASE_URL: str = "https://api.binance.com"
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_API_SECRET: Optional[str] = None
    BINANCE_FUTURES_API_KEY: Optional[str] = None
    BINANCE_FUTURES_API_SECRET: Optional[str] = None
    BINANCE_TIMEOUT_SECONDS: float = 10.0

    # Redis Configuration
    REDIS_HOST: str = ""
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_ENABLED: bool = True  # Feature flag for easy disable

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

    # Cooldown System Settings
    COOLDOWN_MINUTES: int = 5  # 자동 쿨다운 간격 (분)
    COOLDOWN_TRIGGER_THRESHOLD: int = 3  # 쿨다운 시작 임계값 (슬롯 개수)
    MAX_COOLDOWN_TIMERS_PER_DAY: int = 10  # 일일 쿨다운 타이머 생성 제한
    # COOLDOWN_WARMUP_OFFSET_MINUTES 제거됨 (Warmup 로직 제거)

    # Point Management
    CORRECT_PREDICTION_POINTS: int = 100  # 정답 예측 시 지급 포인트
    PREDICTION_FEE_POINTS: int = 10  # 예측 수수료
    SIGNUP_BONUS_POINTS: int = 1000  # 신규 가입 보너스 포인트
    VOID_REFUND_ENABLED: bool = True  # VOID 처리 시 수수료 환불 여부
    FLAT_PRICE_POLICY: str = (
        "ALL_WRONG"  # FLAT 가격일 때 처리 정책: ALL_WRONG | ALL_CORRECT | VOID
    )
    SETTLEMENT_TIMEOUT_MINUTES: int = 30  # 정산 작업 타임아웃 (분)

    # Range Prediction Settings (Asset-agnostic)
    ALLOWED_RANGE_SYMBOLS_CRYPTO: List[str] = ["BTCUSDT"]  # Allowed crypto symbols for RANGE
    ALLOWED_RANGE_SYMBOLS_STOCK: List[str] = []  # Allowed stock symbols for RANGE (future)
    RANGE_PREDICTION_TIME_WINDOW_HOURS: int = 1  # Time window for RANGE predictions (hours)

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

    # EventBridge → SQS delivery role (optional)
    EVENTBRIDGE_TARGET_ROLE_ARN: Optional[str] = (
        "arn:aws:iam::849441246713:role/service-role/Amazon_EventBridge_Invoke_Sqs_1118066146"
    )

    # EventBridge Scheduler → Lambda
    LAMBDA_FUNCTION_NAME: str = "ox-universe-lambda"
    SCHEDULER_TARGET_ROLE_ARN: Optional[str] = (
        "arn:aws:iam::849441246713:role/service-role/Amazon_EventBridge_Scheduler_LAMBDA_49a1ee802b"  # must allow lambda:InvokeFunction
    )
    SCHEDULER_GROUP_NAME: str = "default"

    # Batch dispatch mode: SQS | LAMBDA_INVOKE | LAMBDA_URL
    BATCH_DISPATCH_MODE: str = "SQS"
    # For LAMBDA_INVOKE mode
    LAMBDA_FUNCTION_NAME_DIRECT: str = "ox-universe-lambda"
    # For LAMBDA_URL mode (use IAM auth)
    LAMBDA_FUNCTION_URL: str | None = None
    LAMBDA_URL_TIMEOUT_SEC: int = 15
    # Internal auth forwarding when using Function URL (avoid clobbering AWS SigV4 Authorization header)
    # Using custom header to prevent conflict with Lambda IAM authentication
    INTERNAL_AUTH_HEADER: str = "x-internal-authorization"

    @property
    def api_base_url(self) -> str:
        """Return environment-appropriate API base URL for callbacks."""
        # Always use production URL (local도 production API 호출)
        return self.API_BASE_URL_PROD or self.API_BASE_URL

    @property
    def magic_link_base_url(self) -> str:
        """Return environment-appropriate magic link base URL."""
        env = (self.ENVIRONMENT or "").lower()

        if env in {"local", "development", "dev"}:
            url = self.MAGIC_LINK_BASE_URL_LOCAL or self.MAGIC_LINK_BASE_URL
            if url:
                return url

        if env in {"production", "prod", "staging"}:
            url = self.MAGIC_LINK_BASE_URL_PROD or self.MAGIC_LINK_BASE_URL
            if url:
                return url

        return self.MAGIC_LINK_BASE_URL

    @property
    def magic_link_client_redirect_url(self) -> str:
        """Return frontend redirect URL used after magic link verification."""
        env = (self.ENVIRONMENT or "").lower()

        if env in {"local", "development", "dev"}:
            url = (
                self.MAGIC_LINK_CLIENT_REDIRECT_URL_LOCAL
                or self.MAGIC_LINK_CLIENT_REDIRECT_URL
            )
            if url:
                return url

        if env in {"production", "prod", "staging"}:
            url = (
                self.MAGIC_LINK_CLIENT_REDIRECT_URL_PROD
                or self.MAGIC_LINK_CLIENT_REDIRECT_URL
            )
            if url:
                return url

        return self.MAGIC_LINK_CLIENT_REDIRECT_URL


settings = Settings()
