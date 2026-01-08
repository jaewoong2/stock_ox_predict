"""Range prediction router - handles price range predictions (asset-agnostic)."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from myapi.core.auth_middleware import get_current_active_user, require_admin
from myapi.deps import get_range_prediction_service
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.range_prediction import (
    RangePredictionCreate,
    RangePredictionResponse,
    RangePredictionUpdate,
)
from myapi.schemas.user import User as UserSchema
from myapi.services.range_prediction_service import (
    RangePredictionError,
    RangePredictionService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/range-predictions", tags=["range-predictions"])


def _error_response(
    status_code: int, code: ErrorCode, message: str, details: dict | None = None
) -> JSONResponse:
    """Create error response."""
    return JSONResponse(
        status_code=status_code,
        content=BaseResponse(
            success=False,
            data=None,
            error=Error(code=code, message=message, details=details),
        ).model_dump(),
    )


@router.post("", response_model=BaseResponse)
async def create_range_prediction(
    payload: RangePredictionCreate,
    current_user: UserSchema = Depends(get_current_active_user),
    service: RangePredictionService = Depends(get_range_prediction_service),
) -> Any:
    """Create RANGE prediction (price range for future time window)."""
    try:
        prediction: RangePredictionResponse = await service.create_prediction(
            current_user.id, payload
        )
        return BaseResponse(success=True, data={"prediction": prediction.model_dump()})
    except RangePredictionError as exc:
        return _error_response(
            exc.status_code, exc.error_code, exc.message, exc.details
        )
    except Exception:
        logger.exception("[RangePrediction] create failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Range prediction creation failed",
        )


@router.patch("/{prediction_id}", response_model=BaseResponse)
async def update_range_prediction(
    prediction_id: int,
    payload: RangePredictionUpdate,
    current_user: UserSchema = Depends(get_current_active_user),
    service: RangePredictionService = Depends(get_range_prediction_service),
) -> Any:
    """Update RANGE prediction bounds (only PENDING predictions)."""
    try:
        prediction: RangePredictionResponse = await service.update_range_prediction(
            current_user.id, prediction_id, payload
        )
        return BaseResponse(success=True, data={"prediction": prediction.model_dump()})
    except RangePredictionError as exc:
        return _error_response(
            exc.status_code, exc.error_code, exc.message, exc.details
        )
    except Exception:
        logger.exception("[RangePrediction] update failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Range prediction update failed",
        )


@router.get("", response_model=BaseResponse)
async def list_range_predictions(
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: UserSchema = Depends(get_current_active_user),
    service: RangePredictionService = Depends(get_range_prediction_service),
) -> Any:
    """List user's RANGE predictions (latest first)."""
    try:
        result = await service.list_user_predictions(
            current_user.id,
            symbol,
            limit=limit,
            offset=offset,
        )
        return BaseResponse(
            success=True,
            data={"predictions": [pred.model_dump() for pred in result.predictions]},
            meta={
                "total_count": result.total_count,
                "limit": result.limit,
                "offset": result.offset,
                "has_next": result.has_next,
            },
        )
    except RangePredictionError as exc:
        return _error_response(
            exc.status_code, exc.error_code, exc.message, exc.details
        )
    except Exception:
        logger.exception("[RangePrediction] list failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Range predictions fetch failed",
        )


@router.get("/history", response_model=BaseResponse)
async def range_prediction_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserSchema = Depends(get_current_active_user),
    service: RangePredictionService = Depends(get_range_prediction_service),
) -> Any:
    """Get prediction history."""
    try:
        result = await service.list_user_predictions(
            current_user.id,
            None,
            limit=limit,
            offset=offset,
        )
        return BaseResponse(
            success=True,
            data={"history": [pred.model_dump() for pred in result.predictions]},
            meta={
                "total_count": result.total_count,
                "limit": result.limit,
                "offset": result.offset,
                "has_next": result.has_next,
            },
        )
    except RangePredictionError as exc:
        return _error_response(
            exc.status_code, exc.error_code, exc.message, exc.details
        )
    except Exception:
        logger.exception("[RangePrediction] history failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Range prediction history fetch failed",
        )


@router.post("/settle", response_model=BaseResponse)
async def settle_range_predictions(
    _current_user: UserSchema = Depends(require_admin),
    service: RangePredictionService = Depends(get_range_prediction_service),
) -> Any:
    """Settle expired RANGE predictions (admin/batch only)."""
    try:
        result = await service.settle_due_predictions()
        return BaseResponse(success=True, data={"result": result})
    except Exception:
        logger.exception("[RangePrediction] settle failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Range predictions settlement failed",
        )

