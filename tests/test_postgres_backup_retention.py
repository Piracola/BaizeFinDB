import importlib.util
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "postgres_backup_retention.py"
)
SPEC = importlib.util.spec_from_file_location("postgres_backup_retention", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
postgres_backup_retention = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = postgres_backup_retention
SPEC.loader.exec_module(postgres_backup_retention)


NOW = datetime(2026, 5, 5, 10, 0, tzinfo=UTC)


def test_retention_dry_run_reports_candidates_without_deleting(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    old_backup = _write_backup(backup_dir / "old.sql", age_days=20)
    fresh_backup = _write_backup(backup_dir / "fresh.sql", age_days=3)
    _write_backup(backup_dir / "note.txt", age_days=90)
    (backup_dir / "nested").mkdir()

    exit_code = postgres_backup_retention.run_retention(
        tmp_path,
        retention_days=14,
        now=NOW,
    )

    assert exit_code == 0
    assert old_backup.exists()
    assert fresh_backup.exists()

    report, candidates = postgres_backup_retention.build_retention_report(
        tmp_path,
        backup_dir,
        backup_dir="backups",
        retention_days=14,
        delete=False,
        generated_at=NOW,
    )
    assert candidates == [old_backup]
    assert report["mode"] == "dry-run"
    assert report["summary"]["candidate_count"] == 1
    assert report["summary"]["retained_count"] == 1
    assert report["summary"]["ignored_non_sql_count"] == 1
    assert report["summary"]["ignored_non_regular_count"] == 1
    assert report["candidate_files"][0]["name"] == "old.sql"


def test_retention_delete_removes_only_old_regular_sql_files(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    old_backup = _write_backup(backup_dir / "old.sql", age_days=20)
    fresh_backup = _write_backup(backup_dir / "fresh.sql", age_days=1)
    non_sql = _write_backup(backup_dir / "old.log", age_days=20)

    exit_code = postgres_backup_retention.run_retention(
        tmp_path,
        retention_days=14,
        delete=True,
        now=NOW,
    )

    assert exit_code == 0
    assert not old_backup.exists()
    assert fresh_backup.exists()
    assert non_sql.exists()


def test_retention_skips_symlinks(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    target = _write_backup(tmp_path / "outside.sql", age_days=30)
    symlink = backup_dir / "linked.sql"
    try:
        symlink.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")

    report, candidates = postgres_backup_retention.build_retention_report(
        tmp_path,
        backup_dir,
        backup_dir="backups",
        retention_days=14,
        delete=False,
        generated_at=NOW,
    )

    assert candidates == []
    assert report["summary"]["ignored_symlink_count"] == 1
    assert target.exists()
    assert symlink.exists()


def test_retention_json_output_is_bounded_and_sanitized(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    for index in range(postgres_backup_retention.MAX_REPORTED_FILES + 2):
        _write_backup(backup_dir / f"old-{index:02d}.sql", age_days=30)
    _write_backup(backup_dir / "token=should-not-leak.sql", age_days=30)
    output = tmp_path / "evidence" / "retention.json"

    exit_code = postgres_backup_retention.run_retention(
        tmp_path,
        retention_days=14,
        json_output=str(output),
        now=NOW,
    )

    report_text = output.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert exit_code == 0
    assert report["report_type"] == "postgres_backup_retention"
    assert report["summary"]["candidate_count"] == (
        postgres_backup_retention.MAX_REPORTED_FILES + 3
    )
    assert len(report["candidate_files"]) == postgres_backup_retention.MAX_REPORTED_FILES
    assert report["candidate_files_truncated"] is True
    assert "should-not-leak" not in report_text


def test_retention_main_rejects_non_positive_days_before_repo_lookup(
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        postgres_backup_retention.postgres_backup,
        "find_repo_root",
        lambda: calls.append("repo"),
    )

    with pytest.raises(SystemExit) as exc_info:
        postgres_backup_retention.main(["--retention-days", "0"])

    assert exc_info.value.code == 2
    assert calls == []


def test_retention_missing_backup_dir_reports_zero_counts(tmp_path: Path) -> None:
    report, candidates = postgres_backup_retention.build_retention_report(
        tmp_path,
        tmp_path / "missing",
        backup_dir="missing",
        retention_days=14,
        delete=False,
        generated_at=NOW,
    )

    assert candidates == []
    assert report["backup_dir"]["exists"] is False
    assert report["summary"]["candidate_count"] == 0
    assert report["summary"]["ignored_count"] == 0


def _write_backup(path: Path, *, age_days: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("backup\n", encoding="utf-8")
    modified_at = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(path, (modified_at, modified_at))
    return path
