"""
Authentication Issuer
Central authentication coordinator inspired by OpenAuth.js patterns
"""

import secrets
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import structlog

from .storage import DatabaseStorage
from .subjects import UserSubject, TokenManager
from providers.base import BaseProvider

logger = structlog.get_logger()


class AuthIssuer:
    """Central authentication issuer following OpenAuth.js patterns"""

    def __init__(
        self,
        providers: Dict[str, BaseProvider],
        storage: DatabaseStorage,
        secret_key: str,
        success_callback: Optional[Callable] = None
    ):
        self.providers = providers
        self.storage = storage
        self.token_manager = TokenManager(secret_key)
        self.success_callback = success_callback
        self._sessions: Dict[str, Dict[str, Any]] = {}  # In-memory session storage

    def get_provider(self, provider_name: str) -> BaseProvider:
        """Get OAuth provider by name"""
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        return self.providers[provider_name]

    def create_authorization_url(self, provider_name: str, redirect_uri: str) -> Dict[str, str]:
        """Create authorization URL and state for OAuth flow"""
        provider = self.get_provider(provider_name)
        state = secrets.token_urlsafe(32)

        # Store session data
        self._sessions[state] = {
            "provider": provider_name,
            "redirect_uri": redirect_uri,
            "created_at": datetime.utcnow(),
        }

        # Update provider redirect URI
        provider.config.redirect_uri = redirect_uri

        authorization_url = provider.get_authorization_url(state)

        return {
            "url": authorization_url,
            "state": state,
        }

    async def handle_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle OAuth callback and complete authentication"""
        logger.info("Handling callback", state=state, code_length=len(code) if code else 0)

        # Validate state and atomically remove it to prevent concurrent processing
        if state not in self._sessions:
            logger.warning("Invalid state received", state=state, available_states=list(self._sessions.keys()))
            raise ValueError("Invalid or expired state")

        # Atomically get and remove session to prevent race conditions
        session = self._sessions.pop(state)
        provider_name = session["provider"]
        provider = self.get_provider(provider_name)

        logger.info("Processing callback", provider=provider_name, state=state)

        try:
            # Exchange code for token
            token_response = await provider.exchange_code_for_token(code)

            # Get user information
            user_info = await provider.get_user_info(token_response.access_token)

            # Store/update user in database
            user_subject = await self.storage.create_or_update_user(
                user_info,
                token_response.access_token,
                token_response.refresh_token
            )

            # Create our JWT tokens
            access_token = self.token_manager.create_access_token(user_subject)
            refresh_token = self.token_manager.create_refresh_token(user_subject)

            # Call success callback if provided
            if self.success_callback:
                await self.success_callback(user_subject, user_info, token_response)

            logger.info(
                "User authenticated successfully",
                user_id=user_subject.id,
                github_id=user_subject.github_id,
                provider=provider_name
            )


            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": {
                    "id": user_subject.id,
                    "github_id": user_subject.github_id,
                    "username": user_subject.username,
                    "email": user_subject.email,
                    "created_at": user_subject.created_at.isoformat(),
                    "properties": user_subject.properties,
                }
            }

        except Exception as e:
            logger.error(
                "Authentication failed",
                provider=provider_name,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def verify_token(self, access_token: str) -> Optional[UserSubject]:
        """Verify JWT access token and return user subject"""
        try:
            payload = self.token_manager.verify_token(access_token, "access")
            user_id = int(payload["sub"])

            # Get fresh user data from database
            user = await self.storage.get_user_by_id(user_id)
            return user

        except Exception as e:
            logger.debug("Token verification failed", error=str(e))
            return None

    async def refresh_user_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Refresh access token using refresh token"""
        try:
            payload = self.token_manager.verify_token(refresh_token, "refresh")
            user_id = int(payload["sub"])

            # Get user from database
            user = await self.storage.get_user_by_id(user_id)
            if not user:
                return None

            # Create new access token
            new_access_token = self.token_manager.create_access_token(user)

            return {
                "access_token": new_access_token,
                "refresh_token": refresh_token,  # Refresh tokens are long-lived
            }

        except Exception as e:
            logger.debug("Token refresh failed", error=str(e))
            return None

    def cleanup_expired_sessions(self):
        """Clean up expired sessions (call periodically)"""
        now = datetime.utcnow()
        expired_states = []

        for state, session in self._sessions.items():
            # Sessions expire after 10 minutes
            if (now - session["created_at"]).total_seconds() > 600:
                expired_states.append(state)

        for state in expired_states:
            del self._sessions[state]

        if expired_states:
            logger.info("Cleaned up expired sessions", count=len(expired_states))