from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text

from stk.extensions import Base


class Job(Base):
    """One durable job. `stk worker` claims due rows, runs them, and records the end."""

    __tablename__ = "stk_job"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=False)
    # queued -> running -> done | failed; a retry goes back to queued.
    status = Column(String(16), default="queued", nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    run_after = Column(DateTime, default=datetime.now, nullable=False)
    locked_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    __table_args__ = (Index("ix_stk_job_status_run_after", "status", "run_after"),)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "payload": self.payload,
            "status": self.status,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "run_after": self.run_after.strftime("%Y-%m-%d %H:%M:%S"),
            "last_error": self.last_error,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
