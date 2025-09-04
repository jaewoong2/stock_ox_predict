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
        except Exception as e:
            # fallback: 수동으로 dict 변환
            model_dict = {}

            # SQLAlchemy 모델의 모든 속성 추출
            if hasattr(model_instance, "__mapper__"):
                mapper = getattr(model_instance, "__mapper__", None)
                if mapper and hasattr(mapper, "columns"):
                    for column in mapper.columns:
                        column_name = getattr(column, "name", None)
                        if column_name:
                            value = getattr(model_instance, column_name, None)
                            # None이 아닌 값만 포함
                            if value is not None:
                                model_dict[column_name] = value

            # __dict__에서도 속성 추출 (SQLAlchemy 내부 속성 제외)
            if hasattr(model_instance, "__dict__"):
                for key, value in model_instance.__dict__.items():
                    if not key.startswith("_") and key not in model_dict:
                        model_dict[key] = value

            # Pydantic 스키마 생성 시도
            try:
                return self.schema_class(**model_dict)
            except Exception:
                # 최종 fallback: 에러 정보와 함께 실패
                raise ValueError(
                    f"Failed to convert model to schema: {e}. Model dict: {model_dict}"
                )

    def _ensure_clean_session(self) -> None:
        """보류중/실패한 트랜잭션이 있으면 롤백하여 세션을 정상화"""
        try:
            # 1) 세션 레벨 실패 상태 감지
            is_active = getattr(self.db, "is_active", True)
            if not is_active:
                self.db.rollback()
                return

            # 2) 트랜잭션 객체 상태 감지 (활성 아님 = 실패/종료 상태)
            get_tx = getattr(self.db, "get_transaction", None)
            if callable(get_tx):
                tx = get_tx()
                tx_is_active = getattr(tx, "is_active", None)
                if tx is not None and tx_is_active is not None and not tx_is_active:
                    self.db.rollback()
                    return

            # 3) 트랜잭션이 열려 있다면 방어적으로 롤백 (잉여 실패 상태 방지)
            in_tx = getattr(self.db, "in_transaction", None)
            if callable(in_tx) and in_tx():
                self.db.rollback()
                return
        except Exception:
            # 세션/트랜잭션 점검 중 예외는 무시 (안전 우선)
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

    def create(self, commit: bool = True, **kwargs) -> Optional[SchemaType]:
        """새 레코드 생성 - Pydantic 스키마 반환"""
        self._ensure_clean_session()
        instance = self.model_class(**kwargs)
        self.db.add(instance)
        try:
            self.db.flush()
            self.db.refresh(instance)
            if commit:
                self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self._to_schema(instance)

    def update(
        self, instance_id: Any, commit: bool = True, **kwargs
    ) -> Optional[SchemaType]:
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
            if commit:
                self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self._to_schema(instance)

    def delete(self, instance_id: Any, commit: bool = True) -> bool:
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
            if commit:
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
