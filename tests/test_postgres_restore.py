import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

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
