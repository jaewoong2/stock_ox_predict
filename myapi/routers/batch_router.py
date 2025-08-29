import datetime as dt
import json
import pytz
from fastapi import APIRouter, Depends, HTTPException
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

router = APIRouter(
    prefix="/batch",
    tags=["batch"],
)


# ====================================================================================
# 예측 시스템 스케줄링 엔드포인트 - AWS EventBridge로 호출됨
# ====================================================================================


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
    queue_url = settings.SQS_MAIN_QUEUE_URL
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)

    # 현재 시간 (한국 시간 KST, UTC+9)
    kst = pytz.timezone("Asia/Seoul")
    now = dt.datetime.now(kst)
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
            "path": f"api/v1/prices/collect-eod/{yesterday.isoformat()}",
            "method": "POST",
            "body": {},
            "group_id": "daily-morning-batch",
            "description": f"Collect EOD data for {yesterday.isoformat()}",
            "deduplication_id": f"eod-collection-{yesterday.strftime('%Y%m%d')}",
            "sequence": 1,
        }
    )

    # 2. 정산 작업 (EOD 데이터 수집 후 실행)
    all_jobs.append(
        {
            "path": f"api/v1/admin/settlement/settle-day/{yesterday.isoformat()}",
            "method": "POST",
            "body": {},
            "group_id": "daily-morning-batch",
            "description": f"Settlement for {yesterday.isoformat()}",
            "deduplication_id": f"settlement-{yesterday.strftime('%Y%m%d')}",
            "sequence": 2,
        }
    )

    # 3. 세션 시작 작업 (정산 후 실행)
    all_jobs.append(
        {
            "path": "api/v1/session/flip-to-predict",
            "method": "POST",
            "body": {},
            "group_id": "daily-morning-batch",
            "description": "Start new prediction session",
            "deduplication_id": f"session-start-{today.strftime('%Y%m%d')}",
            "sequence": 3,
        }
    )

    # 4. 유니버스 설정 작업 (세션 시작 후 실행)
    all_jobs.append(
        {
            "path": "api/v1/universe/upsert",
            "method": "POST",
            "body": {
                "trading_day": today.isoformat(),
                "symbols": get_default_tickers(),
            },
            "group_id": "daily-morning-batch",
            "description": f"Setup universe for {today.isoformat()} with {len(get_default_tickers())} symbols",
            "deduplication_id": f"universe-setup-{today.strftime('%Y%m%d')}",
            "sequence": 4,
        }
    )

    # 23:59 KST 시간대 작업들
    if is_within_time_range(23, 59):
        # 세션 종료 작업
        all_jobs.append(
            {
                "path": "api/v1/session/cutoff",
                "method": "POST",
                "body": {},
                "group_id": "daily-evening-batch",
                "description": "Close prediction session",
                "deduplication_id": f"session-close-{today.strftime('%Y%m%d')}",
                "sequence": 1,
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
            message_body = aws_service.generate_queue_message_http(
                path=job["path"],
                method=job["method"],
                body=json.dumps(job["body"]),
                auth_token=settings.AUTH_TOKEN,
            )
            response = aws_service.send_sqs_fifo_message(
                queue_url=queue_url,
                message_body=json.dumps(message_body.model_dump()),
                message_group_id=job["group_id"],
                message_deduplication_id=job["deduplication_id"],
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
    queue_url = settings.SQS_MAIN_QUEUE_URL
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
        }
    ]

    responses = []
    for job in jobs:
        try:
            message_body = aws_service.generate_queue_message_http(
                path=job["path"],
                method=job["method"],
                body=json.dumps(job["body"]),
                auth_token=settings.AUTH_TOKEN,
            )

            deduplication_id = f"settlement-{yesterday}-{today_str}"

            response = aws_service.send_sqs_fifo_message(
                queue_url=queue_url,
                message_body=json.dumps(message_body.model_dump()),
                message_group_id=job["group_id"],
                message_deduplication_id=deduplication_id,
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
    queue_url = settings.SQS_MAIN_QUEUE_URL
    today_str = dt.date.today().strftime("%Y%m%d")

    jobs = [
        {
            "path": "session/flip-to-predict",
            "method": "POST",
            "body": {},
            "group_id": "session",
            "description": "Start new prediction session",
        }
    ]

    responses = []
    for job in jobs:
        try:
            message_body = aws_service.generate_queue_message_http(
                path=job["path"],
                method=job["method"],
                body=json.dumps(job["body"]),
                auth_token=settings.AUTH_TOKEN,
            )

            deduplication_id = f"session-start-{today_str}"

            response = aws_service.send_sqs_fifo_message(
                queue_url=queue_url,
                message_body=json.dumps(message_body.model_dump()),
                message_group_id=job["group_id"],
                message_deduplication_id=deduplication_id,
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
    queue_url = settings.SQS_MAIN_QUEUE_URL
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
        }
    ]

    responses = []
    for job in jobs:
        try:
            message_body = aws_service.generate_queue_message_http(
                path=job["path"],
                method=job["method"],
                body=json.dumps(job["body"]),
                auth_token=settings.AUTH_TOKEN,
            )

            deduplication_id = f"universe-setup-{today_str}"

            response = aws_service.send_sqs_fifo_message(
                queue_url=queue_url,
                message_body=json.dumps(message_body.model_dump()),
                message_group_id=job["group_id"],
                message_deduplication_id=deduplication_id,
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
    queue_url = settings.SQS_MAIN_QUEUE_URL
    today_str = dt.date.today().strftime("%Y%m%d")

    jobs = [
        {
            "path": "session/cutoff",
            "method": "POST",
            "body": {},
            "group_id": "session",
            "description": "Close prediction session",
        }
    ]

    responses = []
    for job in jobs:
        try:
            message_body = aws_service.generate_queue_message_http(
                path=job["path"],
                method=job["method"],
                body=json.dumps(job["body"]),
                auth_token=settings.AUTH_TOKEN,
            )

            deduplication_id = f"session-close-{today_str}"

            response = aws_service.send_sqs_fifo_message(
                queue_url=queue_url,
                message_body=json.dumps(message_body.model_dump()),
                message_group_id=job["group_id"],
                message_deduplication_id=deduplication_id,
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
