from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from dependency_injector.wiring import inject, Provide
from typing import Any, Optional, Dict
from sqlalchemy.orm import Session

from myapi.containers import Container
from myapi.services.batch_service import BatchService
from myapi.services.aws_service import AwsService
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.batch import (
    UniverseBatchCreate,
    SessionPhaseTransition,
    BatchScheduleRequest,
    BatchWorkflowResponse,
)
from myapi.config import Settings
from myapi.core.auth_middleware import get_current_active_user
from myapi.schemas.user import User as UserSchema
from myapi.core.exceptions import ValidationError, BusinessLogicError

router = APIRouter(
    prefix="/batch",
    tags=["batch"],
)


@router.post("/universe/create", response_model=BaseResponse)
@inject
def create_universe_batch(
    payload: UniverseBatchCreate,
    _current_user: UserSchema = Depends(get_current_active_user),
    batch_service: BatchService = Depends(Provide[Container.services.batch_service]),
) -> Any:
    """
    배치로 일일 유니버스를 생성합니다.

    Args:
        payload: 유니버스 생성 요청 데이터
        _current_user: 현재 활성 사용자 (관리자 권한 필요)
        batch_service: 배치 서비스

    Returns:
        BaseResponse: 생성된 유니버스 정보
    """
    try:
        trading_day = date.fromisoformat(payload.trading_day)

        if payload.use_default or not payload.symbols:
            # Use default tickers from docs/tickers.md
            universe = batch_service.create_default_universe(trading_day)
        else:
            # Use provided symbols
            universe = batch_service.create_daily_universe(trading_day, payload.symbols)

        return BaseResponse(
            success=True,
            data={
                "operation": "create_universe",
                "trading_day": trading_day.strftime("%Y-%m-%d"),
                "universe": universe.model_dump(),
            },
        )
    except (ValidationError, BusinessLogicError) as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=str(e)),
        )
    except ValueError as e:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message=f"Invalid date format: {e}"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Universe creation failed: {str(e)}",
        )


@router.post("/session/transition", response_model=BaseResponse)
@inject
def transition_session_phase(
    payload: SessionPhaseTransition,
    _current_user: UserSchema = Depends(get_current_active_user),
    batch_service: BatchService = Depends(Provide[Container.services.batch_service]),
) -> Any:
    """
    세션의 단계를 변경합니다.

    Args:
        payload: 세션 단계 전환 요청 데이터
        _current_user: 현재 활성 사용자 (관리자 권한 필요)
        batch_service: 배치 서비스

    Returns:
        BaseResponse: 변경된 세션 상태
    """
    try:
        trading_day = None
        if payload.trading_day:
            trading_day = date.fromisoformat(payload.trading_day)

        session_status = batch_service.transition_session_phase(
            trading_day=trading_day, target_phase=payload.target_phase
        )

        if not session_status:
            return BaseResponse(
                success=False,
                error=Error(
                    code=ErrorCode.USER_NOT_FOUND,
                    message="Session not found or transition failed",
                ),
            )

        return BaseResponse(
            success=True,
            data={
                "operation": "session_transition",
                "trading_day": session_status.trading_day.strftime("%Y-%m-%d"),
                "previous_phase": "unknown",  # Could track this if needed
                "current_phase": session_status.phase.value,
                "session_status": {
                    "trading_day": session_status.trading_day.strftime("%Y-%m-%d"),
                    "phase": session_status.phase.value,
                    "is_prediction_open": session_status.is_prediction_open,
                    "is_settling": session_status.is_settling,
                    "is_closed": session_status.is_closed,
                },
            },
        )
    except (ValidationError, BusinessLogicError) as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=str(e)),
        )
    except ValueError as e:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message=f"Invalid date format: {e}"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Session transition failed: {str(e)}",
        )


@router.get("/summary", response_model=BaseResponse)
@inject
def get_batch_summary(
    trading_day: str = date.today().isoformat(),
    _current_user: UserSchema = Depends(get_current_active_user),
    batch_service: BatchService = Depends(Provide[Container.services.batch_service]),
) -> Any:
    """
    배치 작업 요약 정보를 조회합니다.

    Args:
        trading_day: 거래일 (YYYY-MM-DD, 선택사항)
        _current_user: 현재 활성 사용자
        batch_service: 배치 서비스

    Returns:
        BaseResponse: 배치 작업 요약 정보
    """
    try:
        target_day = None
        if trading_day:
            target_day = date.fromisoformat(trading_day)

        summary = batch_service.get_batch_summary(target_day)

        return BaseResponse(success=True, data={"summary": summary})
    except ValueError as e:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message=f"Invalid date format: {e}"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch summary failed: {str(e)}",
        )


