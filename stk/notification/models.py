from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from stk.extensions import Base


class Notification(Base):
    __tablename__ = "stk_notification"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(64), nullable=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String(2048), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    read_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_stk_notification_user_id_created_at", "user_id", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "link": self.link,
            "created_at": self.created_at.isoformat(),
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }
