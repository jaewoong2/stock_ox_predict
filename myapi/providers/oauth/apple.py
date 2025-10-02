import httpx
import jwt
import time
from urllib.parse import urlencode
from myapi.config import settings
from myapi.core.exceptions import OAuthError
from myapi.schemas.oauth import OAuthTokenResponse, OAuthUserInfo
import logging

logger = logging.getLogger(__name__)


class AppleOAuthProvider:
    def __init__(self):
        self.client_id = settings.APPLE_CLIENT_ID
        self.team_id = settings.APPLE_TEAM_ID
        self.key_id = settings.APPLE_KEY_ID
        self.private_key = settings.APPLE_PRIVATE_KEY
        self.auth_url = "https://appleid.apple.com/auth/authorize"
        self.token_url = "https://appleid.apple.com/auth/token"
        self.scope = "name email"

    def _generate_client_secret(self) -> str:
        """Generate client secret JWT for Apple OAuth"""
        headers = {
            "kid": self.key_id,
            "alg": "ES256"
        }
        
        payload = {
            "iss": self.team_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + 86400 * 180,  # 180 days
            "aud": "https://appleid.apple.com",
            "sub": self.client_id,
        }
        
        return jwt.encode(payload, self.private_key, algorithm="ES256", headers=headers)

    def generate_auth_url(self, redirect_uri: str, state: str) -> str:
        """Generate Apple OAuth authorization URL"""
        params = {
            "response_type": "code",
            "response_mode": "form_post",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def get_access_token(self, code: str, redirect_uri: str) -> OAuthTokenResponse:
        """Exchange authorization code for access token"""
        try:
            client_secret = self._generate_client_secret()
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    logger.error(f"Apple token exchange failed: {response.text}")
                    raise OAuthError("Failed to exchange authorization code")

                data = response.json()
                if "access_token" not in data and "id_token" not in data:
                    raise OAuthError("Invalid token response from provider")
                    
                return OAuthTokenResponse(**data, raw=data)
        except httpx.TimeoutException:
            logger.error("Apple OAuth token exchange timeout")
            raise OAuthError("OAuth provider timeout")
        except Exception as e:
            logger.error(f"Apple OAuth error: {str(e)}")
            raise OAuthError("OAuth provider error")

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user information from Apple ID token"""
        try:
            # Apple doesn't have a userinfo endpoint, decode id_token instead
            # The id_token is passed as access_token parameter
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            
            # Validate required fields
            if not decoded.get("email"):
                raise OAuthError("Email not provided by OAuth provider")

            return OAuthUserInfo(
                id=decoded.get("sub", ""),
                email=decoded.get("email"),
                name=decoded.get("name", ""),  # Name is only provided on first auth
                picture=None,  # Apple doesn't provide profile pictures
                verified_email=decoded.get("email_verified", False),
            )
        except Exception as e:
            logger.error(f"Apple OAuth user info error: {str(e)}")
            raise OAuthError("Failed to fetch user information")
