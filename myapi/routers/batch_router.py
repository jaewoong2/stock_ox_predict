import datetime as dt
import json
from fastapi import APIRouter, Depends, HTTPException
from dependency_injector.wiring import inject, Provide

from myapi.containers import Container
from myapi.services.aws_service import AwsService
from myapi.core.auth_middleware import verify_bearer_token
from myapi.config import Settings

# 전체 티커 목록
DEFAULT_TICKERS = [
    "CRWV", "SPY", "QQQ", "AMAT", "AMD", "ANET", "ASML", "AVGO", "COHR", "GFS",
    "KLAC", "MRVL", "MU", "NVDA", "NVMI", "ONTO", "SMCI", "STX", "TSM", "VRT",
    "WDC", "AXON", "LMT", "NOC", "RCAT", "AFRM", "APP", "COIN", "HOOD", "IREN",
    "MQ", "MSTR", "SOFI", "TOST", "CEG", "FSLR", "LNG", "NRG", "OKLO", "PWR",
    "SMR", "VST", "CRWD", "FTNT", "GTLB", "NET", "OKTA", "PANW", "S", "TENB",
    "ZS", "AAPL", "ADBE", "ADSK", "AI", "AMZN", "ASAN", "BILL", "CRM", "DDOG",
    "DOCN", "GOOGL", "HUBS", "META", "MNDY", "MSFT", "NOW", "PCOR", "PLTR",
    "SNOW", "VEEV", "IONQ", "QBTS", "RGTI", "PL", "RKLB", "LUNR", "ACHR",
    "ARBE", "JOBY", "TSLA", "UBER", "ORCL", "CFLT", "CRNC", "DXCM", "INTU",
    "IOT", "LRCX", "NFLX", "PODD", "PSTG", "RBLX", "RDDT", "SERV", "SHOP",
    "SOUN", "TDOC", "PATH", "DXYZ", "NKE"
]

router = APIRouter(
    prefix="/batch",
    tags=["batch"],
)


# ====================================================================================
# 예측 시스템 스케줄링 엔드포인트 - AWS EventBridge로 호출됨
# ====================================================================================


@router.post("/all-jobs", dependencies=[Depends(verify_bearer_token)])
@inject
def execute_all_jobs(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    모든 일일 배치 작업을 실행합니다. (정산, 세션 시작, 유니버스 설정, 세션 종료)
    """
    queue_url = "https://sqs.ap-northeast-2.amazonaws.com/849441246713/crypto.fifo"
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    
    all_jobs = []
    
    # 1. 정산 작업
    all_jobs.append({
        "path": f"admin/settlement/settle-day/{yesterday.isoformat()}",
        "method": "POST", "body": {}, "group_id": "settlement",
        "description": f"Settlement for {yesterday.isoformat()}",
        "deduplication_id": f"settlement-{yesterday.strftime('%Y%m%d')}"
    })
    
    # 2. 세션 시작 작업
    all_jobs.append({
        "path": "session/flip-to-predict",
        "method": "POST", "body": {}, "group_id": "session",
        "description": "Start new prediction session",
        "deduplication_id": f"session-start-{today.strftime('%Y%m%d')}"
    })
    
    # 3. 유니버스 설정 작업
    all_jobs.append({
        "path": "universe/upsert",
        "method": "POST",
        "body": {"trading_day": today.isoformat(), "symbols": DEFAULT_TICKERS},
        "group_id": "universe",
        "description": f"Setup universe for {today.isoformat()} with {len(DEFAULT_TICKERS)} symbols",
        "deduplication_id": f"universe-setup-{today.strftime('%Y%m%d')}"
    })

    # 4. 세션 종료 작업
    all_jobs.append({
        "path": "session/cutoff",
        "method": "POST", "body": {}, "group_id": "session",
        "description": "Close prediction session",
        "deduplication_id": f"session-close-{today.strftime('%Y%m%d')}"
    })

    responses = []
    for job in all_jobs:
        try:
            message_body = aws_service.generate_queue_message_http(
                path=job["path"],
                method=job["method"],
                body=json.dumps(job["body"]),
                auth_token=settings.AUTH_TOKEN,
            )
            response = aws_service.send_sqs_fifo_message(
                queue_url=queue_url,
                message_body=json.dumps(message_body),
                message_group_id=job["group_id"],
                message_deduplication_id=job["deduplication_id"],
            )
            responses.append({"job": job["description"], "status": "queued", "response": response})
        except Exception as e:
            responses.append({"job": job["description"], "status": "failed", "error": str(e)})

    successful_jobs = [r for r in responses if r["status"] == "queued"]
    failed_jobs = [r for r in responses if r["status"] == "failed"]

    if not successful_jobs:
        raise HTTPException(status_code=500, detail={"message": "All batch jobs failed to queue.", "details": failed_jobs})

    return {
        "message": f"All daily batch jobs have been queued. Success: {len(successful_jobs)}, Failed: {len(failed_jobs)}",
        "details": responses,
    }


@router.post("/prediction-settlement", dependencies=[Depends(verify_bearer_token)])
@inject
def execute_prediction_settlement(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    전날 예측 결과 정산 및 포인트 지급 (06:00 실행)
    AWS EventBridge에서 매일 06:00에 호출되어 전날 예측을 정산하고 포인트를 지급합니다.
    """
    queue_url = "https://sqs.ap-northeast-2.amazonaws.com/849441246713/crypto.fifo"
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
                message_body=json.dumps(message_body),
                message_group_id=job["group_id"],
                message_deduplication_id=deduplication_id,
            )
            responses.append(
                {"job": job["description"], "status": "queued", "response": response}
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to queue settlement job: {str(e)}"
            )

    return {
        "message": f"Prediction settlement for {yesterday} has been queued.",
        "details": responses,
    }


