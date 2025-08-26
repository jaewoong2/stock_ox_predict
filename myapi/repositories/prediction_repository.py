from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, asc, func
from datetime import date, datetime, timezone

from myapi.models.prediction import (
    Prediction as PredictionModel,
    ChoiceEnum,
    StatusEnum,
    UserDailyStats as UserDailyStatsModel,
)
from myapi.schemas.prediction import (
    PredictionResponse,
    UserPredictionsResponse,
    PredictionStats,
    PredictionSummary,
    PredictionChoice,
    PredictionStatus,
)
from myapi.repositories.base import BaseRepository

from myapi.schemas.prediction import UserDailyStatsResponse


class PredictionRepository(BaseRepository[PredictionModel, PredictionResponse]):
    """예측 리포지토리"""

    def __init__(self, db: Session):
        super().__init__(PredictionModel, PredictionResponse, db)

    def _to_prediction_response(
        self, model_instance: PredictionModel
    ) -> PredictionResponse:
        """Prediction 모델을 PredictionResponse 스키마로 변환"""

        # SQLAlchemy 모델의 속성들을 딕셔너리로 변환 후 Pydantic 생성
        data = {
            "id": model_instance.id,
            "user_id": model_instance.user_id,
            "trading_day": model_instance.trading_day.strftime("%Y-%m-%d"),
            "symbol": str(model_instance.symbol),
            "choice": PredictionChoice(model_instance.choice.value),
            "status": PredictionStatus(model_instance.status.value),
            "submitted_at": model_instance.submitted_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": (
                model_instance.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if model_instance.updated_at
                else None
            ),
            "points_earned": (
                model_instance.points_earned
                if model_instance.points_earned is not None
                else 0
            ),
        }
        return PredictionResponse(**data)

    def create_prediction(
        self,
        user_id: int,
        trading_day: date,
        symbol: str,
        choice: ChoiceEnum,
        submitted_at: datetime,
    ) -> Optional[PredictionResponse]:
        """새 예측 생성"""
        submitted_at = datetime.now(timezone.utc)

        # Pydantic 스키마로 데이터 준비 후 생성
        return self.create(
            user_id=user_id,
            trading_day=trading_day,
            symbol=symbol,
            choice=choice,
            status=StatusEnum.PENDING,
            submitted_at=submitted_at,
            points_earned=0,
        )

    def update_prediction_choice(
        self, prediction_id: int, new_choice: ChoiceEnum
    ) -> Optional[PredictionResponse]:
        """예측 선택 업데이트 (수정 허용 시간 내에서만)"""
        # BaseRepository의 update 메서드 사용
        return self.update(
            prediction_id, choice=new_choice, updated_at=datetime.now(timezone.utc)
        )

    def get_user_predictions_for_day(
        self, user_id: int, trading_day: date
    ) -> UserPredictionsResponse:
        """특정 사용자의 특정 날짜 예측 조회"""
        model_instances = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                )
            )
            .order_by(asc(self.model_class.submitted_at))
            .all()
        )

        predictions = [
            self._to_prediction_response(instance) for instance in model_instances
        ]

        total_predictions = len(predictions)
        completed_predictions = sum(
            1 for p in predictions if p.status != PredictionStatus.PENDING
        )
        pending_predictions = total_predictions - completed_predictions

        return UserPredictionsResponse(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            predictions=predictions,
            total_predictions=total_predictions,
            completed_predictions=completed_predictions,
            pending_predictions=pending_predictions,
        )

    def get_predictions_by_symbol_and_date(
        self, symbol: str, trading_day: date, status_filter: Optional[StatusEnum] = None
    ) -> List[PredictionResponse]:
        """특정 심볼과 날짜의 모든 예측 조회"""

        query = self.db.query(self.model_class).filter(
            and_(
                self.model_class.symbol == symbol,
                self.model_class.trading_day == trading_day,
            )
        )

        if status_filter:
            query = query.filter(self.model_class.status == status_filter)

        model_instances = query.order_by(asc(self.model_class.submitted_at)).all()
        return [self._to_prediction_response(instance) for instance in model_instances]

    def prediction_exists(self, user_id: int, trading_day: date, symbol: str) -> bool:
        """특정 사용자의 특정 날짜/심볼 예측 존재 여부 확인"""
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                    self.model_class.symbol == symbol,
                )
            )
            .first()
            is not None
        )

    def lock_predictions_for_settlement(self, trading_day: date) -> int:
        """정산을 위한 예측 잠금 (수정 불가)"""
        locked_count = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.status == StatusEnum.PENDING,
                    self.model_class.locked_at.is_(None),
                )
            )
            .update(
                {"locked_at": datetime.now(timezone.utc)}, synchronize_session=False
            )
        )

        self.db.commit()
        return locked_count

    def update_prediction_status(
        self, prediction_id: int, status: StatusEnum, points_earned: int = 0
    ) -> Optional[PredictionResponse]:
        """예측 상태 및 획득 포인트 업데이트"""
        return self.update(
            prediction_id,
            status=status,
            points_earned=points_earned,
            updated_at=datetime.now(timezone.utc),
        )

    def bulk_update_predictions_status(
        self,
        trading_day: date,
        symbol: str,
        correct_choice: ChoiceEnum,
        points_per_correct: int = 10,
    ) -> Tuple[int, int]:
        """대량 예측 상태 업데이트 (정산용)"""
        # 정답 예측들 업데이트
        correct_count = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.symbol == symbol,
                    self.model_class.choice == correct_choice,
                    self.model_class.status == StatusEnum.PENDING,
                )
            )
            .update(
                {
                    "status": StatusEnum.CORRECT,
                    "points_earned": points_per_correct,
                    "updated_at": datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )
        )

        # 오답 예측들 업데이트
        incorrect_count = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.symbol == symbol,
                    self.model_class.choice != correct_choice,
                    self.model_class.status == StatusEnum.PENDING,
                )
            )
            .update(
                {
                    "status": StatusEnum.INCORRECT,
                    "points_earned": 0,
                    "updated_at": datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )
        )

        self.db.flush()
        self.db.commit()
        return correct_count, incorrect_count

    def get_prediction_stats(self, trading_day: date) -> PredictionStats:
        """예측 통계 조회"""
        stats = (
            self.db.query(
                func.count(self.model_class.id).label("total"),
                func.sum(
                    func.case([(self.model_class.choice == ChoiceEnum.UP, 1)], else_=0)
                ).label("up_count"),
                func.sum(
                    func.case(
                        [(self.model_class.choice == ChoiceEnum.DOWN, 1)], else_=0
                    )
                ).label("down_count"),
                func.sum(
                    func.case(
                        [(self.model_class.status == StatusEnum.CORRECT, 1)], else_=0
                    )
                ).label("correct_count"),
                func.sum(self.model_class.points_earned).label("total_points"),
            )
            .filter(self.model_class.trading_day == trading_day)
            .first()
        )

        if not stats:
            return PredictionStats(
                trading_day=trading_day.strftime("%Y-%m-%d"),
                total_predictions=0,
                up_predictions=0,
                down_predictions=0,
                correct_predictions=0,
                accuracy_rate=0.0,
                points_distributed=0,
            )

        total = stats.total or 0
        up_count = stats.up_count or 0
        down_count = stats.down_count or 0
        correct_count = stats.correct_count or 0
        total_points = stats.total_points or 0

        accuracy_rate = (correct_count / total * 100) if total > 0 else 0.0

        return PredictionStats(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            total_predictions=total,
            up_predictions=up_count,
            down_predictions=down_count,
            correct_predictions=correct_count,
            accuracy_rate=accuracy_rate,
            points_distributed=total_points,
        )

    def get_user_prediction_summary(
        self, user_id: int, trading_day: date
    ) -> PredictionSummary:
        """사용자별 예측 요약 조회"""
        stats = (
            self.db.query(
                func.count(self.model_class.id).label("total"),
                func.sum(
                    func.case(
                        [(self.model_class.status == StatusEnum.CORRECT, 1)], else_=0
                    )
                ).label("correct"),
                func.sum(
                    func.case(
                        [(self.model_class.status == StatusEnum.INCORRECT, 1)], else_=0
                    )
                ).label("incorrect"),
                func.sum(
                    func.case(
                        [(self.model_class.status == StatusEnum.PENDING, 1)], else_=0
                    )
                ).label("pending"),
                func.sum(self.model_class.points_earned).label("total_points"),
            )
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                )
            )
            .first()
        )

        if not stats:
            return PredictionSummary(
                user_id=user_id,
                trading_day=trading_day.strftime("%Y-%m-%d"),
                total_submitted=0,
                correct_count=0,
                incorrect_count=0,
                pending_count=0,
                accuracy_rate=0.0,
                total_points_earned=0,
            )

        total = stats.total or 0
        correct = stats.correct or 0
        incorrect = stats.incorrect or 0
        pending = stats.pending or 0
        total_points = stats.total_points or 0

        accuracy_rate = (
            (correct / (correct + incorrect) * 100)
            if (correct + incorrect) > 0
            else 0.0
        )

        return PredictionSummary(
            user_id=user_id,
            trading_day=trading_day.strftime("%Y-%m-%d"),
            total_submitted=total,
            correct_count=correct,
            incorrect_count=incorrect,
            pending_count=pending,
            accuracy_rate=accuracy_rate,
            total_points_earned=total_points,
        )

    def get_pending_predictions_for_settlement(
        self, trading_day: date
    ) -> List[PredictionResponse]:
        """정산 대상 pending 예측들 조회"""
        model_instances = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.status == StatusEnum.PENDING,
                )
            )
            .order_by(asc(self.model_class.symbol), asc(self.model_class.submitted_at))
            .all()
        )

        return [self._to_prediction_response(instance) for instance in model_instances]

    def cancel_prediction(self, prediction_id: int) -> Optional[PredictionResponse]:
        """예측 취소"""
        return self.update_prediction_status(prediction_id, StatusEnum.CANCELLED)

    def get_user_prediction_history(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> List[PredictionResponse]:
        """사용자 예측 이력 조회 (최신순)"""
        model_instances = (
            self.db.query(self.model_class)
            .filter(self.model_class.user_id == user_id)
            .order_by(
                desc(self.model_class.trading_day), desc(self.model_class.submitted_at)
            )
            .limit(limit)
            .offset(offset)
            .all()
        )

        return [self._to_prediction_response(instance) for instance in model_instances]

    def count_predictions_by_date(self, trading_day: date) -> int:
        """특정 날짜의 전체 예측 개수"""
        return (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .count()
        )

    def count_predictions_by_date_and_status(
        self, trading_day: date, status: StatusEnum
    ) -> int:
        """특정 날짜 및 상태의 예측 개수"""
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.status == status,
                )
            )
            .count()
        )


