import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from app.providers.tushare_anns_preflight import (
    PreflightReport,
    RadarRiskGoldenReport,
    validate_anns_d_preflight_cases,
    validate_radar_risk_announcement_golden_cases,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = ROOT_DIR / "golden_cases" / "tushare_anns_d_preflight.json"
DEFAULT_RADAR_RISK_CASES_PATH = (
    ROOT_DIR / "golden_cases" / "radar_m5_risk_announcements.json"
)
DEFAULT_READINESS_URL = "http://127.0.0.1:8000/providers/tushare/readiness"
DEFAULT_ANNS_D_BEAT_INTERVAL_SECONDS = 3600
SCRIPT_NAME = "check_tushare_anns_d_beat_enablement"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Tushare anns_d Beat enablement checklist. "
            "Default mode is offline/no-token and never calls live Tushare APIs."
        )
    )
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES_PATH),
        help="Path to local JSON preflight cases.",
    )
    parser.add_argument(
        "--radar-risk-cases",
        default=str(DEFAULT_RADAR_RISK_CASES_PATH),
        help="Path to local radar risk announcement golden cases.",
    )
    parser.add_argument(
        "--check-readiness",
        action="store_true",
        help=(
            "Opt in to a read-only HTTP GET against the Tushare readiness endpoint. "
            "This does not call live Tushare by itself."
        ),
    )
    parser.add_argument(
        "--readiness-url",
        default=DEFAULT_READINESS_URL,
        help="Readiness endpoint URL used only with --check-readiness.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=5.0,
        help="HTTP timeout used only with --check-readiness.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path for writing the checklist JSON evidence report.",
    )
    return parser


def build_report(
    *,
    cases_path: Path = DEFAULT_CASES_PATH,
    radar_risk_cases_path: Path = DEFAULT_RADAR_RISK_CASES_PATH,
    environ: Mapping[str, str] | None = None,
    check_readiness: bool = False,
    readiness_url: str = DEFAULT_READINESS_URL,
    timeout_seconds: float = 5.0,
) -> dict[str, object]:
    env = os.environ if environ is None else environ
    checklist: list[dict[str, object]] = []

    preflight_report = _run_offline_preflight(cases_path)
    checklist.append(_offline_preflight_gate(preflight_report, cases_path))
    radar_risk_report = _run_radar_risk_golden_cases(radar_risk_cases_path)
    checklist.append(
        _radar_risk_golden_gate(radar_risk_report, radar_risk_cases_path)
    )
    checklist.append(_token_gate(env))
    checklist.append(_beat_enabled_gate(env))
    checklist.append(_interval_gate(env))
    checklist.append(_live_verify_gate())
    checklist.append(
        _readiness_gate(
            check_readiness=check_readiness,
            readiness_url=readiness_url,
            timeout_seconds=timeout_seconds,
        )
    )

    summary = _summarize(checklist)
    status = "fail" if summary["fail"] else "warn" if summary["warn"] else "ok"
    return {
        "status": status,
        "mode": "readiness_opt_in" if check_readiness else "offline_no_token",
        "endpoint": "anns_d",
        "generated_by": SCRIPT_NAME,
        "live_tushare_called": False,
        "database_mutated": False,
        "safe_to_enable_beat": _safe_to_enable(checklist),
        "summary": summary,
        "checklist": checklist,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        cases_path=Path(args.cases),
        radar_risk_cases_path=Path(args.radar_risk_cases),
        check_readiness=args.check_readiness,
        readiness_url=args.readiness_url,
        timeout_seconds=args.timeout_seconds,
    )
    encoded = encode_report(report)
    if args.json_output is not None:
        write_report(args.json_output, encoded)
    sys.stdout.write(encoded)
    return 1 if report["status"] == "fail" else 0


