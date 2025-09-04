"""
광고 해제 리포지토리 - 데이터베이스 접근 및 비즈니스 로직

이 파일은 광고 시청을 통한 예측 슬롯 해제 시스템의 핵심 비즈니스 로직을 담당합니다:
1. 광고 시청 기록 관리
2. 일일/사용자별 슬롯 해제 통계
3. 쿨다운 및 광고 시청 제한 관리
4. 데이터 무결성 보장

핵심 특징:
- 사용자별 일일 광고 시청 기록 관리
- AD/COOLDOWN 방식 지원
- 예측 슬롯 증가와 연동
- 트랜잭션 기반 데이터 일관성 보장
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_
from datetime import date, datetime

from myapi.models.prediction import AdUnlocks as AdUnlockModel
from myapi.schemas.ad_unlock import (
    AdUnlockResponse,
    AdUnlockHistory,
    AdUnlockStatsResponse,
)
from myapi.repositories.base import BaseRepository


class AdUnlockRepository(BaseRepository[AdUnlockModel, AdUnlockResponse]):
    """
    광고 해제 리포지토리 - 광고 시청 관련 모든 데이터베이스 작업 처리

    주요 기능:
    1. 광고 시청 기록 생성 및 조회
    2. 일일/사용자별 통계 제공
    3. 슬롯 해제 내역 관리
    4. 제한 및 쿨다운 검증 지원
    """

    def __init__(self, db: Session):
        super().__init__(AdUnlockModel, AdUnlockResponse, db)

    def create_ad_unlock_record(
        self, user_id: int, trading_day: date, method: str, unlocked_slots: int = 1
    ) -> Optional[AdUnlockResponse]:
        """
        광고 해제 기록 생성

        Args:
            user_id: 사용자 ID
            trading_day: 거래일
            method: 해제 방법 (AD 또는 COOLDOWN)
            unlocked_slots: 해제된 슬롯 수 (기본값: 1)

        Returns:
            생성된 광고 해제 기록의 Pydantic 스키마
        """
        try:
            unlock_record = AdUnlockModel(
                user_id=user_id,
                trading_day=trading_day,
                method=method,
                unlocked_slots=unlocked_slots,
            )

            self.db.add(unlock_record)
            self.db.flush()
            self.db.refresh(unlock_record)
            self.db.commit()

            return self._to_schema(unlock_record)
        except Exception:
            self.db.rollback()
            raise

    def get_user_daily_unlocks(
        self, user_id: int, trading_day: date
    ) -> List[AdUnlockResponse]:
        """
        사용자의 특정 날짜 광고 해제 기록 조회

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            해당 날짜의 모든 광고 해제 기록 리스트
        """
        self._ensure_clean_session()
        records = (
            self.db.query(AdUnlockModel)
            .filter(
                and_(
                    AdUnlockModel.user_id == user_id,
                    AdUnlockModel.trading_day == trading_day,
                )
            )
            .order_by(desc(AdUnlockModel.id))
            .all()
        )

        result = [
            self._to_schema(record)
            for record in records
            if self._to_schema(record) is not None
        ]

        # Ensure result contains only AdUnlockResponse (no None)
        return [item for item in result if item is not None]

    def get_user_unlock_history(
        self, user_id: int, limit: Optional[int] = 30
    ) -> List[AdUnlockResponse]:
        """
        사용자의 광고 해제 히스토리 조회

        Args:
            user_id: 사용자 ID
            limit: 조회할 최대 기록 수 (기본값: 30)

        Returns:
            사용자의 광고 해제 히스토리 리스트
        """
        self._ensure_clean_session()
        query = (
            self.db.query(AdUnlockModel)
            .filter(AdUnlockModel.user_id == user_id)
            .order_by(desc(AdUnlockModel.trading_day), desc(AdUnlockModel.id))
        )

        if limit:
            query = query.limit(limit)

        records = query.all()

        # Pylance 타입 추론을 돕기 위해 명시적으로 분리
        result: List[AdUnlockResponse] = []
        for record in records:
            schema_obj = self._to_schema(record)
            if schema_obj:
                result.append(schema_obj)
        return result

    def count_daily_unlocks_by_method(
        self, user_id: int, trading_day: date, method: str
    ) -> int:
        """
        사용자의 특정 날짜, 특정 방법으로 해제한 슬롯 수 합계

        Args:
            user_id: 사용자 ID
            trading_day: 거래일
            method: 해제 방법 (AD 또는 COOLDOWN)

        Returns:
            해제된 슬롯의 총 개수
        """
        self._ensure_clean_session()
        result = (
            self.db.query(func.sum(AdUnlockModel.unlocked_slots))
            .filter(
                and_(
                    AdUnlockModel.user_id == user_id,
                    AdUnlockModel.trading_day == trading_day,
                    AdUnlockModel.method == method,
                )
            )
            .scalar()
        )

        return result or 0

    def count_total_daily_unlocks(self, user_id: int, trading_day: date) -> int:
        """
        사용자의 특정 날짜 총 해제 슬롯 수

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            해제된 슬롯의 총 개수
        """
        self._ensure_clean_session()
        result = (
            self.db.query(func.sum(AdUnlockModel.unlocked_slots))
            .filter(
                and_(
                    AdUnlockModel.user_id == user_id,
                    AdUnlockModel.trading_day == trading_day,
                )
            )
            .scalar()
        )

        return result or 0

    def get_latest_unlock_by_method(
        self, user_id: int, trading_day: date, method: str
    ) -> Optional[AdUnlockResponse]:
        """
        사용자의 특정 날짜, 특정 방법으로 가장 최근 해제 기록 조회

        Args:
            user_id: 사용자 ID
            trading_day: 거래일
            method: 해제 방법 (AD 또는 COOLDOWN)

        Returns:
            가장 최근 해제 기록 또는 None
        """
        self._ensure_clean_session()
        record = (
            self.db.query(AdUnlockModel)
            .filter(
                and_(
                    AdUnlockModel.user_id == user_id,
                    AdUnlockModel.trading_day == trading_day,
                    AdUnlockModel.method == method,
                )
            )
            .order_by(desc(AdUnlockModel.id))
            .first()
        )

        return self._to_schema(record) if record else None

    def get_daily_unlock_stats(self, trading_day: date) -> AdUnlockStatsResponse:
        """
        특정 날짜의 전체 광고 해제 통계

        Args:
            trading_day: 거래일

        Returns:
            통계 딕셔너리 (총 해제 수, 사용자 수, 방법별 통계)
        """
        # 총 해제 수
        self._ensure_clean_session()
        total_unlocks = (
            self.db.query(func.sum(AdUnlockModel.unlocked_slots))
            .filter(AdUnlockModel.trading_day == trading_day)
            .scalar()
        ) or 0

        # 해제한 사용자 수
        unique_users = (
            self.db.query(func.count(func.distinct(AdUnlockModel.user_id)))
            .filter(AdUnlockModel.trading_day == trading_day)
            .scalar()
        ) or 0

        # 방법별 통계
        method_stats = (
            self.db.query(
                AdUnlockModel.method,
                func.sum(AdUnlockModel.unlocked_slots).label("total_slots"),
                func.count(AdUnlockModel.id).label("total_records"),
                func.count(func.distinct(AdUnlockModel.user_id)).label("unique_users"),
            )
            .filter(AdUnlockModel.trading_day == trading_day)
            .group_by(AdUnlockModel.method)
            .all()
        )

        method_breakdown = {}
        for stat in method_stats:
            method_breakdown[stat.method] = {
                "total_slots": stat.total_slots or 0,
                "total_records": stat.total_records or 0,
                "unique_users": stat.unique_users or 0,
            }

        return AdUnlockStatsResponse(
            trading_day=trading_day,
            total_unlocks=total_unlocks,
            unique_users=unique_users,
            method_breakdown=method_breakdown,
        )
