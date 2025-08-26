from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from myapi.services.universe_service import UniverseService
from myapi.services.session_service import SessionService
from myapi.services.aws_service import AwsService
from myapi.schemas.universe import UniverseItem, UniverseUpdate, UniverseResponse
from myapi.schemas.session import SessionStatus
from myapi.core.exceptions import ValidationError, BusinessLogicError
from myapi.config import Settings
from myapi.utils.market_hours import USMarketHours


class BatchService:
    """배치 작업 관련 비즈니스 로직"""

    def __init__(
        self,
        db: Session,
        aws_service: Optional[AwsService] = None,
        settings: Optional[Settings] = None,
    ):
        self.db = db
        self.universe_service = UniverseService(db)
        self.session_service = SessionService(db)
        self.aws_service = aws_service
        self.settings = settings

    def create_daily_universe(
        self, trading_day: date, symbols: List[str]
    ) -> UniverseResponse:
        """
        일일 유니버스를 생성합니다.

        Args:
            trading_day: 거래일
            symbols: 종목 심볼 리스트

        Returns:
            UniverseResponse: 생성된 유니버스 정보
        """
        if not symbols:
            raise ValidationError("Symbols list cannot be empty")

        if len(symbols) > 20:
            raise ValidationError("Cannot create universe with more than 20 symbols")

        # Create UniverseItem objects with sequence numbers
        universe_items = [
            UniverseItem(symbol=symbol.upper(), seq=i + 1)
            for i, symbol in enumerate(symbols[:20])  # Limit to 20
        ]

        # Create UniverseUpdate payload
        update_payload = UniverseUpdate(
            trading_day=trading_day.strftime("%Y-%m-%d"), symbols=universe_items
        )

        return self.universe_service.upsert_universe(update_payload)

    def create_default_universe(self, trading_day: date) -> UniverseResponse:
        """
        기본 종목 리스트로 일일 유니버스를 생성합니다.

        Args:
            trading_day: 거래일

        Returns:
            UniverseResponse: 생성된 유니버스 정보
        """
        # Default tickers from docs/tickers.md
        default_tickers = [
            "CRWV",
            "SPY",
            "QQQ",
            "AMAT",
            "AMD",
            "ANET",
            "ASML",
            "AVGO",
            "COHR",
            "GFS",
            "KLAC",
            "MRVL",
            "MU",
            "NVDA",
            "NVMI",
            "ONTO",
            "SMCI",
            "STX",
            "TSM",
            "VRT",
        ]

        return self.create_daily_universe(trading_day, default_tickers)

    def transition_session_phase(
        self, trading_day: Optional[date] = None, target_phase: str = "OPEN"
    ) -> Optional[SessionStatus]:
        """
        세션의 단계를 변경합니다.

        Args:
            trading_day: 거래일 (None이면 현재 세션)
            target_phase: 변경할 단계 ("OPEN", "CLOSED", "SETTLING")

        Returns:
            SessionStatus: 변경된 세션 상태
        """
        if target_phase == "OPEN":
            return self.session_service.open_predictions(trading_day)
        elif target_phase == "CLOSED":
            return self.session_service.close_predictions(trading_day)
        elif target_phase == "SETTLE_READY":
            return self.session_service.mark_settle_ready(trading_day)
        elif target_phase == "SETTLED":
            return self.session_service.mark_settlement_complete(trading_day)
        else:
            raise ValidationError(f"Invalid target phase: {target_phase}")

    def get_batch_summary(self, trading_day: Optional[date] = None) -> Dict[str, Any]:
        """
        배치 작업 요약 정보를 반환합니다.

        Args:
            trading_day: 거래일 (None이면 현재 세션)

        Returns:
            Dict: 배치 작업 요약 정보
        """
        # Get session info
        if trading_day:
            session = self.session_service.get_status_by_date(trading_day)
        else:
            session = self.session_service.get_current_status()
            trading_day = session.trading_day if session else date.today()

        # Get universe info
        universe = self.universe_service.get_universe_for_date(trading_day)

        return {
            "trading_day": trading_day.strftime("%Y-%m-%d"),
            "session": (
                {
                    "phase": session.phase.value if session else None,
                    "is_prediction_open": (
                        session.is_prediction_open if session else False
                    ),
                    "is_settling": session.is_settling if session else False,
                }
                if session
                else None
            ),
            "universe": (
                {
                    "total_symbols": universe.total_count if universe else 0,
                    "symbols": (
                        [item.symbol for item in universe.symbols] if universe else []
                    ),
                }
                if universe
                else None
            ),
        }

    def schedule_batch_jobs(self, queue_url: str) -> List[Dict[str, Any]]:
        """
        배치 작업들을 SQS 큐에 스케줄링합니다.

        Args:
            queue_url: SQS FIFO 큐 URL

        Returns:
            List[Dict]: 스케줄링된 작업들의 응답 정보
        """
        if not self.aws_service or not self.settings:
            raise ValidationError(
                "AWS service and settings are required for batch scheduling"
            )

        today_str = date.today().isoformat()

        # 배치 작업 정의
        batch_jobs = [
            {
                "operation": "create_universe",
                "path": "batch/universe/create",
                "method": "POST",
                "body": {"trading_day": today_str, "use_default": True},
                "group_id": "universe-batch",
                "description": "Create daily universe with default tickers",
            },
            {
                "operation": "open_predictions",
                "path": "batch/session/transition",
                "method": "POST",
                "body": {"target_phase": "OPEN"},
                "group_id": "session-batch",
                "description": "Open predictions for the day",
                "delay_seconds": 60,  # 1분 후 실행
            },
            {
                "operation": "close_predictions",
                "path": "batch/session/transition",
                "method": "POST",
                "body": {"target_phase": "CLOSED"},
                "group_id": "session-batch",
                "description": "Close predictions",
                "delay_seconds": 3600,  # 1시간 후 실행
            },
        ]

        responses = []
        for job in batch_jobs:
            try:
                # HTTP 요청을 SQS 메시지 형식으로 변환
                message_body = self.aws_service.generate_queue_message_http(
                    path=job["path"],
                    method=job["method"],
                    body=json.dumps(job["body"]),
                    auth_token=(
                        getattr(self.settings, "AUTH_TOKEN", "")
                        if self.settings
                        else ""
                    ),
                )

                # 고유한 중복 제거 ID 생성
                deduplication_id = f"{job['operation']}-{today_str}"

                # SQS FIFO 큐에 메시지 전송
                response = self.aws_service.send_sqs_fifo_message(
                    queue_url=queue_url,
                    message_body=json.dumps(message_body),
                    message_group_id=job["group_id"],
                    message_deduplication_id=deduplication_id,
                    delay_seconds=job.get("delay_seconds", 0),
                )

                responses.append(
                    {
                        "operation": job["operation"],
                        "description": job["description"],
                        "status": "queued",
                        "message_id": response.get("MessageId"),
                        "delay_seconds": job.get("delay_seconds", 0),
                    }
                )

            except Exception as e:
                responses.append(
                    {
                        "operation": job["operation"],
                        "description": job["description"],
                        "status": "failed",
                        "error": str(e),
                    }
                )

        return responses

    def schedule_daily_workflow(self, queue_url: str) -> Dict[str, Any]:
        """
        일일 워크플로우를 스케줄링합니다 (유니버스 생성 → 예측 시작 → 예측 마감).

        Args:
            queue_url: SQS FIFO 큐 URL

        Returns:
            Dict: 워크플로우 스케줄링 결과
        """
        try:
            scheduled_jobs = self.schedule_batch_jobs(queue_url)

            return {
                "workflow": "daily_batch_workflow",
                "trading_day": date.today().isoformat(),
                "total_jobs": len(scheduled_jobs),
                "successful_jobs": len(
                    [job for job in scheduled_jobs if job["status"] == "queued"]
                ),
                "failed_jobs": len(
                    [job for job in scheduled_jobs if job["status"] == "failed"]
                ),
                "jobs": scheduled_jobs,
            }

        except Exception as e:
            raise BusinessLogicError(
                error_code="WORKFLOW_SCHEDULING_FAILED",
                message=f"Failed to schedule daily workflow: {str(e)}",
            )

    def schedule_time_based_session_transitions(self, queue_url: str, trading_day: Optional[date] = None) -> Dict[str, Any]:
        """
        시간 기반 세션 전환을 스케줄링합니다.
        - 06:00: 예측 시작 (OPEN)
        - 23:59: 예측 마감 (CLOSED)
        
        Args:
            queue_url: SQS FIFO 큐 URL
            trading_day: 대상 거래일 (None이면 오늘)
            
        Returns:
            Dict: 스케줄링 결과
        """
        if not self.aws_service or not self.settings:
            raise ValidationError("AWS service and settings are required for scheduling")
        
        target_date = trading_day or USMarketHours.get_current_kst_time().date()
        current_kst = USMarketHours.get_current_kst_time()
        
        # 거래일 확인
        if not USMarketHours.is_us_trading_day(target_date):
            return {
                "status": "skipped",
                "message": f"{target_date}는 미국 증시 거래일이 아닙니다.",
                "trading_day": target_date.isoformat()
            }
        
        # 예측 시작 시간 (06:00)
        predict_start_time = datetime.combine(target_date, time(6, 0))
        # 예측 마감 시간 (23:59)
        predict_end_time = datetime.combine(target_date, time(23, 59))
        
        scheduled_jobs = []
        
        # 예측 시작 스케줄링 (06:00)
        if current_kst < predict_start_time:
            delay_seconds = int((predict_start_time - current_kst).total_seconds())
            
            start_job = {
                "operation": "auto_open_predictions",
                "path": "batch/session/transition", 
                "method": "POST",
                "body": {"target_phase": "OPEN", "trading_day": target_date.isoformat()},
                "group_id": "auto-session-batch",
                "description": f"Auto open predictions at 06:00 for {target_date}",
                "delay_seconds": delay_seconds,
                "scheduled_time": predict_start_time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            try:
                message_body = self.aws_service.generate_queue_message_http(
                    path=start_job["path"],
                    method=start_job["method"], 
                    body=json.dumps(start_job["body"]),
                    auth_token=getattr(self.settings, "AUTH_TOKEN", "")
                )
                
                deduplication_id = f"auto-open-{target_date.isoformat()}"
                
                response = self.aws_service.send_sqs_fifo_message(
                    queue_url=queue_url,
                    message_body=json.dumps(message_body),
                    message_group_id=start_job["group_id"],
                    message_deduplication_id=deduplication_id,
                    delay_seconds=delay_seconds
                )
                
                scheduled_jobs.append({
                    **start_job,
                    "status": "scheduled",
                    "message_id": response.get("MessageId")
                })
                
            except Exception as e:
                scheduled_jobs.append({
                    **start_job,
                    "status": "failed",
                    "error": str(e)
                })
        
        # 예측 마감 스케줄링 (23:59)  
        if current_kst < predict_end_time:
            delay_seconds = int((predict_end_time - current_kst).total_seconds())
            
            end_job = {
                "operation": "auto_close_predictions",
                "path": "batch/session/transition",
                "method": "POST", 
                "body": {"target_phase": "CLOSED", "trading_day": target_date.isoformat()},
                "group_id": "auto-session-batch",
                "description": f"Auto close predictions at 23:59 for {target_date}",
                "delay_seconds": delay_seconds,
                "scheduled_time": predict_end_time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            try:
                message_body = self.aws_service.generate_queue_message_http(
                    path=end_job["path"],
                    method=end_job["method"],
                    body=json.dumps(end_job["body"]),
                    auth_token=getattr(self.settings, "AUTH_TOKEN", "")
                )
                
                deduplication_id = f"auto-close-{target_date.isoformat()}"
                
                response = self.aws_service.send_sqs_fifo_message(
                    queue_url=queue_url,
                    message_body=json.dumps(message_body), 
                    message_group_id=end_job["group_id"],
                    message_deduplication_id=deduplication_id,
                    delay_seconds=delay_seconds
                )
                
                scheduled_jobs.append({
                    **end_job,
                    "status": "scheduled", 
                    "message_id": response.get("MessageId")
                })
                
            except Exception as e:
                scheduled_jobs.append({
                    **end_job,
                    "status": "failed",
                    "error": str(e)
                })
        
        return {
            "workflow": "time_based_session_transitions",
            "trading_day": target_date.isoformat(),
            "current_time": current_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "total_jobs": len(scheduled_jobs),
            "successful_jobs": len([job for job in scheduled_jobs if job["status"] == "scheduled"]),
            "failed_jobs": len([job for job in scheduled_jobs if job["status"] == "failed"]),
            "jobs": scheduled_jobs
        }

    def auto_check_and_schedule_sessions(self, queue_url: str) -> Dict[str, Any]:
        """
        현재 시간을 확인하여 필요한 세션 전환을 자동으로 스케줄링합니다.
        
        Args:
            queue_url: SQS FIFO 큐 URL
            
        Returns:
            Dict: 자동 스케줄링 결과
        """
        current_kst = USMarketHours.get_current_kst_time()
        today = current_kst.date()
        
        # 거래일이 아니면 스킵
        if not USMarketHours.is_us_trading_day(today):
            return {
                "status": "skipped",
                "message": f"{today}는 미국 증시 거래일이 아닙니다.",
                "current_time": current_kst.strftime("%Y-%m-%d %H:%M:%S")
            }
        
        # 현재 세션 상태 확인
        current_session = self.session_service.get_status_by_date(today)
        
        # 세션이 없으면 생성
        if not current_session:
            try:
                current_session = self.session_service.create_session(today)
            except Exception as e:
                return {
                    "status": "failed",
                    "message": f"세션 생성 실패: {str(e)}",
                    "current_time": current_kst.strftime("%Y-%m-%d %H:%M:%S")
                }
        
        # 예측 시간 확인
        predict_status = self.session_service.get_prediction_time_status(today)
        
        results = []
        
        # 06:00이 지났고 아직 OPEN 상태가 아니면 즉시 OPEN으로 전환
        if (current_kst.time() >= time(6, 0) and 
            current_kst.time() <= time(23, 59) and 
            current_session.phase.value != "OPEN"):
            
            try:
                updated_session = self.session_service.open_predictions(today)
                results.append({
                    "action": "immediate_open",
                    "status": "success",
                    "message": "예측을 즉시 시작했습니다.",
                    "session_phase": updated_session.phase.value if updated_session else None
                })
            except Exception as e:
                results.append({
                    "action": "immediate_open", 
                    "status": "failed",
                    "error": str(e)
                })
        
        # 23:59가 지났고 아직 CLOSED가 아니면 즉시 CLOSED로 전환  
        elif (current_kst.time() > time(23, 59) and 
              current_session.phase.value == "OPEN"):
            
            try:
                updated_session = self.session_service.close_predictions(today)
                results.append({
                    "action": "immediate_close",
                    "status": "success", 
                    "message": "예측을 즉시 마감했습니다.",
                    "session_phase": updated_session.phase.value if updated_session else None
                })
            except Exception as e:
                results.append({
                    "action": "immediate_close",
                    "status": "failed",
                    "error": str(e)
                })
        
        # 향후 전환 스케줄링
        schedule_result = self.schedule_time_based_session_transitions(queue_url, today)
        
        return {
            "workflow": "auto_session_check_and_schedule",
            "trading_day": today.isoformat(),
            "current_time": current_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "session_status": {
                "phase": current_session.phase.value if current_session else None,
                "can_predict": predict_status["can_predict"],
                "message": predict_status["message"]
            },
            "immediate_actions": results,
            "scheduled_transitions": schedule_result
        }
