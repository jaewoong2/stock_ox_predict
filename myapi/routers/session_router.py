from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from dependency_injector.wiring import inject, Provide

from myapi.containers import Container
from myapi.core.auth_middleware import (
    get_current_user_optional,
    get_current_active_user,
)
from myapi.schemas.user import User as UserSchema
from myapi.schemas.auth import BaseResponse, Error, ErrorCode
from myapi.schemas.session import SessionToday
from myapi.services.session_service import SessionService
from myapi.utils.market_hours import USMarketHours


router = APIRouter(prefix="/session", tags=["session"])


@router.get("/today", response_model=BaseResponse)
@inject
def get_today_session(
    _user: Optional[UserSchema] = Depends(get_current_user_optional),  # optional
    service: SessionService = Depends(Provide[Container.services.session_service]),
) -> Any:
    """
    오늘의 세션 정보를 조회합니다.
    미국 증시 기준으로 현재 날짜의 거래일 여부와 시장 상태를 확인합니다.

    Args:
        _user (Optional[UserSchema]): 현재 사용자 정보 (인증되지 않아도 접근 가능)
        service (SessionService): 세션 서비스

    Returns:
        BaseResponse: 오늘의 세션 정보 및 시장 상태
    """
    try:
        current_kst = USMarketHours.get_current_kst_time()
        today = current_kst.date()

        # 시장 상태 확인
        market_status = USMarketHours.get_market_status(today)

        # 세션 정보 조회
        today_session = service.get_today()

        response_data = {
            "session": today_session.model_dump() if today_session else None,
            "market_status": {
                "current_date": today.strftime("%Y-%m-%d"),
                "current_time_kst": current_kst.strftime("%H:%M:%S"),
                "is_trading_day": market_status.is_trading_day,
                "message": market_status.message,
            },
        }

        # 거래일이 아닌 경우 다음 거래일 정보 추가
        if not market_status.is_trading_day:
            next_trading_day = USMarketHours.get_next_trading_day(today)
            response_data["market_status"]["next_trading_day"] = (
                next_trading_day.strftime("%Y-%m-%d")
            )

        return BaseResponse(success=True, data=response_data)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fetch session failed",
        )


# Internal-ish endpoints (should be admin-protected in production)
@router.post("/flip-to-predict", response_model=BaseResponse)
@inject
def flip_to_predict(
    _current_user: UserSchema = Depends(get_current_active_user),
    service: SessionService = Depends(Provide[Container.services.session_service]),
) -> Any:
    """
    예측 모드로 세션을 전환합니다.
    미국 증시 거래일에만 실행 가능합니다.
    """
    try:
        status_obj = service.open_predictions()
        return BaseResponse(
            success=True,
            data={"status": status_obj.model_dump() if status_obj else None},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Flip to predict failed",
        )


@router.post("/cutoff", response_model=BaseResponse)
@inject
def cutoff_predictions(
    _current_user: UserSchema = Depends(get_current_active_user),
    service: SessionService = Depends(Provide[Container.services.session_service]),
) -> Any:
    try:
        status_obj = service.close_predictions()
        return BaseResponse(
            success=True,
            data={"status": status_obj.model_dump() if status_obj else None},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cutoff failed"
        )


@router.get("/prediction-status", response_model=BaseResponse)
@inject
def get_prediction_status(
    trading_day: Optional[str] = None,
    user: Optional[UserSchema] = Depends(get_current_user_optional),
    service: SessionService = Depends(Provide[Container.services.session_service]),
) -> Any:
    """
    예측 가능 시간 상태를 상세히 조회합니다.

    Args:
        trading_day: 확인할 거래일 (선택사항, 기본값은 오늘)
        _user: 현재 사용자 정보 (인증되지 않아도 접근 가능)
        service: 세션 서비스

    Returns:
        BaseResponse: 예측 시간 상태 정보
    """
    try:
        from datetime import date

        target_date = None
        if trading_day:
            target_date = date.fromisoformat(trading_day)

        status = service.get_prediction_time_status(target_date)

        return BaseResponse(success=True, data={"prediction_status": status})

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get prediction status: {str(e)}"
        )


@router.get("/can-predict", response_model=BaseResponse)
@inject
def can_predict_now(
    trading_day: Optional[str] = None,
    user: Optional[UserSchema] = Depends(get_current_user_optional),
    service: SessionService = Depends(Provide[Container.services.session_service]),
) -> Any:
    """
    현재 예측 가능한지 간단히 확인합니다.

    Args:
        trading_day: 확인할 거래일 (선택사항, 기본값은 오늘)
        _user: 현재 사용자 정보 (인증되지 않아도 접근 가능)
        service: 세션 서비스

    Returns:
        BaseResponse: 예측 가능 여부
    """
    try:
        from datetime import date

        target_date = None
        if trading_day:
            target_date = date.fromisoformat(trading_day)

        can_predict = service.is_prediction_time(target_date)

        return BaseResponse(
            success=True,
            data={
                "can_predict": can_predict,
                "trading_day": (
                    target_date or USMarketHours.get_current_kst_time().date()
                ).isoformat(),
                "current_time": USMarketHours.get_current_kst_time().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to check prediction availability: {str(e)}"
        )
