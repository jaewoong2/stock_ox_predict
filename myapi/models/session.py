import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import PrimaryKeyConstraint

from myapi.models.base import BaseModel


class PhaseEnum(enum.Enum):
    OPEN = "OPEN"  # Predictions are being accepted
    CLOSED = "CLOSED"  # Predictions are closed, waiting for market close
    SETTLING = "SETTLING"  # Settlement in progress


class SessionControl(BaseModel):
    __tablename__ = "session_control"
    __table_args__ = (
        Index("idx_session_control_phase", "phase"),
        Index("idx_session_control_cutoff", "predict_cutoff_at"),
        {"schema": "crypto"},
    )

    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)
    phase: Mapped[PhaseEnum] = mapped_column(
        Enum(PhaseEnum), nullable=False, default=PhaseEnum.CLOSED
    )
    predict_open_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    predict_cutoff_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    settle_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When EOD data becomes available
    settled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When settlement is complete

    def __repr__(self):
        return f"<SessionControl(trading_day={self.trading_day}, phase={self.phase.value})>"

    @property
    def is_prediction_open(self) -> bool:
        """Check if predictions are currently being accepted"""
        phase_val = getattr(self, "phase", None)
        return bool(phase_val == PhaseEnum.OPEN)

    @property
    def is_settling(self) -> bool:
        """Check if settlement is in progress"""
        phase_val = getattr(self, "phase", None)
        return bool(phase_val == PhaseEnum.SETTLING)

    @property
    def is_closed(self) -> bool:
        """Check if session is closed (no predictions, no settlement)"""
        phase_val = getattr(self, "phase", None)
        return bool(phase_val == PhaseEnum.CLOSED)


class ActiveUniverse(BaseModel):
    __tablename__ = "active_universe"
    __table_args__ = (
        PrimaryKeyConstraint("trading_day", "symbol"),
        {"schema": "crypto"},
    )

    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Optional real-time-ish price snapshot fields
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    previous_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    change_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    change_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    market_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_price_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
