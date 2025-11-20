import datetime as dt
import json
import pytz
from typing import Literal, cast
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from dependency_injector.wiring import inject, Provide

from myapi.containers import Container
from myapi.services.aws_service import AwsService
from myapi.schemas.batch import (
    BatchJobResult,
    BatchQueueResponse,
    BatchJobsStatusResponse,
    BatchScheduleInfo,
    QueueStatus,
)
from myapi.core.auth_middleware import require_admin
from myapi.config import Settings
from myapi.core.tickers import get_default_tickers
from myapi.utils.market_hours import USMarketHours
from myapi.database.session import get_db
from myapi.repositories.active_universe_repository import ActiveUniverseRepository

router = APIRouter(
    prefix="/batch",
    tags=["batch"],
)


# Optional per-path dispatch policy.
# Key = API path (as placed in job['path']), Value in {"SQS", "LAMBDA_INVOKE", "LAMBDA_URL"}
# Leave empty to use global default or per-job overrides.
DISPATCH_POLICY: dict[str, str] = {
    # Example usage:
    # "api/v1/universe/refresh-prices": "LAMBDA_URL",
    # "api/v1/admin/settlement/settle-day/{date}": "LAMBDA_INVOKE",
}


def _resolve_dispatch_mode(path: str, explicit: str | None, settings: Settings) -> str:
    if explicit:
        return explicit.upper()
    # Exact match first
    if path in DISPATCH_POLICY:
        return DISPATCH_POLICY[path].upper()
    # Startswith match support for simple grouping
    for key, val in DISPATCH_POLICY.items():
        if key.endswith("*"):
            prefix = key[:-1]
            if path.startswith(prefix):
                return val.upper()
    return (settings.BATCH_DISPATCH_MODE or "SQS").upper()


def _dispatch_job(
    *,
    aws_service: AwsService,
    settings: Settings,
    path: str,
    method: str,
    body: dict,
    group_id: str,
    deduplication_id: str,
    dispatch_mode: str | None = None,
):
    """Dispatch a job via SQS, direct Lambda invoke, or Lambda Function URL based on settings."""
    # Prepare proxy event payload for Lambda-based handlers
    message_body = aws_service.generate_queue_message_http(
        path=path,
        method=cast(Literal["GET", "POST", "PUT", "DELETE"], method.upper()),
        body=json.dumps(body),
        auth_token=settings.AUTH_TOKEN,
    )

    # Priority: explicit per-job -> per-path policy -> global default
    mode = _resolve_dispatch_mode(path, dispatch_mode, settings)
    if mode == "SQS":
        queue_url = settings.SQS_MAIN_QUEUE_URL
        return aws_service.send_sqs_fifo_message(
            queue_url=queue_url,
            message_body=json.dumps(message_body.model_dump()),
            message_group_id=group_id,
            message_deduplication_id=deduplication_id,
        )
    elif mode == "LAMBDA_INVOKE":
        fn_name = settings.LAMBDA_FUNCTION_NAME_DIRECT or settings.LAMBDA_FUNCTION_NAME
        return aws_service.invoke_lambda(
            function_name=fn_name,
            payload=message_body.model_dump(),
            asynchronous=True,
        )
    elif mode == "LAMBDA_URL":
        if not settings.LAMBDA_FUNCTION_URL:
            raise HTTPException(
                status_code=500, detail="LAMBDA_FUNCTION_URL is not configured"
            )
        return aws_service.invoke_lambda_function_url(
            function_url=settings.LAMBDA_FUNCTION_URL,
            path=path,
            method=cast(Literal["GET", "POST", "PUT", "DELETE"], method),
            body=json.dumps(body),
            internal_auth_bearer=settings.AUTH_TOKEN,
            timeout_sec=settings.LAMBDA_URL_TIMEOUT_SEC,
        )
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported BATCH_DISPATCH_MODE: {settings.BATCH_DISPATCH_MODE}",
        )


# ====================================================================================
# 예측 시스템 스케줄링 엔드포인트 - AWS EventBridge로 호출됨
# ====================================================================================


