from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import datetime
from myapi.repositories.base import BaseRepository
from myapi.models.rewards import RewardsInventory, RewardsRedemption
from myapi.schemas.rewards import RewardsInventoryResponse, RewardsRedemptionResponse


class RewardsInventoryRepository(BaseRepository[RewardsInventory, RewardsInventoryResponse]):
    """리워드 인벤토리 리포지토리"""

    def __init__(self, db: Session):
        super().__init__(RewardsInventory, RewardsInventoryResponse, db)

    def _to_inventory_schema(self, inventory: RewardsInventory) -> RewardsInventoryResponse:
        """RewardsInventory를 RewardsInventoryResponse 스키마로 변환"""
        if not inventory:
            return None
            
        return RewardsInventoryResponse(
            sku=inventory.sku,
            title=inventory.title,
            cost_points=inventory.cost_points,
            stock=inventory.stock,
            reserved=inventory.reserved,
            vendor=inventory.vendor,
            available_stock=inventory.stock - inventory.reserved,
            created_at=inventory.created_at.isoformat() if inventory.created_at else None,
            updated_at=inventory.updated_at.isoformat() if inventory.updated_at else None
        )

    def get_available_rewards(self) -> List[RewardsInventoryResponse]:
        """사용 가능한 리워드 목록 조회"""
        rewards = self.db.query(RewardsInventory).filter(
            RewardsInventory.stock > RewardsInventory.reserved
        ).order_by(RewardsInventory.cost_points).all()
        
        return [self._to_inventory_schema(reward) for reward in rewards]

    def get_reward_by_sku(self, sku: str) -> Optional[RewardsInventoryResponse]:
        """SKU로 리워드 조회"""
        reward = self.db.query(RewardsInventory).filter(RewardsInventory.sku == sku).first()
        return self._to_inventory_schema(reward)

    def is_reward_available(self, sku: str, quantity: int = 1) -> bool:
        """리워드 재고 확인"""
        reward = self.db.query(RewardsInventory).filter(RewardsInventory.sku == sku).first()
        if not reward:
            return False
        return (reward.stock - reward.reserved) >= quantity

    def reserve_reward(self, sku: str, quantity: int = 1) -> bool:
        """리워드 예약"""
        reward = self.db.query(RewardsInventory).filter(RewardsInventory.sku == sku).first()
        if not reward or (reward.stock - reward.reserved) < quantity:
            return False
        
        reward.reserved += quantity
        reward.updated_at = datetime.utcnow()
        self.db.add(reward)
        self.db.flush()
        return True

    def release_reservation(self, sku: str, quantity: int = 1) -> bool:
        """리워드 예약 해제"""
        reward = self.db.query(RewardsInventory).filter(RewardsInventory.sku == sku).first()
        if not reward or reward.reserved < quantity:
            return False
        
        reward.reserved -= quantity
        reward.updated_at = datetime.utcnow()
        self.db.add(reward)
        self.db.flush()
        return True

    def update_stock(self, sku: str, new_stock: int) -> Optional[RewardsInventoryResponse]:
        """재고 수량 업데이트"""
        reward = self.db.query(RewardsInventory).filter(RewardsInventory.sku == sku).first()
        if not reward:
            return None
        
        reward.stock = new_stock
        reward.updated_at = datetime.utcnow()
        self.db.add(reward)
        self.db.flush()
        self.db.refresh(reward)
        
        return self._to_inventory_schema(reward)

    def create_reward(self, sku: str, title: str, cost_points: int, stock: int, vendor: str) -> RewardsInventoryResponse:
        """새 리워드 생성"""
        reward = RewardsInventory(
            sku=sku,
            title=title,
            cost_points=cost_points,
            stock=stock,
            vendor=vendor,
            reserved=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.db.add(reward)
        self.db.flush()
        self.db.refresh(reward)
        
        return self._to_inventory_schema(reward)


class RewardsRedemptionRepository(BaseRepository[RewardsRedemption, RewardsRedemptionResponse]):
    """리워드 교환 리포지토리"""

    def __init__(self, db: Session):
        super().__init__(RewardsRedemption, RewardsRedemptionResponse, db)

    def _to_redemption_schema(self, redemption: RewardsRedemption) -> RewardsRedemptionResponse:
        """RewardsRedemption을 RewardsRedemptionResponse 스키마로 변환"""
        if not redemption:
            return None
            
        return RewardsRedemptionResponse(
            id=redemption.id,
            user_id=redemption.user_id,
            sku=redemption.sku,
            cost_points=redemption.cost_points,
            status=redemption.status.value,
            vendor_code=redemption.vendor_code,
            created_at=redemption.created_at.isoformat() if redemption.created_at else None,
            updated_at=redemption.updated_at.isoformat() if redemption.updated_at else None
        )

    def create_redemption(self, user_id: int, sku: str, cost_points: int) -> RewardsRedemptionResponse:
        """리워드 교환 요청 생성"""
        from myapi.models.rewards import RedemptionStatusEnum
        
        redemption = RewardsRedemption(
            user_id=user_id,
            sku=sku,
            cost_points=cost_points,
            status=RedemptionStatusEnum.REQUESTED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.db.add(redemption)
        self.db.flush()
        self.db.refresh(redemption)
        
        return self._to_redemption_schema(redemption)

    def update_redemption_status(self, redemption_id: int, status: str, vendor_code: str = None) -> Optional[RewardsRedemptionResponse]:
        """교환 상태 업데이트"""
        from myapi.models.rewards import RedemptionStatusEnum
        
        redemption = self.db.query(RewardsRedemption).filter(
            RewardsRedemption.id == redemption_id
        ).first()
        
        if not redemption:
            return None
        
        redemption.status = RedemptionStatusEnum(status)
        if vendor_code:
            redemption.vendor_code = vendor_code
        redemption.updated_at = datetime.utcnow()
        
        self.db.add(redemption)
        self.db.flush()
        self.db.refresh(redemption)
        
        return self._to_redemption_schema(redemption)

    def get_user_redemptions(self, user_id: int, limit: int = 50, offset: int = 0) -> List[RewardsRedemptionResponse]:
        """사용자 교환 내역 조회"""
        redemptions = self.db.query(RewardsRedemption).filter(
            RewardsRedemption.user_id == user_id
        ).order_by(desc(RewardsRedemption.created_at)).offset(offset).limit(limit).all()
        
        return [self._to_redemption_schema(redemption) for redemption in redemptions]

    def get_redemption_by_id(self, redemption_id: int) -> Optional[RewardsRedemptionResponse]:
        """교환 ID로 조회"""
        redemption = self.db.query(RewardsRedemption).filter(
            RewardsRedemption.id == redemption_id
        ).first()
        
        return self._to_redemption_schema(redemption)

    def get_pending_redemptions(self, limit: int = 100) -> List[RewardsRedemptionResponse]:
        """처리 대기 중인 교환 조회"""
        from myapi.models.rewards import RedemptionStatusEnum
        
        redemptions = self.db.query(RewardsRedemption).filter(
            RewardsRedemption.status.in_([
                RedemptionStatusEnum.REQUESTED,
                RedemptionStatusEnum.RESERVED
            ])
        ).order_by(RewardsRedemption.created_at).limit(limit).all()
        
        return [self._to_redemption_schema(redemption) for redemption in redemptions]

    def get_redemptions_by_status(self, status: str, limit: int = 100) -> List[RewardsRedemptionResponse]:
        """상태별 교환 조회"""
        from myapi.models.rewards import RedemptionStatusEnum
        
        redemptions = self.db.query(RewardsRedemption).filter(
            RewardsRedemption.status == RedemptionStatusEnum(status)
        ).order_by(desc(RewardsRedemption.created_at)).limit(limit).all()
        
        return [self._to_redemption_schema(redemption) for redemption in redemptions]

    def get_redemption_stats(self, sku: str = None) -> dict:
        """교환 통계"""
        from myapi.models.rewards import RedemptionStatusEnum
        
        query = self.db.query(RewardsRedemption)
        if sku:
            query = query.filter(RewardsRedemption.sku == sku)
        
        total = query.count()
        issued = query.filter(RewardsRedemption.status == RedemptionStatusEnum.ISSUED).count()
        failed = query.filter(RewardsRedemption.status == RedemptionStatusEnum.FAILED).count()
        cancelled = query.filter(RewardsRedemption.status == RedemptionStatusEnum.CANCELLED).count()
        pending = query.filter(RewardsRedemption.status.in_([
            RedemptionStatusEnum.REQUESTED, RedemptionStatusEnum.RESERVED
        ])).count()
        
        return {
            "sku": sku,
            "total_redemptions": total,
            "issued": issued,
            "failed": failed,
            "cancelled": cancelled,
            "pending": pending,
            "success_rate": (issued / total) if total > 0 else 0.0
        }