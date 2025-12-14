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
    InventorySummary,
    RedemptionStats,
    AdminRewardsStatsResponse,
    RewardsSummaryResponse,
    RewardActivationResponse,
)
from myapi.models.rewards import RedemptionStatusEnum
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

    def get_inventory_summary(self) -> InventorySummary:
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

    def get_redemption_stats(self) -> RedemptionStats:
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

    # ==================== 마이페이지용 메서드 ====================

    def get_user_rewards_summary(self, user_id: int) -> RewardsSummaryResponse:
        """사용자 리워드 전체 요약

        Args:
            user_id: 사용자 ID

        Returns:
            RewardsSummaryResponse: 리워드 요약 정보
        """
        try:
            available = self.rewards_repo.get_available_rewards_for_user(user_id)
            used = self.rewards_repo.get_used_rewards_for_user(user_id, limit=50)

            # pending: REQUESTED, RESERVED 상태 (기존 메서드 활용)
            all_history_response = self.rewards_repo.get_user_redemption_history(user_id, limit=100)
            pending = [
                h for h in all_history_response.history
                if h.status in ["REQUESTED", "RESERVED"]
            ]

            total_points = sum(r.cost_points for r in used)

            logger.info(f"Retrieved rewards summary for user {user_id}")
            return RewardsSummaryResponse(
                available_rewards=available,
                used_rewards=used,
                pending_rewards=pending,
                total_points_spent=total_points
            )
        except Exception as e:
            logger.error(f"Failed to get rewards summary for user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to retrieve rewards summary: {str(e)}")

    async def activate_reward(self, user_id: int, redemption_id: int) -> RewardActivationResponse:
        """리워드 사용 처리 (SKU 기반 액션 판단)

        Args:
            user_id: 사용자 ID
            redemption_id: 교환 ID

        Returns:
            RewardActivationResponse: 활성화 결과
        """
        try:
            # 1. 소유권 및 상태 확인
            result = self.rewards_repo.get_redemption_with_inventory(redemption_id, user_id)
            if not result:
                raise NotFoundError("리워드를 찾을 수 없습니다")

            redemption, inventory = result

            if redemption.status != "AVAILABLE":
                raise ValidationError(f"사용할 수 없는 상태입니다: {redemption.status}")

            # 2. SKU 기반 액션 판단 및 실행
            reward_type = getattr(inventory, "reward_type", "SLOT_REFRESH")
            activation_result = {}

            if reward_type == "SLOT_REFRESH":
                # 슬롯 리프레시 실행
                # TODO: CooldownService 연동 구현 필요
                activation_result = {
                    "slots_added": 1,
                    "new_slot_count": 0,  # 실제 쿨다운 서비스 연동 시 업데이트
                    "message": "예측 슬롯이 1개 추가되었습니다"
                }
                logger.info(f"Activated SLOT_REFRESH reward for user {user_id}")

            elif reward_type == "GIFT_VOUCHER":
                # 기프티콘 정보 반환 (이미지 URL 등)
                activation_data = getattr(inventory, "activation_data", {}) or {}
                activation_result = {
                    "voucher_code": activation_data.get("vendor_code"),
                    "image_url": getattr(inventory, "image_url", None),
                    "expires_at": None,
                    "message": "기프티콘이 발급되었습니다"
                }
                logger.info(f"Activated GIFT_VOUCHER reward for user {user_id}")

            elif reward_type == "POINTS_BONUS":
                # 보너스 포인트 지급
                activation_data = getattr(inventory, "activation_data", {}) or {}
                bonus_points = activation_data.get("bonus_amount", 100)
                ref_id = f"reward_bonus_{redemption_id}"

                self.points_repo.add_points(
                    user_id=user_id,
                    points=bonus_points,
                    reason="reward_bonus",
                    ref_id=ref_id
                )
                activation_result = {
                    "points_added": bonus_points,
                    "message": f"{bonus_points} 포인트가 지급되었습니다"
                }
                logger.info(f"Activated POINTS_BONUS reward for user {user_id}")

            else:
                raise ValidationError(f"지원하지 않는 리워드 타입: {reward_type}")

            # 3. 상태 변경: AVAILABLE → USED
            self.rewards_repo.mark_as_used(redemption_id)

            return RewardActivationResponse(
                success=True,
                message=activation_result.get("message", "리워드가 사용되었습니다"),
                redemption_id=redemption_id,
                reward_type=reward_type,
                activation_result=activation_result
            )

        except (NotFoundError, ValidationError):
            raise
        except Exception as e:
            logger.error(f"리워드 활성화 실패: {e}")
            raise ValidationError(f"리워드 사용 중 오류가 발생했습니다: {str(e)}")
