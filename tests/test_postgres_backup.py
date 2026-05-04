import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "postgres_backup.py"
)
SPEC = importlib.util.spec_from_file_location("postgres_backup", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
postgres_backup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = postgres_backup
SPEC.loader.exec_module(postgres_backup)


def test_pg_dump_command_uses_server_overlay_and_pg_dump() -> None:
    assert postgres_backup.pg_dump_command(
        service="postgres",
        db_user="baizefindb",
        db_name="baizefindb",
    ) == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.server.yml",
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "-U",
        "baizefindb",
        "-d",
        "baizefindb",
    ]


def test_pg_dump_version_command_uses_server_overlay_without_database_args() -> None:
    command = postgres_backup.pg_dump_version_command(service="postgres")

    assert command == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.server.yml",
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "--version",
    ]
    assert "-d" not in command
    assert "-U" not in command


def test_backup_path_uses_explicit_output(tmp_path: Path) -> None:
    output = tmp_path / "custom" / "backup.sql"

    assert postgres_backup.backup_path(tmp_path, "backups", str(output)) == output


def test_backup_path_defaults_to_backup_dir(tmp_path: Path) -> None:
    path = postgres_backup.backup_path(tmp_path, "backups", None)

    assert path.parent == tmp_path / "backups"
    assert path.name.startswith("baizefindb-")
    assert path.suffix == ".sql"


def test_find_repo_root_from_nested_path(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    nested = tmp_path / "infra" / "scripts"
    nested.mkdir(parents=True)

    assert postgres_backup.find_repo_root(nested) == tmp_path


def test_check_only_writes_success_evidence_without_backup_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    backup_output = tmp_path / "backups" / "check.sql"
    evidence_output = tmp_path / "evidence" / "backup-check.json"
    calls = []

    class Completed:
        returncode = 0
        stdout = "pg_dump (PostgreSQL) 16.3\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(postgres_backup.subprocess, "run", fake_run)

    exit_code = postgres_backup.run_check_only(
        tmp_path,
        backup_output,
        backup_dir="backups",
        explicit_output=str(backup_output),
        check_json_output=str(evidence_output),
        service="postgres",
        db_user="baizefindb",
        db_name="baizefindb",
    )

    evidence = json.loads(evidence_output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert not backup_output.exists()
    assert not backup_output.parent.exists()
    assert calls == [
        (
            postgres_backup.pg_dump_version_command(service="postgres"),
            {
                "cwd": tmp_path,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "capture_output": True,
                "check": False,
            },
        )
    ]
    assert evidence["status"] == "ok"
    assert evidence["compose_command_shape"] == postgres_backup.pg_dump_version_command(
        service="postgres"
    )
    assert evidence["postgres"] == {
        "service": "postgres",
        "db_user": "baizefindb",
        "db_name": "baizefindb",
    }
    assert evidence["output"]["path"] == str(backup_output)
    assert evidence["output"]["parent_exists"] is False
    assert evidence["output"]["parent_would_create"] is True
    assert evidence["pg_dump_version"]["returncode"] == 0
    assert evidence["pg_dump_version"]["detail"] == "pg_dump (PostgreSQL) 16.3"


def test_check_only_writes_failure_evidence_and_returns_nonzero(
    monkeypatch,
    tmp_path: Path,
) -> None:
    evidence_output = tmp_path / "backup-check.json"

    class Completed:
        returncode = 17
        stdout = ""
        stderr = "password=should-not-leak\npg_dump unavailable\n"

    monkeypatch.setattr(
        postgres_backup.subprocess,
        "run",
        lambda *args, **kwargs: Completed(),
    )

    exit_code = postgres_backup.run_check_only(
        tmp_path,
        tmp_path / "backups" / "check.sql",
        backup_dir="backups",
        explicit_output=None,
        check_json_output=str(evidence_output),
        service="postgres",
        db_user="baizefindb",
        db_name="baizefindb",
    )

    evidence_text = evidence_output.read_text(encoding="utf-8")
    evidence = json.loads(evidence_text)
    assert exit_code == 17
    assert evidence["status"] == "fail"
    assert evidence["pg_dump_version"]["returncode"] == 17
    assert "should-not-leak" not in evidence_text
    assert "[redacted sensitive output line]" in evidence["pg_dump_version"]["detail"]
    assert "pg_dump unavailable" in evidence["pg_dump_version"]["detail"]


def test_check_json_output_requires_check_only_before_shelling_out(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(postgres_backup, "find_repo_root", lambda: calls.append("root"))
    monkeypatch.setattr(postgres_backup.subprocess, "run", lambda *args, **kwargs: calls)

    with pytest.raises(SystemExit) as exc_info:
        postgres_backup.main(["--check-json-output", "evidence.json"])

    assert exc_info.value.code == 2
    assert calls == []
