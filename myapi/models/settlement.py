
from sqlalchemy import Column, DateTime, Text, Date, Enum, Numeric, Integer
from sqlalchemy.schema import PrimaryKeyConstraint
from myapi.models.base import BaseModel
import enum

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
    __tablename__ = 'settlements'
    __table_args__ = (PrimaryKeyConstraint('trading_day', 'symbol'), { 'schema': 'crypto' })

    trading_day = Column(Date, nullable=False)
    symbol = Column(Text, nullable=False)
    outcome = Column(Enum(OutcomeEnum), nullable=False)
    close_price = Column(Numeric(18, 6), nullable=False)
    prev_close_price = Column(Numeric(18, 6), nullable=False)
    price_change_percent = Column(Numeric(8, 4), nullable=False)
    status = Column(Enum(SettlementStatusEnum), default=SettlementStatusEnum.PENDING, nullable=False)
    predictions_settled = Column(Integer, default=0, nullable=False)
    correct_predictions = Column(Integer, default=0, nullable=False)
    incorrect_predictions = Column(Integer, default=0, nullable=False)
    points_awarded = Column(Integer, default=0, nullable=False)
    computed_at = Column(DateTime(timezone=True), nullable=False)
    error_message = Column(Text)
