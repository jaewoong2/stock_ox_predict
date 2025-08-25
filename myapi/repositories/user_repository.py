from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timezone

from myapi.models.user import User as UserModel
from myapi.schemas.user import User as UserSchema, UserProfile, UserStats
from myapi.repositories.base import BaseRepository


class UserRepository(BaseRepository[UserModel, UserSchema]):
    """사용자 리포지토리 - OAuth 지원"""

    def __init__(self, db: Session):
        super().__init__(UserModel, UserSchema, db)

    def get_by_email(self, email: str) -> Optional[UserSchema]:
        """이메일로 사용자 조회"""
        return self.get_by_field("email", email)

    def get_by_provider_info(
        self, auth_provider: str, provider_id: str
    ) -> Optional[UserSchema]:
        """OAuth 제공자 정보로 사용자 조회"""
        model_instance = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.auth_provider == auth_provider,
                    self.model_class.provider_id == provider_id,
                )
            )
            .first()
        )
        return self._to_schema(model_instance)

    def create_oauth_user(
        self, email: str, nickname: str, auth_provider: str, provider_id: str
    ) -> Optional[UserSchema]:
        """OAuth 사용자 생성"""
        return self.create(
            email=email,
            nickname=nickname,
            auth_provider=auth_provider,
            provider_id=provider_id,
            password_hash=None,  # OAuth users don't have password
            is_active=True,
        )

    def create_local_user(
        self, email: str, nickname: str, password_hash: str
    ) -> Optional[UserSchema]:
        """로컬 사용자 생성"""
        return self.create(
            email=email,
            nickname=nickname,
            auth_provider="local",
            provider_id=None,
            password_hash=password_hash,
            is_active=True,
        )

    def update_last_login(
        self, user_id: int, login_time: Optional[datetime] = None
    ) -> Optional[UserSchema]:
        """마지막 로그인 시간 업데이트"""
        if login_time is None:
            login_time = datetime.now(timezone.utc)

        return self.update(user_id, last_login_at=login_time)

    def deactivate_user(self, user_id: int) -> Optional[UserSchema]:
        """사용자 비활성화"""
        return self.update(user_id, is_active=False)

    def activate_user(self, user_id: int) -> Optional[UserSchema]:
        """사용자 활성화"""
        return self.update(user_id, is_active=True)

    def get_active_users(self, limit: int = 10, offset: int = 10) -> List[UserSchema]:
        """활성 사용자 목록 조회"""
        return self.find_all(
            filters={"is_active": True},
            order_by="created_at",
            limit=limit,
            offset=offset,
        )

    def get_oauth_users(self, auth_provider: str = "") -> List[UserSchema]:
        """OAuth 사용자 목록 조회"""
        filters = {}
        if auth_provider:
            filters["auth_provider"] = auth_provider
        else:
            # OAuth users have auth_provider != 'local'
            pass

        if auth_provider:
            return self.find_all(filters=filters, order_by="created_at")
        else:
            # Custom query for non-local users
            model_instances = (
                self.db.query(self.model_class)
                .filter(self.model_class.auth_provider != "local")
                .order_by(self.model_class.created_at)
                .all()
            )
            results = []
            for instance in model_instances:
                schema_instance = self._to_schema(instance)
                if schema_instance is not None:
                    results.append(schema_instance)
            return results

    def get_user_profile(self, user_id: int) -> Optional[UserProfile]:
        """사용자 프로필 조회 (UserProfile 스키마 반환)"""
        model_instance = (
            self.db.query(self.model_class)
            .filter(self.model_class.id == user_id)
            .first()
        )

        if not model_instance:
            return None

        return UserProfile.model_validate(model_instance)

    def get_user_stats(self) -> UserStats:
        """전체 사용자 통계 조회"""
        total_users = self.count()
        active_users = self.count(filters={"is_active": True})

        oauth_users_count = (
            self.db.query(self.model_class)
            .filter(self.model_class.auth_provider != "local")
            .count()
        )

        local_users_count = self.count(filters={"auth_provider": "local"})

        return UserStats(
            total_users=total_users,
            active_users=active_users,
            oauth_users=oauth_users_count,
            local_users=local_users_count,
        )

    def search_users_by_nickname(
        self, nickname_pattern: str, limit: int = 50
    ) -> List[UserSchema]:
        """닉네임으로 사용자 검색 (LIKE 패턴)"""
        model_instances = (
            self.db.query(self.model_class)
            .filter(self.model_class.nickname.ilike(f"%{nickname_pattern}%"))
            .limit(limit)
            .all()
        )

        results = []
        for instance in model_instances:
            schema_instance = self._to_schema(instance)
            if schema_instance is not None:
                results.append(schema_instance)
        return results

    def email_exists(self, email: str) -> bool:
        """이메일 중복 체크"""
        return self.exists(filters={"email": email})

    def provider_user_exists(self, auth_provider: str, provider_id: str) -> bool:
        """OAuth 제공자별 사용자 존재 여부 확인"""
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.auth_provider == auth_provider,
                    self.model_class.provider_id == provider_id,
                )
            )
            .first()
            is not None
        )
