from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from myapi.repositories.base import BaseRepository
from myapi.models.user import User
from myapi.schemas.user import User as UserSchema, UserProfile
from myapi.schemas.auth import UserCreate


class UserRepository(BaseRepository[User, UserSchema]):
    """사용자 리포지토리 - Pydantic 응답 보장"""

    def __init__(self, db: Session):
        super().__init__(User, UserSchema, db)

    def get_by_email(self, email: str) -> Optional[UserSchema]:
        """이메일로 사용자 조회"""
        user = self.db.query(User).filter(User.email == email).first()
        return self._to_schema(user)

    def get_by_provider_id(self, auth_provider: str, provider_id: str) -> Optional[UserSchema]:
        """OAuth 제공자별 사용자 조회"""
        user = self.db.query(User).filter(
            and_(
                User.auth_provider == auth_provider,
                User.provider_id == provider_id
            )
        ).first()
        return self._to_schema(user)

    def create_user(self, user_data: UserCreate, password_hash: str = None, 
                   auth_provider: str = "local", provider_id: str = None) -> UserSchema:
        """새 사용자 생성"""
        user = User(
            email=user_data.email,
            nickname=user_data.nickname,
            password_hash=password_hash,
            auth_provider=auth_provider,
            provider_id=provider_id,
            is_active=True
        )
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return self._to_schema(user)

    def create_oauth_user(self, email: str, nickname: str, auth_provider: str, provider_id: str) -> UserSchema:
        """OAuth 사용자 생성"""
        user = User(
            email=email,
            nickname=nickname,
            password_hash=None,
            auth_provider=auth_provider,
            provider_id=provider_id,
            is_active=True
        )
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return self._to_schema(user)

    def update_last_login(self, user_id: int) -> Optional[UserSchema]:
        """마지막 로그인 시간 업데이트"""
        from datetime import datetime
        
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
            
        user.last_login_at = datetime.utcnow()
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return self._to_schema(user)

    def update_user(self, user_id: int, **updates) -> Optional[UserSchema]:
        """사용자 정보 업데이트"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
            
        for field, value in updates.items():
            if hasattr(user, field):
                setattr(user, field, value)
        
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return self._to_schema(user)

    def deactivate_user(self, user_id: int) -> bool:
        """사용자 비활성화"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
            
        user.is_active = False
        self.db.add(user)
        self.db.flush()
        return True

    def is_email_taken(self, email: str, exclude_user_id: int = None) -> bool:
        """이메일 중복 확인"""
        query = self.db.query(User).filter(User.email == email)
        if exclude_user_id:
            query = query.filter(User.id != exclude_user_id)
        return query.first() is not None

    def get_active_users(self, limit: int = 100, offset: int = 0) -> List[UserSchema]:
        """활성 사용자 목록 조회"""
        users = self.db.query(User).filter(User.is_active == True).offset(offset).limit(limit).all()
        return [self._to_schema(user) for user in users]

    def get_user_stats(self) -> dict:
        """사용자 통계 조회"""
        total_users = self.db.query(User).count()
        active_users = self.db.query(User).filter(User.is_active == True).count()
        oauth_users = self.db.query(User).filter(User.auth_provider != "local").count()
        local_users = self.db.query(User).filter(User.auth_provider == "local").count()
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "oauth_users": oauth_users,
            "local_users": local_users
        }