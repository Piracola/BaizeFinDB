"""Read-only database inventory helper for BaizeFinDB.

The helper is intentionally bounded: it reports schema/migration visibility and
row counts for known application tables, but never prints connection strings,
row samples, provider payloads, report bodies, prompts, or secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.db.audit_models import ModelCallLog
from app.db.health_models import SchemaHealthCheck
from app.db.portfolio_models import PortfolioHolding, UserProfile, WatchlistItem
from app.db.provider_models import DataQualityCheck, MarketSnapshot, ProviderFetchLog
from app.db.push_models import PushLog
from app.db.radar_models import RadarScanBatch, RadarSignal, RadarSignalReview, SignalEvidence
from app.db.report_models import Report
from app.db.score_models import ScoreRecord
from app.db.session import AsyncSessionLocal
from app.db.telegram_models import TelegramBinding

ALEMBIC_VERSION_TABLE = "alembic_version"
SECRET_VALUE_RE = re.compile(r"(?i)\b(password|token|secret|api_key)=([^&\s]+)")
URL_PASSWORD_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/@\s]+):([^@\s]+)@")


@dataclass(frozen=True)
class TableSpec:
    name: str
    model: type[DeclarativeBase]
    category: str


APPLICATION_TABLES: tuple[TableSpec, ...] = (
    TableSpec("schema_health_checks", SchemaHealthCheck, "health"),
    TableSpec("market_snapshots", MarketSnapshot, "provider"),
    TableSpec("provider_fetch_logs", ProviderFetchLog, "provider"),
    TableSpec("data_quality_checks", DataQualityCheck, "provider"),
    TableSpec("users", UserProfile, "user"),
    TableSpec("portfolio_holdings", PortfolioHolding, "user"),
    TableSpec("watchlist_items", WatchlistItem, "user"),
    TableSpec("reports", Report, "report"),
    TableSpec("push_logs", PushLog, "telegram"),
    TableSpec("score_records", ScoreRecord, "score"),
    TableSpec("telegram_bindings", TelegramBinding, "telegram"),
    TableSpec("radar_scan_batches", RadarScanBatch, "radar"),
    TableSpec("radar_signals", RadarSignal, "radar"),
    TableSpec("signal_evidences", SignalEvidence, "radar"),
    TableSpec("radar_signal_reviews", RadarSignalReview, "radar"),
    TableSpec("model_call_logs", ModelCallLog, "model"),
)


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (
            candidate / "alembic.ini"
        ).exists():
            return candidate

    msg = "could not find repository root with pyproject.toml and alembic.ini"
    raise RuntimeError(msg)


def read_repo_alembic_heads(root: Path) -> list[str]:
    config = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    return sorted(script.get_heads())


async def collect_database_inventory(
    session: AsyncSession,
    *,
    repo_heads: Sequence[str],
    generated_at: datetime | None = None,
    application_tables: Sequence[TableSpec] = APPLICATION_TABLES,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(UTC)
    connection = await session.connection()
    dialect = connection.dialect
    table_names = sorted(
        await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_table_names()
        )
    )
    table_name_set = set(table_names)

    applied_versions = await _read_applied_alembic_versions(session, table_name_set)
    application_table_reports = await _build_application_table_reports(
        session,
        table_name_set=table_name_set,
        application_tables=application_tables,
    )
    warnings = _build_warnings(
        repo_heads=repo_heads,
        applied_versions=applied_versions,
        table_reports=application_table_reports,
    )
    summary = _build_summary(
        table_names=table_names,
        table_reports=application_table_reports,
        warnings=warnings,
    )

    return {
        "generated_at": timestamp.isoformat(),
        "status": "warn" if warnings else "ok",
        "database": {
            "dialect": dialect.name,
            "driver": dialect.driver,
            "url_redacted": True,
        },
        "migrations": {
            "repo_heads": list(repo_heads),
            "applied_versions": applied_versions,
            "alembic_version_table_present": ALEMBIC_VERSION_TABLE in table_name_set,
        },
        "summary": summary,
        "tables": {
            "all": table_names,
            "application": application_table_reports,
        },
        "warnings": warnings,
    }


async def collect_live_inventory(root: Path) -> dict[str, Any]:
    repo_heads = read_repo_alembic_heads(root)
    async with AsyncSessionLocal() as session:
        return await collect_database_inventory(session, repo_heads=repo_heads)


def build_failure_report(error: BaseException) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "fail",
        "database": {
            "dialect": "unknown",
            "driver": "unknown",
            "url_redacted": True,
        },
        "migrations": {
            "repo_heads": [],
            "applied_versions": [],
            "alembic_version_table_present": False,
        },
        "summary": {
            "table_count": 0,
            "application_table_count": 0,
            "present_application_table_count": 0,
            "missing_application_table_count": 0,
            "known_row_count_total": 0,
            "warning_count": 0,
        },
        "tables": {
            "all": [],
            "application": [],
        },
        "warnings": [],
        "error": {
            "type": error.__class__.__name__,
            "detail": _truncate(_redact_sensitive(str(error))),
        },
    }


def write_report(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def print_report(report: dict[str, Any]) -> None:
    label = str(report.get("status", "unknown")).upper()
    print(f"[{label}] database inventory")

    database = report.get("database", {})
    print(
        "database="
        f"{database.get('dialect', 'unknown')}+{database.get('driver', 'unknown')} "
        "url=redacted"
    )

    migrations = report.get("migrations", {})
    repo_heads = _format_list(migrations.get("repo_heads", []))
    applied_versions = _format_list(migrations.get("applied_versions", []))
    print(f"repo_heads={repo_heads}")
    print(f"applied_versions={applied_versions}")

    summary = report.get("summary", {})
    print(
        "tables="
        f"{summary.get('present_application_table_count', 0)}/"
        f"{summary.get('application_table_count', 0)} application present; "
        f"known_rows={summary.get('known_row_count_total', 0)}"
    )

    for warning in report.get("warnings", []):
        print(f"[WARN] {warning}")

    error = report.get("error")
    if isinstance(error, dict):
        print(f"[FAIL] {error.get('type', 'Error')}: {error.get('detail', '')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print a read-only sanitized inventory of the configured BaizeFinDB database."
        ),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Write the same bounded sanitized inventory report as JSON.",
    )
    args = parser.parse_args(argv)

    try:
        root = find_repo_root()
        report = asyncio.run(collect_live_inventory(root))
    except Exception as exc:  # pragma: no cover - exercised through CLI behavior
        report = build_failure_report(exc)

    print_report(report)

    if args.json_output:
        write_report(args.json_output, report)

    return 1 if report["status"] == "fail" else 0


async def _read_applied_alembic_versions(
    session: AsyncSession,
    table_name_set: set[str],
) -> list[str]:
    if ALEMBIC_VERSION_TABLE not in table_name_set:
        return []

    result = await session.execute(
        text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE} ORDER BY version_num")
    )
    return [str(row[0]) for row in result]


async def _build_application_table_reports(
    session: AsyncSession,
    *,
    table_name_set: set[str],
    application_tables: Sequence[TableSpec],
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for table in application_tables:
        present = table.name in table_name_set
        row_count = await _count_rows(session, table.model) if present else None
        reports.append(
            {
                "name": table.name,
                "category": table.category,
                "present": present,
                "row_count": row_count,
            }
        )
    return reports


async def _count_rows(session: AsyncSession, model: type[DeclarativeBase]) -> int:
    count = await session.scalar(select(func.count()).select_from(model))
    return int(count or 0)


def _build_warnings(
    *,
    repo_heads: Sequence[str],
    applied_versions: Sequence[str],
    table_reports: Sequence[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if not applied_versions:
        warnings.append("alembic_version table is missing or empty")
    elif set(repo_heads) - set(applied_versions):
        warnings.append("applied migrations do not include all repository heads")

    missing_tables = [
        str(table["name"]) for table in table_reports if table.get("present") is False
    ]
    if missing_tables:
        warnings.append(f"missing application tables: {', '.join(missing_tables)}")

    return warnings


def _build_summary(
    *,
    table_names: Sequence[str],
    table_reports: Sequence[dict[str, Any]],
    warnings: Sequence[str],
) -> dict[str, int]:
    present_tables = [table for table in table_reports if table.get("present") is True]
    known_row_count_total = sum(
        int(table.get("row_count") or 0)
        for table in present_tables
        if isinstance(table.get("row_count"), int)
    )
    return {
        "table_count": len(table_names),
        "application_table_count": len(table_reports),
        "present_application_table_count": len(present_tables),
        "missing_application_table_count": len(table_reports) - len(present_tables),
        "known_row_count_total": known_row_count_total,
        "warning_count": len(warnings),
    }


def _format_list(values: object) -> str:
    if isinstance(values, list) and values:
        return ", ".join(str(value) for value in values)
    return "-"


def _truncate(value: str, *, limit: int = 500) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _redact_sensitive(value: str) -> str:
    text = URL_PASSWORD_RE.sub(r"\1:<redacted>@", value)
    return SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)


if __name__ == "__main__":
    raise SystemExit(main())
