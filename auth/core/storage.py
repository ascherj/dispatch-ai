"""
Database Storage
Handles user data persistence and retrieval
"""

import os
from typing import Optional, Dict, Any
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import structlog

from .subjects import UserSubject
from providers.base import UserInfo

logger = structlog.get_logger()


class DatabaseStorage:
    """Database storage for user and session data"""

    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/dispatchai"
        )

    def get_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.database_url)

    async def create_or_update_user(
        self,
        user_info: UserInfo,
        access_token: str,
        refresh_token: Optional[str] = None
    ) -> UserSubject:
        """Create or update user in database"""
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # First try to update existing user
                cur.execute("""
                    UPDATE dispatchai.users
                    SET username = %s, access_token = %s, refresh_token = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE github_id = %s
                    RETURNING *
                """, (
                    user_info.username,
                    self._encrypt_token(access_token),
                    self._encrypt_token(refresh_token) if refresh_token else None,
                    int(user_info.id)
                ))

                user_row = cur.fetchone()

                if not user_row:
                    # Create new user
                    cur.execute("""
                        INSERT INTO dispatchai.users (github_id, username, access_token, refresh_token)
                        VALUES (%s, %s, %s, %s)
                        RETURNING *
                    """, (
                        int(user_info.id),
                        user_info.username,
                        self._encrypt_token(access_token),
                        self._encrypt_token(refresh_token) if refresh_token else None
                    ))
                    user_row = cur.fetchone()

            conn.commit()
            conn.close()

            return UserSubject(
                id=user_row["id"],
                github_id=user_row["github_id"],
                username=user_row["username"],
                email=user_info.email,
                created_at=user_row["created_at"],
                properties={
                    "avatar_url": user_info.avatar_url,
                    "name": user_info.name,
                }
            )

        except Exception as e:
            logger.error("Error creating/updating user", error=str(e))
            raise

    async def get_user_by_id(self, user_id: int) -> Optional[UserSubject]:
        """Get user by ID"""
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM dispatchai.users WHERE id = %s",
                    (user_id,)
                )
                user_row = cur.fetchone()

            conn.close()

            if not user_row:
                return None

            return UserSubject(
                id=user_row["id"],
                github_id=user_row["github_id"],
                username=user_row["username"],
                created_at=user_row["created_at"],
                properties={}
            )

        except Exception as e:
            logger.error("Error fetching user", user_id=user_id, error=str(e))
            return None

    async def get_user_by_github_id(self, github_id: int) -> Optional[UserSubject]:
        """Get user by GitHub ID"""
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM dispatchai.users WHERE github_id = %s",
                    (github_id,)
                )
                user_row = cur.fetchone()

            conn.close()

            if not user_row:
                return None

            return UserSubject(
                id=user_row["id"],
                github_id=user_row["github_id"],
                username=user_row["username"],
                created_at=user_row["created_at"],
                properties={}
            )

        except Exception as e:
            logger.error("Error fetching user by GitHub ID", github_id=github_id, error=str(e))
            return None

    async def get_user_access_token(self, user_id: int) -> Optional[str]:
        """Get decrypted access token for user"""
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT access_token FROM dispatchai.users WHERE id = %s",
                    (user_id,)
                )
                result = cur.fetchone()

            conn.close()

            if not result or not result["access_token"]:
                return None

            return self._decrypt_token(result["access_token"])

        except Exception as e:
            logger.error("Error fetching user access token", user_id=user_id, error=str(e))
            return None

    def _encrypt_token(self, token: str) -> str:
        """Encrypt token for storage - simplified for now"""
        # TODO: Implement proper encryption using cryptography library
        # For now, storing as-is (would add encryption in production)
        return token

    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt token from storage - simplified for now"""
        # TODO: Implement proper decryption using cryptography library
        # For now, returning as-is (would add decryption in production)
        return encrypted_token