from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from dependency_injector.wiring import inject, Provide
from typing import Any

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
