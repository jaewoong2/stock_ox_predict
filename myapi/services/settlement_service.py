from datetime import date, datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from decimal import Decimal

from sqlalchemy.orm import Session

from myapi.core.exceptions import ValidationError, NotFoundError, ServiceException
from myapi.models.prediction import ChoiceEnum, StatusEnum
from myapi.repositories.prediction_repository import PredictionRepository
from myapi.repositories.active_universe_repository import ActiveUniverseRepository
from myapi.services.price_service import PriceService
from myapi.services.point_service import PointService
from myapi.schemas.price import SettlementPriceData, PriceComparisonResult
from myapi.schemas.prediction import PredictionChoice, PredictionStatus


class SettlementService:
    """예측 정산 및 결과 검증 서비스"""

    def __init__(self, db: Session):
        self.db = db
        self.pred_repo = PredictionRepository(db)
        self.universe_repo = ActiveUniverseRepository(db)
        self.price_service = PriceService(db)
        self.point_service = PointService(db)
        
        # 포인트 지급 설정 (비즈니스 설정)
        self.CORRECT_PREDICTION_POINTS = 100
        self.PREDICTION_FEE_POINTS = 10

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.price_service.__aexit__(exc_type, exc_val, exc_tb)

    async def validate_and_settle_day(self, trading_day: date) -> Dict[str, Any]:
        """특정 거래일의 예측을 검증하고 정산합니다."""
        try:
            # 1. 해당 날짜의 정산용 가격 데이터 수집 및 검증
            async with self.price_service as price_svc:
                settlement_data = await price_svc.validate_settlement_prices(
                    trading_day
                )

            if not settlement_data:
                raise NotFoundError(
                    f"No price data available for settlement on {trading_day}"
                )

            # 2. 각 종목별로 예측 정산 처리
            settlement_results = []
            total_processed = 0
            total_correct = 0

            for price_data in settlement_data:
                if not price_data.is_valid_settlement:
                    # 유효하지 않은 가격 데이터는 예측을 VOID로 처리
                    await self._handle_void_predictions(
                        trading_day, price_data.symbol, price_data.void_reason
                    )
                    settlement_results.append(
                        {
                            "symbol": price_data.symbol,
                            "status": "VOIDED",
                            "reason": price_data.void_reason,
                            "processed_count": 0,
                            "correct_count": 0,
                        }
                    )
                else:
                    # 정상 정산 처리
                    result = await self._settle_predictions_for_symbol(
                        trading_day, price_data
                    )
                    settlement_results.append(result)
                    total_processed += result["processed_count"]
                    total_correct += result["correct_count"]

            # 3. 전체 정산 통계 반환
            return {
                "trading_day": trading_day.strftime("%Y-%m-%d"),
                "settlement_completed_at": datetime.now(timezone.utc).isoformat(),
                "total_predictions_processed": total_processed,
                "total_correct_predictions": total_correct,
                "accuracy_rate": (
                    (total_correct / total_processed * 100) if total_processed else 0
                ),
                "symbol_results": settlement_results,
            }

        except Exception as e:
            raise ServiceException(f"Settlement failed for {trading_day}: {str(e)}")

    async def _settle_predictions_for_symbol(
        self, trading_day: date, price_data: SettlementPriceData
    ) -> Dict[str, Any]:
        """특정 종목의 예측들을 정산합니다."""
        symbol = price_data.symbol

        # 해당 종목의 대기 중인 예측들 조회
        pending_predictions = self.pred_repo.get_predictions_by_symbol_and_date(
            symbol, trading_day, status_filter=StatusEnum.PENDING
        )

        if not pending_predictions:
            return {
                "symbol": symbol,
                "status": "NO_PREDICTIONS",
                "processed_count": 0,
                "correct_count": 0,
                "price_movement": price_data.price_movement,
            }

        correct_count = 0
        processed_count = len(pending_predictions)

        # 각 예측을 검증하고 결과 업데이트
        for prediction in pending_predictions:
            # 예측 방향과 실제 결과 비교
            predicted_direction = prediction.choice.value.upper()  # UP or DOWN
            actual_movement = price_data.price_movement  # UP, DOWN, or FLAT

            is_correct = self._is_prediction_correct(
                predicted_direction, actual_movement
            )

            if is_correct:
                correct_count += 1
                # 정답 예측 처리 (포인트 지급 등)
                await self._award_correct_prediction(
                    prediction.id, prediction.user_id, trading_day, symbol
                )
            else:
                # 오답 예측 처리
                await self._handle_incorrect_prediction(
                    prediction.id, prediction.user_id, trading_day, symbol
                )

        return {
            "symbol": symbol,
            "status": "SETTLED",
            "processed_count": processed_count,
            "correct_count": correct_count,
            "accuracy_rate": (
                (correct_count / processed_count * 100) if processed_count else 0
            ),
            "price_movement": price_data.price_movement,
            "settlement_price": float(price_data.settlement_price),
            "change_percent": float(price_data.change_percent),
        }

    async def _handle_void_predictions(
        self, trading_day: date, symbol: str, void_reason: Optional[str]
    ) -> None:
        """유효하지 않은 가격으로 인한 예측 무효 처리"""
        pending_predictions = self.pred_repo.get_predictions_by_symbol_and_date(
            symbol, trading_day, status_filter=StatusEnum.PENDING
        )

        for prediction in pending_predictions:
            # 예측을 VOID 상태로 변경 (포인트는 반환하거나 유지)
            await self._void_prediction(
                prediction.id, prediction.user_id, trading_day, symbol, void_reason
            )

    def _is_prediction_correct(self, predicted: str, actual: str) -> bool:
        """예측이 맞는지 확인"""
        if actual == "FLAT":
            # 가격 변동이 없는 경우는 모든 예측을 틀린 것으로 처리하거나
            # 별도 규칙 적용 (여기서는 틀린 것으로 처리)
            return False
        return predicted == actual

    async def _award_correct_prediction(
        self, prediction_id: int, user_id: int, trading_day: date, symbol: str
    ) -> None:
        """정답 예측에 대한 보상 처리"""
        try:
            # 1. 예측 상태를 CORRECT로 변경
            self.pred_repo.update_prediction_status(prediction_id, StatusEnum.CORRECT)

            # 2. 포인트 지급
            result = self.point_service.award_prediction_points(
                user_id=user_id,
                prediction_id=prediction_id,
                points=self.CORRECT_PREDICTION_POINTS,
                trading_day=trading_day,
                symbol=symbol
            )

            if result.success:
                print(
                    f"✅ Awarded {self.CORRECT_PREDICTION_POINTS} points to user {user_id} for correct prediction {prediction_id}"
                )
            else:
                print(
                    f"❌ Failed to award points to user {user_id}: {result.message}"
                )
        except Exception as e:
            print(f"❌ Error awarding points for prediction {prediction_id}: {str(e)}")
            # 포인트 지급 실패해도 예측 결과는 유지

    async def _handle_incorrect_prediction(
        self, prediction_id: int, user_id: int, trading_day: date, symbol: str
    ) -> None:
        """오답 예측 처리"""
        # 예측 상태를 INCORRECT로 변경
        self.pred_repo.update_prediction_status(prediction_id, StatusEnum.INCORRECT)

        print(f"Marked prediction {prediction_id} as incorrect for user {user_id}")

    async def _void_prediction(
        self,
        prediction_id: int,
        user_id: int,
        trading_day: date,
        symbol: str,
        void_reason: Optional[str],
    ) -> None:
        """예측 무효 처리"""
        try:
            # 예측 상태를 VOID로 변경
            self.pred_repo.update_prediction_status(prediction_id, StatusEnum.VOID)

            # VOID 처리 시에는 예측 수수료를 환불해줌 (비즈니스 규칙)
            try:
                from myapi.schemas.points import PointsTransactionRequest
                
                refund_request = PointsTransactionRequest(
                    amount=self.PREDICTION_FEE_POINTS,
                    reason=f"Refund for void prediction {prediction_id} ({symbol}): {void_reason or 'Price data unavailable'}",
                    ref_id=f"void_refund_{prediction_id}_{trading_day.strftime('%Y%m%d')}"
                )
                
                result = self.point_service.add_points(
                    user_id=user_id,
                    request=refund_request,
                    trading_day=trading_day,
                    symbol=symbol
                )
                
                if result.success:
                    print(
                        f"✅ Refunded {self.PREDICTION_FEE_POINTS} points to user {user_id} for void prediction {prediction_id}"
                    )
                else:
                    print(
                        f"❌ Failed to refund points to user {user_id}: {result.message}"
                    )
            except Exception as refund_error:
                print(f"❌ Error refunding points for void prediction {prediction_id}: {str(refund_error)}")

            print(
                f"Voided prediction {prediction_id} for user {user_id}, reason: {void_reason}"
            )
        except Exception as e:
            print(f"❌ Error voiding prediction {prediction_id}: {str(e)}")

    async def get_settlement_summary(self, trading_day: date) -> Dict[str, Any]:
        """특정 날짜의 정산 요약 정보를 조회합니다."""
        try:
            # 해당 날짜의 모든 예측 통계
            total_predictions = self.pred_repo.count_predictions_by_date(trading_day)
            correct_predictions = self.pred_repo.count_predictions_by_date_and_status(
                trading_day, StatusEnum.CORRECT
            )
            incorrect_predictions = self.pred_repo.count_predictions_by_date_and_status(
                trading_day, StatusEnum.INCORRECT
            )
            void_predictions = self.pred_repo.count_predictions_by_date_and_status(
                trading_day, StatusEnum.VOID
            )
            pending_predictions = self.pred_repo.count_predictions_by_date_and_status(
                trading_day, StatusEnum.PENDING
            )

            # 종목별 통계
            symbol_stats = self._get_symbol_wise_stats(trading_day)

            return {
                "trading_day": trading_day.strftime("%Y-%m-%d"),
                "total_predictions": total_predictions,
                "correct_predictions": correct_predictions,
                "incorrect_predictions": incorrect_predictions,
                "void_predictions": void_predictions,
                "pending_predictions": pending_predictions,
                "overall_accuracy": (
                    (correct_predictions / total_predictions * 100)
                    if total_predictions
                    else 0
                ),
                "settlement_status": (
                    "COMPLETED" if pending_predictions == 0 else "PENDING"
                ),
                "symbol_statistics": symbol_stats,
            }

        except Exception as e:
            raise ServiceException(f"Failed to get settlement summary: {str(e)}")

    def _get_symbol_wise_stats(self, trading_day: date) -> List[Dict[str, Any]]:
        """종목별 정산 통계"""
        # 유니버스 종목들 조회
        universe_items = self.universe_repo.get_universe_for_date(trading_day)
        
        symbol_stats = []
        for universe_item in universe_items:
            symbol = universe_item.symbol
            predictions = self.pred_repo.get_predictions_by_symbol_and_date(
                symbol, trading_day, None
            )

            total = len(predictions)
            correct = len([p for p in predictions if p.status == PredictionStatus.CORRECT])
            incorrect = len(
                [p for p in predictions if p.status == PredictionStatus.INCORRECT]
            )
            void = len([p for p in predictions if p.status == PredictionStatus.VOID])

            symbol_stats.append(
                {
                    "symbol": symbol,
                    "total_predictions": total,
                    "correct_predictions": correct,
                    "incorrect_predictions": incorrect,
                    "void_predictions": void,
                    "accuracy_rate": (correct / total * 100) if total else 0,
                }
            )

        return symbol_stats

    async def manual_settle_symbol(
        self,
        trading_day: date,
        symbol: str,
        correct_choice: PredictionChoice,
        override_price_validation: bool = False,
    ) -> Dict[str, Any]:
        """특정 종목에 대해 수동으로 정산을 수행합니다."""
        try:
            if not override_price_validation:
                # 가격 데이터 검증
                async with self.price_service as price_svc:
                    try:
                        eod_price = await price_svc.get_eod_price(symbol, trading_day)
                        actual_movement = price_svc._calculate_price_movement(
                            eod_price.close_price, eod_price.previous_close
                        )

                        if correct_choice.value.upper() != actual_movement:
                            print(
                                f"Warning: Manual choice {correct_choice.value} differs from calculated movement {actual_movement}"
                            )
                    except Exception as e:
                        print(f"Could not validate price data: {e}")

            # 수동 정산 실행
            correct_count, total_count = self.pred_repo.bulk_update_predictions_status(
                trading_day,
                symbol,
                ChoiceEnum(correct_choice.value),
                points_per_correct=100,
            )

            return {
                "symbol": symbol,
                "trading_day": trading_day.strftime("%Y-%m-%d"),
                "manual_settlement": True,
                "correct_choice": correct_choice.value,
                "total_predictions": total_count,
                "correct_predictions": correct_count,
                "accuracy_rate": (
                    (correct_count / total_count * 100) if total_count else 0
                ),
            }

        except Exception as e:
            raise ServiceException(f"Manual settlement failed for {symbol}: {str(e)}")
