"""Developer environment preflight checks for BaizeFinDB.

This script validates the local machine before development work starts. It is
intentionally read-only: it does not install packages, start containers, or print
expanded environment values.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVER_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.server.yml")
MAX_DIRTY_PATHS = 12


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status != "fail"


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


def run_command(name: str, command: list[str], root: Path) -> CheckResult:
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
        return CheckResult(name, "fail", f"command not found: {exc.filename}")

    output = "\n".join(
        part
        for part in (
            (completed.stdout or "").strip(),
            (completed.stderr or "").strip(),
        )
        if part
    )
    if completed.returncode == 0:
        return CheckResult(name, "ok", _truncate(output))
    return CheckResult(name, "fail", _truncate(output or f"exit code {completed.returncode}"))


def run_raw_command(command: list[str], root: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # noqa: S603
            command,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return None


def check_python_version(root: Path, version_info: tuple[int, int] | None = None) -> CheckResult:
    pyproject = _read_pyproject(root)
    requirement = str(pyproject.get("project", {}).get("requires-python", "")).strip()
    major_minor = version_info or (sys.version_info.major, sys.version_info.minor)

    if not requirement:
        return CheckResult("python version", "warn", "pyproject.toml has no requires-python")

    if _version_satisfies_project_requirement(major_minor, requirement):
        return CheckResult(
            "python version",
            "ok",
            f"Python {major_minor[0]}.{major_minor[1]} satisfies {requirement}",
        )

    return CheckResult(
        "python version",
        "fail",
        f"Python {major_minor[0]}.{major_minor[1]} does not satisfy {requirement}",
    )


def check_uv_available() -> CheckResult:
    path = shutil.which("uv")
    if path:
        return CheckResult("uv", "ok", f"uv found at {path}")
    return CheckResult("uv", "fail", "uv is not on PATH")


def check_virtualenv(root: Path) -> CheckResult:
    venv = root / ".venv"
    if not venv.exists():
        return CheckResult(".venv", "fail", ".venv is missing; run `uv sync --dev`")

    linux_python = venv / "bin" / "python"
    windows_python = venv / "Scripts" / "python.exe"
    pyvenv_cfg = venv / "pyvenv.cfg"

    if linux_python.exists():
        return CheckResult(".venv", "ok", "Linux virtualenv detected")

    if windows_python.exists():
        return CheckResult(
            ".venv",
            "fail",
            "Windows virtualenv detected; move it aside and run `uv sync --dev` on Linux",
        )

    if pyvenv_cfg.exists():
        return CheckResult(".venv", "fail", ".venv exists but no Linux python was found")

    return CheckResult(".venv", "fail", ".venv is not a recognized Python virtualenv")


def check_tkinter() -> CheckResult:
    if importlib.util.find_spec("tkinter") is None:
        return CheckResult(
            "tkinter",
            "fail",
            "tkinter is not importable; install python3-tk for Windows GUI helper tests",
        )
    return CheckResult("tkinter", "ok", "tkinter import spec found")


def check_powershell() -> CheckResult:
    path = shutil.which("pwsh") or shutil.which("powershell")
    if path:
        return CheckResult("powershell", "ok", f"PowerShell found at {path}")
    return CheckResult(
        "powershell",
        "warn",
        "PowerShell not found; Windows launcher/packaging tests may skip on Linux",
    )


def check_git_worktree(root: Path) -> CheckResult:
    status = run_raw_command(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        root,
    )
    if status is None:
        return CheckResult("git worktree", "fail", "git command not found")
    if status.returncode != 0:
        return CheckResult("git worktree", "fail", _truncate(status.stderr or status.stdout))

    dirty_lines = [line for line in status.stdout.splitlines() if line.strip()]
    if not dirty_lines:
        return CheckResult("git worktree", "ok", "tracked worktree is clean")

    cached_clean = _git_quiet(root, ["git", "diff", "--cached", "--ignore-cr-at-eol", "--quiet"])
    worktree_clean = _git_quiet(root, ["git", "diff", "--ignore-cr-at-eol", "--quiet"])
    paths = _dirty_path_summary(dirty_lines)
    if cached_clean and worktree_clean:
        return CheckResult(
            "git worktree",
            "warn",
            f"tracked files are dirty only by CRLF/stat noise: {paths}",
        )

    return CheckResult("git worktree", "warn", f"tracked dirty files: {paths}")


def collect_checks(root: Path) -> list[CheckResult]:
    return [
        check_python_version(root),
        check_uv_available(),
        check_virtualenv(root),
        run_command("docker", ["docker", "--version"], root),
        run_command("docker compose", ["docker", "compose", "version"], root),
        run_command("docker compose config", ["docker", "compose", "config", "--quiet"], root),
        run_command(
            "docker compose server config",
            server_compose_command("config", "--quiet"),
            root,
        ),
        check_tkinter(),
        check_powershell(),
        check_git_worktree(root),
    ]


def build_report(checks: list[CheckResult]) -> dict[str, Any]:
    summary = {
        "total": len(checks),
        "ok": sum(1 for check in checks if check.status == "ok"),
        "warn": sum(1 for check in checks if check.status == "warn"),
        "fail": sum(1 for check in checks if check.status == "fail"),
    }
    status = "fail" if summary["fail"] else "warn" if summary["warn"] else "ok"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "summary": summary,
        "checks": [
            {"name": check.name, "status": check.status, "detail": check.detail}
            for check in checks
        ],
    }


def write_report(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def print_checks(checks: list[CheckResult]) -> None:
    labels = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
    for check in checks:
        print(f"[{labels.get(check.status, check.status.upper())}] {check.name}")
        if check.detail:
            print(check.detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether the local BaizeFinDB development environment is usable.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Write a bounded JSON environment check report.",
    )
    args = parser.parse_args(argv)

    root = find_repo_root()
    checks = collect_checks(root)
    report = build_report(checks)
    print_checks(checks)

    if args.json_output:
        write_report(args.json_output, report)

    return 1 if report["summary"]["fail"] else 0


def _read_pyproject(root: Path) -> dict[str, Any]:
    with (root / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _version_satisfies_project_requirement(
    major_minor: tuple[int, int],
    requirement: str,
) -> bool:
    current = major_minor[0] * 100 + major_minor[1]
    for operator, raw_major, raw_minor in re.findall(r"(>=|<=|==|>|<)\s*(\d+)\.(\d+)", requirement):
        target = int(raw_major) * 100 + int(raw_minor)
        if operator == ">=" and current < target:
            return False
        if operator == "<=" and current > target:
            return False
        if operator == "==" and current != target:
            return False
        if operator == ">" and current <= target:
            return False
        if operator == "<" and current >= target:
            return False
    return True


def _git_quiet(root: Path, command: list[str]) -> bool:
    completed = run_raw_command(command, root)
    return completed is not None and completed.returncode == 0


def _dirty_path_summary(lines: list[str]) -> str:
    paths = []
    for line in lines[:MAX_DIRTY_PATHS]:
        path = line[3:] if len(line) > 3 else line
        paths.append(path.strip())
    suffix = "" if len(lines) <= MAX_DIRTY_PATHS else f", ... +{len(lines) - MAX_DIRTY_PATHS} more"
    return ", ".join(paths) + suffix


def _truncate(value: str, *, limit: int = 500) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


if __name__ == "__main__":
    raise SystemExit(main())
