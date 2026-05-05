import importlib.util
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.portfolio_models import UserProfile
from app.db.radar_models import RadarSignal

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_MODULE_PATH = ROOT / "infra" / "scripts" / "database_inventory.py"
SEED_MODULE_PATH = ROOT / "infra" / "scripts" / "seed_demo_data.py"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


database_inventory = _load_module("database_inventory", INVENTORY_MODULE_PATH)
seed_demo_data = _load_module("seed_demo_data_for_inventory", SEED_MODULE_PATH)


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_inventory_reports_empty_migrated_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory().bind.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _insert_alembic_version(connection, "test_head")

    async with session_factory() as session:
        report = await database_inventory.collect_database_inventory(
            session,
            repo_heads=("test_head",),
            generated_at=datetime(2026, 5, 5, 17, 0, tzinfo=UTC),
        )

    assert report["status"] == "ok"
    assert report["database"] == {
        "dialect": "sqlite",
        "driver": "aiosqlite",
        "url_redacted": True,
    }
    assert report["migrations"]["applied_versions"] == ["test_head"]
    assert report["summary"]["present_application_table_count"] == len(
        database_inventory.APPLICATION_TABLES
    )
    assert report["summary"]["known_row_count_total"] == 0
    assert report["warnings"] == []


@pytest.mark.asyncio
async def test_database_inventory_counts_seeded_demo_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory().bind.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _insert_alembic_version(connection, "test_head")

    fixed_now = datetime(2026, 5, 5, 17, 0, tzinfo=UTC)
    async with session_factory() as session:
        await seed_demo_data.seed_demo_data(session, now=fixed_now)
        report = await database_inventory.collect_database_inventory(
            session,
            repo_heads=("test_head",),
            generated_at=fixed_now,
        )

    row_counts = {
        table["name"]: table["row_count"]
        for table in report["tables"]["application"]
    }
    assert report["status"] == "ok"
    assert row_counts["users"] == 1
    assert row_counts["portfolio_holdings"] == 1
    assert row_counts["watchlist_items"] == 1
    assert row_counts["radar_scan_batches"] == 1
    assert row_counts["radar_signals"] == 2
    assert row_counts["signal_evidences"] == 3
    assert row_counts["radar_signal_reviews"] == 2
    assert row_counts["reports"] == 1
    assert report["summary"]["known_row_count_total"] >= 12


@pytest.mark.asyncio
async def test_database_inventory_warns_for_missing_application_tables(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory().bind.begin() as connection:
        await connection.run_sync(UserProfile.__table__.create)
        await _insert_alembic_version(connection, "test_head")

    async with session_factory() as session:
        report = await database_inventory.collect_database_inventory(
            session,
            repo_heads=("test_head",),
            application_tables=(
                database_inventory.TableSpec("users", UserProfile, "user"),
                database_inventory.TableSpec("radar_signals", RadarSignal, "radar"),
            ),
        )

    assert report["status"] == "warn"
    assert report["summary"]["present_application_table_count"] == 1
    assert report["summary"]["missing_application_table_count"] == 1
    assert report["tables"]["application"] == [
        {
            "name": "users",
            "category": "user",
            "present": True,
            "row_count": 0,
        },
        {
            "name": "radar_signals",
            "category": "radar",
            "present": False,
            "row_count": None,
        },
    ]
    assert "missing application tables: radar_signals" in report["warnings"]


@pytest.mark.asyncio
async def test_database_inventory_warns_when_alembic_version_is_missing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory().bind.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        report = await database_inventory.collect_database_inventory(
            session,
            repo_heads=("test_head",),
        )

    assert report["status"] == "warn"
    assert report["migrations"]["alembic_version_table_present"] is False
    assert report["migrations"]["applied_versions"] == []
    assert "alembic_version table is missing or empty" in report["warnings"]


def test_database_inventory_writes_json_and_prints_sanitized_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = {
        "status": "ok",
        "database": {
            "dialect": "postgresql",
            "driver": "asyncpg",
            "url_redacted": True,
        },
        "migrations": {
            "repo_heads": ["202605030010"],
            "applied_versions": ["202605030010"],
        },
        "summary": {
            "application_table_count": 16,
            "present_application_table_count": 16,
            "known_row_count_total": 12,
        },
        "warnings": [],
    }
    output = tmp_path / "nested" / "database-inventory.json"

    database_inventory.write_report(output, report)
    database_inventory.print_report(report)

    assert output.exists()
    assert '"url_redacted": true' in output.read_text(encoding="utf-8")
    summary = capsys.readouterr().out
    assert "database=postgresql+asyncpg url=redacted" in summary
    assert "202605030010" in summary


def test_database_inventory_failure_report_redacts_connection_secrets() -> None:
    report = database_inventory.build_failure_report(
        RuntimeError(
            "could not connect to postgresql+asyncpg://user:secret-password@db/db"
            "?token=raw-token password=hunter2"
        )
    )
    encoded = str(report)

    assert report["status"] == "fail"
    assert "secret-password" not in encoded
    assert "raw-token" not in encoded
    assert "hunter2" not in encoded
    assert "<redacted>" in encoded


async def _insert_alembic_version(connection: Any, version: str) -> None:
    await connection.execute(
        text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
    )
    await connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
        {"version": version},
    )
