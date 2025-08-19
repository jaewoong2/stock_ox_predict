
from sqlalchemy import Column, String, BigInteger, DateTime, Text, Date, Enum, SmallInteger, Numeric, Integer
from sqlalchemy.schema import PrimaryKeyConstraint, UniqueConstraint
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

class EODPrice(BaseModel):
    __tablename__ = 'eod_prices'
    __table_args__ = (
        UniqueConstraint('asof', 'symbol', 'vendor_rev', name='uq_eod_prices_asof_symbol_vendor'),
        { 'schema': 'crypto' }
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    asof = Column(Date, nullable=False)
    symbol = Column(Text, nullable=False)
    open_price = Column(Numeric(18, 6), nullable=False)
    high_price = Column(Numeric(18, 6), nullable=False)
    low_price = Column(Numeric(18, 6), nullable=False)
    close_price = Column(Numeric(18, 6), nullable=False)
    prev_close_price = Column(Numeric(18, 6), nullable=False)
    volume = Column(BigInteger, default=0, nullable=False)
    vendor_rev = Column(Integer, default=0, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    
class SettlementJob(BaseModel):
    __tablename__ = 'settlement_jobs'
    __table_args__ = ({'schema': 'crypto', 'extend_existing': True})

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trading_day = Column(Date, nullable=False)
    status = Column(Enum(SettlementStatusEnum), default=SettlementStatusEnum.PENDING, nullable=False)
    total_symbols = Column(Integer, default=0, nullable=False)
    processed_symbols = Column(Integer, default=0, nullable=False)
    failed_symbols = Column(Integer, default=0, nullable=False)
    total_predictions = Column(Integer, default=0, nullable=False)
    total_points_awarded = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
