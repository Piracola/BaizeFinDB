from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RadarScanBatch(Base):
    __tablename__ = "radar_scan_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_snapshot_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class RadarSignal(Base):
    __tablename__ = "radar_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("radar_scan_batches.id"),
        nullable=False,
        index=True,
    )
    signal_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    subject_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    subject_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    lifecycle_stage: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SignalEvidence(Base):
    __tablename__ = "signal_evidences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("radar_signals.id"),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    freshness: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    public_share_policy: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