@router.post("/schedule", response_model=BaseResponse)
@inject
def schedule_batch_workflow(
    payload: BatchScheduleRequest,
    _current_user: UserSchema = Depends(get_current_active_user),
    batch_service: BatchService = Depends(Provide[Container.services.batch_service]),
) -> Any:
    """
    배치 워크플로우를 SQS 큐에 스케줄링합니다.

    Args:
        payload: 배치 스케줄링 요청 데이터
        _current_user: 현재 활성 사용자 (관리자 권한 필요)
        batch_service: 배치 서비스 (AWS 서비스와 설정 포함)

    Returns:
        BaseResponse: 스케줄링된 배치 워크플로우 정보
    """
    try:
        workflow_result = batch_service.schedule_daily_workflow(payload.queue_url)

        return BaseResponse(
            success=True,
            data={
                "operation": "schedule_batch_workflow",
                "workflow_result": workflow_result,
            },
        )
    except (ValidationError, BusinessLogicError) as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=str(e)),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch workflow scheduling failed: {str(e)}",
        )


@router.post("/auto-schedule/session-transitions", response_model=BaseResponse)
@inject  
def schedule_session_transitions(
    payload: BatchScheduleRequest,
    trading_day: Optional[str] = None,
    current_user: UserSchema = Depends(get_current_active_user),
    batch_service: BatchService = Depends(Provide[Container.services.batch_service]),
) -> Any:
    """
    시간 기반 자동 세션 전환을 스케줄링합니다.
    - 06:00: 예측 시작 (OPEN)
    - 23:59: 예측 마감 (CLOSED)
    
    Args:
        payload: 스케줄링 요청 데이터 (queue_url 포함)
        trading_day: 대상 거래일 (선택사항, 기본값은 오늘)  
        _current_user: 현재 활성 사용자 (관리자 권한 필요)
        batch_service: 배치 서비스
        
    Returns:
        BaseResponse: 스케줄링 결과
    """
    try:
        target_date = None
        if trading_day:
            target_date = date.fromisoformat(trading_day)
            
        result = batch_service.schedule_time_based_session_transitions(
            queue_url=payload.queue_url,
            trading_day=target_date
        )
        
        return BaseResponse(
            success=True,
            data={
                "operation": "schedule_session_transitions", 
                "result": result
            }
        )
        
    except ValidationError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=str(e))
        )
    except ValueError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=f"Invalid date format: {e}")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Session transitions scheduling failed: {str(e)}"
        )


@router.post("/auto-check-and-schedule", response_model=BaseResponse)
@inject
def auto_check_and_schedule_sessions(
    payload: BatchScheduleRequest,
    current_user: UserSchema = Depends(get_current_active_user),
    batch_service: BatchService = Depends(Provide[Container.services.batch_service]),
) -> Any:
    """
    현재 시간을 확인하여 필요한 세션 전환을 자동으로 수행하고 향후 전환을 스케줄링합니다.
    
    Args:
        payload: 스케줄링 요청 데이터 (queue_url 포함)
        _current_user: 현재 활성 사용자 (관리자 권한 필요)
        batch_service: 배치 서비스
        
    Returns: 
        BaseResponse: 자동 체크 및 스케줄링 결과
    """
    try:
        result = batch_service.auto_check_and_schedule_sessions(payload.queue_url)
        
        return BaseResponse(
            success=True,
            data={
                "operation": "auto_check_and_schedule_sessions",
                "result": result
            }
        )
        
    except ValidationError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=str(e))
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto check and schedule failed: {str(e)}"
        )


# ============================================================================ 
# 새로운 시간대별 Queue 기반 배치 시스템 엔드포인트들
# ============================================================================

@router.post("/schedule/daily-workflow", response_model=BaseResponse)
@inject
async def schedule_daily_prediction_workflow(
    queue_url: str,
    trading_day: Optional[str] = None,
    _current_user: UserSchema = Depends(get_current_active_user),
    db: Session = Depends(Provide[Container.repositories.get_db]),
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
) -> Any:
    """
    일일 예측 시스템 전체 워크플로우를 시간대별로 Queue에 스케줄링합니다.
    
    스케줄되는 작업들:
    - 06:00 KST: 전날 예측 결과 정산 및 포인트 지급
    - 06:01 KST: 새로운 예측 세션 시작
    - 06:05 KST: 오늘의 유니버스 설정
    - 09:30 KST: 가격 캐시 갱신 (미장 시작 후)
    - 23:59 KST: 예측 마감 및 세션 종료
    
    Args:
        queue_url: SQS FIFO 큐 URL
        trading_day: 대상 거래일 (선택사항, 기본값은 오늘)
        current_user: 현재 사용자 (관리자 권한 필요)
        
    Returns:
        BaseResponse: 스케줄링 결과
    """
    try:
        from myapi.services.batch_scheduler_service import BatchSchedulerService
        
        scheduler = BatchSchedulerService(db, aws_service)
        
        target_day = None
        if trading_day:
            target_day = date.fromisoformat(trading_day)
            
        workflow_result = await scheduler.schedule_daily_workflow(queue_url, target_day)
        
        return BaseResponse(
            success=True,
            data={
                "operation": "schedule_daily_workflow",
                "workflow_result": workflow_result.model_dump()
            }
        )
        
    except ValueError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=f"Invalid date format: {e}")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Daily workflow scheduling failed: {str(e)}"
        )


