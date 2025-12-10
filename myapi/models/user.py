from datetime import datetime
from enum import Enum
from typing import Optional, Union

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from myapi.models.base import BaseModel

"""User role enumeration for role-based access control."""


class UserRole(str, Enum):
    """사용자 역할 정의"""

    USER = "user"  # 일반 사용자
    PREMIUM = "premium"  # 과금 사용자
    ADMIN = "admin"  # 관리자
    SUPER_ADMIN = "super_admin"  # 최고 관리자

    @classmethod
    def get_hierarchy_level(cls, role: Union[str, "UserRole"]) -> int:
        """역할의 계층 레벨을 반환 (숫자가 높을수록 높은 권한)"""
        if isinstance(role, cls):
            role = role.value

        hierarchy = {
            cls.USER.value: 1,
            cls.PREMIUM.value: 2,
            cls.ADMIN.value: 3,
            cls.SUPER_ADMIN.value: 4,
        }
        return hierarchy.get(str(role), 0)

    @classmethod
    def has_permission(
        cls, user_role: Union[str, "UserRole"], required_role: Union[str, "UserRole"]
    ) -> bool:
        """사용자 역할이 요구되는 역할 이상인지 확인"""
        return cls.get_hierarchy_level(user_role) >= cls.get_hierarchy_level(
            required_role
        )

    @classmethod
    def is_admin(cls, role: Union[str, "UserRole"]) -> bool:
        """관리자 권한 확인 (기존 is_admin 호환성을 위해)"""
        if isinstance(role, cls):
            role = role.value
        return role in [cls.ADMIN.value, cls.SUPER_ADMIN.value]

    @classmethod
    def is_premium_or_above(cls, role: Union[str, "UserRole"]) -> bool:
        """프리미엄 이상 권한 확인"""
        return cls.get_hierarchy_level(role) >= cls.get_hierarchy_level(cls.PREMIUM)


class User(BaseModel):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("auth_provider", "provider_id", name="uq_user_provider"),
        Index("idx_users_email", "email"),
        Index("idx_users_auth_provider", "auth_provider", "provider_id"),
        {"schema": "crypto"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    nickname: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # NULL for OAuth users
    auth_provider: Mapped[str] = mapped_column(
        String(50), default="local", nullable=False
    )
    provider_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # OAuth provider user ID
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )  # For user deactivation
    role: Mapped[str] = mapped_column(
        String(20), default=UserRole.USER, nullable=False
    )  # User role

    def __repr__(self):
        return (
            f"<User(id={self.id}, email={self.email}, provider={self.auth_provider})>"
        )

    @property
    def is_oauth_user(self) -> bool:
        """Check if user is OAuth authenticated"""
        # Avoid SQLAlchemy ColumnElement truthiness; access instance value safely
        auth_provider_val = getattr(self, "auth_provider", "local")
        return bool(auth_provider_val != "local")

    @property
    def is_admin(self) -> bool:
        """Check if user has admin privileges (backward compatibility)"""
        role = str(self.role)
        return UserRole.is_admin(role)

    @property
    def is_premium_or_above(self) -> bool:
        """Check if user has premium or higher privileges"""
        role = str(self.role)
        return UserRole.is_premium_or_above(role)

    def has_permission(self, required_role: str) -> bool:
        """Check if user has required role or higher"""
        role = str(self.role)
        return UserRole.has_permission(role, required_role)
