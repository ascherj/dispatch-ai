"""
OAuth Providers
Clean provider-based authentication architecture
"""

from .base import BaseProvider
from .github import GitHubProvider

__all__ = ["BaseProvider", "GitHubProvider"]