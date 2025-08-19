from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, List, Dict, Any, Type
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from pydantic import BaseModel

T = TypeVar('T')
SchemaType = TypeVar('SchemaType', bound=BaseModel)


class BaseRepository(Generic[T, SchemaType], ABC):
    """모든 리포지토리의 베이스 클래스 - Pydantic 응답 보장"""

    def __init__(self, model_class: Type[T], schema_class: Type[SchemaType], db: Session):
        self.model_class = model_class
        self.schema_class = schema_class
        self.db = db

    def _to_schema(self, model_instance: T) -> SchemaType:
        """SQLAlchemy 모델을 Pydantic 스키마로 변환"""
        if model_instance is None:
            return None
        
        # Convert SQLAlchemy model to dict and then to Pydantic
        model_dict = {}
        for column in model_instance.__table__.columns:
            model_dict[column.name] = getattr(model_instance, column.name)
        
        return self.schema_class(**model_dict)

    def get_by_id(self, id: Any) -> Optional[SchemaType]:
        """ID로 조회 - Pydantic 스키마 반환"""
        model_instance = self.db.query(self.model_class).filter(
            self.model_class.id == id
        ).first()
        return self._to_schema(model_instance)

    def get_by_field(self, field_name: str, value: Any) -> Optional[SchemaType]:
        """특정 필드로 조회 - Pydantic 스키마 반환"""
        model_instance = self.db.query(self.model_class).filter(
            getattr(self.model_class, field_name) == value
        ).first()
        return self._to_schema(model_instance)

    def find_all(
        self,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = None,
        offset: int = None
    ) -> List[SchemaType]:
        """조건에 맞는 모든 레코드 조회 - Pydantic 스키마 리스트 반환"""
        query = self.db.query(self.model_class)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)

        if order_by and hasattr(self.model_class, order_by):
            query = query.order_by(getattr(self.model_class, order_by))

        if offset:
            query = query.offset(offset)

        if limit:
            query = query.limit(limit)

        model_instances = query.all()
        return [self._to_schema(instance) for instance in model_instances]

    def create(self, **kwargs) -> SchemaType:
        """새 레코드 생성 - Pydantic 스키마 반환"""
        instance = self.model_class(**kwargs)
        self.db.add(instance)
        self.db.flush()
        self.db.refresh(instance)
        return self._to_schema(instance)

    def update(self, instance_id: Any, **kwargs) -> Optional[SchemaType]:
        """레코드 업데이트 - Pydantic 스키마 반환"""
        instance = self.db.query(self.model_class).filter(
            self.model_class.id == instance_id
        ).first()
        
        if not instance:
            return None
            
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        self.db.add(instance)
        self.db.flush()
        self.db.refresh(instance)
        return self._to_schema(instance)

    def delete(self, instance_id: Any) -> bool:
        """레코드 삭제"""
        instance = self.db.query(self.model_class).filter(
            self.model_class.id == instance_id
        ).first()
        
        if not instance:
            return False
            
        try:
            self.db.delete(instance)
            self.db.flush()
            return True
        except Exception:
            return False

    def count(self, filters: Dict[str, Any] = None) -> int:
        """레코드 수 조회"""
        query = self.db.query(self.model_class)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)

        return query.count()

    def exists(self, filters: Dict[str, Any]) -> bool:
        """레코드 존재 여부 확인"""
        query = self.db.query(self.model_class)

        for key, value in filters.items():
            if hasattr(self.model_class, key):
                query = query.filter(getattr(self.model_class, key) == value)

        return query.first() is not None