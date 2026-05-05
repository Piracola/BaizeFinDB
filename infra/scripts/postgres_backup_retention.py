"""Filesystem-only retention helper for BaizeFinDB PostgreSQL backups."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import postgres_backup  # noqa: E402

DEFAULT_BACKUP_DIR = "backups"
DEFAULT_RETENTION_DAYS = 14
MAX_REPORTED_FILES = 50
BOUNDARY = (
    "filesystem-only PostgreSQL backup retention helper; dry-run by default; "
    "does not read .env, run Docker, run restore commands, or touch the database"
)


def resolve_backup_dir(root: Path, backup_dir: str) -> Path:
    path = Path(backup_dir).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def run_retention(
    root: Path,
    *,
    backup_dir: str = DEFAULT_BACKUP_DIR,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    delete: bool = False,
    json_output: str | None = None,
    now: datetime | None = None,
) -> int:
    if retention_days <= 0:
        msg = "retention_days must be positive"
        raise ValueError(msg)

    generated_at = _coerce_utc(now or datetime.now(UTC))
    resolved_backup_dir = resolve_backup_dir(root, backup_dir)
    report, candidate_paths = build_retention_report(
        root,
        resolved_backup_dir,
        backup_dir=backup_dir,
        retention_days=retention_days,
        delete=delete,
        generated_at=generated_at,
    )

    if delete:
        deleted, delete_errors = delete_candidates(candidate_paths)
        report["deleted_files"] = _bounded_file_entries(deleted)
        report["deleted_files_truncated"] = len(deleted) > MAX_REPORTED_FILES
        report["delete_errors"] = delete_errors[:MAX_REPORTED_FILES]
        report["delete_errors_truncated"] = len(delete_errors) > MAX_REPORTED_FILES
        report["summary"]["deleted_count"] = len(deleted)  # type: ignore[index]
        report["summary"]["delete_error_count"] = len(delete_errors)  # type: ignore[index]
        report["status"] = "fail" if delete_errors else "ok"

    if json_output:
        write_json_report(Path(json_output).expanduser().resolve(), report)

    print_retention_summary(report)
    return 1 if report["status"] == "fail" else 0


def build_retention_report(
    root: Path,
    resolved_backup_dir: Path,
    *,
    backup_dir: str,
    retention_days: int,
    delete: bool,
    generated_at: datetime,
) -> tuple[dict[str, Any], list[Path]]:
    cutoff = generated_at - timedelta(days=retention_days)
    scan = scan_backup_dir(resolved_backup_dir, cutoff=cutoff, now=generated_at)
    candidates = scan["candidates"]
    retained = scan["retained"]
    candidate_paths = [entry["path"] for entry in candidates]

    report: dict[str, Any] = {
        "report_type": "postgres_backup_retention",
        "status": "ok",
        "generated_at": generated_at.isoformat(),
        "mode": "delete" if delete else "dry-run",
        "boundary": BOUNDARY,
        "repo_root": str(root),
        "backup_dir": {
            "input": backup_dir,
            "path": str(resolved_backup_dir),
            "exists": resolved_backup_dir.exists(),
        },
        "retention": {
            "days": retention_days,
            "cutoff": cutoff.isoformat(),
        },
        "summary": {
            "total_sql_count": len(candidates) + len(retained),
            "candidate_count": len(candidates),
            "retained_count": len(retained),
            "ignored_count": scan["ignored_count"],
            "ignored_symlink_count": scan["ignored_symlink_count"],
            "ignored_non_sql_count": scan["ignored_non_sql_count"],
            "ignored_non_regular_count": scan["ignored_non_regular_count"],
            "candidate_bytes": sum(int(entry["size_bytes"]) for entry in candidates),
            "retained_bytes": sum(int(entry["size_bytes"]) for entry in retained),
            "deleted_count": 0,
            "delete_error_count": 0,
        },
        "candidate_files": _bounded_file_entries(candidates),
        "candidate_files_truncated": len(candidates) > MAX_REPORTED_FILES,
        "retained_files": _bounded_file_entries(retained),
        "retained_files_truncated": len(retained) > MAX_REPORTED_FILES,
        "deleted_files": [],
        "deleted_files_truncated": False,
        "delete_errors": [],
        "delete_errors_truncated": False,
    }
    return report, candidate_paths


def scan_backup_dir(
    backup_dir: Path,
    *,
    cutoff: datetime,
    now: datetime,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    ignored_symlink_count = 0
    ignored_non_sql_count = 0
    ignored_non_regular_count = 0

    if not backup_dir.exists():
        return {
            "candidates": candidates,
            "retained": retained,
            "ignored_count": 0,
            "ignored_symlink_count": 0,
            "ignored_non_sql_count": 0,
            "ignored_non_regular_count": 0,
        }

    for path in sorted(backup_dir.iterdir(), key=lambda item: item.name):
        if path.is_symlink():
            ignored_symlink_count += 1
            continue
        if not path.is_file():
            ignored_non_regular_count += 1
            continue
        if path.suffix.lower() != ".sql":
            ignored_non_sql_count += 1
            continue

        entry = build_file_entry(path, now=now)
        if _coerce_utc(datetime.fromtimestamp(path.stat().st_mtime, UTC)) < cutoff:
            candidates.append(entry)
        else:
            retained.append(entry)

    return {
        "candidates": sorted(candidates, key=lambda entry: str(entry["modified_at"])),
        "retained": sorted(retained, key=lambda entry: str(entry["modified_at"])),
        "ignored_count": (
            ignored_symlink_count + ignored_non_sql_count + ignored_non_regular_count
        ),
        "ignored_symlink_count": ignored_symlink_count,
        "ignored_non_sql_count": ignored_non_sql_count,
        "ignored_non_regular_count": ignored_non_regular_count,
    }


def build_file_entry(path: Path, *, now: datetime) -> dict[str, Any]:
    stat_result = path.stat()
    modified_at = _coerce_utc(datetime.fromtimestamp(stat_result.st_mtime, UTC))
    age = now - modified_at
    return {
        "path": path,
        "name": path.name,
        "modified_at": modified_at.isoformat(),
        "age_days": round(age.total_seconds() / 86400, 3),
        "size_bytes": stat_result.st_size,
    }


def delete_candidates(candidate_paths: list[Path]) -> tuple[list[Path], list[dict[str, str]]]:
    deleted: list[Path] = []
    errors: list[dict[str, str]] = []
    for path in candidate_paths:
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".sql":
            errors.append({"path": str(path), "error": "candidate is no longer safe"})
            continue
        try:
            path.unlink()
        except OSError as exc:
            errors.append({"path": str(path), "error": str(exc)})
        else:
            deleted.append(path)
    return deleted, errors


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    safe_report = postgres_backup.sanitize_evidence_value(_json_ready(report))
    if not isinstance(safe_report, dict):
        msg = "sanitized retention report must remain a JSON object"
        raise TypeError(msg)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(safe_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def print_retention_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(
        "postgres backup retention "
        f"{report['mode']}: {summary['candidate_count']} candidate(s), "
        f"{summary['retained_count']} retained, "
        f"{summary['ignored_count']} ignored, "
        f"{summary['deleted_count']} deleted"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report and optionally prune old BaizeFinDB PostgreSQL backups.",
    )
    parser.add_argument(
        "--backup-dir",
        default=DEFAULT_BACKUP_DIR,
        help=f"Backup directory to scan, default: {DEFAULT_BACKUP_DIR}.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"Keep backups newer than this many days, default: {DEFAULT_RETENTION_DAYS}.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete eligible old .sql files. Omit for dry-run/report-only mode.",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Write bounded JSON retention evidence to this path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.retention_days <= 0:
        parser.error("--retention-days must be positive")

    root = postgres_backup.find_repo_root()
    return run_retention(
        root,
        backup_dir=args.backup_dir,
        retention_days=args.retention_days,
        delete=args.delete,
        json_output=args.json_output,
    )


def _bounded_file_entries(entries: list[Any]) -> list[dict[str, Any]]:
    bounded: list[dict[str, Any]] = []
    for entry in entries[:MAX_REPORTED_FILES]:
        if isinstance(entry, Path):
            bounded.append({"path": str(entry), "name": entry.name})
            continue
        safe_entry = dict(entry)
        safe_entry["path"] = str(safe_entry["path"])
        bounded.append(safe_entry)
    return bounded


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


if __name__ == "__main__":
    sys.exit(main())
