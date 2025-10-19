import json
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Set
from urllib.parse import urlparse
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

            redirect_target = self._resolve_redirect_url(
                str(request.redirect_url) if request.redirect_url else None
            )

            state_payload = {"email": request.email}
            if redirect_target:
                state_payload["redirect_url"] = redirect_target

            self.oauth_state_repo.save(
                state=token,
                client_redirect_uri=json.dumps(state_payload),
                expires_at=expires_at,
            )

            base_url = self.settings.magic_link_base_url
            if not base_url:
                raise ValidationError("MAGIC_LINK_BASE_URL is not configured.")

            # Generate magic link URL
            magic_link_url = f"{base_url}?token={token}"

            # Send email via AWS SES
            await self._send_email(
                to_email=request.email,
                subject="[Bamtoly | AI로 분석하는 미국주식] 로그인 링크",
                body_html=self._generate_email_html(magic_link_url),
            )

            return MagicLinkResponse(
                success=True, message="Magic link sent to your email"
            )

        except Exception as e:
            logger.error(f"Failed to send magic link: {str(e)}")
            return MagicLinkResponse(success=False, message="Failed to send magic link")

    async def verify_magic_link(
        self, token: str
    ) -> Tuple[OAuthLoginResponse, Optional[str]]:
        """Verify magic link token and authenticate user"""
        state_value = self.oauth_state_repo.pop(token)

        if not state_value:
            raise AuthenticationError("Invalid or expired magic link")

        email, state_redirect = self._extract_state_payload(state_value)

        if not email:
            raise AuthenticationError("Invalid or expired magic link")

        redirect_target = self._resolve_redirect_url(state_redirect)

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

        auth_response = OAuthLoginResponse(
            user_id=user.id,
            token=access_token,
            nickname=user.nickname,
            is_new_user=is_new_user,
        )

        return auth_response, redirect_target

    def _extract_state_payload(
        self, stored_value: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Parse stored magic link payload (backward compatible with legacy format)."""
        try:
            data = json.loads(stored_value)
        except json.JSONDecodeError:
            # Legacy entries stored plain email string
            return stored_value, None

        if isinstance(data, dict):
            email = data.get("email")
            redirect_url = data.get("redirect_url")
            return email, redirect_url

        return None, None

    def _resolve_redirect_url(self, supplied: Optional[str]) -> Optional[str]:
        """Validate supplied redirect or fall back to configured default."""
        if supplied:
            try:
                return self._validate_redirect_url(supplied)
            except ValidationError as exc:
                logger.warning(
                    "Ignoring invalid magic link redirect '%s': %s", supplied, exc
                )

        default_url = self.settings.magic_link_client_redirect_url
        try:
            return self._validate_redirect_url(default_url)
        except ValidationError as exc:
            if default_url:
                logger.warning("Configured magic link redirect URL is invalid: %s", exc)
            return None

    def _validate_redirect_url(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidationError("Invalid redirect URL")

        allowed_hosts = self._allowed_redirect_hosts()
        if allowed_hosts and parsed.netloc not in allowed_hosts:
            raise ValidationError(f"Redirect host '{parsed.netloc}' not permitted")

        return url

    def _allowed_redirect_hosts(self) -> Set[str]:
        urls = [
            self.settings.MAGIC_LINK_CLIENT_REDIRECT_URL,
            self.settings.MAGIC_LINK_CLIENT_REDIRECT_URL_LOCAL,
            self.settings.MAGIC_LINK_CLIENT_REDIRECT_URL_PROD,
            self.settings.magic_link_client_redirect_url,
        ]

        hosts: Set[str] = set()
        for candidate in urls:
            if not candidate:
                continue
            parsed = urlparse(candidate)
            if parsed.netloc:
                hosts.add(parsed.netloc)
        return hosts

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
        """Generate polished login email template"""
        return f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{self.settings.APP_NAME} Magic Link</title>
        </head>
        <body style="margin:0; padding:0; background-color:#f6f7fb; color:#1f2937; font-family:'Helvetica Neue', Arial, sans-serif;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f6f7fb; padding:48px 0;">
                <tr>
                    <td align="center">
                        <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:16px; border:1px solid #e5e7eb; overflow:hidden;">
                            <tr>
                                <td style="padding:32px 40px 16px 40px; text-align:center;">
                                    <div style="font-size:26px; font-weight:700; color:#111827; letter-spacing:-0.4px;">
                                        {self.settings.APP_NAME or "OX Universe"}
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:0 40px 8px 40px;">
                                    <div style="background-color:#f3f4f6; border-radius:12px; padding:20px 24px; font-size:15px; line-height:1.7; color:#4b5563; text-align:center;">
                                        <strong style="display:block; margin-bottom:8px; color:#111827;">안녕하세요!</strong>
                                        로그인 요청이 확인되었습니다. 아래 버튼을 눌러 로그인을 완료하세요.<br>
                                        만약 본인이 요청하지 않았다면, 이 메일을 무시해 주세요.
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:16px 40px 24px 40px; text-align:center;">
                                    <a href="{magic_link_url}" style="display:inline-block; background:linear-gradient(135deg,#7c3aed,#6366f1); color:#ffffff; text-decoration:none; font-weight:600; padding:14px 48px; border-radius:9999px; font-size:17px;">
                                        계속하기
                                    </a>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:0 40px 24px 40px; text-align:center; font-size:13px; color:#6b7280; line-height:1.7;">
                                    버튼이 작동하지 않는다면 아래 링크를 브라우저 주소창에 붙여넣으세요.<br>
                                    <a href="{magic_link_url}" style="color:#7c3aed; text-decoration:none;">{magic_link_url}</a>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:0 40px 32px 40px; font-size:12px; color:#9ca3af; text-align:center; line-height:1.7;">
                                    이 링크는 발송 시점부터 {self.settings.MAGIC_LINK_EXPIRE_MINUTES}분 동안만 유효합니다.<br>
                                    보안을 위해 타인과 공유하지 말아 주세요.
                                </td>
                            </tr>
                        </table>
                        <div style="margin-top:24px; font-size:12px; color:#9ca3af;">
                            © {datetime.now().year} {self.settings.APP_NAME or "OX Universe"} · All rights reserved.
                        </div>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
