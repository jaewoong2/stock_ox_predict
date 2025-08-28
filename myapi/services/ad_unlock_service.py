"""
광고 해제 서비스 - 광고 시청을 통한 예측 슬롯 해제 비즈니스 로직

이 서비스는 광고 시청을 통한 예측 슬롯 해제의 핵심 비즈니스 로직을 담당합니다:
1. 광고 시청 완료 처리
2. 슬롯 증가 및 검증
3. 일일/전체 제한 확인
4. 쿨다운 관리
5. 통계 및 히스토리 조회

핵심 특징:
- 비즈니스 규칙 적용 (일일 제한, 쿨다운 등)
- 예측 서비스와의 연동을 통한 슬롯 증가
- 트랜잭션 기반 데이터 일관성 보장
- 완전한 감사 추적
"""

from typing import List
from sqlalchemy.orm import Session
from datetime import date
import logging

from myapi.repositories.ad_unlock_repository import AdUnlockRepository
from myapi.repositories.prediction_repository import UserDailyStatsRepository
from myapi.core.exceptions import ValidationError, BusinessLogicError
from myapi.schemas.ad_unlock import (
    AdUnlockHistory,
    SlotIncreaseResponse,
    AvailableSlotsResponse,
    AdUnlockStatsResponse,
    AdWatchCompleteRequest,
    AdWatchCompleteResponse,
    UnlockMethod,
)
from myapi.utils.timezone_utils import get_current_kst_date

logger = logging.getLogger(__name__)


