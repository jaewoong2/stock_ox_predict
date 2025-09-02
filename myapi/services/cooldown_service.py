from datetime import date, datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from myapi.repositories.cooldown_repository import CooldownRepository
from myapi.services.aws_service import AwsService
from myapi.schemas.cooldown import SlotRefillMessage, CooldownStatusResponse
from myapi.core.exceptions import BusinessLogicError, ValidationError
from myapi.utils.timezone_utils import get_current_kst_date
from myapi.utils.market_hours import USMarketHours
from myapi.config import Settings, settings
from myapi.repositories.prediction_repository import UserDailyStatsRepository
from myapi.schemas.cooldown import CooldownTimerSchema
import logging

logger = logging.getLogger(__name__)


class CooldownService:
    """자동 쿨다운 타이머 관리 서비스"""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.cooldown_repo = CooldownRepository(db)
        self.stats_repo = UserDailyStatsRepository(db)
        self.aws_service = AwsService(settings)

    async def start_auto_cooldown(self, user_id: int, trading_day: date) -> bool:
        """
        자동 쿨다운 타이머 시작

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            bool: 쿨다운 시작 성공 여부

        Raises:
            BusinessLogicError: 비즈니스 규칙 위반
            ValidationError: 유효하지 않은 요청
        """
        try:
            # 1. 활성 타이머 중복 확인 (일일 제한 없음)
            active_timer: Optional[CooldownTimerSchema] = (
                self.cooldown_repo.get_active_timer(user_id, trading_day)
            )
            if active_timer:
                logger.warning(f"User {user_id} already has active cooldown timer")
                return False

            # 2. 현재 슬롯 수 및 임계값 확인 (동적 임계값: 현재 최대 허용치보다 클 수 없음)
            current_slots = self._get_available_slots(user_id, trading_day)
            stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
            threshold = 3  # 정책: 쿨다운 트리거/회복 임계값은 3
            if current_slots > threshold:
                logger.info(
                    f"User {user_id} has enough slots ({current_slots} > {threshold}), no cooldown needed"
                )
                return False

            # 3. 스케줄 시간 계산
            now = USMarketHours.get_current_kst_time()
            scheduled_at = now + timedelta(minutes=settings.COOLDOWN_MINUTES)

            # 4. DB에 타이머 생성
            timer: Optional[CooldownTimerSchema] = (
                self.cooldown_repo.create_cooldown_timer(
                    user_id=user_id,
                    trading_day=trading_day,
                    scheduled_at=scheduled_at,
                    slots_to_refill=1,
                )
            )

            if not timer:
                raise BusinessLogicError(
                    "TIMER_CREATE_FAILED", "쿨다운 타이머 생성에 실패했습니다."
                )

            timer_id = int(timer.id)
            # 5. SQS 메시지 준비
            message_body = SlotRefillMessage(
                user_id=user_id,
                timer_id=timer_id,
                trading_day=trading_day.isoformat(),
                slots_to_refill=1,
            ).model_dump()

            # 6. EventBridge 스케줄링
            rule_arn = self.aws_service.schedule_one_time_event(
                delay_minutes=settings.COOLDOWN_MINUTES,
                target_queue_url=settings.SQS_MAIN_QUEUE_URL,
                message_body=message_body,
                message_group_id="cooldown",
                rule_name_prefix=f"cooldown-{user_id}",
            )

            # 7. ARN 업데이트
            self.cooldown_repo.update_timer_arn(timer_id, rule_arn)

            logger.info(
                f"Started auto cooldown for user {user_id}, timer_id: {timer_id}, "
                f"scheduled_at: {scheduled_at}, rule_arn: {rule_arn}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to start auto cooldown for user {user_id}: {str(e)}")
            raise ValidationError(f"자동 쿨다운 시작 중 오류가 발생했습니다: {str(e)}")

    async def handle_cooldown_completion(self, timer_id: int) -> bool:
        """
        쿨다운 완료 처리 (SQS 메시지 핸들러에서 호출)

        Args:
            timer_id: 완료할 타이머 ID

        Returns:
            bool: 처리 성공 여부
        """
        try:
            # 1. 타이머 조회
            timer: Optional[CooldownTimerSchema] = self.cooldown_repo.get_by_id(
                timer_id
            )
            if not timer or timer.status != "ACTIVE":
                logger.warning(f"Timer {timer_id} not found or not active")
                return False

            # 2. 현재 슬롯 수 확인
            current_slots = self._get_available_slots(timer.user_id, timer.trading_day)

            # 3. 슬롯 충전 (임계값 이하일 때만, 쿨다운은 최대 3까지만 회복)
            threshold = 3  # 정책: 쿨다운 트리거/회복 임계값은 3
            if current_slots <= threshold:
                # 쿨다운 회복: 3 미만일 때만 +1 (최대 3)
                self.stats_repo.refill_by_cooldown(
                    timer.user_id, timer.trading_day, timer.slots_to_refill
                )
                logger.info(
                    f"Refilled {timer.slots_to_refill} slots for user {timer.user_id}"
                )

            # 4. 타이머 완료 처리
            self.cooldown_repo.complete_timer(timer_id)

            # 5. 아직 슬롯이 부족하면 다음 쿨다운 시작
            updated_slots = self._get_available_slots(timer.user_id, timer.trading_day)
            threshold = 3  # 정책: 쿨다운 트리거/회복 임계값은 3
            if updated_slots <= threshold:
                await self.start_auto_cooldown(timer.user_id, timer.trading_day)

            return True

        except Exception as e:
            logger.error(
                f"Failed to handle cooldown completion for timer {timer_id}: {str(e)}"
            )
            return False

    def cancel_active_cooldown(self, user_id: int, trading_day: date) -> bool:
        """
        활성 쿨다운 취소

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            bool: 취소 성공 여부
        """
        try:
            active_timer: Optional[CooldownTimerSchema] = (
                self.cooldown_repo.get_active_timer(user_id, trading_day)
            )
            if not active_timer:
                return True  # 이미 활성 타이머 없음

            # EventBridge 규칙 취소
            if active_timer.eventbridge_rule_arn:
                self.aws_service.cancel_scheduled_event(
                    str(active_timer.eventbridge_rule_arn)
                )

            # 타이머 취소 처리
            self.cooldown_repo.cancel_timer(active_timer.id)

            logger.info(
                f"Cancelled cooldown timer {active_timer.id} for user {user_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to cancel cooldown for user {user_id}: {str(e)}")
            return False

    def get_cooldown_status(
        self, user_id: int, trading_day: date
    ) -> CooldownStatusResponse:
        """
        사용자의 쿨다운 상태 조회

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            CooldownStatusResponse: 쿨다운 상태 정보
        """
        try:
            active_timer: Optional[CooldownTimerSchema] = (
                self.cooldown_repo.get_active_timer(user_id, trading_day)
            )
            daily_count = self.cooldown_repo.count_daily_timers(user_id, trading_day)

            return CooldownStatusResponse(
                has_active_cooldown=active_timer is not None,
                next_refill_at=active_timer.scheduled_at if active_timer else None,
                daily_timer_count=daily_count,
                remaining_timer_quota=max(
                    0, settings.MAX_COOLDOWN_TIMERS_PER_DAY - daily_count
                ),
            )

        except Exception as e:
            logger.error(f"Failed to get cooldown status for user {user_id}: {str(e)}")
            raise ValidationError(f"쿨다운 상태 조회 중 오류가 발생했습니다: {str(e)}")

    def _get_available_slots(self, user_id: int, trading_day: date) -> int:
        """
        사용자의 현재 사용 가능한 예측 슬롯 수 계산

        Args:
            user_id: 사용자 ID
            trading_day: 거래일

        Returns:
            int: 사용 가능한 슬롯 수
        """
        try:
            stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
            # 가용 슬롯은 현재 available_predictions (소모/회복 직결)
            return max(0, stats.available_predictions)
        except Exception:
            return 0  # 오류 시 0 반환
