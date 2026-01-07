from datetime import date, datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from myapi.models.crypto_prediction import (
    CryptoBandPrediction,
    CryptoBandPredictionStatus,
)
from myapi.repositories.base import BaseRepository
from myapi.schemas.crypto_prediction import (
    CryptoBandPredictionListResponse,
    CryptoBandPredictionSchema,
)


class CryptoBandPredictionRepository(
    BaseRepository[CryptoBandPrediction, CryptoBandPredictionSchema]
):
    """가격 밴드 예측 리포지토리 (Pydantic 스키마 반환)."""

    def __init__(self, db: Session):
        super().__init__(CryptoBandPrediction, CryptoBandPredictionSchema, db)

    def prediction_exists(self, user_id: int, target_open_time_ms: int, row: int) -> bool:
        """동일 유저/타겟 시간/행(row) 조합 중복 여부."""
        self._ensure_clean_session()
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.target_open_time_ms == target_open_time_ms,
                    self.model_class.row == row,
                )
            )
            .first()
            is not None
        )

    def create_prediction(
        self,
        *,
        user_id: int,
        trading_day: date,
        symbol: str,
        interval: str,
        future_col: int,
        row: int,
        target_open_time_ms: int,
        target_close_time_ms: int,
        p0,
        band_pct_low,
        band_pct_high,
        band_price_low,
        band_price_high,
    ) -> Optional[CryptoBandPredictionSchema]:
        """신규 예측 생성."""
        return self.create(
            user_id=user_id,
            trading_day=trading_day,
            symbol=symbol,
            interval=interval,
            future_col=future_col,
            row=row,
            target_open_time_ms=target_open_time_ms,
            target_close_time_ms=target_close_time_ms,
            p0=p0,
            band_pct_low=band_pct_low,
            band_pct_high=band_pct_high,
            band_price_low=band_price_low,
            band_price_high=band_price_high,
            status=CryptoBandPredictionStatus.PENDING,
            settlement_attempts=0,
        )

    def list_user_predictions(
        self,
        user_id: int,
        symbol: str,
        interval: str,
        *,
        limit: int,
        offset: int,
    ) -> CryptoBandPredictionListResponse:
        """사용자 예측 목록 조회 (최근순)."""
        self._ensure_clean_session()
        query = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.symbol == symbol,
                    self.model_class.interval == interval,
                )
            )
            .order_by(desc(self.model_class.created_at))
        )
        total_count = query.count()
        items = query.limit(limit + 1).offset(offset).all()

        schemas: List[CryptoBandPredictionSchema] = [
            schema for schema in (self._to_schema(item) for item in items) if schema
        ]
        has_next = len(schemas) > limit
        predictions = schemas[:limit]

        return CryptoBandPredictionListResponse(
            predictions=predictions,
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_next=has_next,
        )

    def get_pending_for_settlement(
        self, *, now_ms: int, max_attempts: int, limit: int = 100
    ) -> List[CryptoBandPredictionSchema]:
        """정산 대상 pending 예측 조회."""
        self._ensure_clean_session()
        items = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.status == CryptoBandPredictionStatus.PENDING,
                    self.model_class.target_close_time_ms <= now_ms,
                    self.model_class.settlement_attempts < max_attempts,
                )
            )
            .order_by(self.model_class.target_close_time_ms)
            .limit(limit)
            .all()
        )
        return [schema for schema in (self._to_schema(item) for item in items) if schema]

    def update_status(
        self,
        prediction_id: int,
        status: CryptoBandPredictionStatus,
        *,
        settlement_price=None,
        last_error: Optional[str] = None,
    ) -> Optional[CryptoBandPredictionSchema]:
        """정산 결과 업데이트."""
        self._ensure_clean_session()
        instance = (
            self.db.query(self.model_class)
            .filter(self.model_class.id == prediction_id)
            .first()
        )
        if not instance:
            return None

        instance.status = status
        instance.settlement_price = settlement_price
        instance.last_error = last_error
        instance.last_settlement_at = datetime.now(timezone.utc)
        instance.settlement_attempts = getattr(instance, "settlement_attempts", 0) + 1

        try:
            self.db.flush()
            self.db.refresh(instance)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return self._to_schema(instance)

    def mark_attempt_failed(
        self, prediction_id: int, *, last_error: str, mark_error: bool = False
    ) -> Optional[CryptoBandPredictionSchema]:
        """정산 시도 실패 (재시도 또는 ERROR 전환)."""
        self._ensure_clean_session()
        instance = (
            self.db.query(self.model_class)
            .filter(self.model_class.id == prediction_id)
            .first()
        )
        if not instance:
            return None

        instance.settlement_attempts = getattr(instance, "settlement_attempts", 0) + 1
        instance.last_error = last_error
        instance.last_settlement_at = datetime.now(timezone.utc)
        if mark_error:
            instance.status = CryptoBandPredictionStatus.ERROR

        try:
            self.db.flush()
            self.db.refresh(instance)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return self._to_schema(instance)