@router.post("/session-start", dependencies=[Depends(verify_bearer_token)])
@inject
def execute_session_start(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    새로운 예측 세션 시작 (06:00 실행)
    AWS EventBridge에서 매일 06:00에 호출되어 새로운 예측 세션을 시작합니다.
    """
    queue_url = "https://sqs.ap-northeast-2.amazonaws.com/849441246713/crypto.fifo"
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
                message_body=json.dumps(message_body),
                message_group_id=job["group_id"],
                message_deduplication_id=deduplication_id,
            )
            responses.append(
                {"job": job["description"], "status": "queued", "response": response}
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to queue session start job: {str(e)}"
            )

    return {
        "message": "New prediction session start has been queued.",
        "details": responses,
    }


@router.post("/universe-setup", dependencies=[Depends(verify_bearer_token)])
@inject
def execute_universe_setup(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    오늘의 유니버스 설정 (06:00 실행)
    AWS EventBridge에서 매일 06:00에 호출되어 오늘의 종목 유니버스를 설정합니다.
    기본 50개 종목으로 설정됩니다.
    """
    queue_url = "https://sqs.ap-northeast-2.amazonaws.com/849441246713/crypto.fifo"
    today = dt.date.today().isoformat()
    today_str = dt.date.today().strftime("%Y%m%d")

    # 기본 50개 종목 설정
    default_symbols = DEFAULT_TICKERS

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
                message_body=json.dumps(message_body),
                message_group_id=job["group_id"],
                message_deduplication_id=deduplication_id,
            )
            responses.append(
                {"job": job["description"], "status": "queued", "response": response}
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to queue universe setup job: {str(e)}"
            )

    return {
        "message": f"Universe setup for {today} has been queued.",
        "details": responses,
    }


@router.post("/session-close", dependencies=[Depends(verify_bearer_token)])
@inject
def execute_session_close(
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
    settings: Settings = Depends(Provide[Container.config.config]),
):
    """
    예측 마감 및 세션 종료 (23:59 실행)
    AWS EventBridge에서 매일 23:59에 호출되어 예측을 마감하고 세션을 종료합니다.
    """
    queue_url = "https://sqs.ap-northeast-2.amazonaws.com/849441246713/crypto.fifo"
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
                message_body=json.dumps(message_body),
                message_group_id=job["group_id"],
                message_deduplication_id=deduplication_id,
            )
            responses.append(
                {"job": job["description"], "status": "queued", "response": response}
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to queue session close job: {str(e)}"
            )

    return {
        "message": "Prediction session close has been queued.",
        "details": responses,
    }
