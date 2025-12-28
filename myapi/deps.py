from fastapi import Depends, Request
from sqlalchemy.orm import Session
from datetime import date

from myapi.database.session import get_db
from myapi.config import settings
from myapi.core.exceptions import NonTradingDayError
from myapi.utils.market_hours import USMarketHours

# Services
from myapi.services.user_service import UserService
from myapi.services.prediction_service import PredictionService
from myapi.services.session_service import SessionService
from myapi.services.universe_service import UniverseService
from myapi.services.price_service import PriceService
from myapi.services.settlement_service import SettlementService
from myapi.services.reward_service import RewardService
from myapi.services.point_service import PointService
from myapi.services.ad_unlock_service import AdUnlockService
from myapi.services.cooldown_service import CooldownService
from myapi.services.auth_service import AuthService
from myapi.services.magic_link_service import MagicLinkService
from myapi.services.favorites_service import FavoritesService


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db=db, settings=settings)


def get_prediction_service(db: Session = Depends(get_db)) -> PredictionService:
    return PredictionService(db=db, settings=settings)


def get_session_service(db: Session = Depends(get_db)) -> SessionService:
    return SessionService(db=db)


def get_universe_service(db: Session = Depends(get_db)) -> UniverseService:
    return UniverseService(db=db)


def get_price_service(db: Session = Depends(get_db)) -> PriceService:
    return PriceService(db=db)


def get_settlement_service(db: Session = Depends(get_db)) -> SettlementService:
    return SettlementService(db=db, settings=settings)


def get_reward_service(db: Session = Depends(get_db)) -> RewardService:
    from myapi.services.aws_service import AwsService

    prediction_service = PredictionService(db=db, settings=settings)
    aws_service = AwsService(settings=settings)
    return RewardService(
        db=db, prediction_service=prediction_service, aws_service=aws_service
    )


def get_point_service(db: Session = Depends(get_db)) -> PointService:
    return PointService(db=db)


def get_ad_unlock_service(db: Session = Depends(get_db)) -> AdUnlockService:
    return AdUnlockService(db=db)


def get_cooldown_service(db: Session = Depends(get_db)) -> CooldownService:
    return CooldownService(db=db, settings=settings)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db=db, settings=settings)


def get_magic_link_service(db: Session = Depends(get_db)) -> MagicLinkService:
    return MagicLinkService(db=db, settings=settings)


def get_favorites_service(db: Session = Depends(get_db)) -> FavoritesService:
    return FavoritesService(db=db)


# ============================================================================
# Trading Day Validation Dependencies
# ============================================================================


def _get_day_type(check_date: date) -> str:
    """주어진 날짜가 어떤 타입인지 반환 (holiday, weekend, 또는 trading)"""
    if check_date.weekday() >= 5:
        return "weekend"
    elif check_date in USMarketHours.US_HOLIDAYS_2025:
        return "holiday"
    return "trading"


def validate_trading_day(allow_past: bool = True, allow_future: bool = False):
    """
    Trading day 검증 dependency factory

    Args:
        allow_past: 과거 거래일 허용 여부 (기본: True)
        allow_future: 미래 거래일 허용 여부 (기본: False)

    Returns:
        Validated date object

    Raises:
        NonTradingDayError: 비거래일인 경우 422 에러
    """

    def _validate(request: Request) -> date:
        # Query parameter에서 trading_day 추출
        trading_day_str = request.query_params.get("trading_day", "")

        # 날짜 파싱 (없으면 현재 KST 거래일)
        if trading_day_str:
            try:
                check_date = date.fromisoformat(trading_day_str)
            except ValueError:
                raise NonTradingDayError(
                    requested_date=trading_day_str,
                    day_type="invalid_format",
                    next_trading_day=str(USMarketHours.get_kst_trading_day()),
                )
        else:
            check_date = USMarketHours.get_kst_trading_day()

        # 거래일 여부 확인
        if not USMarketHours.is_us_trading_day(check_date):
            day_type = _get_day_type(check_date)
            next_trading_day = USMarketHours.get_next_trading_day(check_date)
            raise NonTradingDayError(
                requested_date=str(check_date),
                day_type=day_type,
                next_trading_day=str(next_trading_day),
            )

        # 과거/미래 날짜 검증
        today = USMarketHours.get_kst_trading_day()

        if not allow_past and check_date < today:
            next_trading_day = USMarketHours.get_next_trading_day(today)
            raise NonTradingDayError(
                requested_date=str(check_date),
                day_type="past_not_allowed",
                next_trading_day=str(next_trading_day),
            )

        if not allow_future and check_date > today:
            raise NonTradingDayError(
                requested_date=str(check_date),
                day_type="future_not_allowed",
                next_trading_day=str(today),
            )

        return check_date

    return _validate


def require_trading_day(request: Request) -> date:
    """
    거래일 검증 dependency (과거/미래 모두 허용)

    Use Case: 히스토리 데이터 조회 등 과거 거래일 접근이 필요한 경우

    Returns:
        Validated trading day (date)

    Raises:
        NonTradingDayError: 비거래일인 경우 422 에러
    """
    validator = validate_trading_day(allow_past=True, allow_future=True)
    return validator(request)


def require_current_trading_day(request: Request) -> date:
    """
    현재 거래일 검증 dependency (오늘만 허용)

    Use Case: 예측 제출, 실시간 데이터 등 현재 거래일만 유효한 경우

    Returns:
        Current trading day (date)

    Raises:
        NonTradingDayError: 오늘이 아니거나 비거래일인 경우 422 에러
    """
    validator = validate_trading_day(allow_past=False, allow_future=False)
    return validator(request)
