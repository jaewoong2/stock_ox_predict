import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import PrimaryKeyConstraint

from myapi.models.base import BaseModel

class OutcomeEnum(enum.Enum):
    UP = "UP"
    DOWN = "DOWN"
    NO_CHANGE = "NO_CHANGE"

class SettlementStatusEnum(enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Settlement(BaseModel):
    """
    정산 결과 저장 모델

    각 거래일/종목별 예측 결과 정산 정보를 저장합니다.
    """

    __tablename__ = "settlements"
    __table_args__ = (
        PrimaryKeyConstraint("trading_day", "symbol"),
        {"schema": "crypto"},
    )

    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[OutcomeEnum] = mapped_column(Enum(OutcomeEnum), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    prev_close_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price_change_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    status: Mapped[SettlementStatusEnum] = mapped_column(
        Enum(SettlementStatusEnum), default=SettlementStatusEnum.PENDING, nullable=False
    )
    predictions_settled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_predictions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_predictions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
