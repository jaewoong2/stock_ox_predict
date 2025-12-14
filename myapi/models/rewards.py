import enum
from typing import Optional

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, Text, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from myapi.models.base import BaseModel

class RedemptionStatusEnum(enum.Enum):
    REQUESTED = "REQUESTED"
    RESERVED = "RESERVED"
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    AVAILABLE = "AVAILABLE"  # 사용 가능 (구매 완료, 아직 사용 안 함)
    USED = "USED"  # 사용 완료

class RewardType(enum.Enum):
    SLOT_REFRESH = "SLOT_REFRESH"  # 슬롯 리프레시
    GIFT_VOUCHER = "GIFT_VOUCHER"  # 기프티콘
    POINTS_BONUS = "POINTS_BONUS"  # 보너스 포인트

class RewardsInventory(BaseModel):
    __tablename__ = "rewards_inventory"
    __table_args__ = ({"schema": "crypto", "extend_existing": True})

    sku: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cost_points: Mapped[int] = mapped_column(Integer, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vendor: Mapped[str] = mapped_column(Text, nullable=False)

    # 신규 필드 (DB 마이그레이션 필요)
    reward_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="SLOT_REFRESH")
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activation_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

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
