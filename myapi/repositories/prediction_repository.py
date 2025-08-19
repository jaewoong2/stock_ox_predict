from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime
from myapi.repositories.base import BaseRepository
from myapi.models.prediction import Prediction, UserDailyStats
from myapi.schemas.prediction import PredictionResponse, PredictionSummary


class PredictionRepository(BaseRepository[Prediction, PredictionResponse]):
    """예측 리포지토리 - Pydantic 응답 보장"""

    def __init__(self, db: Session):
        super().__init__(Prediction, PredictionResponse, db)

    def get_user_predictions(self, user_id: int, trading_day: date = None) -> List[PredictionResponse]:
        """사용자 예측 조회"""
        if trading_day is None:
            trading_day = date.today()
            
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.user_id == user_id,
                Prediction.trading_day == trading_day
            )
        ).all()
        
        return [self._to_schema(prediction) for prediction in predictions]

    def get_prediction(self, user_id: int, trading_day: date, symbol: str) -> Optional[PredictionResponse]:
        """특정 예측 조회"""
        prediction = self.db.query(Prediction).filter(
            and_(
                Prediction.user_id == user_id,
                Prediction.trading_day == trading_day,
                Prediction.symbol == symbol
            )
        ).first()
        
        return self._to_schema(prediction)

    def create_prediction(self, user_id: int, trading_day: date, symbol: str, choice: str) -> PredictionResponse:
        """예측 생성"""
        from myapi.models.prediction import ChoiceEnum, StatusEnum
        
        prediction = Prediction(
            user_id=user_id,
            trading_day=trading_day,
            symbol=symbol,
            choice=ChoiceEnum(choice),
            status=StatusEnum.PENDING,
            submitted_at=datetime.utcnow()
        )
        
        self.db.add(prediction)
        self.db.flush()
        self.db.refresh(prediction)
        
        return self._to_schema(prediction)

    def update_prediction(self, user_id: int, trading_day: date, symbol: str, choice: str) -> Optional[PredictionResponse]:
        """예측 업데이트"""
        from myapi.models.prediction import ChoiceEnum
        
        prediction = self.db.query(Prediction).filter(
            and_(
                Prediction.user_id == user_id,
                Prediction.trading_day == trading_day,
                Prediction.symbol == symbol
            )
        ).first()
        
        if not prediction:
            return None
            
        prediction.choice = ChoiceEnum(choice)
        prediction.updated_at = datetime.utcnow()
        
        self.db.add(prediction)
        self.db.flush()
        self.db.refresh(prediction)
        
        return self._to_schema(prediction)

    def lock_predictions(self, trading_day: date) -> int:
        """예측 잠금 (정산 준비)"""
        locked_at = datetime.utcnow()
        count = self.db.query(Prediction).filter(
            and_(
                Prediction.trading_day == trading_day,
                Prediction.locked_at.is_(None)
            )
        ).update({"locked_at": locked_at})
        
        self.db.flush()
        return count

    def get_predictions_for_settlement(self, trading_day: date, symbol: str = None) -> List[PredictionResponse]:
        """정산용 예측 조회"""
        from myapi.models.prediction import StatusEnum
        
        query = self.db.query(Prediction).filter(
            and_(
                Prediction.trading_day == trading_day,
                Prediction.status == StatusEnum.PENDING
            )
        )
        
        if symbol:
            query = query.filter(Prediction.symbol == symbol)
            
        predictions = query.all()
        return [self._to_schema(prediction) for prediction in predictions]

    def update_prediction_result(self, prediction_id: int, status: str, points_earned: int = 0) -> Optional[PredictionResponse]:
        """예측 결과 업데이트"""
        from myapi.models.prediction import StatusEnum
        
        prediction = self.db.query(Prediction).filter(Prediction.id == prediction_id).first()
        if not prediction:
            return None
            
        prediction.status = StatusEnum(status)
        prediction.points_earned = points_earned
        prediction.updated_at = datetime.utcnow()
        
        self.db.add(prediction)
        self.db.flush()
        self.db.refresh(prediction)
        
        return self._to_schema(prediction)

    def get_user_prediction_stats(self, user_id: int, trading_day: date = None) -> dict:
        """사용자 예측 통계"""
        from myapi.models.prediction import StatusEnum
        
        if trading_day is None:
            trading_day = date.today()
        
        query = self.db.query(Prediction).filter(
            and_(
                Prediction.user_id == user_id,
                Prediction.trading_day == trading_day
            )
        )
        
        total = query.count()
        correct = query.filter(Prediction.status == StatusEnum.CORRECT).count()
        incorrect = query.filter(Prediction.status == StatusEnum.INCORRECT).count()
        pending = query.filter(Prediction.status == StatusEnum.PENDING).count()
        
        accuracy_rate = (correct / total) if total > 0 else 0.0
        total_points = query.filter(Prediction.points_earned > 0).with_entities(
            func.sum(Prediction.points_earned)
        ).scalar() or 0
        
        return {
            "user_id": user_id,
            "trading_day": str(trading_day),
            "total_submitted": total,
            "correct_count": correct,
            "incorrect_count": incorrect,
            "pending_count": pending,
            "accuracy_rate": accuracy_rate,
            "total_points_earned": total_points
        }

    def get_symbol_prediction_stats(self, trading_day: date, symbol: str) -> dict:
        """종목별 예측 통계"""
        from myapi.models.prediction import ChoiceEnum, StatusEnum
        
        query = self.db.query(Prediction).filter(
            and_(
                Prediction.trading_day == trading_day,
                Prediction.symbol == symbol
            )
        )
        
        total = query.count()
        up_count = query.filter(Prediction.choice == ChoiceEnum.UP).count()
        down_count = query.filter(Prediction.choice == ChoiceEnum.DOWN).count()
        correct_count = query.filter(Prediction.status == StatusEnum.CORRECT).count()
        
        accuracy_rate = (correct_count / total) if total > 0 else 0.0
        total_points = query.filter(Prediction.points_earned > 0).with_entities(
            func.sum(Prediction.points_earned)
        ).scalar() or 0
        
        return {
            "trading_day": str(trading_day),
            "symbol": symbol,
            "total_predictions": total,
            "up_predictions": up_count,
            "down_predictions": down_count,
            "correct_predictions": correct_count,
            "accuracy_rate": accuracy_rate,
            "points_distributed": total_points
        }


