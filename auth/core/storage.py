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
from cryptography.fernet import Fernet
import base64

from .subjects import UserSubject
from providers.base import UserInfo

logger = structlog.get_logger()


class DatabaseStorage:
    """Database storage for user and session data"""

    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/dispatchai"
        )

        # Initialize encryption key
        encryption_key = os.getenv("ENCRYPTION_KEY")
        if not encryption_key:
            # Generate a key for development (should be set in production)
            encryption_key = Fernet.generate_key().decode()
            logger.warning("No ENCRYPTION_KEY found, using generated key for development")

        # Ensure key is properly formatted
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()

        self.cipher_suite = Fernet(encryption_key)

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
        """Encrypt token for secure storage"""
        if not token:
            return token
        try:
            logger.info("Encrypting token", token=token)
            encrypted_bytes = self.cipher_suite.encrypt(token.encode())
            encrypted_token = base64.b64encode(encrypted_bytes).decode()
            logger.info("Encrypted token", encrypted_token=encrypted_token)
            return encrypted_token
        except Exception as e:
            logger.error("Token encryption failed", error=str(e))
            raise

    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt token from storage"""
        if not encrypted_token:
            return encrypted_token
        try:
            encrypted_bytes = base64.b64decode(encrypted_token.encode())
            decrypted_bytes = self.cipher_suite.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error("Token decryption failed", error=str(e))
            raise
