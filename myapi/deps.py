from fastapi import Depends
from sqlalchemy.orm import Session

from myapi.database.session import get_db
from myapi.config import settings

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
    return RewardService(db=db)


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
