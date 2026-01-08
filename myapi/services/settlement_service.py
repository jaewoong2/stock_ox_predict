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
from myapi.schemas.settlement import (
    DailySettlementResult,
    ManualSettlementResult,
    SettlementRetryResult,
    SettlementRetryResultItem,
    SettlementStatusResponse,
    SettlementSummary,
    SymbolSettlementResult,
    SymbolWiseStats,
)
from myapi.config import Settings
from myapi.services.error_log_service import ErrorLogService


class SettlementService:
    """예측 정산 및 결과 검증 서비스"""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.pred_repo = PredictionRepository(db)
        self.universe_repo = ActiveUniverseRepository(db)
        self.price_service = PriceService(db)
        self.point_service = PointService(db)
        self.error_log_service = ErrorLogService(db)
        self.settings = settings

        # 포인트 지급 설정 (환경변수에서 로드)
        self.CORRECT_PREDICTION_POINTS = settings.CORRECT_PREDICTION_POINTS
        self.PREDICTION_FEE_POINTS = settings.PREDICTION_FEE_POINTS

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.price_service.__aexit__(exc_type, exc_val, exc_tb)

    async def validate_and_settle_day(self, trading_day: date) -> DailySettlementResult:
        """특정 거래일의 예측을 검증하고 정산합니다."""
        # 시작 전에 세션 상태를 확실히 정상화 (이전 실패 잔여 상태 제거)
        try:
            self.db.rollback()
        except Exception:
            pass
        settlement_results: List[SymbolSettlementResult] = (
            []
        )  # 초기화를 try 블록 밖으로 이동
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
            total_processed = 0
            total_correct = 0

            for price_data in settlement_data:
                if not price_data.is_valid_settlement:
                    # 유효하지 않은 가격 데이터는 예측을 VOID로 처리
                    await self._handle_void_predictions(
                        trading_day, price_data.symbol, price_data.void_reason
                    )
                    settlement_results.append(
                        SymbolSettlementResult(
                            symbol=price_data.symbol,
                            status="VOIDED",
                            reason=price_data.void_reason,
                            processed_count=0,
                            correct_count=0,
                        )
                    )
                else:
                    # 정상 정산 처리 (심볼 단위 격리 및 예외 방지)
                    try:
                        result = await self._settle_predictions_for_symbol(
                            trading_day, price_data
                        )
                        settlement_results.append(result)
                        total_processed += result.processed_count
                        total_correct += result.correct_count
                    except Exception as sym_err:
                        # 해당 심볼 처리 실패 시 롤백 후 계속 진행
                        try:
                            self.db.rollback()
                        except Exception:
                            pass
                        settlement_results.append(
                            SymbolSettlementResult(
                                symbol=price_data.symbol,
                                status="FAILED",
                                processed_count=0,
                                correct_count=0,
                                reason=str(sym_err),
                            )
                        )
                        continue

            # 3. 전체 정산 통계 반환
            return DailySettlementResult(
                trading_day=trading_day.strftime("%Y-%m-%d"),
                settlement_completed_at=datetime.now(timezone.utc),
                total_predictions_processed=total_processed,
                total_correct_predictions=total_correct,
                accuracy_rate=(
                    (total_correct / total_processed * 100) if total_processed else 0
                ),
                symbol_results=settlement_results,
            )

        except Exception as e:
            # 정산 실패 에러 로깅
            failed_symbols = [
                result.symbol
                for result in settlement_results
                if result.status == "FAILED"
            ]
            # 로깅 전에 항상 세션 롤백으로 트랜잭션 상태 정리 (안전)
            try:
                self.db.rollback()
            except Exception:
                pass
            self.error_log_service.log_settlement_error(
                trading_day=trading_day,
                failed_symbols=failed_symbols,
                total_symbols=len(settlement_results) if settlement_results else 0,
                error_message=str(e),
                context="Daily settlement validation",
            )
            raise ServiceException(f"Settlement failed for {trading_day}: {str(e)}")

    async def _settle_predictions_for_symbol(
        self, trading_day: date, price_data: SettlementPriceData
    ) -> SymbolSettlementResult:
        """특정 종목의 예측들을 정산합니다."""
        # 심볼 단위 처리 전 세션 상태 정리 (보수적)
        try:
            self.db.rollback()
        except Exception:
            pass
        symbol = price_data.symbol

        # 해당 종목의 대기 중인 예측들 조회
        pending_predictions = self.pred_repo.get_predictions_by_symbol_and_date(
            symbol, trading_day, status_filter=StatusEnum.PENDING
        )

        if not pending_predictions:
            return SymbolSettlementResult(
                symbol=symbol,
                status="NO_PREDICTIONS",
                processed_count=0,
                correct_count=0,
                price_movement=price_data.price_movement,
            )

        correct_count = 0
        processed_count = len(pending_predictions)

        # 각 예측을 검증하고 결과 업데이트
        for prediction in pending_predictions:
            # 예측 방향과 실제 결과 비교
            predicted_direction = prediction.choice.value.upper()  # UP or DOWN

            # 기준 가격: 반드시 예측 시점 스냅샷 가격을 사용 (요건 강화)
            if getattr(prediction, "prediction_price", None) is None:
                # 스냅샷이 없으면 VOID 처리
                await self._void_prediction(
                    prediction.id,
                    prediction.user_id,
                    trading_day,
                    symbol,
                    "Missing snapshot price at prediction time",
                    settlement_price=price_data.settlement_price,
                )
                processed_count -= 1
                continue

            # 스냅샷 값이 비정상(<=0)인 경우도 VOID 처리
            try:
                base_price = Decimal(str(prediction.prediction_price))
            except Exception:
                await self._void_prediction(
                    prediction.id,
                    prediction.user_id,
                    trading_day,
                    symbol,
                    "Invalid snapshot price format",
                    settlement_price=price_data.settlement_price,
                )
                processed_count -= 1
                continue
            if base_price <= 0:
                await self._void_prediction(
                    prediction.id,
                    prediction.user_id,
                    trading_day,
                    symbol,
                    "Invalid snapshot price (<= 0)",
                    settlement_price=price_data.settlement_price,
                )
                processed_count -= 1
                continue

            # 정산 가격 대비 움직임 계산 (예측시점 → 정산시점)
            try:
                actual_movement = self.price_service._calculate_price_movement(
                    price_data.settlement_price, base_price
                )
            except Exception:
                # 안전하게 FLAT 처리 (정산 불가 케이스로 VOID 처리될 수 있음)
                actual_movement = "FLAT"

            is_correct = self._is_prediction_correct(
                predicted_direction, actual_movement
            )

            if is_correct is None:
                # VOID 처리
                await self._void_prediction(
                    prediction.id,
                    prediction.user_id,
                    trading_day,
                    symbol,
                    "FLAT price movement with VOID policy",
                    settlement_price=price_data.settlement_price,
                )
                processed_count -= 1  # VOID는 처리 수에서 제외
            elif is_correct:
                correct_count += 1
                # 정답 예측 처리 (포인트 지급 등)
                await self._award_correct_prediction(
                    prediction.id,
                    prediction.user_id,
                    trading_day,
                    symbol,
                    settlement_price=price_data.settlement_price,
                )
            else:
                # 오답 예측 처리
                await self._handle_incorrect_prediction(
                    prediction.id,
                    prediction.user_id,
                    trading_day,
                    symbol,
                    settlement_price=price_data.settlement_price,
                )

        return SymbolSettlementResult(
            symbol=symbol,
            status="SETTLED",
            processed_count=processed_count,
            correct_count=correct_count,
            accuracy_rate=(
                (correct_count / processed_count * 100) if processed_count else 0
            ),
            price_movement=price_data.price_movement,
            settlement_price=price_data.settlement_price.__float__(),
            change_percent=price_data.change_percent.__float__(),
        )

    async def _handle_void_predictions(
        self, trading_day: date, symbol: str, void_reason: Optional[str]
    ) -> None:
        """유효하지 않은 가격으로 인한 예측 무효 처리"""
        try:
            self.db.rollback()
        except Exception:
            pass
        pending_predictions = self.pred_repo.get_predictions_by_symbol_and_date(
            symbol, trading_day, status_filter=StatusEnum.PENDING
        )

        for prediction in pending_predictions:
            # 예측을 VOID 상태로 변경 (포인트는 반환하거나 유지)
            await self._void_prediction(
                prediction.id, prediction.user_id, trading_day, symbol, void_reason
            )

    def _is_prediction_correct(self, predicted: str, actual: str) -> Optional[bool]:
        """예측이 맞는지 확인

        Returns:
            True: 정답
            False: 오답
            None: VOID 처리 필요
        """
        if actual == "FLAT":
            # 환경변수 설정에 따른 FLAT 가격 처리 정책
            if self.settings.FLAT_PRICE_POLICY == "ALL_CORRECT":
                return True
            elif self.settings.FLAT_PRICE_POLICY == "ALL_WRONG":
                return False
            elif self.settings.FLAT_PRICE_POLICY == "VOID":
                return None  # VOID 처리
            else:
                return False  # 기본값은 틀린 것으로 처리
        return predicted == actual

    async def _award_correct_prediction(
        self,
        prediction_id: int,
        user_id: int,
        trading_day: date,
        symbol: str,
        settlement_price: Optional[Decimal] = None,
    ) -> None:
        """정답 예측에 대한 보상 처리"""
        try:
            # 1. 예측 상태를 CORRECT로 변경
            self.pred_repo.update_prediction_status(
                prediction_id=prediction_id,
                status=StatusEnum.CORRECT,
                points_earned=self.CORRECT_PREDICTION_POINTS,
                settlement_price=settlement_price,
                commit=True,
            )

            # 2. 포인트 지급
            result = self.point_service.award_prediction_points(
                user_id=user_id,
                prediction_id=prediction_id,
                points=self.CORRECT_PREDICTION_POINTS,
                trading_day=trading_day,
                symbol=symbol,
            )

            if result.success:
                print(
                    f"✅ Awarded {self.CORRECT_PREDICTION_POINTS} points to user {user_id} for correct prediction {prediction_id}"
                )
            else:
                # 포인트 지급 실패 에러 로깅
                self.error_log_service.log_point_transaction_error(
                    user_id=user_id,
                    transaction_type="PREDICTION_REWARD",
                    amount=self.CORRECT_PREDICTION_POINTS,
                    error_message=result.message,
                    ref_id=f"prediction_{prediction_id}",
                    trading_day=trading_day,
                )
                print(f"❌ Failed to award points to user {user_id}: {result.message}")
        except Exception as e:
            # 포인트 지급 시스템 에러 로깅
            self.error_log_service.log_point_transaction_error(
                user_id=user_id,
                transaction_type="PREDICTION_REWARD",
                amount=self.CORRECT_PREDICTION_POINTS,
                error_message=str(e),
                ref_id=f"prediction_{prediction_id}",
                trading_day=trading_day,
            )
            print(f"❌ Error awarding points for prediction {prediction_id}: {str(e)}")
            # 포인트 지급 실패해도 예측 결과는 유지

    async def _handle_incorrect_prediction(
        self,
        prediction_id: int,
        user_id: int,
        trading_day: date,
        symbol: str,
        settlement_price: Optional[Decimal] = None,
    ) -> None:
        """오답 예측 처리"""
        # 예측 상태를 INCORRECT로 변경
        self.pred_repo.update_prediction_status(
            prediction_id,
            StatusEnum.INCORRECT,
            settlement_price=settlement_price,
        )

        print(f"Marked prediction {prediction_id} as incorrect for user {user_id}")

    async def _void_prediction(
        self,
        prediction_id: int,
        user_id: int,
        trading_day: date,
        symbol: str,
        void_reason: Optional[str],
        settlement_price: Optional[Decimal] = None,
    ) -> None:
        """예측 무효 처리"""
        try:
            # 예측 상태를 VOID로 변경
            self.pred_repo.update_prediction_status(
                prediction_id,
                StatusEnum.VOID,
                settlement_price=settlement_price,
            )

            # VOID 처리 시에는 예측 수수료를 환불해줌 (비즈니스 규칙)
            try:
                from myapi.schemas.points import PointsTransactionRequest

                refund_request = PointsTransactionRequest(
                    amount=self.PREDICTION_FEE_POINTS,
                    reason=f"Refund for void prediction {prediction_id} ({symbol}): {void_reason or 'Price data unavailable'}",
                    ref_id=f"void_refund_{prediction_id}_{trading_day.strftime('%Y%m%d')}",
                )

                result = self.point_service.add_points(
                    user_id=user_id,
                    request=refund_request,
                    trading_day=trading_day,
                    symbol=symbol,
                )

                if result.success:
                    print(
                        f"✅ Refunded {self.PREDICTION_FEE_POINTS} points to user {user_id} for void prediction {prediction_id}"
                    )
                else:
                    # 포인트 환불 실패 에러 로깅
                    self.error_log_service.log_point_transaction_error(
                        user_id=user_id,
                        transaction_type="PREDICTION_FEE_REFUND",
                        amount=self.PREDICTION_FEE_POINTS,
                        error_message=result.message,
                        ref_id=f"void_refund_{prediction_id}_{trading_day.strftime('%Y%m%d')}",
                        trading_day=trading_day,
                    )
                    print(
                        f"❌ Failed to refund points to user {user_id}: {result.message}"
                    )
            except Exception as refund_error:
                # 환불 시스템 에러 로깅
                self.error_log_service.log_point_transaction_error(
                    user_id=user_id,
                    transaction_type="PREDICTION_FEE_REFUND",
                    amount=self.PREDICTION_FEE_POINTS,
                    error_message=str(refund_error),
                    ref_id=f"void_refund_{prediction_id}_{trading_day.strftime('%Y%m%d')}",
                    trading_day=trading_day,
                )
                print(
                    f"❌ Error refunding points for void prediction {prediction_id}: {str(refund_error)}"
                )

            print(
                f"Voided prediction {prediction_id} for user {user_id}, reason: {void_reason}"
            )
        except Exception as e:
            print(f"❌ Error voiding prediction {prediction_id}: {str(e)}")

    async def get_settlement_summary(self, trading_day: date) -> SettlementSummary:
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

            return SettlementSummary(
                trading_day=trading_day.strftime("%Y-%m-%d"),
                total_predictions=total_predictions,
                correct_predictions=correct_predictions,
                incorrect_predictions=incorrect_predictions,
                void_predictions=void_predictions,
                pending_predictions=pending_predictions,
                overall_accuracy=(
                    (correct_predictions / total_predictions * 100)
                    if total_predictions
                    else 0
                ),
                settlement_status=(
                    "COMPLETED" if pending_predictions == 0 else "PENDING"
                ),
                symbol_statistics=symbol_stats,
            )

        except Exception as e:
            raise ServiceException(f"Failed to get settlement summary: {str(e)}")

    def _get_symbol_wise_stats(self, trading_day: date) -> List[SymbolWiseStats]:
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
            correct = len(
                [p for p in predictions if p.status == PredictionStatus.CORRECT]
            )
            incorrect = len(
                [p for p in predictions if p.status == PredictionStatus.INCORRECT]
            )
            void = len([p for p in predictions if p.status == PredictionStatus.VOID])

            symbol_stats.append(
                SymbolWiseStats(
                    symbol=symbol,
                    total_predictions=total,
                    correct_predictions=correct,
                    incorrect_predictions=incorrect,
                    void_predictions=void,
                    accuracy_rate=(correct / total * 100) if total else 0,
                )
            )

        return symbol_stats

    async def manual_settle_symbol(
        self,
        trading_day: date,
        symbol: str,
        correct_choice: PredictionChoice,
        override_price_validation: bool = False,
    ) -> ManualSettlementResult:
        """특정 종목에 대해 수동으로 정산을 수행합니다."""
        try:
            settlement_price: Optional[Decimal] = None
            if not override_price_validation:
                # 가격 데이터 검증
                async with self.price_service as price_svc:
                    try:
                        eod_price = await price_svc.get_eod_price(symbol, trading_day)
                        settlement_price = eod_price.close_price
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
                points_per_correct=self.CORRECT_PREDICTION_POINTS,
                settlement_price=settlement_price,
            )

            # 수동 정산에서도 포인트 지급 (자동 정산과 동일하게 처리)
            if correct_count > 0:
                # 정답 예측한 사용자들에게 포인트 지급
                correct_predictions = self.pred_repo.get_predictions_by_symbol_and_date(
                    symbol, trading_day, StatusEnum.CORRECT
                )

                for prediction in correct_predictions:
                    try:
                        result = self.point_service.award_prediction_points(
                            user_id=prediction.user_id,
                            prediction_id=prediction.id,
                            points=self.CORRECT_PREDICTION_POINTS,
                            trading_day=trading_day,
                            symbol=symbol,
                        )

                        if result.success:
                            print(
                                f"✅ Manual settlement: Awarded {self.CORRECT_PREDICTION_POINTS} points to user {prediction.user_id} for prediction {prediction.id}"
                            )
                        else:
                            print(
                                f"❌ Manual settlement: Failed to award points to user {prediction.user_id}: {result.message}"
                            )
                    except Exception as e:
                        print(
                            f"❌ Manual settlement: Error awarding points for prediction {prediction.id}: {str(e)}"
                        )

            return ManualSettlementResult(
                symbol=symbol,
                trading_day=trading_day.strftime("%Y-%m-%d"),
                manual_settlement=True,
                correct_choice=correct_choice.value,
                total_predictions=total_count,
                correct_predictions=correct_count,
                accuracy_rate=(
                    (correct_count / total_count * 100) if total_count else 0
                ),
            )

        except Exception as e:
            raise ServiceException(f"Manual settlement failed for {symbol}: {str(e)}")

    async def get_settlement_status(
        self, trading_day: date
    ) -> SettlementStatusResponse:
        """특정 거래일의 정산 진행 상태를 조회합니다."""
        try:
            # 해당 날짜의 유니버스 종목 수 조회
            universe_items = self.universe_repo.get_universe_for_date(trading_day)
            total_symbols = len(universe_items)

            if total_symbols == 0:
                return SettlementStatusResponse(
                    trading_day=trading_day.strftime("%Y-%m-%d"),
                    status="NO_UNIVERSE",
                    message="No universe defined for this trading day",
                    total_symbols=0,
                    pending_symbols=0,
                    completed_symbols=0,
                    failed_symbols=0,
                    progress_percentage=0.0,
                )

            # 종목별 예측 상태 집계
            pending_symbols = 0
            completed_symbols = 0
            failed_symbols = 0

            for universe_item in universe_items:
                symbol = universe_item.symbol
                predictions = self.pred_repo.get_predictions_by_symbol_and_date(
                    symbol, trading_day, None
                )

                if not predictions:
                    continue

                # 해당 종목의 예측 상태 확인
                has_pending = any(p.status == StatusEnum.PENDING for p in predictions)

                if has_pending:
                    pending_symbols += 1
                else:
                    # 모든 예측이 처리됨 (CORRECT, INCORRECT, VOID)
                    completed_symbols += 1

            # 전체 상태 결정
            if pending_symbols == 0:
                overall_status = "COMPLETED"
            elif completed_symbols == 0:
                overall_status = "PENDING"
            else:
                overall_status = "IN_PROGRESS"

            progress_percentage = (
                (completed_symbols / total_symbols * 100) if total_symbols > 0 else 0
            )

            return SettlementStatusResponse(
                trading_day=trading_day.strftime("%Y-%m-%d"),
                status=overall_status,
                total_symbols=total_symbols,
                pending_symbols=pending_symbols,
                completed_symbols=completed_symbols,
                failed_symbols=failed_symbols,
                progress_percentage=round(progress_percentage, 2),
                last_updated=datetime.now(timezone.utc),
            )

        except Exception as e:
            raise ServiceException(
                f"Failed to get settlement status for {trading_day}: {str(e)}"
            )

    async def retry_settlement(
        self, trading_day: date, symbols: List[str] = []
    ) -> SettlementRetryResult:
        """실패했거나 PENDING 상태인 예측들의 정산을 재시도합니다."""
        try:
            if symbols is None:
                # 모든 PENDING 상태 예측들 재정산
                universe_items = self.universe_repo.get_universe_for_date(trading_day)
                symbols = [item.symbol for item in universe_items]

            retry_results: List[SettlementRetryResultItem] = []
            total_retried = 0
            total_success = 0

            for symbol in symbols:
                # 해당 종목의 PENDING 예측이 있는지 확인
                pending_predictions = self.pred_repo.get_predictions_by_symbol_and_date(
                    symbol, trading_day, status_filter=StatusEnum.PENDING
                )

                if not pending_predictions:
                    retry_results.append(
                        SettlementRetryResultItem(
                            symbol=symbol,
                            status="SKIPPED",
                            message="No pending predictions found",
                        )
                    )
                    continue

                try:
                    # 해당 종목만 다시 정산
                    async with self.price_service as price_svc:
                        settlement_data = await price_svc.validate_settlement_prices(
                            trading_day
                        )

                    # 해당 symbol의 데이터 찾기
                    symbol_price_data = None
                    for price_data in settlement_data:
                        if price_data.symbol == symbol:
                            symbol_price_data = price_data
                            break

                    if symbol_price_data:
                        if symbol_price_data.is_valid_settlement:
                            result = await self._settle_predictions_for_symbol(
                                trading_day, symbol_price_data
                            )
                            retry_results.append(
                                SettlementRetryResultItem(
                                    symbol=symbol,
                                    status="SUCCESS",
                                    processed_count=result.processed_count,
                                    correct_count=result.correct_count,
                                )
                            )
                            total_success += 1
                        else:
                            await self._handle_void_predictions(
                                trading_day, symbol, symbol_price_data.void_reason
                            )
                            retry_results.append(
                                SettlementRetryResultItem(
                                    symbol=symbol,
                                    status="VOIDED",
                                    reason=symbol_price_data.void_reason,
                                )
                            )
                            total_success += 1
                    else:
                        retry_results.append(
                            SettlementRetryResultItem(
                                symbol=symbol,
                                status="FAILED",
                                message="Price data not available",
                            )
                        )

                    total_retried += 1

                except Exception as e:
                    retry_results.append(
                        SettlementRetryResultItem(
                            symbol=symbol, status="FAILED", message=str(e)
                        )
                    )
                    total_retried += 1

            return SettlementRetryResult(
                trading_day=trading_day.strftime("%Y-%m-%d"),
                retry_completed_at=datetime.now(timezone.utc),
                total_symbols_retried=total_retried,
                successful_retries=total_success,
                failed_retries=total_retried - total_success,
                results=retry_results,
            )

        except Exception as e:
            raise ServiceException(
                f"Settlement retry failed for {trading_day}: {str(e)}"
            )
