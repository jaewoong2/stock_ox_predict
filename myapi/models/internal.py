from sqlalchemy import (
    Column,
    BigInteger,
    DateTime,
    Text,
    Date,
    ForeignKey,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import ARRAY
from myapi.models.base import BaseModel


class ConfigurationSetting(BaseModel):
    __tablename__ = "configuration_settings"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    key = Column(Text, nullable=False, unique=True)
    value = Column(Text, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("crypto.users.id"))
    action = Column(Text, nullable=False)
    table_name = Column(Text, nullable=False)
    record_id = Column(Text, nullable=False)
    old_values = Column(JSON)
    new_values = Column(JSON)
    ip_address = Column(INET)
    user_agent = Column(Text)


class SystemHealth(BaseModel):
    __tablename__ = "system_health"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    component = Column(Text, primary_key=True)
    status = Column(Text, nullable=False)
    last_check = Column(DateTime(timezone=True))
    error_message = Column(Text)
    metrics = Column(JSON)


class ErrorLog(BaseModel):
    __tablename__ = "error_logs"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    check_type = Column(Text, nullable=False)
    trading_day = Column(Date)
    status = Column(Text, nullable=False)
    details = Column(JSON)


class EODFetchLog(BaseModel):
    __tablename__ = "eod_fetch_logs"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trading_day = Column(Date, nullable=False)
    provider = Column(Text, nullable=False)
    symbols = Column(ARRAY(Text), nullable=False)
    status = Column(Text, nullable=False)
    response_data = Column(JSON)
    error_message = Column(Text)
    fetched_at = Column(DateTime(timezone=True))


class OAuthState(BaseModel):
    __tablename__ = "oauth_states"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    state = Column(Text, primary_key=True)
    redirect_uri = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