class UserDailyStatsRepository(
    BaseRepository[UserDailyStatsModel, UserDailyStatsResponse]
):
    """사용자 일일 통계 리포지토리"""

    def __init__(self, db: Session):
        super().__init__(UserDailyStatsModel, UserDailyStatsResponse, db)

    def _to_response(
        self, model_instance: UserDailyStatsModel
    ) -> UserDailyStatsResponse:
        """UserDailyStats 모델을 UserDailyStatsResponse로 변환"""
        if model_instance is None:
            return None

        return UserDailyStatsResponse(
            user_id=getattr(model_instance, "user_id", 0),
            trading_day=model_instance.trading_day.strftime("%Y-%m-%d"),
            predictions_made=getattr(model_instance, "predictions_made", 0),
            max_predictions=getattr(model_instance, "max_predictions", 3),
            created_at=(model_instance.created_at.strftime("%Y-%m-%d %H:%M:%S")),
            updated_at=(model_instance.updated_at.strftime("%Y-%m-%d %H:%M:%S")),
        )

    def get_or_create_user_daily_stats(
        self, user_id: int, trading_day: date
    ) -> UserDailyStatsResponse:
        """사용자 일일 통계 조회 또는 생성"""
        model_instance = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                )
            )
            .first()
        )

        if not model_instance:
            model_instance = self.model_class(
                user_id=user_id,
                trading_day=trading_day,
                predictions_made=0,
                max_predictions=3,
            )
            self.db.add(model_instance)
            self.db.flush()
            self.db.refresh(model_instance)
            self.db.commit()

        return self._to_response(model_instance)

    def increment_predictions_made(
        self, user_id: int, trading_day: date
    ) -> UserDailyStatsResponse:
        """예측 수 증가"""
        stats = self.get_or_create_user_daily_stats(user_id, trading_day)

        updated_count = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                )
            )
            .update({"predictions_made": self.model_class.predictions_made + 1})
        )

        if updated_count > 0:
            self.db.commit()
            # 업데이트된 값 재조회
            model_instance = (
                self.db.query(self.model_class)
                .filter(
                    and_(
                        self.model_class.user_id == user_id,
                        self.model_class.trading_day == trading_day,
                    )
                )
                .first()
            )
            return self._to_response(model_instance)

        return stats

    def can_make_prediction(self, user_id: int, trading_day: date) -> bool:
        """예측 가능 여부 확인"""
        stats = self.get_or_create_user_daily_stats(user_id, trading_day)
        return stats.predictions_made < stats.max_predictions

    def get_remaining_predictions(self, user_id: int, trading_day: date) -> int:
        """남은 예측 가능 수"""
        stats = self.get_or_create_user_daily_stats(user_id, trading_day)
        return max(0, stats.max_predictions - stats.predictions_made)

    def increase_max_predictions(
        self, user_id: int, trading_day: date, additional_slots: int = 1
    ) -> UserDailyStatsResponse:
        """최대 예측 수 증가 (광고 시청 등)"""
        model_instance = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                )
            )
            .first()
        )

        if not model_instance:
            model_instance = self.model_class(
                user_id=user_id,
                trading_day=trading_day,
                predictions_made=0,
                max_predictions=3 + additional_slots,
            )
            self.db.add(model_instance)
        else:
            # SQL UPDATE 사용
            self.db.query(self.model_class).filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                )
            ).update(
                {
                    "max_predictions": self.model_class.max_predictions
                    + additional_slots
                },
                synchronize_session=False,
            )

        self.db.commit()

        # 업데이트된 모델 재조회
        updated_model = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                )
            )
            .first()
        )

        return self._to_response(updated_model)
