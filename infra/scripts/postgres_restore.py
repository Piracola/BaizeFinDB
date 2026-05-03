"""PostgreSQL restore helper for BaizeFinDB Docker Compose deployments."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SERVER_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.server.yml")
DEFAULT_DB_USER = "baizefindb"
DEFAULT_DB_NAME = "baizefindb"
DEFAULT_SERVICE = "postgres"
CONFIRMATION_EXIT_CODE = 2


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (
            candidate / "docker-compose.yml"
        ).exists():
            return candidate

    msg = "could not find repository root with pyproject.toml and docker-compose.yml"
    raise RuntimeError(msg)


def server_compose_command(*args: str) -> list[str]:
    command = ["docker", "compose"]
    for compose_file in SERVER_COMPOSE_FILES:
        command.extend(["-f", compose_file])
    command.extend(args)
    return command


def psql_restore_command(
    *,
    service: str = DEFAULT_SERVICE,
    db_user: str = DEFAULT_DB_USER,
    db_name: str = DEFAULT_DB_NAME,
) -> list[str]:
    return server_compose_command(
        "exec",
        "-T",
        service,
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        db_user,
        "-d",
        db_name,
    )


def restore_path(input_path: str) -> Path:
    return Path(input_path).expanduser().resolve()


def run_restore(
    root: Path,
    input_path: Path,
    *,
    confirm_restore: bool,
    service: str = DEFAULT_SERVICE,
    db_user: str = DEFAULT_DB_USER,
    db_name: str = DEFAULT_DB_NAME,
) -> int:
    if not confirm_restore:
        sys.stderr.write(
            "restore refused: pass --confirm-restore after verifying the target database\n"
        )
        return CONFIRMATION_EXIT_CODE

    if not input_path.exists():
        sys.stderr.write(f"backup file not found: {input_path}\n")
        return 1

    command = psql_restore_command(service=service, db_user=db_user, db_name=db_name)
    with input_path.open("rb") as backup_file:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=root,
            stdin=backup_file,
            check=False,
        )

    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restore a BaizeFinDB PostgreSQL backup into the compose database.",
    )
    parser.add_argument("input", help="Input .sql backup path.")
    parser.add_argument(
        "--confirm-restore",
        action="store_true",
        help="Required safety switch. Restore is destructive for existing database state.",
    )
    parser.add_argument("--db-user", default=DEFAULT_DB_USER)
    parser.add_argument("--db-name", default=DEFAULT_DB_NAME)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = find_repo_root()
    input_path = restore_path(args.input)
    return run_restore(
        root,
        input_path,
        confirm_restore=args.confirm_restore,
        service=args.service,
        db_user=args.db_user,
        db_name=args.db_name,
    )


if __name__ == "__main__":
    sys.exit(main())
