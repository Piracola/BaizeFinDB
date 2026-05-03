from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScoreRecord(Base):
    __tablename__ = "score_records"
    __table_args__ = (
        UniqueConstraint(
            "signal_id",
            "window_days",
            name="uq_score_records_signal_window",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("radar_signals.id"),
        nullable=False,
        index=True,
    )
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    score_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    components: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
