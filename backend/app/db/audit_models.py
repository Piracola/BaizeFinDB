from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelCallLog(Base):
    __tablename__ = "model_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_site: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    primary_model: Mapped[str] = mapped_column(String(120), nullable=False)
    fallback_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_length: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
