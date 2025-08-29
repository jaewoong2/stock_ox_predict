import httpx
from urllib.parse import urlencode
from myapi.config import settings
from myapi.core.exceptions import OAuthError
from myapi.schemas.oauth import OAuthTokenResponse, OAuthUserInfo
import logging

logger = logging.getLogger(__name__)


class KakaoOAuthProvider:
    def __init__(self):
        self.client_id = settings.KAKAO_CLIENT_ID
        self.client_secret = settings.KAKAO_CLIENT_SECRET
        self.auth_url = "https://kauth.kakao.com/oauth/authorize"
        self.token_url = "https://kauth.kakao.com/oauth/token"
        self.user_info_url = "https://kapi.kakao.com/v2/user/me"

    def generate_auth_url(self, redirect_uri: str, state: str) -> str:
        """Generate Kakao OAuth authorization URL"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def get_access_token(self, code: str, redirect_uri: str) -> OAuthTokenResponse:
        """Exchange authorization code for access token"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    logger.error(f"Kakao token exchange failed: {response.text}")
                    raise OAuthError("Failed to exchange authorization code")

                data = response.json()
                if "access_token" not in data:
                    raise OAuthError("Invalid token response from provider")
                return OAuthTokenResponse(**data, raw=data)
        except httpx.TimeoutException:
            logger.error("Kakao OAuth token exchange timeout")
            raise OAuthError("OAuth provider timeout")
        except Exception as e:
            logger.error(f"Kakao OAuth error: {str(e)}")
            raise OAuthError("OAuth provider error")

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user information from Kakao"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.user_info_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                if response.status_code != 200:
                    logger.error(f"Kakao user info fetch failed: {response.text}")
                    raise OAuthError("Failed to fetch user information")

                user_data = response.json()

                # Transform Kakao user data to consistent format
                kakao_account = user_data.get("kakao_account", {})
                profile = kakao_account.get("profile", {})
                
                # Validate required fields
                if not kakao_account.get("email"):
                    raise OAuthError("Email not provided by OAuth provider")

                return OAuthUserInfo(
                    id=str(user_data.get("id")),
                    email=kakao_account.get("email"),
                    name=profile.get("nickname", ""),
                    picture=profile.get("profile_image_url", ""),
                    verified_email=kakao_account.get("is_email_verified", False),
                )
        except httpx.TimeoutException:
            logger.error("Kakao OAuth user info fetch timeout")
            raise OAuthError("OAuth provider timeout")
        except Exception as e:
            logger.error(f"Kakao OAuth user info error: {str(e)}")
            raise OAuthError("Failed to fetch user information")