def encode_report(report: dict[str, object]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report(path: Path, encoded_report: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded_report, encoding="utf-8")


def _run_offline_preflight(cases_path: Path) -> PreflightReport | Exception:
    try:
        return validate_anns_d_preflight_cases(_load_cases(cases_path))
    except Exception as exc:
        return exc


def _run_radar_risk_golden_cases(
    cases_path: Path,
) -> RadarRiskGoldenReport | Exception:
    try:
        return validate_radar_risk_announcement_golden_cases(_load_cases(cases_path))
    except Exception as exc:
        return exc


def _load_cases(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list):
        raise ValueError("preflight cases file must contain a JSON array")

    cases: list[dict[str, object]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"preflight case #{index} must be a JSON object")
        cases.append(item)
    return cases


def _offline_preflight_gate(
    preflight_report: PreflightReport | Exception,
    cases_path: Path,
) -> dict[str, object]:
    if isinstance(preflight_report, Exception):
        return {
            "id": "offline_sample_preflight",
            "status": "fail",
            "message": "offline anns_d sample gate could not run",
            "details": {
                "cases_path": str(cases_path),
                "error": f"{preflight_report.__class__.__name__}: {str(preflight_report)[:800]}",
            },
        }

    return {
        "id": "offline_sample_preflight",
        "status": "pass" if preflight_report.ok else "fail",
        "message": (
            "offline sample gate passed"
            if preflight_report.ok
            else "offline sample gate failed"
        ),
        "details": {
            "cases_path": str(cases_path),
            "validator_status": preflight_report.status,
            "case_count": preflight_report.case_count,
            "issue_count": len(preflight_report.issues),
            "required_fields": preflight_report.required_fields,
        },
    }


def _radar_risk_golden_gate(
    radar_risk_report: RadarRiskGoldenReport | Exception,
    cases_path: Path,
) -> dict[str, object]:
    if isinstance(radar_risk_report, Exception):
        return {
            "id": "radar_risk_announcement_golden_cases",
            "status": "fail",
            "message": "radar risk announcement golden cases could not run",
            "details": {
                "cases_path": str(cases_path),
                "error": f"{radar_risk_report.__class__.__name__}: {str(radar_risk_report)[:800]}",
            },
        }

    return {
        "id": "radar_risk_announcement_golden_cases",
        "status": "pass" if radar_risk_report.ok else "fail",
        "message": (
            "radar risk announcement golden cases passed"
            if radar_risk_report.ok
            else "radar risk announcement golden cases failed"
        ),
        "details": {
            "cases_path": str(cases_path),
            "validator_status": radar_risk_report.status,
            "case_count": radar_risk_report.case_count,
            "issue_count": len(radar_risk_report.issues),
        },
    }


def _token_gate(env: Mapping[str, str]) -> dict[str, object]:
    configured = bool(env.get("TUSHARE_TOKEN", "").strip())
    return {
        "id": "tushare_token",
        "status": "pass" if configured else "warn",
        "message": (
            "TUSHARE_TOKEN is configured; value is redacted"
            if configured
            else "TUSHARE_TOKEN is missing; live Tushare verification remains blocked"
        ),
        "details": {
            "configured": configured,
            "value": "redacted" if configured else None,
        },
    }


def _beat_enabled_gate(env: Mapping[str, str]) -> dict[str, object]:
    raw_value = env.get("TUSHARE_ANNS_D_BEAT_ENABLED")
    enabled = _parse_bool(raw_value)
    if enabled is None and raw_value not in (None, ""):
        return {
            "id": "beat_enabled_state",
            "status": "fail",
            "message": "TUSHARE_ANNS_D_BEAT_ENABLED must be a boolean value",
            "details": {
                "raw_value": raw_value,
                "default": False,
            },
        }

    is_enabled = bool(enabled)
    return {
        "id": "beat_enabled_state",
        "status": "warn" if is_enabled else "pass",
        "message": (
            "TUSHARE_ANNS_D_BEAT_ENABLED is already true; confirm live gates before running Beat"
            if is_enabled
            else "TUSHARE_ANNS_D_BEAT_ENABLED is disabled"
        ),
        "details": {
            "enabled": is_enabled,
            "raw_value": raw_value,
            "default": False,
        },
    }


def _interval_gate(env: Mapping[str, str]) -> dict[str, object]:
    raw_value = env.get("TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS")
    if raw_value is None or raw_value.strip() == "":
        return {
            "id": "beat_interval",
            "status": "pass",
            "message": "TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS uses the default positive interval",
            "details": {
                "interval_seconds": DEFAULT_ANNS_D_BEAT_INTERVAL_SECONDS,
                "source": "default",
            },
        }

    try:
        interval_seconds = int(raw_value)
    except ValueError:
        return {
            "id": "beat_interval",
            "status": "fail",
            "message": "TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS must be an integer",
            "details": {
                "raw_value": raw_value,
            },
        }

    return {
        "id": "beat_interval",
        "status": "pass" if interval_seconds > 0 else "fail",
        "message": (
            "TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS is positive"
            if interval_seconds > 0
            else "TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS must be positive"
        ),
        "details": {
            "interval_seconds": interval_seconds,
            "source": "environment",
        },
    }


def _live_verify_gate() -> dict[str, object]:
    return {
        "id": "live_tushare_verify",
        "status": "warn",
        "message": "live Tushare anns_d verification is still required before enabling Beat",
        "details": {
            "checked": False,
            "required_command": (
                "uv run python infra/scripts/verify_tushare_announcements.py --ann-date YYYYMMDD"
            ),
        },
    }


def _readiness_gate(
    *,
    check_readiness: bool,
    readiness_url: str,
    timeout_seconds: float,
) -> dict[str, object]:
    if not check_readiness:
        return {
            "id": "readiness_live_data",
            "status": "warn",
            "message": "readiness and live data were not checked in default offline mode",
            "details": {
                "checked": False,
                "opt_in_flag": "--check-readiness",
                "readiness_url": readiness_url,
            },
        }

    try:
        payload = _fetch_json(readiness_url, timeout_seconds)
    except Exception as exc:
        return {
            "id": "readiness_live_data",
            "status": "fail",
            "message": "readiness endpoint check failed",
            "details": {
                "checked": True,
                "readiness_url": readiness_url,
                "error": f"{exc.__class__.__name__}: {str(exc)[:800]}",
            },
        }

    return {
        "id": "readiness_live_data",
        "status": "pass",
        "message": "readiness endpoint returned JSON",
        "details": {
            "checked": True,
            "readiness_url": readiness_url,
            "readiness_status": payload.get("status"),
            "scheduler_enabled": payload.get("scheduler_enabled"),
        },
    }


def _fetch_json(url: str, timeout_seconds: float) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:300]}") from exc

    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise ValueError("readiness endpoint must return a JSON object")
    return payload


def _parse_bool(value: str | None) -> bool | None:
    if value is None or value.strip() == "":
        return False

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _summarize(checklist: list[dict[str, object]]) -> dict[str, int]:
    return {
        "pass": sum(1 for item in checklist if item["status"] == "pass"),
        "warn": sum(1 for item in checklist if item["status"] == "warn"),
        "fail": sum(1 for item in checklist if item["status"] == "fail"),
    }


def _safe_to_enable(checklist: list[dict[str, object]]) -> bool:
    required_gate_ids = {
        "offline_sample_preflight",
        "radar_risk_announcement_golden_cases",
        "tushare_token",
        "beat_enabled_state",
        "beat_interval",
        "live_tushare_verify",
        "readiness_live_data",
    }
    by_id = {str(item["id"]): item for item in checklist}
    return all(by_id[gate_id]["status"] == "pass" for gate_id in required_gate_ids)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
