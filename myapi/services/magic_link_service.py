import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session

from myapi.config import Settings
from myapi.core.exceptions import AuthenticationError, ValidationError
from myapi.repositories.oauth_state_repository import OAuthStateRepository
from myapi.repositories.user_repository import UserRepository
from myapi.services.point_service import PointService
from myapi.schemas.magic_link import MagicLinkRequest, MagicLinkResponse
from myapi.schemas.auth import OAuthLoginResponse
from myapi.core.security import create_access_token
from myapi.services.aws_service import AwsService

logger = logging.getLogger(__name__)


class MagicLinkService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.oauth_state_repo = OAuthStateRepository(db)
        self.user_repo = UserRepository(db)
        self.point_service = PointService(db)
        self.aws_service = AwsService(settings)

    async def send_magic_link(self, request: MagicLinkRequest) -> MagicLinkResponse:
        """Send magic link email via AWS SES"""
        try:
            # Generate token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=self.settings.MAGIC_LINK_EXPIRE_MINUTES
            )

            # Save token with email as redirect_uri
            self.oauth_state_repo.save(
                state=token, client_redirect_uri=request.email, expires_at=expires_at
            )

            base_url = self.settings.magic_link_base_url
            if not base_url:
                raise ValidationError("MAGIC_LINK_BASE_URL is not configured.")

            # Generate magic link URL
            magic_link_url = f"{base_url}?token={token}"

            # Send email via AWS SES
            await self._send_email(
                to_email=request.email,
                subject="OX Universe 로그인 링크",
                body_html=self._generate_email_html(magic_link_url),
            )

            return MagicLinkResponse(
                success=True, message="Magic link sent to your email"
            )

        except Exception as e:
            logger.error(f"Failed to send magic link: {str(e)}")
            return MagicLinkResponse(success=False, message="Failed to send magic link")

    async def verify_magic_link(self, token: str) -> OAuthLoginResponse:
        """Verify magic link token and authenticate user"""
        # Get email from oauth_states and delete the token
        email = self.oauth_state_repo.pop(token)

        if not email:
            raise AuthenticationError("Invalid or expired magic link")

        # Get or create user
        user = self.user_repo.get_by_email(email)
        is_new_user = False

        if not user:
            # Create new user
            nickname = email.split("@")[0]

            # Handle duplicate nicknames
            original_nickname = nickname
            counter = 1
            while self.user_repo.exists(filters={"nickname": nickname}):
                nickname = f"{original_nickname}_{counter}"
                counter += 1

            user = self.user_repo.create_oauth_user(
                email=email,
                nickname=nickname,
                auth_provider="magic_link",
                provider_id=email,
            )

            if not user:
                raise AuthenticationError("Failed to create user")

            is_new_user = True

            try:
                from myapi.schemas.points import PointsTransactionRequest

                bonus_request = PointsTransactionRequest(
                    amount=self.settings.SIGNUP_BONUS_POINTS,
                    reason="Welcome bonus for new magic link user registration",
                    ref_id=f"magic_link_signup_bonus_{user.id}_{datetime.now().strftime('%Y%m%d')}",
                )

                bonus_result = self.point_service.add_points(
                    user_id=user.id, request=bonus_request
                )

                if bonus_result.success:
                    logger.info(
                        f"✅ Awarded signup bonus to new magic link user {user.id}: {self.settings.SIGNUP_BONUS_POINTS} points"
                    )
                else:
                    logger.warning(
                        f"❌ Failed to award signup bonus to new magic link user {user.id}: {bonus_result.message}"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Error awarding signup bonus to new magic link user {user.id}: {str(e)}"
                )
        else:
            # Update last login
            self.user_repo.update_last_login(user.id)

        # Generate JWT token
        access_token = create_access_token(data={"sub": user.email, "user_id": user.id})

        return OAuthLoginResponse(
            user_id=user.id,
            token=access_token,
            nickname=user.nickname,
            is_new_user=is_new_user,
        )

    async def _send_email(self, to_email: str, subject: str, body_html: str):
        """Send email via AWS SES"""
        ses = self.aws_service._client("ses")

        try:
            response = ses.send_email(
                Source=self.settings.SES_FROM_EMAIL,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Html": {"Data": body_html, "Charset": "UTF-8"}},
                },
            )
            logger.info(f"Email sent to {to_email}, MessageId: {response['MessageId']}")
        except Exception as e:
            logger.error(f"Failed to send email via SES: {str(e)}")
            raise

    def _generate_email_html(self, magic_link_url: str) -> str:
        """Generate email HTML template"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #f8f9fa; border-radius: 10px; padding: 30px;">
                <h2 style="color: #2c3e50; margin-bottom: 20px;">OX Universe 로그인</h2>
                <p style="margin-bottom: 20px;">안녕하세요!</p>
                <p style="margin-bottom: 20px;">아래 버튼을 클릭하여 로그인하세요:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{magic_link_url}" 
                       style="display: inline-block; 
                              background-color: #007bff; 
                              color: white; 
                              padding: 12px 30px; 
                              text-decoration: none; 
                              border-radius: 5px;
                              font-weight: bold;">
                        로그인하기
                    </a>
                </div>
                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    이 링크는 {self.settings.MAGIC_LINK_EXPIRE_MINUTES}분 동안 유효합니다.
                </p>
                <p style="color: #666; font-size: 14px;">
                    본인이 요청하지 않은 경우 이 이메일을 무시하세요.
                </p>
            </div>
        </body>
        </html>
        """
