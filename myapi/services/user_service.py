from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from myapi.repositories.user_repository import UserRepository
from myapi.core.exceptions import ValidationError, NotFoundError
from myapi.services.point_service import PointService
from myapi.config import Settings
from myapi.schemas.user import (
    User as UserSchema,
    UserProfile,
    UserStats,
    UserUpdate,
)
from myapi.schemas.points import PointsBalanceResponse, PointsLedgerResponse
import logging

logger = logging.getLogger(__name__)


class UserService:
    """사용자 관련 비즈니스 로직을 담당하는 서비스"""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.user_repo = UserRepository(db)
        self.point_service = PointService(db)
        self.settings = settings

    def get_user_by_id(self, user_id: int) -> Optional[UserSchema]:
        """사용자 ID로 조회"""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")
        return user

    def get_user_by_email(self, email: str) -> Optional[UserSchema]:
        """이메일로 사용자 조회"""
        return self.user_repo.get_by_email(email)

    def get_user_profile(self, user_id: int) -> Optional[UserProfile]:
        """사용자 프로필 조회"""
        profile = self.user_repo.get_user_profile(user_id)
        if not profile:
            raise NotFoundError(f"User profile not found: {user_id}")
        return profile

    def update_user_profile(
        self, user_id: int, update_data: UserUpdate
    ) -> Optional[UserSchema]:
        """사용자 프로필 업데이트"""
        # 기존 사용자 확인
        existing_user = self.user_repo.get_by_id(user_id)
        if not existing_user:
            raise NotFoundError(f"User not found: {user_id}")

        # 업데이트할 필드만 추출
        update_fields = {}
        if update_data.nickname is not None:
            # 닉네임 중복 확인 (본인 제외)
            if self._is_nickname_taken(update_data.nickname, user_id):
                raise ValidationError("Nickname already taken")
            update_fields["nickname"] = update_data.nickname

        if update_data.email is not None:
            # 이메일 중복 확인 (본인 제외)
            if self._is_email_taken(update_data.email, user_id):
                raise ValidationError("Email already taken")
            update_fields["email"] = update_data.email

        # 업데이트 수행
        updated_user = self.user_repo.update(user_id, **update_fields)
        if not updated_user:
            raise ValidationError("Failed to update user profile")

        return updated_user

    def deactivate_user(self, user_id: int) -> Optional[UserSchema]:
        """사용자 계정 비활성화"""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")

        if not user.is_active:
            raise ValidationError("User is already deactivated")

        return self.user_repo.deactivate_user(user_id)

    def activate_user(self, user_id: int) -> Optional[UserSchema]:
        """사용자 계정 활성화"""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")

        if user.is_active:
            raise ValidationError("User is already active")

        return self.user_repo.activate_user(user_id)

    def get_active_users(
        self, limit: int = 50, offset: int = 0
    ) -> List[UserSchema]:
        """활성 사용자 목록 조회"""
        if limit > 100:  # 최대 제한
            limit = 100
        return self.user_repo.get_active_users(limit=limit, offset=offset)

    def get_oauth_users(self, provider: str = "") -> List[UserSchema]:
        """OAuth 사용자 목록 조회"""
        return self.user_repo.get_oauth_users(auth_provider=provider)

    def search_users_by_nickname(
        self, nickname_pattern: str, limit: int = 20
    ) -> List[UserSchema]:
        """닉네임으로 사용자 검색"""
        if not nickname_pattern.strip():
            raise ValidationError("Search pattern cannot be empty")
        
        if limit > 50:  # 최대 제한
            limit = 50
            
        return self.user_repo.search_users_by_nickname(
            nickname_pattern=nickname_pattern.strip(), limit=limit
        )

    def get_user_stats(self) -> UserStats:
        """전체 사용자 통계 조회"""
        return self.user_repo.get_user_stats()

    def validate_email_availability(self, email: str, exclude_user_id: Optional[int] = None) -> bool:
        """이메일 사용 가능 여부 확인"""
        return not self._is_email_taken(email, exclude_user_id)

    def validate_nickname_availability(self, nickname: str, exclude_user_id: Optional[int] = None) -> bool:
        """닉네임 사용 가능 여부 확인"""
        return not self._is_nickname_taken(nickname, exclude_user_id)

    def update_last_login(self, user_id: int) -> Optional[UserSchema]:
        """마지막 로그인 시간 업데이트"""
        return self.user_repo.update_last_login(user_id)

    def check_user_exists(self, user_id: int) -> bool:
        """사용자 존재 여부 확인"""
        return self.user_repo.exists(filters={"id": user_id})

    def get_user_by_provider(self, provider: str, provider_id: str) -> Optional[UserSchema]:
        """OAuth 프로바이더 정보로 사용자 조회"""
        return self.user_repo.get_by_provider_info(provider, provider_id)

    # 포인트 관련 기능들
    def get_user_points_balance(self, user_id: int) -> PointsBalanceResponse:
        """사용자 포인트 잔액 조회"""
        # 사용자 존재 확인
        if not self.check_user_exists(user_id):
            raise NotFoundError(f"User not found: {user_id}")
        
        return self.point_service.get_user_balance(user_id)

    def get_user_points_ledger(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> PointsLedgerResponse:
        """사용자 포인트 거래 내역 조회"""
        # 사용자 존재 확인
        if not self.check_user_exists(user_id):
            raise NotFoundError(f"User not found: {user_id}")
        
        if limit > 100:
            limit = 100
            
        return self.point_service.get_user_ledger(user_id, limit=limit, offset=offset)

    def can_user_afford(self, user_id: int, amount: int) -> bool:
        """사용자가 특정 포인트를 지불할 수 있는지 확인"""
        try:
            return self.point_service.can_afford(user_id, amount)
        except Exception:
            return False

    def get_user_profile_with_points(self, user_id: int) -> dict:
        """포인트 정보를 포함한 사용자 프로필 조회"""
        profile = self.get_user_profile(user_id)
        balance = self.get_user_points_balance(user_id)
        
        return {
            "user_profile": profile,
            "points_balance": balance.balance,
            "last_updated": datetime.now().isoformat()
        }

    def award_signup_bonus(self, user_id: int) -> bool:
        """신규 가입 보너스 포인트 지급"""
        try:
            from myapi.schemas.points import PointsTransactionRequest
            
            bonus_request = PointsTransactionRequest(
                amount=self.settings.SIGNUP_BONUS_POINTS,
                reason="Welcome bonus for new user registration",
                ref_id=f"signup_bonus_{user_id}_{datetime.now().strftime('%Y%m%d')}"
            )
            
            result = self.point_service.add_points(user_id=user_id, request=bonus_request)
            
            if result.success:
                logger.info(f"✅ Awarded signup bonus to user {user_id}: {self.settings.SIGNUP_BONUS_POINTS} points")
                return True
            else:
                logger.warning(f"❌ Failed to award signup bonus to user {user_id}: {result.message}")
                return False
        except Exception as e:
            logger.error(f"❌ Error awarding signup bonus to user {user_id}: {str(e)}")
            return False

    def get_user_financial_summary(self, user_id: int) -> dict:
        """사용자의 재정 요약 정보"""
        if not self.check_user_exists(user_id):
            raise NotFoundError(f"User not found: {user_id}")
        
        from datetime import date
        
        balance = self.get_user_points_balance(user_id)
        today = date.today()
        
        # 오늘 획득한 포인트
        points_earned_today = self.point_service.get_user_points_earned_today(user_id, today)
        
        return {
            "user_id": user_id,
            "current_balance": balance.balance,
            "points_earned_today": points_earned_today,
            "can_make_predictions": balance.balance >= 10,  # 예측 수수료 10포인트
            "summary_date": today.isoformat()
        }

    def _is_email_taken(self, email: str, exclude_user_id: Optional[int] = None) -> bool:
        """이메일 중복 확인 (특정 사용자 제외)"""
        existing_user = self.user_repo.get_by_email(email)
        if not existing_user:
            return False
        
        # 본인인 경우는 중복이 아님
        if exclude_user_id and existing_user.id == exclude_user_id:
            return False
            
        return True

    def _is_nickname_taken(self, nickname: str, exclude_user_id: Optional[int] = None) -> bool:
        """닉네임 중복 확인 (특정 사용자 제외)"""
        existing_users = self.user_repo.find_all(filters={"nickname": nickname})
        
        if not existing_users:
            return False
            
        # 본인인 경우는 중복이 아님
        if exclude_user_id:
            existing_users = [u for u in existing_users if u.id != exclude_user_id]
            
        return len(existing_users) > 0