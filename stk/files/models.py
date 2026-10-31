from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String

from stk.extensions import Base


class File(Base):
    """One upload. Bytes are shared by sha256 in `stk.files.store`."""

    __tablename__ = "stk_file"

    id = Column(Integer, primary_key=True)
    sha256 = Column(String(64), nullable=False, index=True)
    size = Column(BigInteger, nullable=False)
    # Sniffed from the bytes; the client's claim is never stored.
    content_type = Column(String(100), nullable=False)
    filename = Column(String(255), nullable=False)
    thumb_sha256 = Column(String(64), nullable=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "size": self.size,
            "content_type": self.content_type,
            "sha256": self.sha256,
            "url": f"/files/{self.id}",
            "thumb_url": f"/files/{self.id}/thumb" if self.thumb_sha256 else None,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
        }
