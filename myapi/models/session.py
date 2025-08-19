from sqlalchemy import (
    Column,
    String,
    BigInteger,
    DateTime,
    Text,
    Date,
    Enum,
    SmallInteger,
    Index,
)
from sqlalchemy.schema import PrimaryKeyConstraint
from myapi.models.base import BaseModel
import enum


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

    trading_day = Column(Date, primary_key=True)
    phase = Column(Enum(PhaseEnum), nullable=False, default=PhaseEnum.CLOSED)
    predict_open_at = Column(DateTime(timezone=True), nullable=False)
    predict_cutoff_at = Column(DateTime(timezone=True), nullable=False)
    settle_ready_at = Column(DateTime(timezone=True))  # When EOD data becomes available
    settled_at = Column(DateTime(timezone=True))  # When settlement is complete

    def __repr__(self):
        return f"<SessionControl(trading_day={self.trading_day}, phase={self.phase.value})>"

    @property
    def is_prediction_open(self) -> bool:
        """Check if predictions are currently being accepted"""
        return bool(self.phase == PhaseEnum.OPEN)

    @property
    def is_settling(self) -> bool:
        """Check if settlement is in progress"""
        return bool(self.phase == PhaseEnum.SETTLING)

    @property
    def is_closed(self) -> bool:
        """Check if session is closed (no predictions, no settlement)"""
        return bool(self.phase == PhaseEnum.CLOSED)


class ActiveUniverse(BaseModel):
    __tablename__ = "active_universe"
    __table_args__ = (
        PrimaryKeyConstraint("trading_day", "symbol"),
        {"schema": "crypto"},
    )

    trading_day = Column(Date, nullable=False)
    symbol = Column(Text, nullable=False)
    seq = Column(SmallInteger, nullable=False)
