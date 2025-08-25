from __future__ import annotations

import json
from datetime import date
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from myapi.services.universe_service import UniverseService
from myapi.services.session_service import SessionService
from myapi.services.aws_service import AwsService
from myapi.schemas.universe import UniverseItem, UniverseUpdate, UniverseResponse
from myapi.schemas.session import SessionStatus
from myapi.core.exceptions import ValidationError, BusinessLogicError
from myapi.config import Settings


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