@router.post(
    "/universe-refresh-prices",
    dependencies=[Depends(require_admin)],
    response_model=BatchQueueResponse,
)
@inject
def enqueue_universe_refresh_prices(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
    db: Session = Depends(get_db),
):
    """
    오늘의 거래일 기준으로 유니버스 현재가 강제 갱신 작업을 큐잉합니다. (관리자 전용)
    15분 주기 스케줄러가 호출하도록 설계되었습니다.
    """
    try:
        # 현재 시간 (KST)과 거래일 계산
        kst = pytz.timezone("Asia/Seoul")
        now = dt.datetime.now(kst)
        trading_day = USMarketHours.get_kst_trading_day()

        job = {
            "path": f"api/v1/universe/refresh-prices?trading_day={trading_day.isoformat()}&interval=15m",
            "method": "POST",
            "body": {},
            "group_id": "universe-prices-refresh",
            "description": f"Refresh 30m candle prices for {trading_day.isoformat()}",
            "deduplication_id": f"universe-refresh-{trading_day.strftime('%Y%m%d')}-{now.strftime('%H%M')}",
            "dispatch": "LAMBDA_INVOKE",
        }

        response = _dispatch_job(
            aws_service=aws_service,
            settings=settings,
            path=job["path"],
            method=job["method"],
            body=job["body"],
            group_id=job["group_id"],
            deduplication_id=job["deduplication_id"],
            # Use the job's dispatch mode (default LAMBDA_INVOKE) to avoid URL timeouts
            dispatch_mode=job.get("dispatch"),
        )

        return BatchQueueResponse(
            message=(
                f"Universe price refresh queued for {trading_day.isoformat()} at {now.strftime('%H:%M')} KST."
            ),
            details=[
                BatchJobResult(
                    job=job["description"], status="queued", response=response
                )
            ],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to queue refresh job: {str(e)}"
        )


