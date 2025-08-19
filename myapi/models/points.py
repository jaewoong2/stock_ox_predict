
from sqlalchemy import Column, String, BigInteger, DateTime, Text, Date, ForeignKey
from sqlalchemy.schema import UniqueConstraint
from myapi.models.base import BaseModel

class PointsLedger(BaseModel):
    __tablename__ = 'points_ledger'
    __table_args__ = (UniqueConstraint('ref_id'), { 'schema': 'crypto' })

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('crypto.users.id'), nullable=False)
    trading_day = Column(Date)
    symbol = Column(Text)
    delta_points = Column(BigInteger, nullable=False)
    reason = Column(Text, nullable=False)
    ref_id = Column(Text, nullable=False)
    balance_after = Column(BigInteger, nullable=False)
