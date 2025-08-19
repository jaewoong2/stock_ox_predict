from sqlalchemy import (
    Column,
    String,
    BigInteger,
    DateTime,
    Text,
    Date,
    Enum,
    SmallInteger,
    ForeignKey,
    Integer,
)
from sqlalchemy.schema import UniqueConstraint, PrimaryKeyConstraint
from myapi.models.base import BaseModel
import enum


class ChoiceEnum(enum.Enum):
    UP = "UP"
    DOWN = "DOWN"


class StatusEnum(enum.Enum):
    PENDING = "PENDING"
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    CANCELLED = "CANCELLED"


class Prediction(BaseModel):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("trading_day", "user_id", "symbol"),
        {"schema": "crypto"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trading_day = Column(Date, nullable=False)
    user_id = Column(BigInteger, ForeignKey("crypto.users.id"), nullable=False)
    symbol = Column(Text, nullable=False)
    choice = Column(Enum(ChoiceEnum), nullable=False)
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True))
    locked_at = Column(DateTime(timezone=True))
    points_earned = Column(Integer, default=0)


class UserDailyStats(BaseModel):
    __tablename__ = "user_daily_stats"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "trading_day"),
        {"schema": "crypto"},
    )

    user_id = Column(BigInteger, ForeignKey("crypto.users.id"), nullable=False)
    trading_day = Column(Date, nullable=False)
    predictions_made = Column(SmallInteger, default=0, nullable=False)
    max_predictions = Column(SmallInteger, default=3, nullable=False)


class AdUnlocks(BaseModel):
    __tablename__ = "ad_unlocks"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("crypto.users.id"), nullable=False)
    trading_day = Column(Date, nullable=False)
    method = Column(Text, nullable=False)  # AD | COOLDOWN
    unlocked_slots = Column(SmallInteger, default=1, nullable=False)
