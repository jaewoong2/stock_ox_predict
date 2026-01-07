import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from myapi.core.auth_middleware import get_current_active_user, require_admin
from myapi.deps import get_crypto_prediction_service
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.crypto_prediction import (
    CryptoBandPredictionCreate,
    CryptoBandPredictionSchema,
)
from myapi.schemas.user import User as UserSchema
from myapi.services.crypto_prediction_service import (
    CryptoPredictionError,
    CryptoPredictionService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crypto-predictions", tags=["crypto-predictions"])


def _error_response(
    status_code: int, code: ErrorCode, message: str, details: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=BaseResponse(
            success=False, data=None, error=Error(code=code, message=message, details=details)
        ).model_dump(),
    )


@router.post("", response_model=BaseResponse)
async def create_crypto_prediction(
    payload: CryptoBandPredictionCreate,
    current_user: UserSchema = Depends(get_current_active_user),
    service: CryptoPredictionService = Depends(get_crypto_prediction_service),
) -> Any:
    """BTC 가격 밴드 예측 생성 (idempotent per user/open_time/row)."""
    try:
        prediction: CryptoBandPredictionSchema = await service.create_prediction(
            current_user.id, payload
        )
        return BaseResponse(
            success=True, data={"prediction": prediction.model_dump()}
        )
    except CryptoPredictionError as exc:
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
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("1h"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: UserSchema = Depends(get_current_active_user),
    service: CryptoPredictionService = Depends(get_crypto_prediction_service),
) -> Any:
    """사용자 BTC 예측 목록 조회 (최근 생성순)."""
    try:
        result = await service.list_user_predictions(
            current_user.id,
            symbol.upper(),
            interval.lower(),
            limit=limit,
            offset=offset,
        )
        return BaseResponse(
            success=True,
            data={
                "predictions": [pred.model_dump() for pred in result.predictions],
            },
            meta={
                "total_count": result.total_count,
                "limit": result.limit,
                "offset": result.offset,
                "has_next": result.has_next,
            },
        )
    except CryptoPredictionError as exc:
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
    service: CryptoPredictionService = Depends(get_crypto_prediction_service),
) -> Any:
    """예측 히스토리 조회 (동일 엔드포인트를 이용, 기본 BTCUSDT/1h)."""
    try:
        result = await service.list_user_predictions(
            current_user.id,
            "BTCUSDT",
            "1h",
            limit=limit,
            offset=offset,
        )
        return BaseResponse(
            success=True,
            data={
                "history": [pred.model_dump() for pred in result.predictions],
            },
            meta={
                "total_count": result.total_count,
                "limit": result.limit,
                "offset": result.offset,
                "has_next": result.has_next,
            },
        )
    except CryptoPredictionError as exc:
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
    service: CryptoPredictionService = Depends(get_crypto_prediction_service),
) -> Any:
    """만료된 BTC 예측 정산 (관리자/배치 용)."""
    try:
        result = await service.settle_due_predictions()
        return BaseResponse(success=True, data={"result": result})
    except Exception:
        logger.exception("[CryptoPrediction] settle failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Crypto predictions settlement failed",
        )