@router.post(
    "/all-jobs",
    dependencies=[Depends(require_admin)],
    response_model=BatchQueueResponse,
)
@inject
def execute_all_jobs(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    모든 일일 배치 작업을 실행합니다. (EOD 수집, 정산, 세션 시작, 유니버스 설정, 세션 종료)
    각 작업은 지정된 시간대(±30분 오차 허용) 내에만 실행됩니다.
    06:00 KST 작업들은 의존성 순서대로 순차 실행됩니다.
    """
    # queue_url only needed for SQS mode; dispatch helper handles selection

    # 현재 시간 (한국 시간 KST, UTC+9)
    kst = pytz.timezone("Asia/Seoul")
    now = dt.datetime.now(kst)

    # 거래일 계산 (KST 기준)
    from myapi.utils.market_hours import USMarketHours

    today_kst = now.date()
    # today_trading_day = USMarketHours.get_kst_trading_day()
    yesterday_trading_day = USMarketHours.get_prev_trading_day(today_kst)
    current_hour = now.hour
    current_minute = now.minute
    current_total_minutes = current_hour * 60 + current_minute

    def is_within_time_range(
        target_hour: int, target_minute: int, tolerance_minutes: int = 30
    ) -> bool:
        """지정된 시간 ±tolerance_minutes 범위 내에 있는지 확인"""
        target_total_minutes = target_hour * 60 + target_minute
        return abs(current_total_minutes - target_total_minutes) <= tolerance_minutes

    all_jobs = []

    # 06:00 KST 시간대 작업들 - 순차 실행을 위해 동일한 group_id 사용
    # 1. EOD 데이터 수집 작업 (가장 먼저 실행)
    all_jobs.append(
        {
            "path": f"api/v1/prices/collect-eod/{yesterday_trading_day.isoformat()}",
            "method": "POST",
            "body": {},
            "group_id": "daily-morning-batch",
            "description": f"Collect EOD data for {yesterday_trading_day.isoformat()}",
            "deduplication_id": f"eod-collection-{yesterday_trading_day.strftime('%Y%m%d')}",
            "sequence": 1,
            "dispatch": "SQS",
        }
    )

    # 2. 정산 작업 (EOD 데이터 수집 후 실행)
    all_jobs.append(
        {
            "path": f"api/v1/admin/settlement/settle-day/{yesterday_trading_day.isoformat()}",
            "method": "POST",
            "body": {},
            "group_id": "daily-morning-batch",
            "description": f"Settlement for {yesterday_trading_day.isoformat()}",
            "deduplication_id": f"settlement-{yesterday_trading_day.strftime('%Y%m%d')}",
            "sequence": 2,
            "dispatch": "SQS",
        }
    )

    # 3. 세션 시작 작업 (정산 후 실행)
    # flip-to-predict는 오늘의 거래일이 미국 거래일일 때만 수행
    if USMarketHours.is_us_trading_day(today_kst):
        all_jobs.append(
            {
                "path": "api/v1/session/flip-to-predict",
                "method": "POST",
                "body": {},
                "group_id": "daily-morning-batch",
                "description": (
                    f"Start new prediction session for {today_kst.isoformat()}"
                ),
                "deduplication_id": f"session-start-{today_kst.strftime('%Y%m%d')}",
                "sequence": 3,
                "dispatch": "SQS",
            }
        )

    # 4. 유니버스 설정 작업 (세션 시작 후 실행)
    # 유니버스 upsert도 오늘 거래일이 미국 거래일일 때만 수행
    if USMarketHours.is_us_trading_day(today_kst):
        all_jobs.append(
            {
                "path": "api/v1/universe/upsert",
                "method": "POST",
                "body": {
                    "trading_day": today_kst.isoformat(),
                    "symbols": [],
                },
                "group_id": "daily-morning-batch",
                "description": (
                    f"Setup universe for {today_kst.isoformat()} with symbols"
                ),
                "deduplication_id": f"universe-setup-{today_kst.strftime('%Y%m%d')}",
                "sequence": 4,
                "dispatch": "SQS",
            }
        )

    # 23:59 KST 시간대 작업들
    if is_within_time_range(23, 59):
        # 세션 종료 작업
        all_jobs.append(
            {
                "path": "api/v1/session/cutoff",
                "method": "POST",
                "body": {
                    "trading_day": today_kst.isoformat(),
                },
                "group_id": "daily-evening-batch",
                "description": "Close prediction session",
                "deduplication_id": f"session-close-{today_kst.strftime('%Y%m%d')}",
                "sequence": 1,
                "dispatch": "SQS",
            }
        )

    # 실행할 작업이 없는 경우
    if not all_jobs:
        return BatchQueueResponse(
            message=(
                f"No jobs scheduled for current time ({current_hour:02d}:{current_minute:02d} KST). "
                "Jobs are scheduled for 06:00 (±30min) and 23:59 (±30min) KST."
            ),
            current_time=f"{current_hour:02d}:{current_minute:02d} KST",
            details=[],
        )

    # 작업을 sequence 순으로 정렬하여 순차 실행 보장
    sorted_jobs = sorted(all_jobs, key=lambda x: x.get("sequence", 999))

    responses = []
    for job in sorted_jobs:
        try:
            response = _dispatch_job(
                aws_service=aws_service,
                settings=settings,
                path=job["path"],
                method=job["method"],
                body=job["body"],
                group_id=job["group_id"],
                deduplication_id=job["deduplication_id"],
                dispatch_mode=job.get("dispatch"),
            )
            responses.append(
                BatchJobResult(
                    job=job["description"],
                    status="queued",
                    sequence=job.get("sequence", 0),
                    response=response,
                )
            )
        except Exception as e:
            responses.append(
                BatchJobResult(
                    job=job["description"],
                    status="failed",
                    sequence=job.get("sequence", 0),
                    error=str(e),
                )
            )

    successful_jobs = [r for r in responses if r.status == "queued"]
    failed_jobs = [r for r in responses if r.status == "failed"]

    if not successful_jobs:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "All batch jobs failed to queue.",
                "details": failed_jobs,
            },
        )

    return BatchQueueResponse(
        message=(
            f"Daily batch jobs queued for {current_hour:02d}:{current_minute:02d} KST. "
            f"today_trading_day={today_kst}, yesterday_trading_day={yesterday_trading_day}. "
            f"Success: {len(successful_jobs)}, Failed: {len(failed_jobs)}"
        ),
        current_time=f"{current_hour:02d}:{current_minute:02d} KST",
        details=responses,
    )


@router.post(
    "/prediction-settlement",
    dependencies=[Depends(require_admin)],
    response_model=BatchQueueResponse,
)
@inject
def execute_prediction_settlement(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    전날 예측 결과 정산 및 포인트 지급 (06:00 실행)
    AWS EventBridge에서 매일 06:00에 호출되어 전날 예측을 정산하고 포인트를 지급합니다.
    """
    # queue_url only needed for SQS mode; dispatch helper handles selection
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    today_str = dt.date.today().strftime("%Y%m%d")

    # 전날 예측 정산 작업
    jobs = [
        {
            "path": f"admin/settlement/settle-day/{yesterday}",
            "method": "POST",
            "body": {},
            "group_id": "settlement",
            "description": f"Settlement for {yesterday}",
            "dispatch": "SQS",
        }
    ]

    responses = []
    for job in jobs:
        try:
            deduplication_id = f"settlement-{yesterday}-{today_str}"
            response = _dispatch_job(
                aws_service=aws_service,
                settings=settings,
                path=job["path"],
                method=job["method"],
                body=job["body"],
                group_id=job["group_id"],
                deduplication_id=deduplication_id,
                dispatch_mode=job.get("dispatch"),
            )
            responses.append(
                BatchJobResult(
                    job=job["description"], status="queued", response=response
                )
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to queue settlement job: {str(e)}"
            )

    return BatchQueueResponse(
        message=f"Prediction settlement for {yesterday} has been queued.",
        details=responses,
    )


@router.post(
    "/session-start",
    dependencies=[Depends(require_admin)],
    response_model=BatchQueueResponse,
)
@inject
def execute_session_start(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    새로운 예측 세션 시작 (06:00 실행)
    AWS EventBridge에서 매일 06:00에 호출되어 새로운 예측 세션을 시작합니다.
    """
    # queue_url only needed for SQS mode; dispatch helper handles selection
    today_str = dt.date.today().strftime("%Y%m%d")

    jobs = [
        {
            "path": "session/flip-to-predict",
            "method": "POST",
            "body": {},
            "group_id": "session",
            "description": "Start new prediction session",
            "dispatch": "SQS",
        }
    ]

    responses = []
    for job in jobs:
        try:
            deduplication_id = f"session-start-{today_str}"
            response = _dispatch_job(
                aws_service=aws_service,
                settings=settings,
                path=job["path"],
                method=job["method"],
                body=job["body"],
                group_id=job["group_id"],
                deduplication_id=deduplication_id,
                dispatch_mode=job.get("dispatch"),
            )
            responses.append(
                BatchJobResult(
                    job=job["description"], status="queued", response=response
                )
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to queue session start job: {str(e)}"
            )

    return BatchQueueResponse(
        message="New prediction session start has been queued.", details=responses
    )


@router.post(
    "/universe-setup",
    dependencies=[Depends(require_admin)],
    response_model=BatchQueueResponse,
)
@inject
def execute_universe_setup(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    오늘의 유니버스 설정 (06:00 실행)
    AWS EventBridge에서 매일 06:00에 호출되어 오늘의 종목 유니버스를 설정합니다.
    기본 100개 종목으로 설정됩니다.
    """
    # queue_url only needed for SQS mode; dispatch helper handles selection
    today = dt.date.today().isoformat()
    today_str = dt.date.today().strftime("%Y%m%d")

    # 기본 100개 종목 설정
    default_symbols = get_default_tickers()

    jobs = [
        {
            "path": "universe/upsert",
            "method": "POST",
            "body": {"trading_day": today, "symbols": default_symbols},
            "group_id": "universe",
            "description": f"Setup universe for {today} with {len(default_symbols)} symbols",
            "dispatch": "SQS",
        }
    ]

    responses = []
    for job in jobs:
        try:
            deduplication_id = f"universe-setup-{today_str}"
            response = _dispatch_job(
                aws_service=aws_service,
                settings=settings,
                path=job["path"],
                method=job["method"],
                body=job["body"],
                group_id=job["group_id"],
                deduplication_id=deduplication_id,
                dispatch_mode=job.get("dispatch"),
            )
            responses.append(
                BatchJobResult(
                    job=job["description"], status="queued", response=response
                )
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to queue universe setup job: {str(e)}"
            )

    return BatchQueueResponse(
        message=f"Universe setup for {today} has been queued.", details=responses
    )


@router.post(
    "/session-close",
    dependencies=[Depends(require_admin)],
    response_model=BatchQueueResponse,
)
@inject
def execute_session_close(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    예측 마감 및 세션 종료 (23:59 실행)
    AWS EventBridge에서 매일 23:59에 호출되어 예측을 마감하고 세션을 종료합니다.
    """
    # queue_url only needed for SQS mode; dispatch helper handles selection
    today_str = dt.date.today().strftime("%Y%m%d")

    jobs = [
        {
            "path": "session/cutoff",
            "method": "POST",
            "body": {},
            "group_id": "session",
            "description": "Close prediction session",
            "dispatch": "SQS",
        }
    ]

    responses = []
    for job in jobs:
        try:
            deduplication_id = f"session-close-{today_str}"
            response = _dispatch_job(
                aws_service=aws_service,
                settings=settings,
                path=job["path"],
                method=job["method"],
                body=job["body"],
                group_id=job["group_id"],
                deduplication_id=deduplication_id,
            )
            responses.append(
                BatchJobResult(
                    job=job["description"], status="queued", response=response
                )
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to queue session close job: {str(e)}"
            )

    return BatchQueueResponse(
        message="Prediction session close has been queued.", details=responses
    )


# ====================================================================================
# 배치 작업 상태 조회 및 모니터링 엔드포인트
# ====================================================================================


@router.get(
    "/jobs/status",
    dependencies=[Depends(require_admin)],
    response_model=BatchJobsStatusResponse,
)
@inject
def get_batch_jobs_status(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    현재 실행 중인 배치 작업 상태를 조회합니다. (관리자 전용)

    SQS 큐의 메시지 수, 가시성 타임아웃 등을 확인하여
    현재 배치 작업의 상태를 파악할 수 있습니다.
    """
    try:
        queue_url = settings.SQS_MAIN_QUEUE_URL

        # 현재 시간 정보
        kst = pytz.timezone("Asia/Seoul")
        now = dt.datetime.now(kst)

        # SQS 큐 상태 조회 (실제 SQS 정보)
        try:
            queue_attributes = aws_service.get_sqs_queue_attributes(queue_url)

            return BatchJobsStatusResponse(
                current_time=now.strftime("%Y-%m-%d %H:%M:%S KST"),
                queue_status=QueueStatus(
                    queue_url=queue_url,
                    approximate_number_of_messages=(
                        queue_attributes.ApproximateNumberOfMessages or "0"
                    ),
                    approximate_number_of_messages_not_visible=(
                        queue_attributes.ApproximateNumberOfMessagesNotVisible or "0"
                    ),
                    approximate_number_of_messages_delayed=(
                        queue_attributes.ApproximateNumberOfMessagesDelayed or "0"
                    ),
                    created_timestamp=queue_attributes.CreatedTimestamp or "",
                    last_modified_timestamp=queue_attributes.LastModifiedTimestamp
                    or "",
                ),
                batch_schedule_info=BatchScheduleInfo(
                    morning_batch_time="06:00 KST (±30min tolerance)",
                    evening_batch_time="23:59 KST (±30min tolerance)",
                    next_morning_batch=_get_next_batch_time(now, 6, 0),
                    next_evening_batch=_get_next_batch_time(now, 23, 59),
                ),
                status="ACTIVE",
            )
        except Exception as sqs_error:
            # SQS 조회 실패시 기본 정보만 반환
            return BatchJobsStatusResponse(
                current_time=now.strftime("%Y-%m-%d %H:%M:%S KST"),
                queue_status=QueueStatus(
                    queue_url=queue_url,
                    error=f"Failed to fetch queue status: {str(sqs_error)}",
                    status="UNAVAILABLE",
                ),
                batch_schedule_info=BatchScheduleInfo(
                    morning_batch_time="06:00 KST (±30min tolerance)",
                    evening_batch_time="23:59 KST (±30min tolerance)",
                    next_morning_batch=_get_next_batch_time(now, 6, 0),
                    next_evening_batch=_get_next_batch_time(now, 23, 59),
                ),
                status="PARTIAL",
            )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get batch jobs status: {str(e)}"
        )


def _get_next_batch_time(
    current_time: dt.datetime, target_hour: int, target_minute: int
) -> str:
    """다음 배치 실행 시간 계산"""
    target_time = current_time.replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
    )

    if current_time >= target_time:
        # 오늘 시간이 지났으면 내일
        target_time += dt.timedelta(days=1)

    return target_time.strftime("%Y-%m-%d %H:%M KST")
