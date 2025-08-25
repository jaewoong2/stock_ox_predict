from dependency_injector import containers, providers

from myapi.database.session import get_db
from myapi.services.aws_service import AwsService
from myapi.services.auth_service import AuthService
from myapi.services.user_service import UserService
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
    auth_service = providers.Factory(AuthService, db=repositories.get_db)
    user_service = providers.Factory(UserService, db=repositories.get_db)


class Container(containers.DeclarativeContainer):
    """Application container."""

    wiring_config = containers.WiringConfiguration(
        modules=[
            "myapi.routers.auth_router",
            "myapi.routers.user_router",
        ],
    )

    config = providers.Container(ConfigModule)
    repositories = providers.Container(RepositoryModule)
    services = providers.Container(
        ServiceModule, config=config, repositories=repositories
    )
