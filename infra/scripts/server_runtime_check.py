"""Runtime validation checks for a running BaizeFinDB server.

The deploy preflight verifies files, compose syntax, and one-shot smoke
contracts. This script is for the next step: sample a running API for a short
window and fail when the runtime becomes blocked or API reads are unavailable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import export_ops_evidence  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_TREND_BUCKET_COUNT = 12
MAX_TREND_BUCKET_COUNT = 48
RUNTIME_ENDPOINTS = (
    ("health", "/health", ()),
    ("health_ready", "/health/ready", ()),
    ("ops_overview", "/ops/overview", ("lookback_hours",)),
    ("ops_history", "/ops/history", ("lookback_hours", "limit")),
    ("ops_readiness", "/ops/readiness", ("lookback_hours",)),
)
OPS_TRENDS_ENDPOINT = ("ops_trends", "/ops/trends", ("lookback_hours", "bucket_count"))


@dataclass(frozen=True)
class EndpointRead:
    name: str
    path: str
    status: str
    http_status: int | None = None
    payload: dict[str, Any] | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class RuntimeSample:
    collected_at: str
    endpoints: dict[str, EndpointRead]


class OpsEvidenceExportError(RuntimeError):
    """Raised when optional OPS evidence export could not complete successfully."""


def build_endpoint_path(
    path: str,
    query_keys: tuple[str, ...],
    *,
    lookback_hours: int,
    history_limit: int,
    trend_bucket_count: int = DEFAULT_TREND_BUCKET_COUNT,
) -> str:
    query: dict[str, int] = {}
    if "lookback_hours" in query_keys:
        query["lookback_hours"] = lookback_hours
    if "limit" in query_keys:
        query["limit"] = history_limit
    if "bucket_count" in query_keys:
        query["bucket_count"] = trend_bucket_count
    if not query:
        return path
    return f"{path}?{urlencode(query)}"


def fetch_json_endpoint(
    base_url: str,
    name: str,
    path: str,
    *,
    timeout: int,
) -> EndpointRead:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
            http_status = getattr(response, "status", None)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        payload = _load_json_object(body)
        return EndpointRead(
            name=name,
            path=path,
            status="fail",
            http_status=exc.code,
            payload=payload,
            error=f"HTTP {exc.code}: {_truncate(body)}",
        )
    except (TimeoutError, URLError, OSError) as exc:
        return EndpointRead(name=name, path=path, status="fail", error=str(exc))

    payload = _load_json_object(body)
    if payload is None:
        return EndpointRead(
            name=name,
            path=path,
            status="fail",
            http_status=http_status,
            error=f"response is not a JSON object: {_truncate(body)}",
        )

    return EndpointRead(
        name=name,
        path=path,
        status="ok",
        http_status=http_status,
        payload=payload,
    )


def collect_runtime_sample(
    base_url: str,
    *,
    lookback_hours: int,
    history_limit: int,
    include_ops_trends: bool = False,
    trend_bucket_count: int = DEFAULT_TREND_BUCKET_COUNT,
    timeout: int,
) -> RuntimeSample:
    endpoints: dict[str, EndpointRead] = {}
    endpoint_specs = list(RUNTIME_ENDPOINTS)
    if include_ops_trends:
        endpoint_specs.append(OPS_TRENDS_ENDPOINT)
    for name, path, query_keys in endpoint_specs:
        full_path = build_endpoint_path(
            path,
            query_keys,
            lookback_hours=lookback_hours,
            history_limit=history_limit,
            trend_bucket_count=trend_bucket_count,
        )
        endpoints[name] = fetch_json_endpoint(
            base_url,
            name,
            full_path,
            timeout=timeout,
        )
    return RuntimeSample(collected_at=_now_iso(), endpoints=endpoints)


def build_runtime_report(
    samples: list[RuntimeSample],
    *,
    base_url: str,
    fail_on_warning: bool,
) -> dict[str, Any]:
    endpoint_failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    readiness_status_counts: Counter[str] = Counter()
    alert_counts: Counter[str] = Counter()
    latest_server: dict[str, Any] | None = None
    latest_trend: dict[str, Any] | None = None

    for index, sample in enumerate(samples, start=1):
        for read in sample.endpoints.values():
            if not read.ok:
                endpoint_failures.append(
                    {
                        "sample": index,
                        "endpoint": read.name,
                        "path": read.path,
                        "http_status": read.http_status,
                        "error": read.error,
                    },
                )

        health_ready = sample.endpoints.get("health_ready")
        health_ready_status = _payload_status(health_ready)
        if health_ready and health_ready.ok and health_ready_status != "ready":
            endpoint_failures.append(
                {
                    "sample": index,
                    "endpoint": "health_ready",
                    "path": health_ready.path,
                    "http_status": health_ready.http_status,
                    "error": f"health readiness status is {health_ready_status!r}",
                },
            )

        overview_payload = _payload(sample.endpoints.get("ops_overview"))
        if overview_payload:
            server = overview_payload.get("server")
            if isinstance(server, dict):
                latest_server = _server_snapshot(server)
            for alert in _list_of_dicts(overview_payload.get("alerts")):
                code = str(alert.get("code") or "unknown")
                alert_counts[code] += 1
                warnings.append(
                    {
                        "sample": index,
                        "kind": "ops_alert",
                        "code": code,
                        "severity": alert.get("severity"),
                        "message": alert.get("message"),
                    },
                )

        history_payload = _payload(sample.endpoints.get("ops_history"))
        if history_payload:
            for item in _list_of_dicts(history_payload.get("failure_summary")):
                count = _as_int(item.get("count"))
                if count > 0:
                    warnings.append(
                        {
                            "sample": index,
                            "kind": "failure_summary",
                            "key": item.get("key"),
                            "count": count,
                        },
                    )

        trends_payload = _payload(sample.endpoints.get("ops_trends"))
        if trends_payload:
            latest_trend = _trend_snapshot(trends_payload)

        ops_readiness = sample.endpoints.get("ops_readiness")
        readiness_payload = _payload(ops_readiness)
        readiness_status = _readiness_status(readiness_payload)
        readiness_status_counts[readiness_status] += 1
        if ops_readiness and not ops_readiness.ok:
            continue
        if readiness_status == "blocked":
            endpoint_failures.append(
                {
                    "sample": index,
                    "endpoint": "ops_readiness",
                    "path": ops_readiness.path if ops_readiness else "/ops/readiness",
                    "http_status": ops_readiness.http_status if ops_readiness else None,
                    "error": "ops readiness status is blocked",
                },
            )
        elif readiness_status == "warning":
            warnings.append(
                {
                    "sample": index,
                    "kind": "readiness_warning",
                    "status": readiness_status,
                },
            )
        elif readiness_status == "unknown":
            endpoint_failures.append(
                {
                    "sample": index,
                    "endpoint": "ops_readiness",
                    "path": ops_readiness.path if ops_readiness else "/ops/readiness",
                    "http_status": ops_readiness.http_status if ops_readiness else None,
                    "error": "ops readiness status is missing or unknown",
                },
            )

    failed = bool(endpoint_failures) or (fail_on_warning and bool(warnings))
    return {
        "base_url": base_url,
        "sample_count": len(samples),
        "started_at": samples[0].collected_at if samples else None,
        "finished_at": samples[-1].collected_at if samples else None,
        "status": "fail" if failed else "ok",
        "fail_on_warning": fail_on_warning,
        "readiness_status_counts": dict(sorted(readiness_status_counts.items())),
        "alert_counts": dict(sorted(alert_counts.items())),
        "latest_server": latest_server,
        "latest_trend": latest_trend,
        "failures": endpoint_failures,
        "warnings": warnings,
    }


def run_runtime_check(
    *,
    base_url: str,
    samples: int,
    interval_seconds: float,
    lookback_hours: int,
    history_limit: int,
    include_ops_trends: bool,
    trend_bucket_count: int,
    timeout: int,
    fail_on_warning: bool,
) -> dict[str, Any]:
    collected: list[RuntimeSample] = []
    for index in range(samples):
        collected.append(
            collect_runtime_sample(
                base_url,
                lookback_hours=lookback_hours,
                history_limit=history_limit,
                include_ops_trends=include_ops_trends,
                trend_bucket_count=trend_bucket_count,
                timeout=timeout,
            ),
        )
        if index < samples - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)
    return build_runtime_report(
        collected,
        base_url=base_url,
        fail_on_warning=fail_on_warning,
    )


def write_ops_evidence_report(
    output_path: Path,
    *,
    base_url: str,
    lookback_hours: int,
    history_limit: int,
    include_ops_trends: bool,
    trend_bucket_count: int,
    timeout: int,
) -> dict[str, Any]:
    reads = export_ops_evidence.collect_ops_evidence(
        base_url,
        lookback_hours=lookback_hours,
        history_limit=history_limit,
        include_ops_trends=include_ops_trends,
        trend_bucket_count=trend_bucket_count,
        timeout=timeout,
    )
    report = export_ops_evidence.build_evidence_report(
        reads,
        base_url=base_url,
        lookback_hours=lookback_hours,
        history_limit=history_limit,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(encoded, encoding="utf-8")
    if export_ops_evidence.exit_code_for_report(report) != 0:
        failures = report.get("failures")
        raise OpsEvidenceExportError(
            "OPS evidence export returned a failing status while reading allowed "
            f"health/OPS endpoints: status={report.get('status')!r} failures={failures}",
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sample a running BaizeFinDB API and validate runtime health.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL, default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Number of runtime samples to collect, default: 3.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=30.0,
        help="Delay between samples, default: 30 seconds.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=f"OPS lookback window, default: {DEFAULT_LOOKBACK_HOURS}.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=20,
        help="OPS history event limit, default: 20.",
    )
    parser.add_argument(
        "--include-ops-trends",
        action="store_true",
        help="Also read the read-only /ops/trends endpoint and summarize latest buckets.",
    )
    parser.add_argument(
        "--trend-bucket-count",
        type=int,
        default=DEFAULT_TREND_BUCKET_COUNT,
        help=(
            f"OPS trend bucket count, 1-{MAX_TREND_BUCKET_COUNT}, "
            f"default: {DEFAULT_TREND_BUCKET_COUNT}."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="HTTP timeout per request in seconds, default: 5.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return a failing exit code when warnings or alerts are observed.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write the full JSON report.",
    )
    parser.add_argument(
        "--ops-evidence-output",
        type=Path,
        help=(
            "Optional path to write sanitized read-only OPS evidence using the same "
            "health/OPS endpoints as export_ops_evidence.py."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.samples < 1:
        print("[FAIL] --samples must be >= 1")
        return 2
    if args.lookback_hours < 1:
        print("[FAIL] --lookback-hours must be >= 1")
        return 2
    if args.history_limit < 1:
        print("[FAIL] --history-limit must be >= 1")
        return 2
    if args.trend_bucket_count < 1 or args.trend_bucket_count > MAX_TREND_BUCKET_COUNT:
        print(f"[FAIL] --trend-bucket-count must be between 1 and {MAX_TREND_BUCKET_COUNT}")
        return 2
    if args.timeout < 1:
        print("[FAIL] --timeout must be >= 1")
        return 2

    report = run_runtime_check(
        base_url=args.base_url,
        samples=args.samples,
        interval_seconds=max(args.interval_seconds, 0),
        lookback_hours=args.lookback_hours,
        history_limit=args.history_limit,
        include_ops_trends=args.include_ops_trends,
        trend_bucket_count=args.trend_bucket_count,
        timeout=args.timeout,
        fail_on_warning=args.fail_on_warning,
    )
    evidence_error = ""
    if args.ops_evidence_output:
        try:
            evidence_report = write_ops_evidence_report(
                args.ops_evidence_output,
                base_url=args.base_url,
                lookback_hours=args.lookback_hours,
                history_limit=args.history_limit,
                include_ops_trends=args.include_ops_trends,
                trend_bucket_count=args.trend_bucket_count,
                timeout=args.timeout,
            )
        except OpsEvidenceExportError as exc:
            evidence_error = str(exc)
            report["ops_evidence_output"] = str(args.ops_evidence_output)
            report["ops_evidence_error"] = evidence_error
        except OSError as exc:
            evidence_error = f"OPS evidence export failed while writing output: {exc}"
            report["ops_evidence_output"] = str(args.ops_evidence_output)
            report["ops_evidence_error"] = evidence_error
        else:
            report["ops_evidence_output"] = str(args.ops_evidence_output)
            report["ops_evidence_status"] = evidence_report.get("status")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(_format_report(report))
    if evidence_error:
        print(f"[FAIL] {evidence_error}", file=sys.stderr)
        return 1
    return 0 if report["status"] == "ok" else 1


def _format_report(report: dict[str, Any]) -> str:
    lines = [
        f"[{str(report['status']).upper()}] BaizeFinDB runtime check",
        f"base_url={report['base_url']}",
        f"samples={report['sample_count']}",
        f"readiness={report['readiness_status_counts']}",
        f"alerts={report['alert_counts']}",
    ]
    latest_server = report.get("latest_server")
    if latest_server:
        lines.append(f"server={latest_server}")
    latest_trend = report.get("latest_trend")
    if latest_trend:
        lines.append(f"trend={latest_trend}")
    if report.get("ops_evidence_output"):
        lines.append(f"ops_evidence_output={report['ops_evidence_output']}")
    if report.get("ops_evidence_status"):
        lines.append(f"ops_evidence_status={report['ops_evidence_status']}")
    if report.get("ops_evidence_error"):
        lines.append(f"ops_evidence_error={report['ops_evidence_error']}")
    for failure in report["failures"]:
        lines.append(
            "[FAIL] "
            f"sample={failure['sample']} endpoint={failure['endpoint']} "
            f"detail={failure['error']}",
        )
    for warning in report["warnings"][:20]:
        lines.append(f"[WARN] {warning}")
    if len(report["warnings"]) > 20:
        lines.append(f"[WARN] {len(report['warnings']) - 20} more warning(s)")
    return "\n".join(lines)


def _payload(read: EndpointRead | None) -> dict[str, Any] | None:
    if read is None or read.payload is None:
        return None
    return read.payload


def _payload_status(read: EndpointRead | None) -> str:
    payload = _payload(read)
    if not payload:
        return "unknown"
    return str(payload.get("status") or "unknown")


def _readiness_status(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "unknown"
    status = str(payload.get("status") or "unknown")
    if status in {"ready", "warning", "blocked"}:
        return status
    return "unknown"


def _server_snapshot(server: dict[str, Any]) -> dict[str, Any]:
    return {
        "process_uptime_seconds": server.get("process_uptime_seconds"),
        "disk_free_percent": server.get("disk_free_percent"),
        "cpu_usage_percent": server.get("cpu_usage_percent"),
        "memory_used_percent": server.get("memory_used_percent"),
        "is_disk_space_low": server.get("is_disk_space_low"),
        "is_cpu_pressure_high": server.get("is_cpu_pressure_high"),
        "is_memory_pressure_high": server.get("is_memory_pressure_high"),
    }


def _trend_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    buckets = _list_of_dicts(payload.get("buckets"))
    latest_bucket = buckets[-1] if buckets else {}
    return {
        "bucket_count": _as_int(payload.get("bucket_count")),
        "latest_bucket_started_at": latest_bucket.get("bucket_started_at"),
        "latest_bucket_finished_at": latest_bucket.get("bucket_finished_at"),
        "radar_scan_count": _as_int(latest_bucket.get("radar_scan_count")),
        "radar_failure_count": _as_int(latest_bucket.get("radar_failure_count")),
        "provider_fetch_unhealthy_count": _as_int(
            latest_bucket.get("provider_fetch_unhealthy_count"),
        ),
        "data_quality_unhealthy_count": _as_int(
            latest_bucket.get("data_quality_unhealthy_count"),
        ),
        "telegram_push_unhealthy_count": _as_int(
            latest_bucket.get("telegram_push_unhealthy_count"),
        ),
        "model_call_unhealthy_count": _as_int(
            latest_bucket.get("model_call_unhealthy_count"),
        ),
    }


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _load_json_object(body: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _truncate(text: str, *, limit: int = 700) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 15]}\n... truncated"


if __name__ == "__main__":
    sys.exit(main())
