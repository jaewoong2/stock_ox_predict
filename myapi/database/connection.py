from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from myapi.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # 연결 유효성 검사
    pool_recycle=3600,  # 1시간마다 연결 재생성
    echo=settings.DEBUG,  # 디버그 모드에서 SQL 로깅
    connect_args={"options": f"-csearch_path={settings.POSTGRES_SCHEMA}"},
)

# Use expire_on_commit=False to avoid DetachedInstanceError when accessing
# attributes after commit within the same request scope (common FastAPI pattern).
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)
