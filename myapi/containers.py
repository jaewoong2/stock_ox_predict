from dependency_injector import containers, providers

from myapi.database.session import get_db
from myapi.services.aws_service import AwsService
from myapi.services.auth_service import AuthService
from myapi.services.user_service import UserService
from myapi.services.prediction_service import PredictionService
from myapi.services.session_service import SessionService
from myapi.services.universe_service import UniverseService
from myapi.services.price_service import PriceService
from myapi.services.settlement_service import SettlementService
from myapi.services.reward_service import RewardService
from myapi.services.point_service import PointService
from myapi.services.ad_unlock_service import AdUnlockService
from myapi.config import Settings
from myapi.repositories.oauth_state_repository import OAuthStateRepository


class ConfigModule(containers.DeclarativeContainer):
    """Application configuration."""

    config = providers.Singleton(Settings)


class RepositoryModule(containers.DeclarativeContainer):
    """Database repositories."""

    get_db = providers.Resource(get_db)
    oauth_state_repository = providers.Factory(OAuthStateRepository, db=get_db)


class ServiceModule(containers.DeclarativeContainer):
    """Service layer dependencies."""

    config = providers.DependenciesContainer()
    repositories = providers.DependenciesContainer()

    aws_service = providers.Factory(AwsService, settings=config.config)
    auth_service = providers.Factory(AuthService, db=repositories.get_db, settings=config.config)
    user_service = providers.Factory(UserService, db=repositories.get_db, settings=config.config)
    prediction_service = providers.Factory(PredictionService, db=repositories.get_db, settings=config.config)
    session_service = providers.Factory(SessionService, db=repositories.get_db)
    universe_service = providers.Factory(UniverseService, db=repositories.get_db)
    price_service = providers.Factory(PriceService, db=repositories.get_db)
    settlement_service = providers.Factory(SettlementService, db=repositories.get_db, settings=config.config)
    reward_service = providers.Factory(RewardService, db=repositories.get_db)
    point_service = providers.Factory(PointService, db=repositories.get_db)
    ad_unlock_service = providers.Factory(AdUnlockService, db=repositories.get_db)


class Container(containers.DeclarativeContainer):
    """Application container."""

    wiring_config = containers.WiringConfiguration(
        modules=[
            "myapi.routers.auth_router",
            "myapi.routers.user_router",
            "myapi.routers.prediction_router",
            "myapi.routers.price_router",
            "myapi.routers.settlement_router",
            "myapi.routers.session_router",
            "myapi.routers.universe_router",
            "myapi.routers.batch_router",
            "myapi.routers.reward_router",
            "myapi.routers.point_router",
            "myapi.routers.ad_unlock_router",
        ],
    )

    config = providers.Container(ConfigModule)
    repositories = providers.Container(RepositoryModule)
    services = providers.Container(
        ServiceModule, config=config, repositories=repositories
    )
