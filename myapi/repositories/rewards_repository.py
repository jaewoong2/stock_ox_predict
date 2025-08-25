from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, and_, func
from sqlalchemy.exc import IntegrityError

from myapi.models.rewards import (
    RewardsInventory as RewardsInventoryModel,
    RewardsRedemption as RewardsRedemptionModel,
    RedemptionStatusEnum,
)
from myapi.schemas.rewards import (
    RewardItem,
    RewardCatalogResponse,
    RewardRedemptionResponse,
    RewardRedemptionHistory,
    RewardRedemptionHistoryResponse,
    RewardsInventoryResponse,
    RewardsRedemptionResponse as RedemptionDetailResponse,
)
from myapi.repositories.base import BaseRepository


class RewardsRepository(
    BaseRepository[RewardsInventoryModel, RewardsInventoryResponse]
):
    """리워드 리포지토리 - 인벤토리 및 교환 관리"""

    def __init__(self, db: Session):
        super().__init__(RewardsInventoryModel, RewardsInventoryResponse, db)

    def _to_reward_item(self, model_instance: RewardsInventoryModel) -> RewardItem:
        """RewardsInventory 모델을 RewardItem 스키마로 변환"""
        if model_instance is None:
            return None

        # SQLAlchemy 모델의 속성들을 안전하게 추출
        stock = getattr(model_instance, "stock", 0)
        reserved = getattr(model_instance, "reserved", 0)
        available_stock = stock - reserved

        data = {
            "sku": getattr(model_instance, "sku", ""),
            "title": getattr(model_instance, "title", ""),
            "cost_points": getattr(model_instance, "cost_points", 0),
            "stock": stock,
            "vendor": getattr(model_instance, "vendor", ""),
            "is_available": available_stock > 0,
            "description": None,  # 모델에 description이 없어서 None
            "image_url": None,  # 모델에 image_url이 없어서 None
        }
        return RewardItem(**data)

    def _to_inventory_response(
        self, model_instance: RewardsInventoryModel
    ) -> RewardsInventoryResponse:
        """RewardsInventory 모델을 RewardsInventoryResponse 스키마로 변환"""
        if model_instance is None:
            return None

        # SQLAlchemy 모델의 속성들을 안전하게 추출
        stock = getattr(model_instance, "stock", 0)
        reserved = getattr(model_instance, "reserved", 0)
        available_stock = stock - reserved

        data = {
            "sku": getattr(model_instance, "sku", ""),
            "title": getattr(model_instance, "title", ""),
            "cost_points": getattr(model_instance, "cost_points", 0),
            "stock": stock,
            "reserved": reserved,
            "vendor": getattr(model_instance, "vendor", ""),
            "available_stock": available_stock,
            "created_at": (
                model_instance.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if model_instance.created_at
                else None
            ),
            "updated_at": (
                model_instance.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if model_instance.updated_at
                else None
            ),
        }
        return RewardsInventoryResponse(**data)

    def _to_redemption_response(
        self, model_instance: RewardsRedemptionModel
    ) -> RedemptionDetailResponse:
        """RewardsRedemption 모델을 RewardsRedemptionResponse 스키마로 변환"""
        if model_instance is None:
            return None

        # SQLAlchemy 모델의 속성들을 안전하게 추출
        data = {
            "id": getattr(model_instance, "id", 0),
            "user_id": getattr(model_instance, "user_id", 0),
            "sku": getattr(model_instance, "sku", ""),
            "cost_points": getattr(model_instance, "cost_points", 0),
            "status": model_instance.status.value,
            "vendor_code": getattr(model_instance, "vendor_code", None),
            "created_at": (
                model_instance.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if model_instance.created_at
                else None
            ),
            "updated_at": (
                model_instance.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if model_instance.updated_at
                else None
            ),
        }
        return RedemptionDetailResponse(**data)

    def get_reward_catalog(self, available_only: bool = True) -> RewardCatalogResponse:
        """리워드 카탈로그 조회"""
        query = self.db.query(RewardsInventoryModel)

        if available_only:
            query = query.filter(
                RewardsInventoryModel.stock > RewardsInventoryModel.reserved
            )

        inventory_items = query.order_by(asc(RewardsInventoryModel.cost_points)).all()
        reward_items = [self._to_reward_item(item) for item in inventory_items]

        return RewardCatalogResponse(
            rewards=reward_items, total_count=len(reward_items)
        )

    def get_reward_by_sku(self, sku: str) -> Optional[RewardItem]:
        """SKU로 리워드 조회"""
        model_instance = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .first()
        )

        return self._to_reward_item(model_instance)

    def create_reward_item(
        self, sku: str, title: str, cost_points: int, stock: int, vendor: str
    ) -> RewardsInventoryResponse:
        """새 리워드 아이템 생성 (관리자용)"""
        try:
            # BaseRepository의 create 메서드 사용
            model_instance = RewardsInventoryModel(
                sku=sku,
                title=title,
                cost_points=cost_points,
                stock=stock,
                reserved=0,
                vendor=vendor,
            )

            self.db.add(model_instance)
            self.db.flush()
            self.db.refresh(model_instance)

            return self._to_inventory_response(model_instance)

        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"SKU '{sku}' already exists") from e

    def update_stock(
        self, sku: str, new_stock: int
    ) -> Optional[RewardsInventoryResponse]:
        """재고 업데이트 (관리자용)"""
        # 먼저 해당 sku의 아이템을 찾아서 업데이트
        model_instance = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .first()
        )

        if not model_instance:
            return None

        # 직접 값 할당 대신 update 사용
        updated_count = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .update({"stock": new_stock}, synchronize_session=False)
        )

        if updated_count == 0:
            return None

        self.db.flush()
        # 업데이트된 모델 재조회
        updated_model = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .first()
        )

        return self._to_inventory_response(updated_model)

    def reserve_item(self, sku: str, quantity: int = 1) -> bool:
        """아이템 예약 (교환 처리 시 호출)"""
        model_instance = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .first()
        )

        if not model_instance:
            return False

        available = getattr(model_instance, "stock", 0) - getattr(
            model_instance, "reserved", 0
        )
        if available < quantity:
            return False

        # SQL UPDATE 사용
        updated_count = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .update(
                {"reserved": RewardsInventoryModel.reserved + quantity},
                synchronize_session=False,
            )
        )

        self.db.flush()
        return updated_count > 0

    def release_reservation(self, sku: str, quantity: int = 1) -> bool:
        """예약 해제 (교환 취소/실패 시 호출)"""
        # SQL UPDATE를 사용하여 예약 수량 감소 (음수 방지)
        from sqlalchemy import case

        updated_count = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .update(
                {
                    "reserved": case(
                        (
                            RewardsInventoryModel.reserved >= quantity,
                            RewardsInventoryModel.reserved - quantity,
                        ),
                        else_=0,
                    )
                },
                synchronize_session=False,
            )
        )

        self.db.flush()
        return updated_count > 0

    def consume_reserved_item(self, sku: str, quantity: int = 1) -> bool:
        """예약된 아이템 소비 (교환 완료 시 호출)"""
        model_instance = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .first()
        )

        if not model_instance:
            return False

        reserved_amount = getattr(model_instance, "reserved", 0)
        if reserved_amount < quantity:
            return False

        # SQL UPDATE 사용
        updated_count = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .update(
                {
                    "stock": RewardsInventoryModel.stock - quantity,
                    "reserved": RewardsInventoryModel.reserved - quantity,
                },
                synchronize_session=False,
            )
        )

        self.db.flush()
        return updated_count > 0

    def is_available_for_redemption(self, sku: str, quantity: int = 1) -> bool:
        """교환 가능 여부 확인"""
        model_instance = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .first()
        )

        if not model_instance:
            return False

        available = getattr(model_instance, "stock", 0) - getattr(
            model_instance, "reserved", 0
        )
        return available >= quantity

    def create_redemption(
        self, user_id: int, sku: str, cost_points: int
    ) -> RedemptionDetailResponse:
        """교환 요청 생성"""
        redemption = RewardsRedemptionModel(
            user_id=user_id,
            sku=sku,
            cost_points=cost_points,
            status=RedemptionStatusEnum.REQUESTED,
        )

        self.db.add(redemption)
        self.db.flush()
        self.db.refresh(redemption)

        return self._to_redemption_response(redemption)

    def process_redemption(
        self, user_id: int, sku: str, cost_points: int
    ) -> RewardRedemptionResponse:
        """리워드 교환 처리"""
        # 재고 확인 및 예약
        if not self.is_available_for_redemption(sku, 1):
            return RewardRedemptionResponse(
                issued_at=None,
                success=False,
                redemption_id="",
                status="FAILED",
                message="Item not available",
                cost_points=0,
            )

        try:
            # 재고 예약
            if not self.reserve_item(sku, 1):
                return RewardRedemptionResponse(
                    issued_at=None,
                    success=False,
                    redemption_id="",
                    status="FAILED",
                    message="Failed to reserve item",
                    cost_points=0,
                )

            # 교환 기록 생성
            redemption = self.create_redemption(user_id, sku, cost_points)

            # 예약 상태로 업데이트
            self.update_redemption_status(redemption.id, RedemptionStatusEnum.RESERVED)
            today = func.now().strftime("%Y-%m-%d %H:%M:%S")

            return RewardRedemptionResponse(
                issued_at=today,
                success=True,
                redemption_id=str(redemption.id),
                status="RESERVED",
                message="Redemption request processed successfully",
                cost_points=cost_points,
            )

        except Exception as e:
            # 실패 시 예약 해제
            self.release_reservation(sku, 1)
            return RewardRedemptionResponse(
                success=False,
                issued_at=None,
                redemption_id="",
                status="FAILED",
                message=f"Redemption failed: {str(e)}",
                cost_points=0,
            )

    def update_redemption_status(
        self,
        redemption_id: int,
        new_status: RedemptionStatusEnum,
        vendor_code: str = "",
    ) -> Optional[RedemptionDetailResponse]:
        """교환 상태 업데이트"""
        redemption = (
            self.db.query(RewardsRedemptionModel)
            .filter(RewardsRedemptionModel.id == redemption_id)
            .first()
        )

        if not redemption:
            return None

        old_status = getattr(redemption, "status", None)
        sku = getattr(redemption, "sku", "")

        # SQL UPDATE 사용
        if vendor_code:
            updated_count = (
                self.db.query(RewardsRedemptionModel)
                .filter(RewardsRedemptionModel.id == redemption_id)
                .update(
                    {
                        RewardsRedemptionModel.status: new_status,
                        RewardsRedemptionModel.vendor_code: vendor_code,
                    },
                    synchronize_session=False,
                )
            )
        else:
            updated_count = (
                self.db.query(RewardsRedemptionModel)
                .filter(RewardsRedemptionModel.id == redemption_id)
                .update(
                    {RewardsRedemptionModel.status: new_status},
                    synchronize_session=False,
                )
            )

        if updated_count == 0:
            return None

        self.db.flush()

        # 상태 변경에 따른 재고 처리
        if (
            new_status == RedemptionStatusEnum.ISSUED
            and old_status == RedemptionStatusEnum.RESERVED
        ):
            # 발급 완료 시 예약된 재고 소비
            self.consume_reserved_item(sku, 1)
        elif (
            new_status in [RedemptionStatusEnum.CANCELLED, RedemptionStatusEnum.FAILED]
            and old_status == RedemptionStatusEnum.RESERVED
        ):
            # 취소/실패 시 예약 해제
            self.release_reservation(sku, 1)

        # 업데이트된 redemption 재조회
        updated_redemption = (
            self.db.query(RewardsRedemptionModel)
            .filter(RewardsRedemptionModel.id == redemption_id)
            .first()
        )

        return self._to_redemption_response(updated_redemption)

    def get_user_redemption_history(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> RewardRedemptionHistoryResponse:
        """사용자 교환 내역 조회"""
        # 총 교환 건수
        total_count = (
            self.db.query(RewardsRedemptionModel)
            .filter(RewardsRedemptionModel.user_id == user_id)
            .count()
        )

        # 교환 내역 조회 (최신순)
        redemptions = (
            self.db.query(RewardsRedemptionModel)
            .join(
                RewardsInventoryModel,
                RewardsRedemptionModel.sku == RewardsInventoryModel.sku,
            )
            .filter(RewardsRedemptionModel.user_id == user_id)
            .order_by(desc(RewardsRedemptionModel.id))
            .limit(limit)
            .offset(offset)
            .all()
        )

        # 교환 내역 변환
        history = []
        for redemption in redemptions:
            inventory = (
                self.db.query(RewardsInventoryModel)
                .filter(RewardsInventoryModel.sku == redemption.sku)
                .first()
            )

            # SQLAlchemy 모델의 속성들을 안전하게 추출
            redemption_id = getattr(redemption, "id", 0)
            sku = getattr(redemption, "sku", "")
            cost_points = getattr(redemption, "cost_points", 0)
            status = str(
                redemption.status
                if hasattr(getattr(redemption, "status", ""), "value")
                else str(getattr(redemption, "status", ""))
            )
            created_at = getattr(redemption, "created_at", None)
            updated_at = getattr(redemption, "updated_at", None)

            history_item = RewardRedemptionHistory(
                redemption_id=str(redemption_id),
                sku=sku,
                title=(
                    getattr(inventory, "title", "Unknown") if inventory else "Unknown"
                ),
                cost_points=cost_points,
                status=status,
                requested_at=(
                    created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else ""
                ),
                issued_at=(
                    updated_at.strftime("%Y-%m-%d %H:%M:%S")
                    if str(redemption.status) == RedemptionStatusEnum.ISSUED
                    and updated_at
                    else None
                ),
                vendor=getattr(inventory, "vendor", None) if inventory else None,
            )
            history.append(history_item)

        has_next = offset + limit < total_count

        return RewardRedemptionHistoryResponse(
            history=history, total_count=total_count, has_next=has_next
        )

    def get_redemption_by_id(
        self, redemption_id: int
    ) -> Optional[RedemptionDetailResponse]:
        """교환 ID로 교환 정보 조회"""
        redemption = (
            self.db.query(RewardsRedemptionModel)
            .filter(RewardsRedemptionModel.id == redemption_id)
            .first()
        )

        return self._to_redemption_response(redemption)

    def get_pending_redemptions(
        self, limit: int = 100
    ) -> List[RedemptionDetailResponse]:
        """대기 중인 교환 요청 조회 (관리자용)"""
        redemptions = (
            self.db.query(RewardsRedemptionModel)
            .filter(
                RewardsRedemptionModel.status.in_(
                    [RedemptionStatusEnum.REQUESTED, RedemptionStatusEnum.RESERVED]
                )
            )
            .order_by(asc(RewardsRedemptionModel.id))
            .limit(limit)
            .all()
        )

        return [self._to_redemption_response(r) for r in redemptions]

    def get_inventory_summary(self) -> dict:
        """재고 요약 조회"""
        total_items = self.db.query(func.count(RewardsInventoryModel.sku)).scalar()
        total_stock = self.db.query(func.sum(RewardsInventoryModel.stock)).scalar()
        total_reserved = self.db.query(
            func.sum(RewardsInventoryModel.reserved)
        ).scalar()
        available_stock = (total_stock or 0) - (total_reserved or 0)

        return {
            "total_items": total_items or 0,
            "total_stock": total_stock or 0,
            "total_reserved": total_reserved or 0,
            "available_stock": available_stock,
        }

    def get_redemption_stats(self) -> dict:
        """교환 통계 조회"""
        stats = self.db.query(
            func.count(RewardsRedemptionModel.id).label("total"),
            func.sum(
                func.case(
                    [(RewardsRedemptionModel.status == RedemptionStatusEnum.ISSUED, 1)],
                    else_=0,
                )
            ).label("issued"),
            func.sum(
                func.case(
                    [
                        (
                            RewardsRedemptionModel.status
                            == RedemptionStatusEnum.REQUESTED,
                            1,
                        )
                    ],
                    else_=0,
                )
            ).label("pending"),
            func.sum(
                func.case(
                    [(RewardsRedemptionModel.status == RedemptionStatusEnum.FAILED, 1)],
                    else_=0,
                )
            ).label("failed"),
            func.sum(RewardsRedemptionModel.cost_points).label("total_points_spent"),
        ).first()

        if not stats:
            return {
                "total_redemptions": 0,
                "issued_redemptions": 0,
                "pending_redemptions": 0,
                "failed_redemptions": 0,
                "total_points_spent": 0,
            }

        return {
            "total_redemptions": getattr(stats, "total", 0) or 0,
            "issued_redemptions": getattr(stats, "issued", 0) or 0,
            "pending_redemptions": getattr(stats, "pending", 0) or 0,
            "failed_redemptions": getattr(stats, "failed", 0) or 0,
            "total_points_spent": getattr(stats, "total_points_spent", 0) or 0,
        }

    def delete_reward_item(self, sku: str) -> bool:
        """리워드 아이템 삭제 (관리자용)"""
        # 진행 중인 교환이 있는지 확인
        active_redemptions = (
            self.db.query(RewardsRedemptionModel)
            .filter(
                and_(
                    RewardsRedemptionModel.sku == sku,
                    RewardsRedemptionModel.status.in_(
                        [RedemptionStatusEnum.REQUESTED, RedemptionStatusEnum.RESERVED]
                    ),
                )
            )
            .first()
        )

        if active_redemptions:
            return False  # 활성 교환이 있어 삭제 불가

        deleted_count = (
            self.db.query(RewardsInventoryModel)
            .filter(RewardsInventoryModel.sku == sku)
            .delete()
        )

        self.db.flush()
        return deleted_count > 0
