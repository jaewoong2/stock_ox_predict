import enum
from typing import Optional

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from myapi.models.base import BaseModel

class RedemptionStatusEnum(enum.Enum):
    REQUESTED = "REQUESTED"
    RESERVED = "RESERVED"
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class RewardsInventory(BaseModel):
    __tablename__ = "rewards_inventory"
    __table_args__ = ({"schema": "crypto", "extend_existing": True})

    sku: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cost_points: Mapped[int] = mapped_column(Integer, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vendor: Mapped[str] = mapped_column(Text, nullable=False)

class RewardsRedemption(BaseModel):
    __tablename__ = "rewards_redemptions"
    __table_args__ = ({"schema": "crypto", "extend_existing": True})

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crypto.users.id"), nullable=False
    )
    sku: Mapped[str] = mapped_column(
        Text, ForeignKey("crypto.rewards_inventory.sku"), nullable=False
    )
    cost_points: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RedemptionStatusEnum] = mapped_column(
        Enum(RedemptionStatusEnum), default=RedemptionStatusEnum.REQUESTED, nullable=False
    )
    vendor_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
