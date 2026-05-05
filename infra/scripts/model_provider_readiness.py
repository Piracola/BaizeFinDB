"""Read-only model provider readiness preflight."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.audit.model_provider_readiness import evaluate_model_provider_readiness
from app.core.config import Settings


def write_report(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def print_report(report: dict[str, Any]) -> None:
    status = str(report.get("status", "unknown")).upper()
    print(f"[{status}] model provider readiness")

    configuration = report.get("configuration", {})
    print(
        "model_analysis_enabled="
        f"{configuration.get('model_analysis_enabled', False)} "
        f"provider={configuration.get('model_provider', 'unknown')}"
    )

    summary = report.get("summary", {})
    print(
        "checks="
        f"{summary.get('ok_count', 0)} ok / "
        f"{summary.get('warning_count', 0)} warn / "
        f"{summary.get('failure_count', 0)} fail"
    )

    for check in report.get("checks", []):
        if not isinstance(check, dict):
            continue
        if check.get("status") in {"warn", "fail"}:
            print(
                f"[{str(check.get('status', 'unknown')).upper()}] "
                f"{check.get('name', 'unknown')}: {check.get('detail', '')}"
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write bounded JSON readiness evidence to this path.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return a non-zero exit code when readiness is warning-only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = evaluate_model_provider_readiness(Settings())
    print_report(report)

    if args.json_output is not None:
        write_report(args.json_output, report)

    if report["status"] == "fail":
        return 1
    if report["status"] == "warn" and args.fail_on_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
