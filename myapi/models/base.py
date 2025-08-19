from sqlalchemy import Column, DateTime, func
from sqlalchemy.orm import declarative_base, declared_attr

Base = declarative_base()


class TimestampMixin:
    """타임스탬프 필드를 위한 믹스인"""

    @declared_attr
    def created_at(cls):
        return Column(DateTime(timezone=True), server_default=func.now())

    @declared_attr
    def updated_at(cls):
        return Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
        )


class BaseModel(Base, TimestampMixin):
    """모든 모델의 베이스 클래스"""

    __abstract__ = True

    def dict(self):
        """모델을 딕셔너리로 변환"""
        return {
            column.name: getattr(self, column.name) for column in self.__table__.columns
        }
