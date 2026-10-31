"""Bearer tokens for MCP agents. Only the sha256 of each token is stored."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String

from stk.extensions import Base

PREFIX = "stk_mcp_"
LIFETIME = timedelta(days=90)


class McpToken(Base):
    __tablename__ = "mcp_token"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(80), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    # The user's fs_uniquifier at issue; a password change or "log out
    # everywhere" rotates it, which revokes the token too.
    user_uniquifier = Column(String(255), nullable=False)
    # Role names the token may use; each call also needs the user to hold the role.
    scopes = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    @staticmethod
    def digest(token):
        # A 256-bit random secret needs no salt or slow hash.
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def issue(cls, user, name, scopes):
        """A new row and its secret, which is never stored and cannot be shown again."""
        token = PREFIX + secrets.token_urlsafe(32)
        row = cls(
            user_id=user.id,
            user_uniquifier=user.fs_uniquifier,
            name=name,
            token_hash=cls.digest(token),
            scopes=scopes,
            expires_at=datetime.now() + LIFETIME,
        )
        return row, token

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "scopes": self.scopes,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat()
            if self.last_used_at
            else None,
        }