class UserDailyStatsRepository(BaseRepository[UserDailyStats, dict]):
    """사용자 일일 통계 리포지토리"""

    def __init__(self, db: Session):
        # Using dict as schema for simplicity since it's a simple stats model
        super().__init__(UserDailyStats, dict, db)

    def get_user_daily_stats(self, user_id: int, trading_day: date) -> Optional[dict]:
        """사용자 일일 통계 조회"""
        stats = self.db.query(UserDailyStats).filter(
            and_(
                UserDailyStats.user_id == user_id,
                UserDailyStats.trading_day == trading_day
            )
        ).first()
        
        if stats:
            return {
                "user_id": stats.user_id,
                "trading_day": str(stats.trading_day),
                "predictions_made": stats.predictions_made,
                "max_predictions": stats.max_predictions,
                "remaining_predictions": stats.max_predictions - stats.predictions_made
            }
        return None

    def increment_prediction_count(self, user_id: int, trading_day: date) -> dict:
        """예측 횟수 증가"""
        stats = self.db.query(UserDailyStats).filter(
            and_(
                UserDailyStats.user_id == user_id,
                UserDailyStats.trading_day == trading_day
            )
        ).first()
        
        if not stats:
            # 새로운 통계 생성
            stats = UserDailyStats(
                user_id=user_id,
                trading_day=trading_day,
                predictions_made=1,
                max_predictions=3  # 기본값
            )
            self.db.add(stats)
        else:
            # 기존 통계 업데이트
            stats.predictions_made += 1
            self.db.add(stats)
        
        self.db.flush()
        self.db.refresh(stats)
        
        return {
            "user_id": stats.user_id,
            "trading_day": str(stats.trading_day),
            "predictions_made": stats.predictions_made,
            "max_predictions": stats.max_predictions,
            "remaining_predictions": stats.max_predictions - stats.predictions_made
        }

    def can_make_prediction(self, user_id: int, trading_day: date) -> bool:
        """예측 가능 여부 확인"""
        stats = self.get_user_daily_stats(user_id, trading_day)
        if not stats:
            return True  # 첫 예측은 가능
        return stats["remaining_predictions"] > 0