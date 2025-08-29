from typing import Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from myapi.config import settings, Settings
from myapi.core.security import create_access_token
from myapi.core.exceptions import AuthenticationError, OAuthError
from myapi.repositories.user_repository import UserRepository
from myapi.services.point_service import PointService
from myapi.providers.oauth.google import GoogleOAuthProvider
from myapi.providers.oauth.kakao import KakaoOAuthProvider
from myapi.schemas.oauth import OAuthTokenResponse, OAuthUserInfo
from myapi.schemas.auth import (
    Token,
    TokenData,
    OAuthCallbackRequest,
    OAuthLoginResponse,
)
from myapi.schemas.user import User as UserSchema
import logging

logger = logging.getLogger(__name__)


class AuthService:
    """인증 관련 비즈니스 로직을 담당하는 서비스"""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.user_repo = UserRepository(db)
        self.point_service = PointService(db)
        self.google_oauth = GoogleOAuthProvider()
        self.kakao_oauth = KakaoOAuthProvider()
        self.settings = settings


    def get_oauth_auth_url(self, provider: str, redirect_uri: str, state: str) -> str:
        """OAuth 인증 URL 생성"""
        if provider == "google":
            return self.google_oauth.generate_auth_url(redirect_uri, state)
        elif provider == "kakao":
            return self.kakao_oauth.generate_auth_url(redirect_uri, state)
        else:
            raise OAuthError(f"Unsupported OAuth provider: {provider}")

    async def process_oauth_callback(
        self, callback_data: OAuthCallbackRequest
    ) -> OAuthLoginResponse:
        """OAuth 콜백 처리 및 사용자 인증/생성"""
        try:
            # 1. 액세스 토큰 교환
            if callback_data.provider == "google":
                token_response: OAuthTokenResponse = (
                    await self.google_oauth.get_access_token(
                        callback_data.code, callback_data.redirect_uri
                    )
                )
                user_info: OAuthUserInfo = await self.google_oauth.get_user_info(
                    token_response.access_token
                )
            elif callback_data.provider == "kakao":
                token_response = await self.kakao_oauth.get_access_token(
                    callback_data.code, callback_data.redirect_uri
                )
                user_info = await self.kakao_oauth.get_user_info(
                    token_response.access_token
                )
            else:
                raise OAuthError(
                    f"Unsupported OAuth provider: {callback_data.provider}"
                )

            # 2. 사용자 정보 추출
            email = user_info.email
            provider_id = str(user_info.id)
            name = user_info.name or ""

            if not email or not provider_id:
                raise OAuthError("Required user information not provided")

            # 3. 기존 사용자 조회
            existing_user = self.user_repo.get_by_provider_info(
                callback_data.provider, provider_id
            )

            is_new_user = False
            if existing_user:
                user = existing_user
                # 닉네임 동기화 (변경된 경우, 중복 회피)
                if name and name != user.nickname:
                    desired_nickname = name.strip()
                    if desired_nickname:
                        candidate = desired_nickname
                        counter = 1
                        while True:
                            # 같은 닉네임을 가진 다른 사용자가 있는지 확인
                            conflict_users = self.user_repo.find_all(filters={"nickname": candidate})
                            conflict = any(u.id != user.id for u in conflict_users)
                            if not conflict:
                                break
                            candidate = f"{desired_nickname}_{counter}"
                            counter += 1

                        if candidate != user.nickname:
                            self.user_repo.update(user.id, nickname=candidate)

                # 이미지 동기화는 스키마/모델에 필드가 없어 패스 (필드 추가 시 구현)

                # 마지막 로그인 시간 업데이트
                self.user_repo.update_last_login(user.id)
            else:
                # 4. 신규 사용자 생성
                # 이메일로 기존 사용자 확인 (다른 프로바이더로 가입한 경우)
                email_user = self.user_repo.get_by_email(email)

                if email_user:
                    raise AuthenticationError(
                        f"User already exists with email: {email}"
                    )

                # 닉네임 생성 (이름이 없으면 이메일에서 추출)
                nickname = name if name else email.split("@")[0]

                # 닉네임 중복 확인 및 유니크 처리
                original_nickname = nickname
                counter = 1
                while self.user_repo.exists(filters={"nickname": nickname}):
                    nickname = f"{original_nickname}_{counter}"
                    counter += 1

                user = self.user_repo.create_oauth_user(
                    email=email,
                    nickname=nickname,
                    auth_provider=callback_data.provider,
                    provider_id=provider_id,
                )

                if not user:
                    raise OAuthError("Failed to create OAuth user")

                is_new_user = True

                # 신규 가입 보너스 포인트 지급
                try:
                    from myapi.schemas.points import PointsTransactionRequest
                    
                    bonus_request = PointsTransactionRequest(
                        amount=self.settings.SIGNUP_BONUS_POINTS,
                        reason="Welcome bonus for new OAuth user registration",
                        ref_id=f"oauth_signup_bonus_{user.id}_{datetime.now().strftime('%Y%m%d')}"
                    )
                    
                    bonus_result = self.point_service.add_points(user_id=user.id, request=bonus_request)
                    
                    if bonus_result.success:
                        logger.info(f"✅ Awarded signup bonus to new OAuth user {user.id}: {self.settings.SIGNUP_BONUS_POINTS} points")
                    else:
                        logger.warning(f"❌ Failed to award signup bonus to new OAuth user {user.id}: {bonus_result.message}")
                except Exception as e:
                    logger.error(f"❌ Error awarding signup bonus to new OAuth user {user.id}: {str(e)}")


            # 5. JWT 토큰 생성
            access_token = create_access_token(
                data={"sub": user.email, "user_id": user.id}
            )

            return OAuthLoginResponse(
                user_id=user.id,
                token=access_token,
                nickname=user.nickname,
                is_new_user=is_new_user,
            )

        except OAuthError:
            raise
        except Exception as e:
            logger.error(f"OAuth callback processing error: {str(e)}")
            raise OAuthError("OAuth processing failed")

    def verify_token(self, token: str) -> Optional[TokenData]:
        """JWT 토큰 검증"""
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
            email_val = payload.get("sub")
            user_id_val = payload.get("user_id")

            if not isinstance(email_val, str) or not isinstance(user_id_val, int):
                return None

            return TokenData(email=email_val, user_id=user_id_val)
        except JWTError:
            return None

    def get_current_user(self, token: str) -> Optional[UserSchema]:
        """토큰으로 현재 사용자 조회"""
        token_data = self.verify_token(token)
        if not token_data or not token_data.user_id:
            return None

        user = self.user_repo.get_by_id(token_data.user_id)
        if not user or not user.is_active:
            return None

        return user

    def refresh_token(self, current_token: str) -> Optional[Token]:
        """토큰 갱신"""
        token_data = self.verify_token(current_token)
        if not token_data or token_data.email is None:
            return None

        user = self.user_repo.get_by_email(str(token_data.email))
        if not user or not user.is_active:
            return None

        # 새 토큰 생성
        access_token = create_access_token(data={"sub": user.email, "user_id": user.id})

        return Token(access_token=access_token, token_type="bearer")

    def revoke_token(self, token: str) -> bool:
        """토큰 무효화 (블랙리스트 처리)"""
        # TODO: 토큰 블랙리스트 구현
        # 현재는 토큰 검증만 수행
        return self.verify_token(token) is not None
