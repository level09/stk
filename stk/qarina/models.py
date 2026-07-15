from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from stk.extensions import Base


class ResearchRun(Base):
    __tablename__ = "research_run"
    __table_args__ = (
        Index("ix_research_run_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    costs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "query": self.query,
            "model": self.model,
            "status": self.status,
            "costs": self.costs or {},
            "created_at": self.created_at.isoformat(),
        }

    def to_dict(self) -> dict:
        return {
            **self.summary(),
            "report": self.report,
            "sources": self.sources or {},
            "costs": self.costs or {},
            "error": self.error,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }
