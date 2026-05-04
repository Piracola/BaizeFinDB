"""PostgreSQL backup helper for BaizeFinDB Docker Compose deployments."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SERVER_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.server.yml")
DEFAULT_DB_USER = "baizefindb"
DEFAULT_DB_NAME = "baizefindb"
DEFAULT_SERVICE = "postgres"
SENSITIVE_PATTERN = re.compile(
    r"(?i)(token|secret|password|passwd|credential|authorization|api[_-]?key)"
)


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


def pg_dump_version_command(*, service: str = DEFAULT_SERVICE) -> list[str]:
    return server_compose_command("exec", "-T", service, "pg_dump", "--version")


def run_pg_dump_version(root: Path, command: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, f"command not found: {exc.filename}"

    detail = "\n".join(
        part
        for part in (
            (completed.stdout or "").strip(),
            (completed.stderr or "").strip(),
        )
        if part
    )
    return completed.returncode, sanitize_detail(detail)


def build_check_evidence(
    *,
    status: str,
    root: Path,
    output_path: Path,
    backup_dir: str,
    explicit_output: str | None,
    service: str,
    db_user: str,
    db_name: str,
    command: list[str],
    pg_dump_returncode: int | None = None,
    pg_dump_detail: str = "",
) -> dict[str, object]:
    parent_path = output_path.parent
    return {
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
        "repo_root": {
            "path": str(root),
            "has_pyproject": (root / "pyproject.toml").exists(),
            "has_docker_compose": (root / "docker-compose.yml").exists(),
        },
        "compose_command_shape": command,
        "postgres": {
            "service": service,
            "db_user": db_user,
            "db_name": db_name,
        },
        "output": {
            "path": str(output_path),
            "suffix": output_path.suffix,
            "backup_dir": backup_dir,
            "explicit_output": explicit_output is not None,
            "exists": output_path.exists(),
            "parent": str(parent_path),
            "parent_exists": parent_path.exists(),
            "parent_would_create": not parent_path.exists(),
        },
        "pg_dump_version": {
            "returncode": pg_dump_returncode,
            "detail": sanitize_detail(pg_dump_detail),
        },
    }


def write_check_evidence(path: Path, evidence: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_check_only(
    root: Path,
    output_path: Path,
    *,
    backup_dir: str,
    explicit_output: str | None,
    check_json_output: str | None,
    service: str = DEFAULT_SERVICE,
    db_user: str = DEFAULT_DB_USER,
    db_name: str = DEFAULT_DB_NAME,
) -> int:
    command = pg_dump_version_command(service=service)
    returncode, detail = run_pg_dump_version(root, command)
    status = "ok" if returncode == 0 else "fail"
    evidence = build_check_evidence(
        status=status,
        root=root,
        output_path=output_path,
        backup_dir=backup_dir,
        explicit_output=explicit_output,
        service=service,
        db_user=db_user,
        db_name=db_name,
        command=command,
        pg_dump_returncode=returncode,
        pg_dump_detail=detail,
    )

    if check_json_output:
        write_check_evidence(Path(check_json_output).expanduser().resolve(), evidence)

    if status == "ok":
        print(f"backup check passed: pg_dump --version available for {service}")
        return 0

    sys.stderr.write(f"backup check failed: {detail}\n")
    return returncode or 1


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
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate backup command metadata and pg_dump availability without dumping data.",
    )
    parser.add_argument(
        "--check-json-output",
        default=None,
        help="Write bounded check-only evidence JSON to this path. Requires --check-only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check_json_output and not args.check_only:
        parser.error("--check-json-output requires --check-only")

    root = find_repo_root()
    output_path = backup_path(root, args.backup_dir, args.output)
    if args.check_only:
        return run_check_only(
            root,
            output_path,
            backup_dir=args.backup_dir,
            explicit_output=args.output,
            check_json_output=args.check_json_output,
            service=args.service,
            db_user=args.db_user,
            db_name=args.db_name,
        )

    return run_backup(
        root,
        output_path,
        service=args.service,
        db_user=args.db_user,
        db_name=args.db_name,
    )


def sanitize_detail(text: str, *, limit: int = 500) -> str:
    sanitized_lines = []
    for line in text.splitlines():
        if SENSITIVE_PATTERN.search(line):
            sanitized_lines.append("[redacted sensitive output line]")
        else:
            sanitized_lines.append(line)
    sanitized = "\n".join(sanitized_lines).strip()
    if len(sanitized) <= limit:
        return sanitized
    return f"{sanitized[: limit - 15]}\n... truncated"


if __name__ == "__main__":
    sys.exit(main())
