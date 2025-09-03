from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from myapi.core.exceptions import (
    ValidationError,
    NotFoundError,
    ConflictError,
    BusinessLogicError,
    RateLimitError,
)
from myapi.config import Settings
from myapi.models.prediction import (
    Prediction as PredictionModel,
    ChoiceEnum,
    StatusEnum,
)
from myapi.repositories.prediction_repository import (
    PredictionRepository,
    UserDailyStatsRepository,
)
from myapi.repositories.active_universe_repository import ActiveUniverseRepository
from myapi.repositories.session_repository import SessionRepository
from myapi.services.point_service import PointService
from myapi.schemas.prediction import (
    PredictionCreate,
    PredictionUpdate,
    PredictionResponse,
    UserPredictionsResponse,
    PredictionStats,
    PredictionSummary,
    PredictionChoice,
)
from myapi.services.error_log_service import ErrorLogService
from myapi.utils.date_utils import to_date


class PredictionService:
    """예측 관련 비즈니스 로직 서비스"""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.pred_repo = PredictionRepository(db)
        self.stats_repo = UserDailyStatsRepository(db)
        self.universe_repo = ActiveUniverseRepository(db)
        self.session_repo = SessionRepository(db)
        self.point_service = PointService(db)
        self.error_log_service = ErrorLogService(db)
        self.settings = settings

        # 포인트 설정 (비즈니스 설정)
        self.PREDICTION_FEE_POINTS = settings.PREDICTION_FEE_POINTS
        self.PREDICTION_CANCEL_REFUND = True  # 취소 시 수수료 환불 여부
        self.CANCEL_WINDOW_MINUTES = 5  # 취소 허용 시간(분)

    def _safe_transaction(self, operation):
        """
        안전한 트랜잭션 실행을 위한 헬퍼 메서드
        이미 트랜잭션이 시작된 경우와 그렇지 않은 경우를 모두 처리
        """
        try:
            if self.db.in_transaction():
                # 이미 트랜잭션 내부라면 commit/rollback 없이 실행
                return operation()
            else:
                # 새로운 트랜잭션 시작
                with self.db.begin():
                    return operation()
        except Exception as e:
            # 트랜잭션 관련 에러 처리
            if "transaction is already begun" in str(e).lower():
                # 이미 시작된 트랜잭션이 있는 경우, 그냥 실행
                return operation()
            raise

    # 제출/수정/취소
    def submit_prediction(
        self, user_id: int, trading_day: date, payload: PredictionCreate
    ) -> PredictionResponse:
        # 세션 상태 확인 (예측 가능 여부)
        session = self.session_repo.get_session_by_date(trading_day)
        if not session:
            session = self.session_repo.get_current_session()
        if not session or not session.is_prediction_open:
            raise BusinessLogicError(
                error_code="PREDICTION_CLOSED",
                message="Predictions are not open for this trading day.",
            )
        # 서버가 관리하는 거래일 사용
        trading_day = session.trading_day

        symbol = payload.symbol.upper()

        # 심볼 유효성: 오늘의 유니버스 포함 여부
        if not self.universe_repo.symbol_exists_in_universe(trading_day, symbol):
            raise NotFoundError(
                message=f"Symbol not available for predictions: {symbol}"
            )

        # 중복 제출 방지
        if self.pred_repo.prediction_exists(user_id, trading_day, symbol):
            raise ConflictError("Prediction already submitted for this symbol")

        # 가용 슬롯 확인 (남은 슬롯 > 0)
        if not self.stats_repo.can_make_prediction(user_id, trading_day):
            remaining = self.stats_repo.get_remaining_predictions(user_id, trading_day)
            raise RateLimitError(
                message="Daily prediction limit reached",
                details={"remaining": remaining},
            )

        # 생성 + 슬롯 소모를 하나의 트랜잭션으로 처리
        choice = ChoiceEnum(payload.choice.value)
        now = datetime.now(timezone.utc)
        from myapi.models.prediction import (
            Prediction as PredictionModel,
            UserDailyStats as UserDailyStatsModel,
        )
        from sqlalchemy import and_, func

        try:

            def _create_prediction_transaction():
                # 1) 단일 UPDATE로 가용 슬롯 차감(+사용량 증가). 영향 행 수 0이면 제한 초과
                updated = (
                    self.db.query(UserDailyStatsModel)
                    .filter(
                        and_(
                            UserDailyStatsModel.user_id == user_id,
                            UserDailyStatsModel.trading_day == trading_day,
                            UserDailyStatsModel.available_predictions > 0,
                        )
                    )
                    .update(
                        {
                            "available_predictions": UserDailyStatsModel.available_predictions - 1,
                            "predictions_made": UserDailyStatsModel.predictions_made + 1,
                            "updated_at": func.now(),
                        },
                        synchronize_session=False,
                    )
                )

                if updated == 0:
                    raise RateLimitError(
                        message="Daily prediction limit reached",
                        details={
                            "remaining": self.stats_repo.get_remaining_predictions(
                                user_id, trading_day
                            )
                        },
                    )

                # 2) 예측 생성
                model = PredictionModel(
                    user_id=user_id,
                    trading_day=trading_day,
                    symbol=symbol,
                    choice=choice,
                    status=StatusEnum.PENDING,
                    submitted_at=now,
                    points_earned=0,
                )
                self.db.add(model)
                self.db.flush()
                self.db.refresh(model)
                return model

            # 안전한 트랜잭션 실행
            model = self._safe_transaction(_create_prediction_transaction)

            # 트랜잭션 성공 시 Pydantic 스키마로 변환
            created = self.pred_repo._to_schema(model)
        except Exception as e:
            # 에러 로깅 후 전파
            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                error_message=f"Failed to create prediction atomically: {str(e)}",
                prediction_details={
                    "choice": payload.choice.value,
                    "fee_charged": self.PREDICTION_FEE_POINTS,
                },
            )
            raise

        # 자동 쿨다운 트리거 (동기적으로 처리, 실패해도 예측 성공)
        try:
            # 동기적으로 쿨다운 체크 및 트리거
            self._check_and_trigger_cooldown_sync(user_id, trading_day)
        except Exception as e:
            self.error_log_service.log_prediction_error(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                error_message=f"Cooldown trigger failed: {str(e)}",
            )

        if not created:
            raise ValidationError("Failed to create prediction")

        return created

    def _check_and_trigger_cooldown_sync(self, user_id: int, trading_day: date) -> None:
        """
        예측 제출 후 슬롯 수를 확인하여 필요시 자동 쿨다운 시작 (동기 버전)

        Args:
            user_id: 사용자 ID
            trading_day: 거래일
        """
        try:
            # 현재 사용 가능한 슬롯 수 확인 (가용=현재 available_predictions)
            stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
            available_slots = max(0, stats.available_predictions)

            # 쿨다운 트리거 정책
            # - 이미 활성 쿨다운이 있으면 아무 것도 하지 않음
            # - 3 → 2 로 감소한 시점(즉, 현재 값이 2)에서만 타이머 시작
            # - 2 → 1 은 시작 안 함 (이미 활성)
            # - 회복 1 → 2 는 재시작, 2 → 3 은 재시작 안 함 (handle에서 처리)
            if available_slots == self.settings.COOLDOWN_TRIGGER_THRESHOLD - 1:
                from myapi.services.cooldown_service import CooldownService

                cooldown_service = CooldownService(self.db, self.settings)
                active = cooldown_service.cooldown_repo.get_active_timer(
                    user_id, trading_day
                )
                if not active:
                    cooldown_service.start_auto_cooldown_sync(user_id, trading_day)
        except Exception as e:
            # 쿨다운 시작 실패해도 예측 제출은 성공으로 처리
            print(f"Failed to check cooldown for user {user_id}: {str(e)}")

    async def _trigger_cooldown_if_needed(
        self, user_id: int, trading_day: date
    ) -> None:
        """
        예측 제출 후 슬롯 수를 확인하여 필요시 자동 쿨다운 시작 (비동기 버전)

        Args:
            user_id: 사용자 ID
            trading_day: 거래일
        """
        try:
            # 현재 사용 가능한 슬롯 수 확인 (가용=현재 available_predictions)
            stats = self.stats_repo.get_or_create_user_daily_stats(user_id, trading_day)
            available_slots = max(0, stats.available_predictions)

            # 임계값 이하일 때만 쿨다운 시작 (정책: 3 이하)
            if available_slots <= 3:
                from myapi.services.cooldown_service import CooldownService

                cooldown_service = CooldownService(self.db, self.settings)
                await cooldown_service.start_auto_cooldown(user_id, trading_day)

                print(
                    f"Triggered auto cooldown for user {user_id}, "
                    f"available_slots: {available_slots}, "
                    f"threshold: {self.settings.COOLDOWN_TRIGGER_THRESHOLD}"
                )

        except Exception as e:
            # 쿨다운 시작 실패해도 예측 제출은 성공으로 처리
            print(f"Failed to trigger cooldown for user {user_id}: {str(e)}")

    def update_prediction(
        self, user_id: int, prediction_id: int, payload: PredictionUpdate
    ) -> PredictionResponse:
        # 본인 소유/상태 확인을 위해 모델 직접 조회
        model: Optional[PredictionModel] = (
            self.db.query(PredictionModel)
            .filter(PredictionModel.id == prediction_id)
            .first()
        )

        if not model:
            raise NotFoundError("Prediction not found")

        if int(str(model.user_id)) != int(user_id):
            raise BusinessLogicError(
                error_code="FORBIDDEN_PREDICTION",
                message="Cannot modify another user's prediction",
            )

        if str(model.status) != StatusEnum.PENDING:
            raise BusinessLogicError(
                error_code="PREDICTION_LOCKED",
                message="Only pending predictions can be updated",
            )

        if getattr(model, "locked_at", None) is not None:
            raise BusinessLogicError(
                error_code="PREDICTION_LOCKED",
                message="Prediction has been locked for settlement",
            )

        new_choice = ChoiceEnum(payload.choice.value)
        updated = self.pred_repo.update_prediction_choice(prediction_id, new_choice)
        if not updated:
            raise ValidationError("Failed to update prediction")
        return updated

    def cancel_prediction(self, user_id: int, prediction_id: int) -> PredictionResponse:
        model: Optional[PredictionModel] = (
            self.db.query(PredictionModel)
            .filter(PredictionModel.id == prediction_id)
            .first()
        )
        if not model:
            raise NotFoundError("Prediction not found")

        if int(str(model.user_id)) != int(user_id):
            raise BusinessLogicError(
                error_code="FORBIDDEN_PREDICTION",
                message="Cannot cancel another user's prediction",
            )

        if str(model.status) != StatusEnum.PENDING:
            raise BusinessLogicError(
                error_code="PREDICTION_NOT_CANCELABLE",
                message="Only pending predictions can be canceled",
            )

        # 제출 후 취소 허용 시간 경과 여부 체크
        try:
            now = datetime.now(timezone.utc)
            submitted_at = getattr(model, "submitted_at", None)
            if (
                submitted_at
                and (now - submitted_at).total_seconds()
                > self.CANCEL_WINDOW_MINUTES * 60
            ):
                raise BusinessLogicError(
                    error_code="PREDICTION_CANCEL_TIME_EXCEEDED",
                    message=f"Predictions can be canceled within {self.CANCEL_WINDOW_MINUTES} minutes of submission",
                )
        except Exception:
            # 시간 계산 실패 시 보수적으로 취소 불가 처리
            raise BusinessLogicError(
                error_code="PREDICTION_CANCEL_TIME_EXCEEDED",
                message=f"Predictions can be canceled within {self.CANCEL_WINDOW_MINUTES} minutes of submission",
            )

        if getattr(model, "locked_at", None) is not None:
            raise BusinessLogicError(
                error_code="PREDICTION_LOCKED",
                message="Prediction has been locked for settlement",
            )

        # 서비스 단위 원자 트랜잭션으로 취소 + 슬롯 환불 처리
        try:
            with self.db.begin():
                canceled = self.pred_repo.cancel_prediction(
                    prediction_id, commit=False
                )
                if not canceled:
                    raise ValidationError("Failed to cancel prediction")

                # 취소 성공 시 예측 환불 처리 (가용 +1, 사용량 -1)
                trading_day = to_date(model.trading_day)
                if trading_day:
                    self.stats_repo.refund_prediction(
                        user_id, trading_day, 1, commit=False
                    )
        except Exception:
            # 트랜잭션은 자동 롤백
            raise

        # 취소 시 수수료 환불 (비즈니스 규칙에 따라)
        if self.PREDICTION_CANCEL_REFUND:
            try:
                from myapi.schemas.points import PointsTransactionRequest

                refund_request = PointsTransactionRequest(
                    amount=self.PREDICTION_FEE_POINTS,
                    reason=f"Refund for canceled prediction {prediction_id}",
                    ref_id=f"cancel_refund_{prediction_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                )

                refund_result = self.point_service.add_points(
                    user_id=user_id,
                    request=refund_request,
                    trading_day=getattr(model, "trading_day", date.today()),
                )

                if refund_result.success:
                    print(
                        f"✅ Refunded {self.PREDICTION_FEE_POINTS} points for canceled prediction {prediction_id}"
                    )
                else:
                    # 취소 환불 실패 에러 로깅
                    self.error_log_service.log_point_transaction_error(
                        user_id=user_id,
                        transaction_type="PREDICTION_CANCEL_REFUND",
                        amount=self.PREDICTION_FEE_POINTS,
                        error_message=refund_result.message,
                        ref_id=f"cancel_refund_{prediction_id}",
                        trading_day=getattr(model, "trading_day", date.today()),
                    )
                    print(
                        f"❌ Failed to refund points for canceled prediction {prediction_id}: {refund_result.message}"
                    )
            except Exception as e:
                # 취소 환불 시스템 에러 로깅
                self.error_log_service.log_point_transaction_error(
                    user_id=user_id,
                    transaction_type="PREDICTION_CANCEL_REFUND",
                    amount=self.PREDICTION_FEE_POINTS,
                    error_message=str(e),
                    ref_id=f"cancel_refund_{prediction_id}",
                    trading_day=getattr(model, "trading_day", date.today()),
                )
                print(
                    f"❌ Error refunding points for canceled prediction {prediction_id}: {str(e)}"
                )

        return canceled

    # 조회/통계
    def get_user_predictions_for_day(
        self, user_id: int, trading_day: date
    ) -> UserPredictionsResponse:
        return self.pred_repo.get_user_predictions_for_day(user_id, trading_day)

    def get_predictions_by_symbol_and_date(
        self, symbol: str, trading_day: date, status_filter: Optional[StatusEnum] = None
    ) -> List[PredictionResponse]:
        return self.pred_repo.get_predictions_by_symbol_and_date(
            symbol=symbol.upper(),
            trading_day=trading_day,
            status_filter=status_filter or StatusEnum.PENDING,
        )

    def get_prediction_stats(self, trading_day: date) -> PredictionStats:
        return self.pred_repo.get_prediction_stats(trading_day)

    def get_user_prediction_summary(
        self, user_id: int, trading_day: date
    ) -> PredictionSummary:
        return self.pred_repo.get_user_prediction_summary(user_id, trading_day)

    def get_user_prediction_history(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> List[PredictionResponse]:
        return self.pred_repo.get_user_prediction_history(
            user_id, limit=limit, offset=offset
        )

    def get_user_prediction_history_paginated(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> Tuple[List[PredictionResponse], int, bool]:
        """사용자 예측 이력 조회 (페이지네이션 정보 포함)"""
        if limit > 100:  # 최대 제한
            limit = 100

        predictions = self.pred_repo.get_user_prediction_history(
            user_id, limit=limit + 1, offset=offset
        )  # +1로 다음 페이지 존재 여부 확인

        has_next = len(predictions) > limit
        if has_next:
            predictions = predictions[:limit]  # 실제 요청한 limit 만큼만 반환

        # 전체 카운트는 별도 쿼리로 조회
        total_count = self.pred_repo.count_user_predictions(user_id)

        return predictions, total_count, has_next

    # 정산 관련
    def lock_predictions_for_settlement(self, trading_day: date) -> int:
        return self.pred_repo.lock_predictions_for_settlement(trading_day)

    def bulk_update_predictions_status(
        self,
        trading_day: date,
        symbol: str,
        correct_choice: PredictionChoice,
        points_per_correct: int = 10,
    ) -> Tuple[int, int]:
        return self.pred_repo.bulk_update_predictions_status(
            trading_day=trading_day,
            symbol=symbol.upper(),
            correct_choice=ChoiceEnum(correct_choice.value),
            points_per_correct=points_per_correct,
        )

    def get_pending_predictions_for_settlement(
        self, trading_day: date
    ) -> List[PredictionResponse]:
        return self.pred_repo.get_pending_predictions_for_settlement(trading_day)

    # 유저 일일 슬롯 관리
    def get_remaining_predictions(self, user_id: int, trading_day: date) -> int:
        return self.stats_repo.get_remaining_predictions(user_id, trading_day)

    def increase_max_predictions(
        self, user_id: int, trading_day: date, additional_slots: int = 1
    ) -> None:
        if additional_slots <= 0:
            raise ValidationError("additional_slots must be positive")
        self.stats_repo.increase_max_predictions(user_id, trading_day, additional_slots)
