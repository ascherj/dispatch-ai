"""
User Subject Management
Handles user data and session management
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import jwt
from jwt import InvalidTokenError


class UserSubject(BaseModel):
    """User subject representation"""
    id: int
    github_id: int
    username: str
    email: Optional[str] = None
    created_at: datetime
    properties: Dict[str, Any] = {}


class TokenManager:
    """JWT token management"""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expires = timedelta(hours=24)
        self.refresh_token_expires = timedelta(days=30)

    def create_access_token(self, user: UserSubject) -> str:
        """Create JWT access token"""
        payload = {
            "sub": str(user.id),
            "github_id": user.github_id,
            "username": user.username,
            "email": user.email,
            "type": "access",
            "exp": datetime.utcnow() + self.access_token_expires,
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user: UserSubject) -> str:
        """Create JWT refresh token"""
        payload = {
            "sub": str(user.id),
            "type": "refresh",
            "exp": datetime.utcnow() + self.refresh_token_expires,
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            if payload.get("type") != token_type:
                raise InvalidTokenError(f"Invalid token type. Expected {token_type}")

            return payload
        except InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {str(e)}")

    def refresh_access_token(self, refresh_token: str, user: UserSubject) -> str:
        """Create new access token using refresh token"""
        # Verify refresh token
        payload = self.verify_token(refresh_token, "refresh")

        # Ensure the refresh token belongs to the same user
        if int(payload["sub"]) != user.id:
            raise InvalidTokenError("Refresh token user mismatch")

        # Create new access token
        return self.create_access_token(user)