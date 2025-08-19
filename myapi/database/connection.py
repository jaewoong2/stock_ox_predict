from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from myapi.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    connect_args={"options": f"-csearch_path={settings.POSTGRES_SCHEMA}"},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
