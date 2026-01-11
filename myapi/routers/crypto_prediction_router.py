"""
Crypto prediction router - DEPRECATED, use range_prediction_router instead.

This router is maintained for backward compatibility.
All logic delegates to RangePredictionService.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from myapi.core.auth_middleware import get_current_active_user, require_admin
from myapi.deps import get_crypto_prediction_service
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.range_prediction import (
    CryptoPredictionCreate,
    CryptoPredictionSchema,
)
from myapi.schemas.user import User as UserSchema
from myapi.services.range_prediction_service import (
    RangePredictionError,
    RangePredictionService,
)

logger = logging.getLogger(__name__)

# Deprecated: use /range-predictions instead
router = APIRouter(prefix="/crypto-predictions", tags=["crypto-predictions"])


def _error_response(
    status_code: int, code: ErrorCode, message: str, details: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=BaseResponse(
            success=False,
            data=None,
            error=Error(code=code, message=message, details=details),
        ).model_dump(),
    )


@router.post("", response_model=BaseResponse)
async def create_crypto_prediction(
    payload: CryptoPredictionCreate,
    current_user: UserSchema = Depends(get_current_active_user),
    service: RangePredictionService = Depends(get_crypto_prediction_service),
) -> Any:
    """
    DEPRECATED: Use /range-predictions instead.

    Create crypto price range prediction.
    """
    try:
        current_prediction = await service.list_user_predictions(
            user_id=current_user.id, symbol=payload.symbol, limit=1, offset=0
        )

        if len(current_prediction.predictions) > 0:
            prediction = await service.update_range_prediction(
                user_id=current_user.id,
                prediction_id=current_prediction.predictions[0].id,
                payload=payload,
            )

            return BaseResponse(
                success=True, data={"prediction": prediction.model_dump()}
            )

        prediction: CryptoPredictionSchema = await service.create_prediction(
            current_user.id, payload
        )
        return BaseResponse(success=True, data={"prediction": prediction.model_dump()})
    except RangePredictionError as exc:
        return _error_response(
            exc.status_code, exc.error_code, exc.message, exc.details
        )
    except Exception:
        logger.exception("[CryptoPrediction] create failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Crypto prediction creation failed",
        )


@router.get("", response_model=BaseResponse)
async def list_crypto_predictions(
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: UserSchema = Depends(get_current_active_user),
    service: RangePredictionService = Depends(get_crypto_prediction_service),
) -> Any:
    """
    DEPRECATED: Use /range-predictions instead.

    List user's crypto predictions.
    """
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
        logger.exception("[CryptoPrediction] list failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Crypto predictions fetch failed",
        )


@router.get("/history", response_model=BaseResponse)
async def crypto_prediction_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserSchema = Depends(get_current_active_user),
    service: RangePredictionService = Depends(get_crypto_prediction_service),
) -> Any:
    """
    DEPRECATED: Use /range-predictions/history instead.

    Get prediction history.
    """
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
        logger.exception("[CryptoPrediction] history failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Crypto prediction history fetch failed",
        )


@router.post("/settle", response_model=BaseResponse)
async def settle_crypto_predictions(
    _current_user: UserSchema = Depends(require_admin),
    service: RangePredictionService = Depends(get_crypto_prediction_service),
) -> Any:
    """
    DEPRECATED: Use /range-predictions/settle instead.

    Settle expired crypto predictions.
    """
    try:
        result = await service.settle_due_predictions()
        return BaseResponse(success=True, data={"result": result})
    except Exception:
        logger.exception("[CryptoPrediction] settle failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Crypto predictions settlement failed",
        )
