
from sqlalchemy import Column, String, BigInteger, DateTime, Text, Date, Enum, SmallInteger, Integer, ForeignKey
from myapi.models.base import BaseModel
import enum

class RedemptionStatusEnum(enum.Enum):
    REQUESTED = "REQUESTED"
    RESERVED = "RESERVED"
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class RewardsInventory(BaseModel):
    __tablename__ = 'rewards_inventory'
    __table_args__ = ({'schema': 'crypto', 'extend_existing': True})

    sku = Column(Text, primary_key=True)
    title = Column(Text, nullable=False)
    cost_points = Column(Integer, nullable=False)
    stock = Column(Integer, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    vendor = Column(Text, nullable=False)

class RewardsRedemption(BaseModel):
    __tablename__ = 'rewards_redemptions'
    __table_args__ = ({'schema': 'crypto', 'extend_existing': True})

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('crypto.users.id'), nullable=False)
    sku = Column(Text, ForeignKey('crypto.rewards_inventory.sku'), nullable=False)
    cost_points = Column(Integer, nullable=False)
    status = Column(Enum(RedemptionStatusEnum), default=RedemptionStatusEnum.REQUESTED, nullable=False)
    vendor_code = Column(Text)
