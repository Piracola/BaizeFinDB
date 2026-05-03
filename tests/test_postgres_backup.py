import importlib.util
import sys
from pathlib import Path

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
