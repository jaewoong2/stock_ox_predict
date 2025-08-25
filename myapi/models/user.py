from sqlalchemy import Column, String, BigInteger, DateTime, Text, Index, Boolean
from sqlalchemy.schema import UniqueConstraint
from myapi.models.base import BaseModel


class User(BaseModel):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("auth_provider", "provider_id", name="uq_user_provider"),
        Index("idx_users_email", "email"),
        Index("idx_users_auth_provider", "auth_provider", "provider_id"),
        {"schema": "crypto"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    nickname = Column(String(100), nullable=False)
    password_hash = Column(Text, nullable=True)  # NULL for OAuth users
    auth_provider = Column(String(50), default="local", nullable=False)
    provider_id = Column(String(255), nullable=True)  # OAuth provider user ID
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)  # For user deactivation

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
