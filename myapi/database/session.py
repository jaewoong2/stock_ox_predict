from contextlib import contextmanager
from myapi.database.connection import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        if db.in_transaction():
            db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context():
    """컨텍스트 매니저를 사용한 데이터베이스 세션 관리"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