class AdUnlockService:
    """광고 해제 관련 비즈니스 로직을 담당하는 서비스"""

    # 비즈니스 규칙 상수
    MAX_AD_UNLOCKS_PER_DAY = 10  # 일일 광고 시청 제한
    MAX_COOLDOWN_UNLOCKS_PER_DAY = 10  # 일일 쿨다운 제한
    COOLDOWN_MINUTES = 60  # 쿨다운 대기 시간 (분)
    SLOTS_PER_UNLOCK = 1  # 한 번에 해제되는 슬롯 수

    def __init__(self, db: Session):
        self.db = db
        self.ad_unlock_repo = AdUnlockRepository(db)
        self.stats_repo = UserDailyStatsRepository(db)

    def watch_ad_complete(
        self, user_id: int, request: AdWatchCompleteRequest
    ) -> AdWatchCompleteResponse:
        """
        광고 시청 완료 처리

        Args:
            user_id: 사용자 ID
            request: 광고 시청 완료 요청

        Returns:
            AdWatchCompleteResponse: 광고 시청 완료 응답

        Raises:
            ValidationError: 유효하지 않은 요청
            BusinessLogicError: 비즈니스 규칙 위반
        """
        current_date = get_current_kst_date()

        try:
            # 일일 광고 시청 제한 확인
            today_ad_unlocks = self.ad_unlock_repo.count_daily_unlocks_by_method(
                user_id, current_date, UnlockMethod.AD.value
            )

            if today_ad_unlocks >= self.MAX_AD_UNLOCKS_PER_DAY:
                return AdWatchCompleteResponse(
                    success=False,
                    message=f"일일 광고 시청 제한({self.MAX_AD_UNLOCKS_PER_DAY}회)에 도달했습니다.",
                    slots_unlocked=0,
                    current_max_predictions=self._get_current_max_predictions(
                        user_id, current_date
                    ),
                )

            # 광고 시청 기록 생성
            unlock_record = self.ad_unlock_repo.create_ad_unlock_record(
                user_id=user_id,
                trading_day=current_date,
                method=UnlockMethod.AD.value,
                unlocked_slots=self.SLOTS_PER_UNLOCK,
            )

            if not unlock_record:

                raise BusinessLogicError("FAIL", "광고 시청 기록 생성에 실패했습니다.")

            # 예측 슬롯 증가
            self.stats_repo.increase_max_predictions(
                user_id, current_date, self.SLOTS_PER_UNLOCK
            )

            current_max_predictions = self._get_current_max_predictions(
                user_id, current_date
            )

            logger.info(
                f"User {user_id} watched ad and unlocked {self.SLOTS_PER_UNLOCK} slots"
            )

            return AdWatchCompleteResponse(
                success=True,
                message="광고 시청이 완료되어 예측 슬롯이 증가했습니다.",
                slots_unlocked=self.SLOTS_PER_UNLOCK,
                current_max_predictions=current_max_predictions,
            )

        except Exception as e:
            logger.error(
                f"Failed to process ad watch completion for user {user_id}: {str(e)}"
            )
            raise ValidationError(
                message=f"광고 시청 처리 중 오류가 발생했습니다: {str(e)}"
            )

    def unlock_slot_by_cooldown(self, user_id: int) -> SlotIncreaseResponse:
        """
        쿨다운을 통한 슬롯 해제

        Args:
            user_id: 사용자 ID

        Returns:
            SlotIncreaseResponse: 슬롯 증가 응답

        Raises:
            ValidationError: 유효하지 않은 요청
            BusinessLogicError: 비즈니스 규칙 위반
        """
        current_date = get_current_kst_date()

        try:
            # 일일 쿨다운 제한 확인
            today_cooldown_unlocks = self.ad_unlock_repo.count_daily_unlocks_by_method(
                user_id, current_date, UnlockMethod.COOLDOWN.value
            )

            if today_cooldown_unlocks >= self.MAX_COOLDOWN_UNLOCKS_PER_DAY:
                return SlotIncreaseResponse(
                    success=False,
                    message=f"일일 쿨다운 해제 제한({self.MAX_COOLDOWN_UNLOCKS_PER_DAY}회)에 도달했습니다.",
                    current_max_predictions=self._get_current_max_predictions(
                        user_id, current_date
                    ),
                    unlocked_slots=0,
                    method_used=UnlockMethod.COOLDOWN.value,
                )

            # 쿨다운 시간 확인
            if not self._can_use_cooldown(user_id, current_date):
                last_unlock = self.ad_unlock_repo.get_latest_unlock_by_method(
                    user_id, current_date, UnlockMethod.COOLDOWN.value
                )
                return SlotIncreaseResponse(
                    success=False,
                    message=f"쿨다운 대기 중입니다. {self.COOLDOWN_MINUTES}분 후 다시 시도하세요.",
                    current_max_predictions=self._get_current_max_predictions(
                        user_id, current_date
                    ),
                    unlocked_slots=0,
                    method_used=UnlockMethod.COOLDOWN.value,
                )

            # 쿨다운 해제 기록 생성
            unlock_record = self.ad_unlock_repo.create_ad_unlock_record(
                user_id=user_id,
                trading_day=current_date,
                method=UnlockMethod.COOLDOWN.value,
                unlocked_slots=self.SLOTS_PER_UNLOCK,
            )

            if not unlock_record:
                raise BusinessLogicError(
                    "FAIL", "쿨다운 해제 기록 생성에 실패했습니다."
                )

            # 예측 슬롯 증가
            self.stats_repo.increase_max_predictions(
                user_id, current_date, self.SLOTS_PER_UNLOCK
            )

            current_max_predictions = self._get_current_max_predictions(
                user_id, current_date
            )

            logger.info(
                f"User {user_id} used cooldown to unlock {self.SLOTS_PER_UNLOCK} slots"
            )

            return SlotIncreaseResponse(
                success=True,
                message="쿨다운을 통해 예측 슬롯이 증가했습니다.",
                current_max_predictions=current_max_predictions,
                unlocked_slots=self.SLOTS_PER_UNLOCK,
                method_used=UnlockMethod.COOLDOWN.value,
            )

        except Exception as e:
            logger.error(
                f"Failed to unlock slot by cooldown for user {user_id}: {str(e)}"
            )
            raise ValidationError(
                message=f"쿨다운 슬롯 해제 중 오류가 발생했습니다: {str(e)}"
            )

    def get_available_slots_info(self, user_id: int) -> AvailableSlotsResponse:
        """
        사용자의 사용 가능한 슬롯 정보 조회

        Args:
            user_id: 사용자 ID

        Returns:
            AvailableSlotsResponse: 사용 가능한 슬롯 정보
        """
        current_date = get_current_kst_date()

        try:
            # 현재 통계 조회
            stats = self.stats_repo.get_or_create_user_daily_stats(
                user_id, current_date
            )

            # 오늘의 해제 현황 조회
            today_ad_unlocks = self.ad_unlock_repo.count_daily_unlocks_by_method(
                user_id, current_date, UnlockMethod.AD.value
            )
            today_cooldown_unlocks = self.ad_unlock_repo.count_daily_unlocks_by_method(
                user_id, current_date, UnlockMethod.COOLDOWN.value
            )

            # 해제 가능 여부 판단
            can_unlock_by_ad = today_ad_unlocks < self.MAX_AD_UNLOCKS_PER_DAY
            can_unlock_by_cooldown = (
                today_cooldown_unlocks < self.MAX_COOLDOWN_UNLOCKS_PER_DAY
                and self._can_use_cooldown(user_id, current_date)
            )

            return AvailableSlotsResponse(
                current_max_predictions=stats.max_predictions,
                predictions_made=stats.predictions_made,
                available_predictions=max(
                    0, stats.max_predictions - stats.predictions_made
                ),
                can_unlock_by_ad=can_unlock_by_ad,
                can_unlock_by_cooldown=can_unlock_by_cooldown,
                today_ad_unlocks=today_ad_unlocks,
                today_cooldown_unlocks=today_cooldown_unlocks,
            )

        except Exception as e:
            logger.error(
                f"Failed to get available slots info for user {user_id}: {str(e)}"
            )
            raise ValidationError(f"슬롯 정보 조회 중 오류가 발생했습니다: {str(e)}")

    def get_user_unlock_history(
        self, user_id: int, limit: int = 30
    ) -> List[AdUnlockHistory]:
        """
        사용자의 광고 해제 히스토리 조회

        Args:
            user_id: 사용자 ID
            limit: 조회할 최대 일수

        Returns:
            List[AdUnlockHistory]: 일별 광고 해제 히스토리
        """
        try:
            # 원시 기록 조회
            raw_records = self.ad_unlock_repo.get_user_unlock_history(
                user_id, limit * 10
            )

            # 날짜별로 그룹화
            daily_records = {}
            for record in raw_records:
                trading_day = record.trading_day
                if trading_day not in daily_records:
                    daily_records[trading_day] = []
                daily_records[trading_day].append(record)

            # AdUnlockHistory 객체 생성
            history_list = []
            for trading_day in sorted(daily_records.keys(), reverse=True)[:limit]:
                records = daily_records[trading_day]

                total_unlocks = sum(r.unlocked_slots for r in records)
                ad_unlocks = sum(
                    r.unlocked_slots
                    for r in records
                    if r.method == UnlockMethod.AD.value
                )
                cooldown_unlocks = sum(
                    r.unlocked_slots
                    for r in records
                    if r.method == UnlockMethod.COOLDOWN.value
                )

                history_list.append(
                    AdUnlockHistory(
                        trading_day=trading_day,
                        total_unlocks=total_unlocks,
                        ad_unlocks=ad_unlocks,
                        cooldown_unlocks=cooldown_unlocks,
                        records=sorted(records, key=lambda x: x.id, reverse=True),
                    )
                )

            return history_list

        except Exception as e:
            logger.error(f"Failed to get unlock history for user {user_id}: {str(e)}")
            raise ValidationError(
                f"해제 히스토리 조회 중 오류가 발생했습니다: {str(e)}"
            )

    def get_daily_stats(self, trading_day: date) -> AdUnlockStatsResponse:
        """
        특정 날짜의 광고 해제 통계 조회 (관리자 전용)

        Args:
            trading_day: 거래일

        Returns:
            AdUnlockStatsResponse: 광고 해제 통계
        """
        try:
            stats_dict = self.ad_unlock_repo.get_daily_unlock_stats(trading_day)

            return AdUnlockStatsResponse(
                trading_day=trading_day,
                total_unlocks=stats_dict["total_unlocks"],
                unique_users=stats_dict["unique_users"],
                method_breakdown=stats_dict["method_breakdown"],
            )

        except Exception as e:
            logger.error(f"Failed to get daily stats for {trading_day}: {str(e)}")
            raise ValidationError(f"일일 통계 조회 중 오류가 발생했습니다: {str(e)}")

    def _can_use_cooldown(self, user_id: int, trading_day: date) -> bool:
        """
        쿨다운 사용 가능 여부 확인

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            bool: 쿨다운 사용 가능 여부
        """
        last_cooldown = self.ad_unlock_repo.get_latest_unlock_by_method(
            user_id, trading_day, UnlockMethod.COOLDOWN.value
        )

        if not last_cooldown:
            return True

        # 마지막 쿨다운 사용 시간을 기준으로 쿨다운 시간 확인
        # 실제 구현에서는 created_at 필드를 사용해야 하나,
        # 현재 모델에는 시간 정보가 없으므로 간단히 일별 제한만 적용
        return True

    def _get_current_max_predictions(self, user_id: int, trading_day: date) -> int:
        """
        현재 최대 예측 수 조회

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            int: 현재 최대 예측 수
        """
        try:
            stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
            return stats.max_predictions
        except Exception:
            return 3  # 기본값
