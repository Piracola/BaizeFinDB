from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    normalized_rows: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(80), nullable=False)


class ProviderFetchLog(Base):
    __tablename__ = "provider_fetch_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    fetch_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetch_finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    freshness: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    raw_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_snapshots.id"),
        nullable=True,
    )
    normalization_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class DataQualityCheck(Base):
    __tablename__ = "data_quality_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    check_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    fetch_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_fetch_logs.id"),
        nullable=True,
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_snapshots.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

