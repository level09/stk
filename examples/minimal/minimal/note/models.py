"""Models for note blueprint."""

import dataclasses
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from stk.extensions import Base


@dataclasses.dataclass
class Note(Base):
    __tablename__ = "note"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
    # A core table: the app's migration depends on stk's, so `user` exists first.
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    async def from_dict(self, data: dict) -> "Note":
        self.name = data.get("name", self.name)
        self.description = data.get("description", self.description)
        return self

    def __repr__(self) -> str:
        return f"<Note {self.id}: {self.name}>"
