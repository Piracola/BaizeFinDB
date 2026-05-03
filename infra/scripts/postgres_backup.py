"""PostgreSQL backup helper for BaizeFinDB Docker Compose deployments."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SERVER_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.server.yml")
DEFAULT_DB_USER = "baizefindb"
DEFAULT_DB_NAME = "baizefindb"
DEFAULT_SERVICE = "postgres"


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


def backup_path(root: Path, backup_dir: str, output: str | None) -> Path:
    if output:
        return Path(output).expanduser().resolve()

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return (root / backup_dir / f"baizefindb-{timestamp}.sql").resolve()


def pg_dump_command(
    *,
    service: str = DEFAULT_SERVICE,
    db_user: str = DEFAULT_DB_USER,
    db_name: str = DEFAULT_DB_NAME,
) -> list[str]:
    return server_compose_command(
        "exec",
        "-T",
        service,
        "pg_dump",
        "-U",
        db_user,
        "-d",
        db_name,
    )


def run_backup(
    root: Path,
    output_path: Path,
    *,
    service: str = DEFAULT_SERVICE,
    db_user: str = DEFAULT_DB_USER,
    db_name: str = DEFAULT_DB_NAME,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = pg_dump_command(service=service, db_user=db_user, db_name=db_name)

    with output_path.open("wb") as backup_file:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=root,
            stdout=backup_file,
            stderr=subprocess.PIPE,
            check=False,
        )

    if completed.returncode != 0:
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass
        sys.stderr.write(completed.stderr.decode("utf-8", errors="replace"))
        return completed.returncode

    print(f"backup written: {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Back up the BaizeFinDB PostgreSQL container with pg_dump.",
    )
    parser.add_argument(
        "--backup-dir",
        default="backups",
        help="Directory for timestamped backups when --output is omitted.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Exact output .sql path. Parent directories are created automatically.",
    )
    parser.add_argument("--db-user", default=DEFAULT_DB_USER)
    parser.add_argument("--db-name", default=DEFAULT_DB_NAME)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = find_repo_root()
    output_path = backup_path(root, args.backup_dir, args.output)
    return run_backup(
        root,
        output_path,
        service=args.service,
        db_user=args.db_user,
        db_name=args.db_name,
    )


if __name__ == "__main__":
    sys.exit(main())
