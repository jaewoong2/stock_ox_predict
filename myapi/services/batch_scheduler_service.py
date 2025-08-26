"""
배치 스케줄러 서비스

시간대별로 Queue에 예측 시스템 관련 API 요청을 스케줄링하는 서비스입니다.
한국 시간(KST) 기준으로 다음 작업들을 자동화합니다:

- 06:00 KST: 미장 마감 후 정산 작업
- 06:01 KST: 새로운 세션 시작 (예측 가능)
- 23:59 KST: 예측 마감 (세션 종료)
- 00:00 KST: 다음날 유니버스 준비
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from myapi.services.aws_service import AwsService
from myapi.services.settlement_service import SettlementService
from myapi.services.session_service import SessionService
from myapi.services.universe_service import UniverseService
from myapi.services.price_service import PriceService
from myapi.schemas.batch import BatchJobStatus, BatchWorkflowResponse
from myapi.core.exceptions import ValidationError, ServiceException
from myapi.utils.timezone_utils import KST, get_kst_now, to_kst
import logging

logger = logging.getLogger(__name__)


class ScheduledJobType(Enum):
    """스케줄된 작업 타입"""
    SETTLEMENT = "settlement"                    # 정산 작업
    SESSION_START = "session_start"            # 세션 시작
    SESSION_END = "session_end"                # 세션 종료  
    UNIVERSE_PREPARE = "universe_prepare"      # 유니버스 준비
    PRICE_CACHE_REFRESH = "price_cache_refresh" # 가격 캐시 갱신


@dataclass
class ScheduledJob:
    """스케줄된 작업 정보"""
    job_id: str
    job_type: ScheduledJobType
    trading_day: date
    scheduled_time: datetime  # KST 시간
    payload: Dict[str, Any]
    delay_seconds: int = 0
    priority: int = 1  # 1=높음, 2=보통, 3=낮음


class BatchSchedulerService:
    """시간대별 배치 작업 스케줄링 서비스"""
    
    def __init__(self, db: Session, aws_service: Optional[AwsService] = None):
        self.db = db
        self.aws_service = aws_service
        
        # 의존 서비스들
        self.settlement_service = SettlementService(db)
        self.session_service = SessionService(db)
        self.universe_service = UniverseService(db)
        self.price_service = PriceService(db)
        
        # KST 기준 스케줄 시간 설정
        self.SCHEDULE_TIMES = {
            ScheduledJobType.SETTLEMENT: time(6, 0),        # 06:00 KST - 정산
            ScheduledJobType.SESSION_START: time(6, 1),     # 06:01 KST - 예측 시작
            ScheduledJobType.SESSION_END: time(23, 59),     # 23:59 KST - 예측 마감
            ScheduledJobType.UNIVERSE_PREPARE: time(0, 0),  # 00:00 KST - 유니버스 준비
            ScheduledJobType.PRICE_CACHE_REFRESH: time(9, 30), # 09:30 KST - 장 시작 후
        }
        
        # 기본 유니버스 종목
        self.DEFAULT_UNIVERSE = [
            "SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "AMZN", 
            "META", "NFLX", "AMD", "INTC", "CRM", "ORCL", "ADBE", "PYPL",
            "UBER", "AIRB", "ZOOM", "SHOP"
        ]

    async def schedule_daily_workflow(self, queue_url: str, trading_day: Optional[date] = None) -> BatchWorkflowResponse:
        """
        일일 전체 워크플로우를 스케줄링합니다.
        
        Args:
            queue_url: SQS FIFO 큐 URL
            trading_day: 대상 거래일 (None이면 오늘)
            
        Returns:
            BatchWorkflowResponse: 스케줄링 결과
        """
        if not trading_day:
            trading_day = date.today()
            
        if not self.aws_service:
            raise ServiceException("AWS service not configured")
            
        logger.info(f"Starting daily workflow scheduling for {trading_day}")
        
        # 스케줄된 작업들 생성
        scheduled_jobs = await self._create_daily_jobs(trading_day)
        
        # SQS로 작업 큐잉
        job_statuses = []
        successful_jobs = 0
        failed_jobs = 0
        
        for job in scheduled_jobs:
            try:
                message_id = await self._send_job_to_queue(queue_url, job)
                
                job_statuses.append(BatchJobStatus(
                    operation=job.job_type.value,
                    description=f"{job.job_type.value} for {job.trading_day}",
                    status="queued",
                    message_id=message_id,
                    delay_seconds=job.delay_seconds
                ))
                successful_jobs += 1
                
                logger.info(f"Queued job {job.job_id}: {job.job_type.value}")
                
            except Exception as e:
                job_statuses.append(BatchJobStatus(
                    operation=job.job_type.value,
                    description=f"{job.job_type.value} for {job.trading_day}",
                    status="failed",
                    error=str(e)
                ))
                failed_jobs += 1
                
                logger.error(f"Failed to queue job {job.job_id}: {e}")
        
        return BatchWorkflowResponse(
            workflow="daily_prediction_workflow",
            trading_day=trading_day.isoformat(),
            total_jobs=len(scheduled_jobs),
            successful_jobs=successful_jobs,
            failed_jobs=failed_jobs,
            jobs=job_statuses
        )

    async def _create_daily_jobs(self, trading_day: date) -> List[ScheduledJob]:
        """일일 작업들을 생성합니다."""
        jobs = []
        now_kst = get_kst_now()
        
        # 1. 정산 작업 (06:00 KST) - 전날 예측 결과 처리
        settlement_time = self._get_scheduled_datetime(trading_day, ScheduledJobType.SETTLEMENT)
        jobs.append(ScheduledJob(
            job_id=f"settlement_{trading_day}_{uuid.uuid4().hex[:8]}",
            job_type=ScheduledJobType.SETTLEMENT,
            trading_day=trading_day - timedelta(days=1),  # 전날 결과 정산
            scheduled_time=settlement_time,
            payload={
                "action": "settle_predictions",
                "trading_day": (trading_day - timedelta(days=1)).isoformat(),
                "auto_award_points": True,
                "settlement_source": "eod_price"
            },
            delay_seconds=self._calculate_delay_seconds(settlement_time, now_kst),
            priority=1
        ))
        
        # 2. 세션 시작 (06:01 KST) - 새로운 예측 세션 시작
        session_start_time = self._get_scheduled_datetime(trading_day, ScheduledJobType.SESSION_START)
        jobs.append(ScheduledJob(
            job_id=f"session_start_{trading_day}_{uuid.uuid4().hex[:8]}",
            job_type=ScheduledJobType.SESSION_START,
            trading_day=trading_day,
            scheduled_time=session_start_time,
            payload={
                "action": "start_prediction_session",
                "trading_day": trading_day.isoformat(),
                "phase": "OPEN",
                "prediction_cutoff_time": "23:59"
            },
            delay_seconds=self._calculate_delay_seconds(session_start_time, now_kst),
            priority=1
        ))
        
        # 3. 유니버스 준비 (06:05 KST) - 오늘의 예측 대상 종목 설정
        universe_time = self._get_scheduled_datetime(trading_day, ScheduledJobType.UNIVERSE_PREPARE)
        universe_time = universe_time.replace(hour=6, minute=5)  # 06:05로 조정
        jobs.append(ScheduledJob(
            job_id=f"universe_{trading_day}_{uuid.uuid4().hex[:8]}",
            job_type=ScheduledJobType.UNIVERSE_PREPARE,
            trading_day=trading_day,
            scheduled_time=universe_time,
            payload={
                "action": "prepare_universe",
                "trading_day": trading_day.isoformat(),
                "symbols": self.DEFAULT_UNIVERSE,
                "source": "default_list"
            },
            delay_seconds=self._calculate_delay_seconds(universe_time, now_kst),
            priority=2
        ))
        
        # 4. 가격 캐시 갱신 (09:30 KST) - 미장 시작 후 가격 정보 갱신
        price_refresh_time = self._get_scheduled_datetime(trading_day, ScheduledJobType.PRICE_CACHE_REFRESH)
        jobs.append(ScheduledJob(
            job_id=f"price_refresh_{trading_day}_{uuid.uuid4().hex[:8]}",
            job_type=ScheduledJobType.PRICE_CACHE_REFRESH,
            trading_day=trading_day,
            scheduled_time=price_refresh_time,
            payload={
                "action": "refresh_universe_prices",
                "trading_day": trading_day.isoformat(),
                "cache_duration": 300  # 5분
            },
            delay_seconds=self._calculate_delay_seconds(price_refresh_time, now_kst),
            priority=3
        ))
        
        # 5. 세션 종료 (23:59 KST) - 예측 마감
        session_end_time = self._get_scheduled_datetime(trading_day, ScheduledJobType.SESSION_END)
        jobs.append(ScheduledJob(
            job_id=f"session_end_{trading_day}_{uuid.uuid4().hex[:8]}",
            job_type=ScheduledJobType.SESSION_END,
            trading_day=trading_day,
            scheduled_time=session_end_time,
            payload={
                "action": "end_prediction_session",
                "trading_day": trading_day.isoformat(),
                "phase": "CLOSED",
                "lock_predictions": True
            },
            delay_seconds=self._calculate_delay_seconds(session_end_time, now_kst),
            priority=1
        ))
        
        return jobs

    def _get_scheduled_datetime(self, trading_day: date, job_type: ScheduledJobType) -> datetime:
        """작업 타입에 따른 스케줄 시간을 계산합니다."""
        schedule_time = self.SCHEDULE_TIMES[job_type]
        
        # KST 타임존으로 datetime 생성
        return datetime.combine(trading_day, schedule_time, tzinfo=KST)

    def _calculate_delay_seconds(self, scheduled_time: datetime, current_time: datetime) -> int:
        """현재 시간 기준으로 지연 시간(초)을 계산합니다."""
        if scheduled_time <= current_time:
            return 0
        
        delta = scheduled_time - current_time
        return int(delta.total_seconds())

    async def _send_job_to_queue(self, queue_url: str, job: ScheduledJob) -> str:
        """작업을 SQS 큐에 전송합니다."""
        message_body = {
            "job_id": job.job_id,
            "job_type": job.job_type.value,
            "trading_day": job.trading_day.isoformat(),
            "scheduled_time": job.scheduled_time.isoformat(),
            "payload": job.payload,
            "priority": job.priority,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # FIFO 큐를 위한 메시지 그룹 ID (날짜별로 그룹화)
        message_group_id = f"trading_day_{job.trading_day.strftime('%Y%m%d')}"
        
        # 중복 제거를 위한 ID
        deduplication_id = f"{job.job_id}_{job.job_type.value}"
        
        return await self.aws_service.send_sqs_message(
            queue_url=queue_url,
            message_body=json.dumps(message_body),
            delay_seconds=job.delay_seconds,
            message_group_id=message_group_id,
            deduplication_id=deduplication_id
        )

    async def schedule_immediate_settlement(self, queue_url: str, trading_day: date) -> str:
        """즉시 정산 작업을 큐에 추가합니다."""
        job = ScheduledJob(
            job_id=f"immediate_settlement_{trading_day}_{uuid.uuid4().hex[:8]}",
            job_type=ScheduledJobType.SETTLEMENT,
            trading_day=trading_day,
            scheduled_time=get_kst_now(),
            payload={
                "action": "settle_predictions",
                "trading_day": trading_day.isoformat(),
                "auto_award_points": True,
                "settlement_source": "immediate",
                "force_settlement": True
            },
            delay_seconds=0,
            priority=1
        )
        
        return await self._send_job_to_queue(queue_url, job)

    async def get_queue_status(self, queue_url: str) -> Dict[str, Any]:
        """큐 상태를 조회합니다."""
        if not self.aws_service:
            raise ServiceException("AWS service not configured")
            
        return await self.aws_service.get_sqs_queue_attributes(queue_url)

    def get_next_scheduled_jobs(self, hours_ahead: int = 24) -> List[Dict[str, Any]]:
        """다음 N시간 내 스케줄된 작업들을 조회합니다."""
        now = get_kst_now()
        end_time = now + timedelta(hours=hours_ahead)
        
        upcoming_jobs = []
        current_date = now.date()
        
        # 오늘과 내일의 작업들을 확인
        for days_offset in range(2):
            check_date = current_date + timedelta(days=days_offset)
            
            for job_type in ScheduledJobType:
                scheduled_time = self._get_scheduled_datetime(check_date, job_type)
                
                if now <= scheduled_time <= end_time:
                    upcoming_jobs.append({
                        "job_type": job_type.value,
                        "trading_day": check_date.isoformat(),
                        "scheduled_time": scheduled_time.isoformat(),
                        "time_until": str(scheduled_time - now),
                        "priority": 1 if job_type in [ScheduledJobType.SETTLEMENT, ScheduledJobType.SESSION_START, ScheduledJobType.SESSION_END] else 2
                    })
        
        # 시간순으로 정렬
        return sorted(upcoming_jobs, key=lambda x: x["scheduled_time"])