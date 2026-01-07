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
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from myapi.models.base import BaseModel


class CryptoBandPredictionStatus(enum.Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    ERROR = "ERROR"


class CryptoBandPrediction(BaseModel):
    """BTC 가격 밴드 예측 모델.

    BaseModel을 사용하여 created_at/updated_at 타임스탬프 컬럼을 포함합니다.
    """

    __tablename__ = "crypto_band_predictions"
    __table_args__ = (
        UniqueConstraint("user_id", "target_open_time_ms", "row"),
        {"schema": "crypto"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crypto.users.id"), nullable=False
    )
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False, default="1h")
    future_col: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    row: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    target_open_time_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_close_time_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)

    p0: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    band_pct_low: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    band_pct_high: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    band_price_low: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    band_price_high: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8), nullable=True
    )

    status: Mapped[CryptoBandPredictionStatus] = mapped_column(
        Enum(CryptoBandPredictionStatus),
        nullable=False,
        default=CryptoBandPredictionStatus.PENDING,
    )

    settlement_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    settlement_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    last_settlement_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

