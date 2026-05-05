import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "postgres_restore.py"
)
SPEC = importlib.util.spec_from_file_location("postgres_restore", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
postgres_restore = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = postgres_restore
SPEC.loader.exec_module(postgres_restore)


def test_psql_restore_command_uses_server_overlay_and_on_error_stop() -> None:
    assert postgres_restore.psql_restore_command(
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
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "baizefindb",
        "-d",
        "baizefindb",
    ]


def test_psql_version_command_uses_server_overlay_without_database_args() -> None:
    command = postgres_restore.psql_version_command(service="postgres")

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
        "psql",
        "--version",
    ]
    assert "-d" not in command
    assert "-U" not in command


def test_restore_path_resolves_input(tmp_path: Path) -> None:
    backup = tmp_path / "backup.sql"

    assert postgres_restore.restore_path(str(backup)) == backup


def test_restore_requires_explicit_confirmation(tmp_path: Path) -> None:
    backup = tmp_path / "backup.sql"
    backup.write_text("select 1;\n")

    assert (
        postgres_restore.run_restore(
            tmp_path,
            backup,
            confirm_restore=False,
        )
        == postgres_restore.CONFIRMATION_EXIT_CODE
    )


def test_restore_returns_failure_for_missing_input(tmp_path: Path) -> None:
    assert (
        postgres_restore.run_restore(
            tmp_path,
            tmp_path / "missing.sql",
            confirm_restore=True,
        )
        == 1
    )


def test_restore_streams_backup_to_psql(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backup = tmp_path / "backup.sql"
    backup.write_bytes(b"select 1;\n")
    calls = []

    def fake_run(command, *, cwd, stdin, check):
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "stdin": stdin.read(),
                "check": check,
            }
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(postgres_restore.subprocess, "run", fake_run)

    result = postgres_restore.run_restore(
        tmp_path,
        backup,
        confirm_restore=True,
    )

    assert result == 0
    assert calls == [
        {
            "command": postgres_restore.psql_restore_command(),
            "cwd": tmp_path,
            "stdin": b"select 1;\n",
            "check": False,
        }
    ]


def test_check_only_writes_success_evidence_without_streaming_backup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    backup = tmp_path / "backup.sql"
    evidence_output = tmp_path / "evidence" / "restore-check.json"
    backup.write_text("select 1;\n", encoding="utf-8")
    calls = []

    class Completed:
        returncode = 0
        stdout = "psql (PostgreSQL) 16.3\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(postgres_restore.subprocess, "run", fake_run)

    exit_code = postgres_restore.run_check_only(
        tmp_path,
        backup,
        check_json_output=str(evidence_output),
        service="postgres",
        db_user="baizefindb",
        db_name="baizefindb",
    )

    evidence = json.loads(evidence_output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert calls == [
        (
            postgres_restore.psql_version_command(service="postgres"),
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
    assert "stdin" not in calls[0][1]
    assert evidence["status"] == "ok"
    assert evidence["compose_command_shape"] == postgres_restore.psql_version_command(
        service="postgres"
    )
    assert evidence["input"]["status"] == "ok"
    assert evidence["input"]["size_bytes"] == len("select 1;\n")
    assert evidence["psql_version"]["returncode"] == 0
    assert evidence["psql_version"]["detail"] == "psql (PostgreSQL) 16.3"


def test_check_only_writes_failure_evidence_for_invalid_input(
    monkeypatch,
    tmp_path: Path,
) -> None:
    evidence_output = tmp_path / "restore-check.json"

    class Completed:
        returncode = 0
        stdout = "psql (PostgreSQL) 16.3\n"
        stderr = ""

    monkeypatch.setattr(
        postgres_restore.subprocess,
        "run",
        lambda *args, **kwargs: Completed(),
    )

    exit_code = postgres_restore.run_check_only(
        tmp_path,
        tmp_path / "missing.sql",
        check_json_output=str(evidence_output),
    )

    evidence = json.loads(evidence_output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert evidence["status"] == "fail"
    assert evidence["input"]["status"] == "fail"
    assert evidence["input"]["reason"] == "file_not_found"
    assert evidence["psql_version"]["returncode"] == 0


def test_check_only_rejects_unsafe_or_invalid_backup_files(tmp_path: Path) -> None:
    non_sql = tmp_path / "backup.txt"
    non_sql.write_text("select 1;\n", encoding="utf-8")
    empty = tmp_path / "empty.sql"
    empty.write_text("", encoding="utf-8")
    directory = tmp_path / "directory.sql"
    directory.mkdir()

    assert postgres_restore.inspect_backup_file(non_sql)["reason"] == "invalid_suffix"
    assert postgres_restore.inspect_backup_file(empty)["reason"] == "empty_file"
    assert postgres_restore.inspect_backup_file(directory)["reason"] == "not_regular_file"


def test_check_only_rejects_symlink_backup_file(tmp_path: Path) -> None:
    target = tmp_path / "target.sql"
    target.write_text("select 1;\n", encoding="utf-8")
    symlink = tmp_path / "linked.sql"
    try:
        symlink.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")

    assert postgres_restore.inspect_backup_file(symlink)["reason"] == "symlink_refused"


def test_restore_check_evidence_redacts_sensitive_values(tmp_path: Path) -> None:
    evidence_output = tmp_path / "restore-check.json"
    evidence = postgres_restore.build_check_evidence(
        status="fail",
        root=tmp_path,
        input_path=tmp_path / "token=should-not-leak.sql",
        service="postgres",
        db_user="password=should-not-leak",
        db_name="baizefindb",
        command=["docker", "compose", "secret=should-not-leak"],
        file_check={
            "path": str(tmp_path / "token=should-not-leak.sql"),
            "status": "fail",
            "reason": "file_not_found",
        },
        psql_returncode=1,
        psql_detail="authorization=should-not-leak\npsql unavailable",
    )

    postgres_restore.write_check_evidence(evidence_output, evidence)

    evidence_text = evidence_output.read_text(encoding="utf-8")
    written = json.loads(evidence_text)
    assert "should-not-leak" not in evidence_text
    assert written["postgres"]["db_user"] == "[redacted sensitive output line]"
    assert written["compose_command_shape"][-1] == "[redacted sensitive output line]"
    assert "psql unavailable" in written["psql_version"]["detail"]


def test_check_json_output_requires_check_only_before_repo_lookup(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(postgres_restore, "find_repo_root", lambda: calls.append("root"))

    with pytest.raises(SystemExit) as exc_info:
        postgres_restore.main(["backup.sql", "--check-json-output", "evidence.json"])

    assert exc_info.value.code == 2
    assert calls == []
