from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from myapi.repositories.rewards_repository import RewardsRepository
from myapi.repositories.points_repository import PointsRepository
from myapi.core.exceptions import (
    ValidationError,
    NotFoundError,
    InsufficientBalanceError,
)
from myapi.schemas.rewards import (
    RewardItem,
    RewardCatalogResponse,
    RewardRedemptionRequest,
    RewardRedemptionResponse,
    RewardRedemptionHistory,
    RewardRedemptionHistoryResponse,
    AdminRewardCreateRequest,
    AdminStockUpdateRequest,
    RewardsInventoryResponse,
)
import logging

logger = logging.getLogger(__name__)


class RewardService:
    """리워드 관련 비즈니스 로직을 담당하는 서비스"""

    def __init__(self, db: Session):
        self.db = db
        self.rewards_repo = RewardsRepository(db)
        self.points_repo = PointsRepository(db)

    def get_reward_catalog(self, available_only: bool = True) -> RewardCatalogResponse:
        """리워드 카탈로그 조회

        Args:
            available_only: True시 재고가 있는 상품만 반환

        Returns:
            RewardCatalogResponse: 리워드 목록과 총 개수
        """
        try:
            catalog = self.rewards_repo.get_reward_catalog(
                available_only=available_only
            )
            logger.info(f"Retrieved reward catalog with {catalog.total_count} items")
            return catalog
        except Exception as e:
            logger.error(f"Failed to get reward catalog: {str(e)}")
            raise ValidationError(f"Failed to retrieve reward catalog: {str(e)}")

    def get_reward_by_sku(self, sku: str) -> Optional[RewardItem]:
        """SKU로 리워드 상품 조회

        Args:
            sku: 상품 SKU

        Returns:
            RewardItem: 리워드 상품 정보
        """
        reward = self.rewards_repo.get_reward_by_sku(sku)
        if not reward:
            raise NotFoundError(f"Reward not found: {sku}")

        logger.info(f"Retrieved reward: {sku}")
        return reward

    def redeem_reward(
        self, user_id: int, request: RewardRedemptionRequest
    ) -> RewardRedemptionResponse:
        """리워드 교환 처리

        Args:
            user_id: 사용자 ID
            request: 교환 요청 데이터

        Returns:
            RewardRedemptionResponse: 교환 처리 결과
        """
        reward = self.get_reward_by_sku(request.sku)

        try:
            if not reward:
                return RewardRedemptionResponse(
                    success=False,
                    redemption_id="",
                    status="FAILED",
                    message="Reward not found",
                    cost_points=0,
                    issued_at=None,
                )

            # 재고 확인
            if not reward.is_available:
                return RewardRedemptionResponse(
                    success=False,
                    redemption_id="",
                    status="FAILED",
                    message="Reward is out of stock",
                    cost_points=reward.cost_points,
                    issued_at=None,
                )

            # 사용자 포인트 잔액 확인
            user_balance = self.points_repo.get_user_balance(user_id)
            if user_balance < reward.cost_points:
                raise InsufficientBalanceError(
                    f"Insufficient points. Required: {reward.cost_points}, Available: {user_balance}"
                )

            # 포인트 차감 (교환 수수료)
            ref_id = f"redemption_{user_id}_{request.sku}_{datetime.now().timestamp()}"
            deduction_result = self.points_repo.deduct_points(
                user_id=user_id,
                points=reward.cost_points,
                reason=f"Reward redemption: {reward.title}",
                ref_id=ref_id,
            )

            if not deduction_result.success:
                return RewardRedemptionResponse(
                    success=False,
                    redemption_id="",
                    status="FAILED",
                    message=deduction_result.message,
                    cost_points=reward.cost_points,
                    issued_at=None,
                )

            # 리워드 교환 처리
            redemption_result = self.rewards_repo.process_redemption(
                user_id=user_id,
                sku=request.sku,
                cost_points=reward.cost_points,
            )

            if not redemption_result.success:
                # 실패시 포인트 환원 시도
                refund_ref_id = f"refund_{ref_id}"
                refund_result = self.points_repo.add_points(
                    user_id=user_id,
                    points=reward.cost_points,
                    reason=f"Refund for failed redemption: {reward.title}",
                    ref_id=refund_ref_id,
                )

                logger.warning(
                    f"Redemption failed, refund result: {refund_result.success}"
                )

            logger.info(
                f"Reward redemption processed for user {user_id}, sku {request.sku}"
            )
            return redemption_result

        except InsufficientBalanceError as e:
            logger.warning(f"Insufficient balance for user {user_id}: {str(e)}")
            return RewardRedemptionResponse(
                success=False,
                redemption_id="",
                status="FAILED",
                message=str(e),
                cost_points=reward.cost_points if reward else 0,
                issued_at=None,
            )
        except Exception as e:
            logger.error(f"Failed to redeem reward for user {user_id}: {str(e)}")
            return RewardRedemptionResponse(
                success=False,
                redemption_id="",
                status="FAILED",
                message=f"Redemption failed: {str(e)}",
                cost_points=0,
                issued_at=None,
            )

    def get_user_redemption_history(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> RewardRedemptionHistoryResponse:
        """사용자 교환 내역 조회

        Args:
            user_id: 사용자 ID
            limit: 페이지 크기 (최대 100)
            offset: 오프셋

        Returns:
            RewardRedemptionHistoryResponse: 교환 내역 목록
        """
        if limit > 100:
            limit = 100

        try:
            history = self.rewards_repo.get_user_redemption_history(
                user_id=user_id, limit=limit, offset=offset
            )
            logger.info(
                f"Retrieved redemption history for user {user_id}: {history.total_count} entries"
            )
            return history
        except Exception as e:
            logger.error(
                f"Failed to get redemption history for user {user_id}: {str(e)}"
            )
            raise ValidationError(f"Failed to retrieve redemption history: {str(e)}")

    def create_reward_item(
        self, admin_request: AdminRewardCreateRequest
    ) -> RewardsInventoryResponse:
        """새 리워드 아이템 생성 (관리자용)

        Args:
            admin_request: 관리자 생성 요청

        Returns:
            RewardsInventoryResponse: 생성된 리워드 정보
        """
        try:
            # SKU 중복 확인
            existing_reward = self.rewards_repo.get_reward_by_sku(admin_request.sku)
            if existing_reward:
                raise ValidationError(
                    f"Reward with SKU '{admin_request.sku}' already exists"
                )

            reward = self.rewards_repo.create_reward_item(
                sku=admin_request.sku,
                title=admin_request.title,
                cost_points=admin_request.cost_points,
                stock=admin_request.stock,
                vendor=admin_request.vendor,
            )

            logger.info(f"Created new reward item: {admin_request.sku}")
            return reward
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Failed to create reward item: {str(e)}")
            raise ValidationError(f"Failed to create reward item: {str(e)}")

    def update_reward_stock(
        self, admin_request: AdminStockUpdateRequest
    ) -> Optional[RewardsInventoryResponse]:
        """리워드 재고 업데이트 (관리자용)

        Args:
            admin_request: 관리자 재고 업데이트 요청

        Returns:
            RewardsInventoryResponse: 업데이트된 리워드 정보
        """
        try:
            updated_reward = self.rewards_repo.update_stock(
                sku=admin_request.sku, new_stock=admin_request.new_stock
            )

            if not updated_reward:
                raise NotFoundError(f"Reward not found: {admin_request.sku}")

            logger.info(
                f"Updated stock for reward {admin_request.sku}: {admin_request.new_stock}"
            )
            return updated_reward
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to update reward stock: {str(e)}")
            raise ValidationError(f"Failed to update reward stock: {str(e)}")

    def delete_reward_item(self, sku: str) -> bool:
        """리워드 아이템 삭제 (관리자용)

        Args:
            sku: 삭제할 리워드 SKU

        Returns:
            bool: 삭제 성공 여부
        """
        try:
            deleted = self.rewards_repo.delete_reward_item(sku)

            if not deleted:
                raise ValidationError(
                    f"Cannot delete reward '{sku}': Active redemptions exist or item not found"
                )

            logger.info(f"Deleted reward item: {sku}")
            return True
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete reward item: {str(e)}")
            raise ValidationError(f"Failed to delete reward item: {str(e)}")

    def get_inventory_summary(self) -> dict:
        """재고 요약 조회 (관리자용)

        Returns:
            dict: 재고 요약 정보
        """
        try:
            summary = self.rewards_repo.get_inventory_summary()
            logger.info("Retrieved inventory summary")
            return summary
        except Exception as e:
            logger.error(f"Failed to get inventory summary: {str(e)}")
            raise ValidationError(f"Failed to retrieve inventory summary: {str(e)}")

    def get_redemption_stats(self) -> dict:
        """교환 통계 조회 (관리자용)

        Returns:
            dict: 교환 통계 정보
        """
        try:
            stats = self.rewards_repo.get_redemption_stats()
            logger.info("Retrieved redemption stats")
            return stats
        except Exception as e:
            logger.error(f"Failed to get redemption stats: {str(e)}")
            raise ValidationError(f"Failed to retrieve redemption stats: {str(e)}")

    def get_pending_redemptions(self, limit: int = 100) -> List:
        """대기 중인 교환 요청 조회 (관리자용)

        Args:
            limit: 조회할 최대 건수

        Returns:
            List: 대기 중인 교환 요청 목록
        """
        try:
            pending_redemptions = self.rewards_repo.get_pending_redemptions(limit=limit)
            logger.info(f"Retrieved {len(pending_redemptions)} pending redemptions")
            return pending_redemptions
        except Exception as e:
            logger.error(f"Failed to get pending redemptions: {str(e)}")
            raise ValidationError(f"Failed to retrieve pending redemptions: {str(e)}")

    def process_redemption_manually(
        self, redemption_id: int, new_status: str, vendor_code: str = ""
    ) -> bool:
        """교환 요청 수동 처리 (관리자용)

        Args:
            redemption_id: 교환 요청 ID
            new_status: 새로운 상태
            vendor_code: 벤더 코드 (발급완료시 필요)

        Returns:
            bool: 처리 성공 여부
        """
        try:
            from myapi.models.rewards import RedemptionStatusEnum

            # 상태 문자열을 enum으로 변환
            status_mapping = {
                "ISSUED": RedemptionStatusEnum.ISSUED,
                "CANCELLED": RedemptionStatusEnum.CANCELLED,
                "FAILED": RedemptionStatusEnum.FAILED,
                "RESERVED": RedemptionStatusEnum.RESERVED,
            }

            if new_status not in status_mapping:
                raise ValidationError(f"Invalid status: {new_status}")

            status_enum = status_mapping[new_status]

            result = self.rewards_repo.update_redemption_status(
                redemption_id=redemption_id,
                new_status=status_enum,
                vendor_code=vendor_code,
            )

            if not result:
                raise NotFoundError(f"Redemption not found: {redemption_id}")

            logger.info(
                f"Manually processed redemption {redemption_id} to status {new_status}"
            )
            return True
        except (ValidationError, NotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to process redemption manually: {str(e)}")
            raise ValidationError(f"Failed to process redemption: {str(e)}")
