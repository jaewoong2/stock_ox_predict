import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import PrimaryKeyConstraint, UniqueConstraint

from myapi.models.base import BaseModel


class ChoiceEnum(enum.Enum):
    UP = "UP"
    DOWN = "DOWN"


class StatusEnum(enum.Enum):
    PENDING = "PENDING"
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    CANCELLED = "CANCELLED"
    VOID = "VOID"


class Prediction(BaseModel):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("trading_day", "user_id", "symbol"),
        {"schema": "crypto"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crypto.users.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    choice: Mapped[ChoiceEnum] = mapped_column(Enum(ChoiceEnum), nullable=False)
    status: Mapped[StatusEnum] = mapped_column(
        Enum(StatusEnum), default=StatusEnum.PENDING, nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    points_earned: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)

    # Snapshot of price at prediction time (for fair settlement)
    prediction_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    prediction_price_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    prediction_price_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class UserDailyStats(BaseModel):
    __tablename__ = "user_daily_stats"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "trading_day"),
        {"schema": "crypto"},
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crypto.users.id"), nullable=False
    )
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    predictions_made: Mapped[int] = mapped_column(
        SmallInteger, default=0, nullable=False
    )
    available_predictions: Mapped[int] = mapped_column(
        SmallInteger, default=3, nullable=False
    )


class AdUnlocks(BaseModel):
    __tablename__ = "ad_unlocks"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crypto.users.id"), nullable=False
    )
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)  # AD | COOLDOWN
    unlocked_slots: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
