import httpx
from urllib.parse import urlencode
from myapi.config import settings
from myapi.core.exceptions import OAuthError
import logging

logger = logging.getLogger(__name__)


class GoogleOAuthProvider:
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.auth_url = "https://accounts.google.com/o/oauth2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
        self.user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        self.scope = "openid email profile"

    def generate_auth_url(self, redirect_uri: str, state: str) -> str:
        """Generate Google OAuth authorization URL"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def get_access_token(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for access token"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "code": code,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    logger.error(f"Google token exchange failed: {response.text}")
                    raise OAuthError("Failed to exchange authorization code")

                return response.json()
        except httpx.TimeoutException:
            logger.error("Google OAuth token exchange timeout")
            raise OAuthError("OAuth provider timeout")
        except Exception as e:
            logger.error(f"Google OAuth error: {str(e)}")
            raise OAuthError("OAuth provider error")

    async def get_user_info(self, access_token: str) -> dict:
        """Get user information from Google"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.user_info_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                if response.status_code != 200:
                    logger.error(f"Google user info fetch failed: {response.text}")
                    raise OAuthError("Failed to fetch user information")

                user_data = response.json()

                # Validate required fields
                if not user_data.get("email"):
                    raise OAuthError("Email not provided by OAuth provider")

                return user_data
        except httpx.TimeoutException:
            logger.error("Google OAuth user info fetch timeout")
            raise OAuthError("OAuth provider timeout")
        except Exception as e:
            logger.error(f"Google OAuth user info error: {str(e)}")
            raise OAuthError("Failed to fetch user information")
