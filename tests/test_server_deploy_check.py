import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "server_deploy_check.py"
)
SPEC = importlib.util.spec_from_file_location("server_deploy_check", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_deploy_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_deploy_check
SPEC.loader.exec_module(server_deploy_check)


def test_server_compose_command_uses_overlay_files() -> None:
    assert server_deploy_check.server_compose_command("config") == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.server.yml",
        "config",
    ]


def test_pg_dump_version_command_uses_postgres_service() -> None:
    assert server_deploy_check.pg_dump_version_command("postgres") == [
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


def test_find_repo_root_from_nested_path(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    nested = tmp_path / "infra" / "scripts"
    nested.mkdir(parents=True)

    assert server_deploy_check.find_repo_root(nested) == tmp_path


def test_check_env_warns_or_fails_when_missing(tmp_path: Path) -> None:
    warning = server_deploy_check.check_env(tmp_path, strict=False)
    failure = server_deploy_check.check_env(tmp_path, strict=True)

    assert warning.status == "warn"
    assert warning.ok
    assert failure.status == "fail"
    assert not failure.ok


def test_check_env_passes_when_env_exists(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")

    result = server_deploy_check.check_env(tmp_path, strict=True)

    assert result.status == "ok"
    assert result.ok
