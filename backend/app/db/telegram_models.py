from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TelegramBinding(Base):
    __tablename__ = "telegram_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
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
