from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PushLog(Base):
    __tablename__ = "push_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_ref: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    included_signal_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    blocked_signal_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    needs_human_review_signal_ids: Mapped[list[int]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    delivery_details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
