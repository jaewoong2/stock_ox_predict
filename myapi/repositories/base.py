from abc import ABC
from typing import TypeVar, Generic, Optional, List, Dict, Any, Type
from sqlalchemy.orm import Session
from pydantic import BaseModel

T = TypeVar("T")
SchemaType = TypeVar("SchemaType", bound=BaseModel)


class BaseRepository(Generic[T, SchemaType], ABC):
    """모든 리포지토리의 베이스 클래스 - Pydantic 응답 보장"""

    def __init__(
        self, model_class: Type[T], schema_class: Type[SchemaType], db: Session
    ):
        self.model_class = model_class
        self.schema_class = schema_class
        self.db = db

    def _to_schema(self, model_instance: Any) -> Optional[SchemaType]:
        """SQLAlchemy 모델을 Pydantic 스키마로 변환"""
        if model_instance is None:
            return None

        # Pydantic v2의 model_validate를 사용하여 from_attributes 활용
        try:
            return self.schema_class.model_validate(model_instance)
        except Exception:
            # fallback: 수동으로 dict 변환
            model_dict = {}
            if hasattr(model_instance, "__mapper__"):
                mapper = getattr(model_instance, "__mapper__", None)
                if mapper and hasattr(mapper, "columns"):
                    for column in mapper.columns:
                        column_name = getattr(column, "name", None)
                        if column_name:
                            model_dict[column_name] = getattr(
                                model_instance, column_name, None
                            )

            if not model_dict and hasattr(model_instance, "__dict__"):
                model_dict = getattr(model_instance, "__dict__", {})

            return self.schema_class(**model_dict)

    def _ensure_clean_session(self) -> None:
        """보류중/실패한 트랜잭션이 있으면 롤백하여 세션을 정상화"""
        try:
            if hasattr(self.db, "is_active") and not self.db.is_active:  # type: ignore[attr-defined]
                self.db.rollback()
        except Exception:
            pass

    def get_by_id(self, id: Any) -> Optional[SchemaType]:
        """ID로 조회 - Pydantic 스키마 반환"""
        self._ensure_clean_session()
        model_instance = (
            self.db.query(self.model_class)
            .filter(getattr(self.model_class, "id") == id)
            .first()
        )
        return self._to_schema(model_instance)

    def get_by_field(self, field_name: str, value: Any) -> Optional[SchemaType]:
        """특정 필드로 조회 - Pydantic 스키마 반환"""
        self._ensure_clean_session()
        model_instance = (
            self.db.query(self.model_class)
            .filter(getattr(self.model_class, field_name) == value)
            .first()
        )
        return self._to_schema(model_instance)

    def find_all(
        self,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[SchemaType]:
        """조건에 맞는 모든 레코드 조회 - Pydantic 스키마 리스트 반환"""
        self._ensure_clean_session()
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
        results = []
        for instance in model_instances:
            schema_instance = self._to_schema(instance)
            if schema_instance is not None:
                results.append(schema_instance)
        return results

    def create(self, **kwargs) -> Optional[SchemaType]:
        """새 레코드 생성 - Pydantic 스키마 반환"""
        self._ensure_clean_session()
        instance = self.model_class(**kwargs)
        self.db.add(instance)
        try:
            self.db.flush()
            self.db.refresh(instance)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self._to_schema(instance)

    def update(self, instance_id: Any, **kwargs) -> Optional[SchemaType]:
        """레코드 업데이트 - Pydantic 스키마 반환"""
        self._ensure_clean_session()
        instance = (
            self.db.query(self.model_class)
            .filter(getattr(self.model_class, "id") == instance_id)
            .first()
        )

        if not instance:
            return None

        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        self.db.add(instance)
        try:
            self.db.flush()
            self.db.refresh(instance)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self._to_schema(instance)

    def delete(self, instance_id: Any) -> bool:
        """레코드 삭제"""
        self._ensure_clean_session()
        instance = (
            self.db.query(self.model_class)
            .filter(getattr(self.model_class, "id") == instance_id)
            .first()
        )

        if not instance:
            return False

        try:
            self.db.delete(instance)
            self.db.flush()
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """레코드 수 조회"""
        self._ensure_clean_session()
        query = self.db.query(self.model_class)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)

        return query.count()

    def exists(self, filters: Dict[str, Any]) -> bool:
        """레코드 존재 여부 확인"""
        self._ensure_clean_session()
        query = self.db.query(self.model_class)

        for key, value in filters.items():
            if hasattr(self.model_class, key):
                query = query.filter(getattr(self.model_class, key) == value)

        return query.first() is not None
