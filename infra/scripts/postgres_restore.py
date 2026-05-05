"""PostgreSQL restore helper for BaizeFinDB Docker Compose deployments."""

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
CONFIRMATION_EXIT_CODE = 2
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


def psql_version_command(*, service: str = DEFAULT_SERVICE) -> list[str]:
    return server_compose_command("exec", "-T", service, "psql", "--version")


def restore_path(input_path: str) -> Path:
    return Path(input_path).expanduser().resolve()


def inspect_backup_file(input_path: Path) -> dict[str, object]:
    evidence: dict[str, object] = {
        "path": str(input_path),
        "suffix": input_path.suffix,
        "exists": input_path.exists(),
        "is_symlink": input_path.is_symlink(),
        "is_regular_file": False,
        "size_bytes": None,
        "status": "fail",
        "reason": "",
    }
    if not input_path.exists():
        evidence["reason"] = "file_not_found"
        return evidence
    if input_path.is_symlink():
        evidence["reason"] = "symlink_refused"
        return evidence
    if not input_path.is_file():
        evidence["reason"] = "not_regular_file"
        return evidence

    evidence["is_regular_file"] = True
    size_bytes = input_path.stat().st_size
    evidence["size_bytes"] = size_bytes
    if input_path.suffix.lower() != ".sql":
        evidence["reason"] = "invalid_suffix"
        return evidence
    if size_bytes <= 0:
        evidence["reason"] = "empty_file"
        return evidence

    evidence["status"] = "ok"
    evidence["reason"] = "valid_sql_backup_file"
    return evidence


def run_psql_version(root: Path, command: list[str]) -> tuple[int, str]:
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
    input_path: Path,
    service: str,
    db_user: str,
    db_name: str,
    command: list[str],
    file_check: dict[str, object],
    psql_returncode: int | None = None,
    psql_detail: str = "",
) -> dict[str, object]:
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
        "input": {
            "path": str(input_path),
            "parent": str(input_path.parent),
            **file_check,
        },
        "psql_version": {
            "returncode": psql_returncode,
            "detail": sanitize_detail(psql_detail),
        },
        "boundary": (
            "restore check-only evidence; validates backup metadata and psql "
            "availability without streaming the backup into psql"
        ),
    }


def write_check_evidence(path: Path, evidence: dict[str, object]) -> None:
    safe_evidence = sanitize_evidence_value(evidence)
    if not isinstance(safe_evidence, dict):
        msg = "sanitized evidence must remain a JSON object"
        raise TypeError(msg)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(safe_evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_check_only(
    root: Path,
    input_path: Path,
    *,
    check_json_output: str | None,
    service: str = DEFAULT_SERVICE,
    db_user: str = DEFAULT_DB_USER,
    db_name: str = DEFAULT_DB_NAME,
) -> int:
    file_check = inspect_backup_file(input_path)
    command = psql_version_command(service=service)
    returncode, detail = run_psql_version(root, command)
    status = (
        "ok"
        if file_check["status"] == "ok" and returncode == 0
        else "fail"
    )
    evidence = build_check_evidence(
        status=status,
        root=root,
        input_path=input_path,
        service=service,
        db_user=db_user,
        db_name=db_name,
        command=command,
        file_check=file_check,
        psql_returncode=returncode,
        psql_detail=detail,
    )

    if check_json_output:
        write_check_evidence(Path(check_json_output).expanduser().resolve(), evidence)

    if status == "ok":
        print(f"restore check passed: {input_path}")
        return 0

    sys.stderr.write(
        "restore check failed: "
        f"{file_check['reason']}; psql_returncode={returncode}\n"
    )
    return returncode or 1


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
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate restore input metadata and psql availability without restoring.",
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
    input_path = restore_path(args.input)
    if args.check_only:
        return run_check_only(
            root,
            input_path,
            check_json_output=args.check_json_output,
            service=args.service,
            db_user=args.db_user,
            db_name=args.db_name,
        )

    return run_restore(
        root,
        input_path,
        confirm_restore=args.confirm_restore,
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


def sanitize_evidence_value(value: object, *, limit: int = 500) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in list(value.items())[:50]:
            safe_key = sanitize_detail(str(key), limit=120)
            if SENSITIVE_PATTERN.search(str(key)):
                sanitized[safe_key] = "[redacted sensitive field]"
            else:
                sanitized[safe_key] = sanitize_evidence_value(item, limit=limit)
        return sanitized

    if isinstance(value, list):
        sanitized_items = [
            sanitize_evidence_value(item, limit=limit) for item in value[:50]
        ]
        if len(value) > 50:
            sanitized_items.append("... truncated")
        return sanitized_items

    if isinstance(value, tuple):
        return sanitize_evidence_value(list(value), limit=limit)

    if isinstance(value, str):
        return sanitize_detail(value, limit=limit)

    return value


if __name__ == "__main__":
    sys.exit(main())
