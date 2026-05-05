"""One-command Linux server delivery acceptance for BaizeFinDB.

This script is a thin orchestrator. It delegates deployment, backup, backup
retention, and runtime checks to the existing helper CLIs and writes one bounded
acceptance report that points to the generated evidence files.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_EVIDENCE_DIR = Path("evidence/server-delivery-acceptance")
DEFAULT_REPORT_NAME = "server-delivery-acceptance.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
MAX_CAPTURE_LENGTH = 2000


@dataclass(frozen=True)
class StageSpec:
    name: str
    command: list[str]
    evidence_files: list[Path]


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    command: list[str]
    exit_code: int | None
    evidence_files: list[Path]
    evidence_statuses: dict[str, str] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"ok", "warn", "skipped"}


def build_stage_specs(args: argparse.Namespace) -> list[StageSpec]:
    evidence_dir = args.evidence_dir
    python_executable = args.python_executable
    stages = [
        StageSpec(
            name="deploy_preflight",
            command=[
                python_executable,
                "infra/scripts/server_deploy_check.py",
                "--base-url",
                args.base_url,
                "--check-containers",
                "--check-api",
                "--check-m5-smoke",
                "--json-output",
                str(evidence_dir / "server-deploy-check.json"),
            ],
            evidence_files=[evidence_dir / "server-deploy-check.json"],
        ),
    ]

    if args.skip_backup_check:
        stages.append(
            StageSpec(
                name="backup_check",
                command=[],
                evidence_files=[],
            )
        )
    else:
        stages.append(
            StageSpec(
                name="backup_check",
                command=[
                    python_executable,
                    "infra/scripts/server_deploy_check.py",
                    "--check-backup",
                    "--backup-check-json-output",
                    str(evidence_dir / "postgres-backup-check.json"),
                    "--json-output",
                    str(evidence_dir / "server-backup-preflight.json"),
                ],
                evidence_files=[
                    evidence_dir / "postgres-backup-check.json",
                    evidence_dir / "server-backup-preflight.json",
                ],
            )
        )

    if args.skip_backup_retention:
        stages.append(
            StageSpec(
                name="backup_retention",
                command=[],
                evidence_files=[],
            )
        )
    else:
        retention_report = evidence_dir / "postgres-backup-retention.json"
        stages.append(
            StageSpec(
                name="backup_retention",
                command=[
                    python_executable,
                    "infra/scripts/postgres_backup_retention.py",
                    "--json-output",
                    str(retention_report),
                ],
                evidence_files=[retention_report],
            )
        )

    if args.skip_runtime_check:
        stages.append(
            StageSpec(
                name="runtime_check",
                command=[],
                evidence_files=[],
            )
        )
    else:
        runtime_report = evidence_dir / "server-runtime-check.json"
        runtime_command = [
            python_executable,
            "infra/scripts/server_runtime_check.py",
            "--base-url",
            args.base_url,
            "--samples",
            str(args.runtime_samples),
            "--interval-seconds",
            str(args.runtime_interval_seconds),
            "--include-ops-trends",
        ]
        runtime_evidence_files = [runtime_report]
        if args.include_ops_evidence:
            ops_evidence = evidence_dir / "server-ops-evidence.json"
            runtime_command.extend(["--ops-evidence-output", str(ops_evidence)])
            runtime_evidence_files.append(ops_evidence)

        runtime_command.extend(["--json-output", str(runtime_report)])
        if args.fail_on_warning:
            runtime_command.append("--fail-on-warning")

        stages.append(
            StageSpec(
                name="runtime_check",
                command=runtime_command,
                evidence_files=runtime_evidence_files,
            )
        )

    return stages


def run_stage(stage: StageSpec, *, repo_root: Path) -> StageResult:
    if not stage.command:
        return StageResult(
            name=stage.name,
            status="skipped",
            command=[],
            exit_code=None,
            evidence_files=stage.evidence_files,
        )

    completed = subprocess.run(  # noqa: S603
        stage.command,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    evidence_statuses = collect_evidence_statuses(stage.evidence_files)
    stage_status = stage_status_from_evidence(
        completed.returncode,
        evidence_statuses,
    )
    return StageResult(
        name=stage.name,
        status=stage_status,
        command=stage.command,
        exit_code=completed.returncode,
        evidence_files=stage.evidence_files,
        evidence_statuses=evidence_statuses,
        stdout=_truncate(completed.stdout or ""),
        stderr=_truncate(completed.stderr or ""),
    )


def run_acceptance(args: argparse.Namespace, *, repo_root: Path | None = None) -> list[StageResult]:
    root = repo_root or find_repo_root()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    results: list[StageResult] = []
    for stage in build_stage_specs(args):
        result = run_stage(stage, repo_root=root)
        results.append(result)
        if args.fail_fast and result.status == "fail":
            break
    return results


def build_report(
    results: list[StageResult],
    *,
    evidence_dir: Path,
) -> dict[str, object]:
    counts = {
        "ok": sum(1 for result in results if result.status == "ok"),
        "warn": sum(1 for result in results if result.status == "warn"),
        "fail": sum(1 for result in results if result.status == "fail"),
        "skipped": sum(1 for result in results if result.status == "skipped"),
    }
    if counts["fail"]:
        status = "fail"
    elif counts["warn"]:
        status = "warn"
    else:
        status = "ok"

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "evidence_dir": str(evidence_dir),
        "summary": {
            "total": len(results),
            **counts,
        },
        "stages": [
            {
                "name": result.name,
                "status": result.status,
                "command": result.command,
                "exit_code": result.exit_code,
                "evidence_files": [str(path) for path in result.evidence_files],
                "evidence_statuses": result.evidence_statuses,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            for result in results
        ],
    }


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (
            candidate / "docker-compose.yml"
        ).exists():
            return candidate
    raise RuntimeError("could not find repository root with pyproject.toml and docker-compose.yml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run BaizeFinDB Linux server delivery acceptance checks.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL for deploy/runtime checks, default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=DEFAULT_EVIDENCE_DIR,
        help=f"Directory for generated evidence files, default: {DEFAULT_EVIDENCE_DIR}",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help=(
            "Acceptance report path. Defaults to "
            "<evidence-dir>/server-delivery-acceptance.json."
        ),
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used to invoke helper scripts.",
    )
    parser.add_argument(
        "--skip-backup-check",
        action="store_true",
        help="Skip PostgreSQL backup check-only evidence.",
    )
    parser.add_argument(
        "--skip-runtime-check",
        action="store_true",
        help="Skip server_runtime_check.py.",
    )
    parser.add_argument(
        "--skip-backup-retention",
        action="store_true",
        help="Skip PostgreSQL backup retention dry-run evidence.",
    )
    parser.add_argument(
        "--runtime-samples",
        type=int,
        default=3,
        help="Runtime sample count passed to server_runtime_check.py, default: 3.",
    )
    parser.add_argument(
        "--runtime-interval-seconds",
        type=int,
        default=30,
        help="Runtime interval passed to server_runtime_check.py, default: 30.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failing stage.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help=(
            "Return a failing exit code for warning-only acceptance and pass the "
            "strict warning mode to server_runtime_check.py."
        ),
    )
    parser.add_argument(
        "--include-ops-evidence",
        action="store_true",
        help=(
            "Ask server_runtime_check.py to write sanitized read-only OPS evidence "
            "inside the acceptance evidence directory."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.runtime_samples < 1 or args.runtime_samples > 20:
        parser.error("--runtime-samples must be between 1 and 20")
    if args.runtime_interval_seconds < 1 or args.runtime_interval_seconds > 3600:
        parser.error("--runtime-interval-seconds must be between 1 and 3600")

    if args.json_output is None:
        args.json_output = args.evidence_dir / DEFAULT_REPORT_NAME

    results = run_acceptance(args)
    report = build_report(results, evidence_dir=args.evidence_dir)
    write_report(args.json_output, report)
    print(_format_summary(report, args.json_output))
    if report["status"] == "fail":
        return 1
    if report["status"] == "warn" and args.fail_on_warning:
        return 1
    return 0


def _format_summary(report: dict[str, object], output_path: Path) -> str:
    summary = report["summary"]
    lines = [
        f"[{str(report['status']).upper()}] BaizeFinDB server delivery acceptance",
        f"evidence_dir={report['evidence_dir']}",
        f"json_output={output_path}",
        f"summary={summary}",
    ]
    for stage in report["stages"]:
        lines.append(
            f"[{str(stage['status']).upper()}] {stage['name']} exit={stage['exit_code']}"
        )
        evidence_statuses = stage.get("evidence_statuses")
        if evidence_statuses:
            lines.append(f"  evidence_statuses={evidence_statuses}")
    return "\n".join(lines)


def collect_evidence_statuses(evidence_files: list[Path]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for path in evidence_files:
        statuses[str(path)] = read_evidence_status(path)
    return statuses


def read_evidence_status(path: Path) -> str:
    if not path.exists():
        return "missing"

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return "unreadable"
    except json.JSONDecodeError:
        return "invalid_json"

    if not isinstance(payload, dict):
        return "invalid_json"

    status = payload.get("status")
    if status is None:
        return "missing_status"
    return str(status).lower()


def stage_status_from_evidence(
    exit_code: int,
    evidence_statuses: dict[str, str],
) -> str:
    if exit_code != 0:
        return "fail"

    failure_statuses = {
        "fail",
        "error",
        "blocked",
        "missing",
        "unreadable",
        "invalid_json",
        "missing_status",
    }
    if any(status in failure_statuses for status in evidence_statuses.values()):
        return "fail"

    if any(status in {"warn", "warning"} for status in evidence_statuses.values()):
        return "warn"

    return "ok"


def _truncate(text: str, *, limit: int = MAX_CAPTURE_LENGTH) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[: limit - 15]}\n... truncated"


if __name__ == "__main__":
    sys.exit(main())
