from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("radar_signals.id"),
        nullable=True,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion_label: Mapped[str] = mapped_column(String(40), nullable=False)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
