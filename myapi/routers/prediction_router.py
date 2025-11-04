from typing import Any
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from dependency_injector.wiring import inject
from myapi.core.auth_middleware import get_current_active_user, require_admin
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.prediction import (
    PredictionCreate,
    PredictionUpdate,
    PredictionChoice,
)
from myapi.schemas.pagination import PaginationLimits
from myapi.services.prediction_service import PredictionService
from myapi.deps import get_prediction_service
from myapi.core.exceptions import (
    ValidationError,
    BusinessLogicError,
    ConflictError,
    NotFoundError,
    RateLimitError,
)


router = APIRouter(prefix="/predictions", tags=["predictions"])
logger = logging.getLogger("myapi")


@router.post("/{symbol}", response_model=BaseResponse)
@inject
def submit_prediction(
    payload: PredictionUpdate,
    symbol: str = Path(..., pattern=r"^[A-Z]{1,5}$"),
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
):
    try:
        create_payload = PredictionCreate(symbol=symbol.upper(), choice=payload.choice)

        trading_day = date.today()

        created = service.submit_prediction(
            current_user.id, trading_day, create_payload
        )
        return BaseResponse(success=True, data={"prediction": created.model_dump()})
    except (ValidationError, BusinessLogicError, ConflictError, RateLimitError) as e:
        msg = getattr(e, "message", str(e))
        logger.warning(f"[PredictionError] submit: {msg}")
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=msg),
        )
    except NotFoundError as e:
        msg = getattr(e, "message", str(e))
        logger.warning(f"[PredictionError] submit: {msg}")
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.USER_NOT_FOUND, message=msg),
        )
    except Exception as e:
        logger.exception("[PredictionError] submit: unexpected error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction submit failed",
        )


@router.put("/{prediction_id}", response_model=BaseResponse)
@inject
def update_prediction(
    prediction_id: int,
    payload: PredictionUpdate,
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    try:
        updated = service.update_prediction(current_user.id, prediction_id, payload)
        return BaseResponse(success=True, data={"prediction": updated.model_dump()})
    except (ValidationError, BusinessLogicError, ConflictError) as e:
        msg = getattr(e, "message", str(e))
        logger.warning(f"[PredictionError] update: {msg}")
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=msg),
        )
    except NotFoundError as e:
        msg = getattr(e, "message", str(e))
        logger.warning(f"[PredictionError] update: {msg}")
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.USER_NOT_FOUND, message=msg),
        )
    except Exception:
        logger.exception("[PredictionError] update: unexpected error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction update failed",
        )


# DELETE 엔드포인트 제거됨 (예측 취소 기능 제거)


@router.get("/day/{trading_day}", response_model=BaseResponse)
@inject
def get_user_predictions_for_day(
    trading_day: str,
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
):
    try:
        day = date.fromisoformat(trading_day)
        res = service.get_user_predictions_for_day(current_user.id, day)
        return BaseResponse(success=True, data={"result": res.model_dump()})
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception:
        logger.exception(
            "[PredictionError] get_user_predictions_for_day: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Predictions fetch failed",
        )