@router.post("/schedule/immediate-settlement", response_model=BaseResponse)
@inject
async def schedule_immediate_settlement(
    queue_url: str,
    trading_day: str,
    _current_user: UserSchema = Depends(get_current_active_user),
    db: Session = Depends(Provide[Container.repositories.get_db]),
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
) -> Any:
    """
    즉시 정산 작업을 큐에 추가합니다.
    
    Args:
        queue_url: SQS 큐 URL
        trading_day: 정산할 거래일 (YYYY-MM-DD)
        current_user: 현재 사용자 (관리자 권한 필요)
        
    Returns:
        BaseResponse: 즉시 정산 스케줄링 결과
    """
    try:
        from myapi.services.batch_scheduler_service import BatchSchedulerService
        
        scheduler = BatchSchedulerService(db, aws_service)
        target_day = date.fromisoformat(trading_day)
        
        message_id = await scheduler.schedule_immediate_settlement(queue_url, target_day)
        
        return BaseResponse(
            success=True,
            data={
                "operation": "immediate_settlement",
                "trading_day": trading_day,
                "message_id": message_id,
                "status": "queued"
            }
        )
        
    except ValueError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=f"Invalid date format: {e}")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Immediate settlement scheduling failed: {str(e)}"
        )


@router.get("/schedule/upcoming", response_model=BaseResponse)
@inject
def get_upcoming_scheduled_jobs(
    hours_ahead: int = 24,
    _current_user: UserSchema = Depends(get_current_active_user),
    db: Session = Depends(Provide[Container.repositories.get_db]),
) -> Any:
    """
    다음 N시간 내 스케줄된 작업들을 조회합니다.
    
    Args:
        hours_ahead: 조회할 시간 범위 (기본 24시간)
        current_user: 현재 사용자 (관리자 권한 필요)
        
    Returns:
        BaseResponse: 예정된 작업 목록
    """
    try:
        from myapi.services.batch_scheduler_service import BatchSchedulerService
        
        scheduler = BatchSchedulerService(db)
        
        upcoming_jobs = scheduler.get_next_scheduled_jobs(hours_ahead)
        
        return BaseResponse(
            success=True,
            data={
                "operation": "get_upcoming_jobs",
                "hours_ahead": hours_ahead,
                "total_jobs": len(upcoming_jobs),
                "upcoming_jobs": upcoming_jobs
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get upcoming jobs: {str(e)}"
        )


@router.get("/queue/status", response_model=BaseResponse)
@inject
async def get_queue_status(
    queue_url: str,
    _current_user: UserSchema = Depends(get_current_active_user),
    db: Session = Depends(Provide[Container.repositories.get_db]),
    aws_service: AwsService = Depends(Provide[Container.services.aws_service]),
) -> Any:
    """
    SQS 큐 상태를 조회합니다.
    
    Args:
        queue_url: 조회할 SQS 큐 URL
        current_user: 현재 사용자 (관리자 권한 필요)
        
    Returns:
        BaseResponse: 큐 상태 정보
    """
    try:
        from myapi.services.batch_scheduler_service import BatchSchedulerService
        
        scheduler = BatchSchedulerService(db, aws_service)
        queue_status = await scheduler.get_queue_status(queue_url)
        
        return BaseResponse(
            success=True,
            data={
                "operation": "get_queue_status",
                "queue_url": queue_url,
                "queue_status": queue_status
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue status: {str(e)}"
        )


@router.post("/execute/job", response_model=BaseResponse)
@inject
async def execute_batch_job(
    job_message: Dict[str, Any],
    _current_user: UserSchema = Depends(get_current_active_user),
    db: Session = Depends(Provide[Container.repositories.get_db]),
) -> Any:
    """
    배치 작업을 직접 실행합니다. (SQS 워커용)
    
    Args:
        job_message: SQS에서 받은 작업 메시지
        current_user: 현재 사용자 (관리자 권한 필요)
        
    Returns:
        BaseResponse: 작업 실행 결과
    """
    try:
        from myapi.services.batch_job_executor import BatchJobExecutor
        
        executor = BatchJobExecutor(db)
        
        # 작업 메시지 유효성 검증
        if not executor.validate_job_message(job_message):
            return BaseResponse(
                success=False,
                error=Error(code=ErrorCode.INVALID_CREDENTIALS, message="Invalid job message format")
            )
        
        # 작업 실행
        execution_result = await executor.execute_job(job_message)
        
        return BaseResponse(
            success=execution_result.success,
            data={
                "operation": "execute_job",
                "execution_result": {
                    "job_id": execution_result.job_id,
                    "job_type": execution_result.job_type,
                    "success": execution_result.success,
                    "message": execution_result.message,
                    "data": execution_result.data,
                    "error": execution_result.error,
                    "execution_time_ms": execution_result.execution_time_ms
                }
            },
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=execution_result.error) if execution_result.error else None
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job execution failed: {str(e)}"
        )
