import sys
import os

from models.base import Base

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.declarative import declarative_base
from myapi.database.connection import engine
from myapi.config import settings


def init_db():
    """데이터베이스 초기화"""
    try:
        # 스키마 생성
        with engine.connect() as conn:
            conn.execute(
                text(f"CREATE SCHEMA IF NOT EXISTS {settings.POSTGRES_SCHEMA}")
            )
            conn.commit()

        # 테이블 생성
        Base.metadata.create_all(bind=engine)
        print(
            f"Database initialized successfully with schema: {settings.POSTGRES_SCHEMA}"
        )

    except Exception as e:
        print(f"Database initialization failed: {str(e)}")
        raise


if __name__ == "__main__":
    init_db()