@router.get("/stats/{trading_day}", response_model=BaseResponse)
@inject
def get_prediction_stats(
    trading_day: str,
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    try:
        day = date.fromisoformat(trading_day)
        stats = service.get_prediction_stats(day)
        return BaseResponse(success=True, data={"stats": stats.model_dump()})
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception:
        logger.exception("[PredictionError] get_prediction_stats: unexpected error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction stats failed",
        )


@router.get("/summary/{trading_day}", response_model=BaseResponse)
@inject
def get_user_prediction_summary(
    trading_day: str,
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    try:
        day = date.fromisoformat(trading_day)
        summary = service.get_user_prediction_summary(current_user.id, day)
        return BaseResponse(success=True, data={"summary": summary.model_dump()})
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception:
        logger.exception(
            "[PredictionError] get_user_prediction_summary: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction summary failed",
        )


@router.get("/history/month", response_model=BaseResponse)
@inject
def get_user_prediction_history_by_month(
    month: str,
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
):
    try:
        history = service.get_user_prediction_history_by_date(current_user.id, month)
        return BaseResponse(success=True, data={"history": history.model_dump()})
    except Exception:
        logger.exception(
            "[PredictionError] get_user_prediction_history_by_month: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction history fetch failed",
        )


@router.get("/history", response_model=BaseResponse)
@inject
def get_user_prediction_history(
    limit: int = Query(
        PaginationLimits.PREDICTIONS_HISTORY["default"],
        ge=PaginationLimits.PREDICTIONS_HISTORY["min"],
        le=PaginationLimits.PREDICTIONS_HISTORY["max"],
    ),
    offset: int = Query(0, ge=0),
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    """사용자의 예측 이력을 조회합니다 (페이지네이션)."""
    try:
        history, total_count, has_next = service.get_user_prediction_history_paginated(
            current_user.id, limit=limit, offset=offset
        )

        return BaseResponse(
            success=True,
            data={"history": [pred.model_dump() for pred in history]},
            meta={
                "limit": limit,
                "offset": offset,
                "total_count": total_count,
                "has_next": has_next,
            },
        )
    except Exception:
        logger.exception(
            "[PredictionError] get_user_prediction_history: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction history fetch failed",
        )


@router.get("/by-symbol/{symbol}/{trading_day}", response_model=BaseResponse)
@inject
def get_predictions_by_symbol(
    symbol: str = Path(..., pattern=r"^[A-Z]{1,5}$"),
    trading_day: str = Path(...),
    _current_user: UserSchema = Depends(
        get_current_active_user
    ),  # Authentication required but user not used
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    """특정 종목과 날짜의 모든 예측을 조회합니다."""
    try:
        day = date.fromisoformat(trading_day)
        predictions = service.get_predictions_by_symbol_and_date(symbol.upper(), day)
        return BaseResponse(
            success=True,
            data={"predictions": [pred.model_dump() for pred in predictions]},
        )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception:
        logger.exception(
            "[PredictionError] get_predictions_by_symbol: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Predictions by symbol fetch failed",
        )


@router.get("/remaining/{trading_day}", response_model=BaseResponse)
@inject
def get_remaining_predictions(
    trading_day: str,
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    """사용자의 남은 예측 슬롯 수를 조회합니다."""
    try:
        day = date.fromisoformat(trading_day)
        remaining = service.get_remaining_predictions(current_user.id, day)
        return BaseResponse(success=True, data={"remaining_predictions": remaining})
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception:
        logger.exception(
            "[PredictionError] get_remaining_predictions: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Remaining predictions fetch failed",
        )


@router.get("/trends", response_model=BaseResponse)
@inject
def get_prediction_trends(
    date_param: str = Query(None, alias="date", description="조회할 날짜 (YYYY-MM-DD)"),
    limit: int = Query(5, ge=1, le=10, description="각 카테고리별 최대 종목 수 (1-10)"),
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    """
    실시간 예측 트렌드 통계를 반환합니다.

    - **date**: 조회할 날짜 (YYYY-MM-DD 형식, 기본값: 오늘)
    - **limit**: 각 카테고리별 최대 종목 수 (1-10, 기본값: 5)
    """
    try:
        # 날짜 파라미터 처리
        if date_param:
            try:
                trading_day = date.fromisoformat(date_param)
            except ValueError:
                return BaseResponse(
                    success=False,
                    error=Error(
                        code=ErrorCode.INVALID_CREDENTIALS,
                        message="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용하세요.",
                    ),
                )
        else:
            trading_day = date.today()

        # 트렌드 데이터 조회
        trends = service.get_prediction_trends(trading_day, limit)

        return BaseResponse(
            success=True,
            data=trends.model_dump(),
        )
    except Exception:
        logger.exception("[PredictionError] get_prediction_trends: unexpected error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction trends fetch failed",
        )


@router.post("/increase-slots/{trading_day}", response_model=BaseResponse)
@inject
def increase_prediction_slots(
    trading_day: str,
    additional_slots: int = 1,
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    """사용자의 예측 슬롯을 증가시킵니다."""
    try:
        day = date.fromisoformat(trading_day)
        service.increase_max_predictions(current_user.id, day, additional_slots)
        return BaseResponse(
            success=True,
            data={"message": f"Increased prediction slots by {additional_slots}"},
        )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except (ValidationError, BusinessLogicError) as e:
        msg = getattr(e, "message", str(e))
        logger.warning(f"[PredictionError] increase_prediction_slots: {msg}")
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.INVALID_CREDENTIALS, message=msg),
        )
    except Exception:
        logger.exception(
            "[PredictionError] increase_prediction_slots: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Increase prediction slots failed",
        )


# Admin/Internal endpoints for settlement processing
@router.post("/admin/lock-for-settlement/{trading_day}", response_model=BaseResponse)
@inject
def lock_predictions_for_settlement(
    trading_day: str,
    _current_user: UserSchema = Depends(require_admin),  # Admin authentication required
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    """정산을 위해 예측을 잠금합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        locked_count = service.lock_predictions_for_settlement(day)
        return BaseResponse(success=True, data={"locked_predictions": locked_count})
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception:
        logger.exception(
            "[PredictionError] lock_predictions_for_settlement: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lock predictions failed",
        )


@router.get("/admin/pending-settlement/{trading_day}", response_model=BaseResponse)
@inject
def get_pending_predictions_for_settlement(
    trading_day: str,
    _current_user: UserSchema = Depends(require_admin),  # Admin authentication required
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    """정산 대기 중인 예측을 조회합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        pending = service.get_pending_predictions_for_settlement(day)
        return BaseResponse(
            success=True,
            data={"pending_predictions": [pred.model_dump() for pred in pending]},
        )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception:
        logger.exception(
            "[PredictionError] get_pending_predictions_for_settlement: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pending predictions fetch failed",
        )


@router.post("/admin/bulk-update-status/{trading_day}", response_model=BaseResponse)
@inject
def bulk_update_predictions_status(
    trading_day: str,
    symbol: str,
    correct_choice: PredictionChoice,
    points_per_correct: int = 10,
    _current_user: UserSchema = Depends(require_admin),  # Admin authentication required
    service: PredictionService = Depends(get_prediction_service),
) -> Any:
    """예측 상태를 일괄 업데이트합니다. (관리자 전용)"""
    try:
        day = date.fromisoformat(trading_day)
        correct_count, total_count = service.bulk_update_predictions_status(
            day, symbol.upper(), correct_choice, points_per_correct
        )
        return BaseResponse(
            success=True,
            data={
                "correct_predictions": correct_count,
                "total_predictions": total_count,
                "symbol": symbol.upper(),
                "correct_choice": correct_choice.value,
            },
        )
    except ValueError:
        return BaseResponse(
            success=False,
            error=Error(
                code=ErrorCode.INVALID_CREDENTIALS, message="Invalid date format"
            ),
        )
    except Exception:
        logger.exception(
            "[PredictionError] bulk_update_predictions_status: unexpected error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk update predictions failed",
        )
