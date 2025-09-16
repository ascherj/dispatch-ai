"""
GitHub OAuth Provider
Implementation of GitHub OAuth 2.0 flow
"""

import secrets
from typing import Dict, Any
from urllib.parse import urlencode
import httpx
from authlib.common.errors import AuthlibBaseError

from .base import BaseProvider, ProviderConfig, TokenResponse, UserInfo


class GitHubConfig(ProviderConfig):
    """GitHub-specific configuration"""
    scopes: list[str] = ["user:email", "repo"]


class GitHubProvider(BaseProvider):
    """GitHub OAuth provider implementation"""

    def __init__(self, config: GitHubConfig):
        super().__init__(config)
        self.authorization_endpoint = "https://github.com/login/oauth/authorize"
        self.token_endpoint = "https://github.com/login/oauth/access_token"
        self.user_info_endpoint = "https://api.github.com/user"
        self.user_emails_endpoint = "https://api.github.com/user/emails"

    def get_authorization_url(self, state: str) -> str:
        """Generate GitHub authorization URL"""
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": self.get_scopes_string(),
            "state": state,
            "response_type": "code",
        }
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> TokenResponse:
        """Exchange authorization code for GitHub access token"""
        import structlog
        logger = structlog.get_logger()

        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "redirect_uri": self.config.redirect_uri,
        }

        headers = {
            "Accept": "application/json",
            "User-Agent": "DispatchAI/1.0",
        }

        logger.info("Exchanging code for token", code_length=len(code) if code else 0)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_endpoint,
                data=data,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()

            token_data = response.json()
            logger.info("Token exchange response", has_access_token="access_token" in token_data, has_error="error" in token_data)

            if "error" in token_data:
                logger.error("GitHub OAuth error", error=token_data.get("error"), description=token_data.get("error_description"))
                raise AuthlibBaseError(f"GitHub OAuth error: {token_data.get('error_description', token_data['error'])}")

            return TokenResponse(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                expires_in=token_data.get("expires_in"),
                token_type=token_data.get("token_type", "Bearer"),
                scope=token_data.get("scope"),
            )

    async def get_user_info(self, access_token: str) -> UserInfo:
        """Get GitHub user information"""
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "DispatchAI/1.0",
        }

        async with httpx.AsyncClient() as client:
            # Get basic user info
            user_response = await client.get(
                self.user_info_endpoint,
                headers=headers,
                timeout=30.0
            )
            user_response.raise_for_status()
            user_data = user_response.json()

            # Get user emails (if we have email scope)
            email = user_data.get("email")
            if not email and "user:email" in self.config.scopes:
                try:
                    emails_response = await client.get(
                        self.user_emails_endpoint,
                        headers=headers,
                        timeout=30.0
                    )
                    emails_response.raise_for_status()
                    emails = emails_response.json()

                    # Find primary email
                    for email_data in emails:
                        if email_data.get("primary", False):
                            email = email_data.get("email")
                            break
                except Exception:
                    # Email fetch failed, continue without email
                    pass

            return UserInfo(
                id=str(user_data["id"]),
                username=user_data["login"],
                email=email,
                name=user_data.get("name"),
                avatar_url=user_data.get("avatar_url"),
                raw_data=user_data,
            )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """GitHub doesn't support token refresh, tokens are long-lived"""
        raise NotImplementedError("GitHub doesn't support token refresh")

    async def get_user_repositories(self, access_token: str) -> list[Dict[str, Any]]:
        """Get user's accessible repositories"""
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "DispatchAI/1.0",
        }

        repositories = []
        page = 1
        per_page = 100

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(
                    "https://api.github.com/user/repos",
                    headers=headers,
                    params={
                        "per_page": per_page,
                        "page": page,
                        "sort": "updated",
                        "direction": "desc"
                    },
                    timeout=30.0
                )
                response.raise_for_status()

                page_repos = response.json()
                if not page_repos:
                    break

                repositories.extend(page_repos)

                # Check rate limiting
                remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
                if remaining < 10:
                    break

                page += 1

                # Safety limit
                if page > 10:  # Max 1000 repos
                    break

        return repositories