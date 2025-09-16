"""
Base OAuth Provider
Abstract base class for OAuth providers
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel


class ProviderConfig(BaseModel):
    """Base configuration for OAuth providers"""
    client_id: str
    client_secret: str
    scopes: List[str] = []
    redirect_uri: Optional[str] = None


class TokenResponse(BaseModel):
    """Standardized token response"""
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: str = "Bearer"
    scope: Optional[str] = None


class UserInfo(BaseModel):
    """Standardized user information"""
    id: str
    username: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    raw_data: Dict[str, Any] = {}


class BaseProvider(ABC):
    """Abstract base class for OAuth providers"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.provider_name = self.__class__.__name__.lower().replace("provider", "")

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """Generate authorization URL for OAuth flow"""
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> TokenResponse:
        """Exchange authorization code for access token"""
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> UserInfo:
        """Get user information using access token"""
        pass

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token using refresh token"""
        pass

    def get_scopes_string(self) -> str:
        """Convert scopes list to space-separated string"""
        return " ".join(self.config.scopes)