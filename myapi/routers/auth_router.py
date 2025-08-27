from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import secrets
import logging
from datetime import datetime, timedelta, timezone
from myapi.config import settings
from myapi.services.auth_service import AuthService
from myapi.core.exceptions import AuthenticationError, OAuthError, ValidationError
from myapi.repositories.oauth_state_repository import OAuthStateRepository
from myapi.schemas.auth import (
    OAuthCallbackRequest,
    BaseResponse,
    Error,
    ErrorCode,
)

from dependency_injector.wiring import inject, Provide
from myapi.containers import Container
from urllib.parse import urlencode

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)



## Local login endpoint removed (OAuth-only policy)


@router.get("/oauth/{provider}/authorize")
@inject
def oauth_authorize(
    request: Request,
    provider: str,
    client_redirect: str,
    db: Session = Depends(Provide[Container.repositories.get_db]),
    auth_service: AuthService = Depends(Provide[Container.services.auth_service]),
    oauth_state_repo: OAuthStateRepository = Depends(
        Provide[Container.repositories.oauth_state_repository]
    ),
):
    """Redirects the user agent to the provider's authorization page.

    - Stores a short-lived state with the client's post-login redirect URL.
    - Uses this API's callback URL as the provider redirect_uri.
    """
    try:
        # Compute our callback URL for this provider
        callback_url = str(request.url_for("oauth_callback_get", provider=provider))

        # State (CSRF & correlation)
        state = secrets.token_urlsafe(32)
        # Save state -> client redirect mapping
        oauth_state_repo.save(
            state=state,
            client_redirect_uri=client_redirect,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=settings.OAUTH_STATE_EXPIRE_MINUTES),
        )

        # Build provider auth URL and redirect the browser
        auth_url = auth_service.get_oauth_auth_url(provider, callback_url, state)
        return RedirectResponse(
            url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    except OAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"OAuth authorize error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth authorization failed",
        )


@router.get("/oauth/{provider}/callback", name="oauth_callback_get")
@inject
async def oauth_callback_get(
    request: Request,
    provider: str,
    code: str,
    state: str,
    db: Session = Depends(Provide[Container.repositories.get_db]),
    auth_service: AuthService = Depends(Provide[Container.services.auth_service]),
    oauth_state_repo: OAuthStateRepository = Depends(
        Provide[Container.repositories.oauth_state_repository]
    ),
):
    """Provider redirects here. Exchange code -> token, then redirect to client."""
    try:
        # Resolve client redirect from stored state and clear it
        client_redirect = oauth_state_repo.pop(state)
        if not client_redirect:
            raise HTTPException(status_code=400, detail="Invalid or expired state")

        # Build the exact redirect_uri (must match what was used in authorize)
        callback_url = str(request.url_for("oauth_callback_get", provider=provider))

        # Process OAuth via service
        callback_data = OAuthCallbackRequest(
            provider=provider, code=code, state=state, redirect_uri=callback_url
        )
        result = await auth_service.process_oauth_callback(callback_data)

        # Redirect back to client with token and user info

        qs = urlencode(
            {
                "token": result.token,
                "user_id": result.user_id,
                "nickname": result.nickname,
                "provider": provider,
                "is_new_user": str(result.is_new_user).lower(),
            }
        )
        redirect_url = (
            f"{client_redirect}{'&' if ('?' in client_redirect) else '?'}{qs}"
        )
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except OAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth callback processing failed",
        )


@router.post("/oauth/callback", response_model=BaseResponse)
@inject
async def oauth_callback(
    callback_data: OAuthCallbackRequest,
    auth_service: AuthService = Depends(Provide[Container.services.auth_service]),
) -> Any:
    """Programmatic callback API for non-browser clients (kept for compatibility)."""
    try:
        result = await auth_service.process_oauth_callback(callback_data)

        return BaseResponse(
            success=True,
            data={
                "user_id": result.user_id,
                "token": result.token,
                "nickname": result.nickname,
                "is_new_user": result.is_new_user,
            },
        )
    except OAuthError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.OAUTH_PROVIDER_ERROR, message=str(e)),
        )
    except AuthenticationError as e:
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.USER_ALREADY_EXISTS, message=str(e)),
        )
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth callback processing failed",
        )


@router.post("/token/refresh", response_model=BaseResponse)
@inject
def refresh_token(
    current_token: str,
    auth_service: AuthService = Depends(Provide[Container.services.auth_service]),
) -> Any:
    """JWT 토큰 갱신"""
    try:
        new_token = auth_service.refresh_token(current_token)

        if not new_token:
            return BaseResponse(
                success=False,
                error=Error(
                    code=ErrorCode.TOKEN_EXPIRED, message="Token refresh failed"
                ),
            )

        return BaseResponse(
            success=True,
            data={
                "access_token": new_token.access_token,
                "token_type": new_token.token_type,
            },
        )
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed",
        )


@router.post("/logout", response_model=BaseResponse)
@inject
def logout_user(
    token: str,
    auth_service: AuthService = Depends(Provide[Container.services.auth_service]),
) -> Any:
    """사용자 로그아웃 (토큰 무효화)"""
    try:
        success = auth_service.revoke_token(token)

        return BaseResponse(
            success=success,
            data={"message": "Logout successful" if success else "Logout failed"},
        )
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return BaseResponse(
            success=False,
            error=Error(code=ErrorCode.UNAUTHORIZED, message="Logout failed"),
        )
