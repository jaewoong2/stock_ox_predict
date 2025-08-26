"""
배치 작업 실행기

SQS에서 수신된 배치 작업들을 실제로 실행하는 서비스입니다.
각 작업 타입별로 적절한 API 엔드포인트를 호출하여 처리합니다.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from myapi.services.settlement_service import SettlementService
from myapi.services.session_service import SessionService
from myapi.services.universe_service import UniverseService
from myapi.services.price_service import PriceService
from myapi.services.point_service import PointService
from myapi.schemas.universe import UniverseItem, UniverseUpdate
from myapi.schemas.session import SessionPhase
from myapi.core.exceptions import ValidationError, ServiceException, BusinessLogicError
from myapi.utils.timezone_utils import get_kst_now

logger = logging.getLogger(__name__)


@dataclass
class JobExecutionResult:
    """작업 실행 결과"""
    success: bool
    job_id: str
    job_type: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


class BatchJobExecutor:
    """배치 작업 실행기"""
    
    def __init__(self, db: Session):
        self.db = db
        
        # 서비스 의존성
        self.settlement_service = SettlementService(db)
        self.session_service = SessionService(db)
        self.universe_service = UniverseService(db)
        self.price_service = PriceService(db)
        self.point_service = PointService(db)

    async def execute_job(self, job_message: Dict[str, Any]) -> JobExecutionResult:
        """
        SQS에서 받은 작업 메시지를 실행합니다.
        
        Args:
            job_message: SQS 메시지에서 파싱된 작업 정보
            
        Returns:
            JobExecutionResult: 작업 실행 결과
        """
        start_time = datetime.now()
        
        try:
            job_id = job_message.get("job_id")
            job_type = job_message.get("job_type")
            payload = job_message.get("payload", {})
            trading_day = date.fromisoformat(job_message.get("trading_day"))
            
            logger.info(f"Executing job {job_id}: {job_type} for {trading_day}")
            
            # 작업 타입별 실행
            if job_type == "settlement":
                result_data = await self._execute_settlement_job(trading_day, payload)
            elif job_type == "session_start":
                result_data = await self._execute_session_start_job(trading_day, payload)
            elif job_type == "session_end":
                result_data = await self._execute_session_end_job(trading_day, payload)
            elif job_type == "universe_prepare":
                result_data = await self._execute_universe_prepare_job(trading_day, payload)
            elif job_type == "price_cache_refresh":
                result_data = await self._execute_price_refresh_job(trading_day, payload)
            else:
                raise ValidationError(f"Unknown job type: {job_type}")
            
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return JobExecutionResult(
                success=True,
                job_id=job_id,
                job_type=job_type,
                message=f"Job {job_type} completed successfully",
                data=result_data,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            error_msg = str(e)
            
            logger.error(f"Job execution failed: {error_msg}")
            
            return JobExecutionResult(
                success=False,
                job_id=job_message.get("job_id", "unknown"),
                job_type=job_message.get("job_type", "unknown"),
                message=f"Job execution failed: {error_msg}",
                error=error_msg,
                execution_time_ms=execution_time
            )

    async def _execute_settlement_job(self, trading_day: date, payload: Dict[str, Any]) -> Dict[str, Any]:
        """정산 작업을 실행합니다."""
        logger.info(f"Starting settlement for {trading_day}")
        
        try:
            # 정산 서비스 호출
            async with self.settlement_service as settlement_svc:
                settlement_result = await settlement_svc.validate_and_settle_day(trading_day)
            
            logger.info(f"Settlement completed for {trading_day}: {settlement_result['total_predictions_processed']} predictions processed")
            
            return {
                "action": "settlement_completed",
                "trading_day": trading_day.isoformat(),
                "settlement_result": settlement_result,
                "processed_at": get_kst_now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Settlement failed for {trading_day}: {e}")
            raise ServiceException(f"Settlement job failed: {e}")

    async def _execute_session_start_job(self, trading_day: date, payload: Dict[str, Any]) -> Dict[str, Any]:
        """세션 시작 작업을 실행합니다."""
        logger.info(f"Starting prediction session for {trading_day}")
        
        try:
            # 세션을 OPEN 상태로 전환
            session_status = self.session_service.transition_session_phase(
                trading_day=trading_day,
                target_phase=SessionPhase.OPEN
            )
            
            if not session_status:
                raise BusinessLogicError(f"Failed to start session for {trading_day}")
            
            logger.info(f"Prediction session started for {trading_day}")
            
            return {
                "action": "session_started",
                "trading_day": trading_day.isoformat(),
                "phase": session_status.phase.value,
                "is_prediction_open": session_status.is_prediction_open,
                "started_at": get_kst_now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Session start failed for {trading_day}: {e}")
            raise ServiceException(f"Session start job failed: {e}")

    async def _execute_session_end_job(self, trading_day: date, payload: Dict[str, Any]) -> Dict[str, Any]:
        """세션 종료 작업을 실행합니다."""
        logger.info(f"Ending prediction session for {trading_day}")
        
        try:
            # 세션을 CLOSED 상태로 전환
            session_status = self.session_service.transition_session_phase(
                trading_day=trading_day,
                target_phase=SessionPhase.CLOSED
            )
            
            if not session_status:
                raise BusinessLogicError(f"Failed to end session for {trading_day}")
            
            # 예측 잠금 (추가 제출 방지)
            if payload.get("lock_predictions", True):
                # 세션이 CLOSED 상태가 되면 자동으로 예측이 잠김
                logger.info(f"Predictions locked for {trading_day}")
            
            logger.info(f"Prediction session ended for {trading_day}")
            
            return {
                "action": "session_ended",
                "trading_day": trading_day.isoformat(),
                "phase": session_status.phase.value,
                "is_prediction_open": session_status.is_prediction_open,
                "predictions_locked": payload.get("lock_predictions", True),
                "ended_at": get_kst_now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Session end failed for {trading_day}: {e}")
            raise ServiceException(f"Session end job failed: {e}")

    async def _execute_universe_prepare_job(self, trading_day: date, payload: Dict[str, Any]) -> Dict[str, Any]:
        """유니버스 준비 작업을 실행합니다."""
        logger.info(f"Preparing universe for {trading_day}")
        
        try:
            symbols = payload.get("symbols", [])
            
            if not symbols:
                raise ValidationError("No symbols provided for universe preparation")
            
            # UniverseItem 객체 생성
            universe_items = [
                UniverseItem(symbol=symbol.upper(), seq=i + 1)
                for i, symbol in enumerate(symbols[:20])  # 최대 20개
            ]
            
            # 유니버스 업데이트
            update_payload = UniverseUpdate(
                trading_day=trading_day.isoformat(),
                symbols=universe_items
            )
            
            universe_result = self.universe_service.upsert_universe(update_payload)
            
            logger.info(f"Universe prepared for {trading_day}: {len(universe_items)} symbols")
            
            return {
                "action": "universe_prepared",
                "trading_day": trading_day.isoformat(),
                "universe": universe_result.model_dump(),
                "symbol_count": len(universe_items),
                "prepared_at": get_kst_now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Universe preparation failed for {trading_day}: {e}")
            raise ServiceException(f"Universe preparation job failed: {e}")

    async def _execute_price_refresh_job(self, trading_day: date, payload: Dict[str, Any]) -> Dict[str, Any]:
        """가격 캐시 갱신 작업을 실행합니다."""
        logger.info(f"Refreshing price cache for {trading_day}")
        
        try:
            # 오늘의 유니버스 가격 조회 (캐시 갱신 효과)
            async with self.price_service as price_svc:
                universe_prices = await price_svc.get_universe_current_prices(trading_day)
            
            cache_duration = payload.get("cache_duration", 300)  # 기본 5분
            
            logger.info(f"Price cache refreshed for {trading_day}: {len(universe_prices.prices)} symbols")
            
            return {
                "action": "price_cache_refreshed",
                "trading_day": trading_day.isoformat(),
                "symbol_count": len(universe_prices.prices),
                "market_status": universe_prices.market_status,
                "cache_duration_seconds": cache_duration,
                "refreshed_at": get_kst_now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Price cache refresh failed for {trading_day}: {e}")
            raise ServiceException(f"Price cache refresh job failed: {e}")

    def get_supported_job_types(self) -> list[str]:
        """지원하는 작업 타입 목록을 반환합니다."""
        return [
            "settlement",
            "session_start", 
            "session_end",
            "universe_prepare",
            "price_cache_refresh"
        ]

    def validate_job_message(self, job_message: Dict[str, Any]) -> bool:
        """작업 메시지의 유효성을 검증합니다."""
        required_fields = ["job_id", "job_type", "trading_day", "payload"]
        
        for field in required_fields:
            if field not in job_message:
                logger.error(f"Missing required field: {field}")
                return False
        
        job_type = job_message["job_type"]
        if job_type not in self.get_supported_job_types():
            logger.error(f"Unsupported job type: {job_type}")
            return False
        
        try:
            date.fromisoformat(job_message["trading_day"])
        except ValueError:
            logger.error(f"Invalid trading_day format: {job_message['trading_day']}")
            return False
        
        return True