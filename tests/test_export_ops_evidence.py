import importlib.util
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "infra" / "scripts" / "export_ops_evidence.py"
SPEC = importlib.util.spec_from_file_location("export_ops_evidence", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
export_ops_evidence = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = export_ops_evidence
SPEC.loader.exec_module(export_ops_evidence)


def test_collect_ops_evidence_reads_only_allowed_endpoints(monkeypatch) -> None:
    calls = []

    def fake_fetch(base_url: str, name: str, path: str, *, timeout: int):
        calls.append((base_url, name, path, timeout))
        return export_ops_evidence.EndpointRead(
            name=name,
            path=path,
            status="ok",
            payload={"status": "ready" if name == "ops_readiness" else "ok"},
        )

    monkeypatch.setattr(export_ops_evidence, "fetch_json_endpoint", fake_fetch)

    reads = export_ops_evidence.collect_ops_evidence(
        "http://api.test",
        lookback_hours=12,
        history_limit=7,
        timeout=3,
    )

    assert [read.name for read in reads] == [
        "health",
        "health_ready",
        "ops_overview",
        "ops_history",
        "ops_readiness",
    ]
    assert [call[2] for call in calls] == [
        "/health",
        "/health/ready",
        "/ops/overview?lookback_hours=12",
        "/ops/history?lookback_hours=12&limit=7",
        "/ops/readiness?lookback_hours=12",
    ]
    assert all(call[3] == 3 for call in calls)


def test_collect_ops_evidence_optionally_reads_ops_trends(monkeypatch) -> None:
    calls = []

    def fake_fetch(base_url: str, name: str, path: str, *, timeout: int):
        calls.append((base_url, name, path, timeout))
        return export_ops_evidence.EndpointRead(
            name=name,
            path=path,
            status="ok",
            payload={"status": "ready" if name == "ops_readiness" else "ok"},
        )

    monkeypatch.setattr(export_ops_evidence, "fetch_json_endpoint", fake_fetch)

    reads = export_ops_evidence.collect_ops_evidence(
        "http://api.test",
        lookback_hours=12,
        history_limit=7,
        include_ops_trends=True,
        trend_bucket_count=6,
        timeout=3,
    )

    assert [read.name for read in reads] == [
        "health",
        "health_ready",
        "ops_overview",
        "ops_history",
        "ops_readiness",
        "ops_trends",
    ]
    assert calls[-1][2] == "/ops/trends?lookback_hours=12&bucket_count=6"


def test_ready_report_exits_zero_and_contains_required_sections() -> None:
    report = export_ops_evidence.build_evidence_report(
        _reads(readiness_status="ready"),
        base_url="http://api.test",
        lookback_hours=24,
        history_limit=20,
    )

    assert report["status"] == "ok"
    assert export_ops_evidence.exit_code_for_report(report) == 0
    assert report["summary"]["readiness_status"] == "ready"
    assert report["alerts"] == []
    assert report["readiness_checks"] == []
    assert report["failure_summary"] == []
    assert report["recent_events_count"] == 2
    assert len(report["recent_events"]) == 2
    assert report["request"]["allowed_endpoints"] == [
        "/health",
        "/health/ready",
        "/ops/overview",
        "/ops/history",
        "/ops/readiness",
    ]
    assert "ops_trends" not in report["snapshots"]


def test_opt_in_report_contains_sanitized_ops_trends_snapshot() -> None:
    reads = _reads(readiness_status="ready")
    reads.append(
        export_ops_evidence.EndpointRead(
            name="ops_trends",
            path="/ops/trends?lookback_hours=24&bucket_count=2",
            status="ok",
            payload={
                "bucket_count": 2,
                "buckets": [
                    {
                        "bucket_started_at": "2026-05-04T00:00:00+00:00",
                        "provider_url": "https://provider.example.test/raw",
                        "token": "secret-token",
                        "radar_scan_count": 1,
                    }
                ],
            },
        )
    )

    report = export_ops_evidence.build_evidence_report(
        reads,
        base_url="http://api.test",
        lookback_hours=24,
        history_limit=20,
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["request"]["allowed_endpoints"] == [
        "/health",
        "/health/ready",
        "/ops/overview",
        "/ops/history",
        "/ops/readiness",
        "/ops/trends",
    ]
    assert report["snapshots"]["ops_trends"]["buckets"][0]["provider_url"] == "<redacted>"
    assert report["snapshots"]["ops_trends"]["buckets"][0]["token"] == "<redacted>"
    assert "provider.example.test" not in encoded
    assert "https://" not in encoded
    assert "secret-token" not in encoded


def test_warning_report_is_non_fatal() -> None:
    report = export_ops_evidence.build_evidence_report(
        _reads(
            readiness_status="warning",
            checks=[
                {
                    "name": "provider_quality",
                    "status": "warning",
                    "message": "historical provider failures",
                    "metadata": {"source_url": "https://provider.example.test/raw"},
                },
            ],
            alerts=[
                {
                    "severity": "warning",
                    "code": "provider_failure_rate_high",
                    "message": "Warnings remain non-fatal",
                }
            ],
            failure_summary=[{"kind": "provider", "key": "failed", "count": 3}],
        ),
        base_url="http://api.test",
        lookback_hours=24,
        history_limit=20,
    )

    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "ok"
    assert report["summary"]["warning_non_fatal"] is True
    assert export_ops_evidence.exit_code_for_report(report) == 0
    assert report["alerts"][0]["code"] == "provider_failure_rate_high"
    assert report["readiness_checks"][0]["metadata"]["source_url"] == "<redacted>"
    assert "provider.example.test" not in encoded
    assert "https://" not in encoded


def test_blocked_report_exits_nonzero_after_report_build() -> None:
    report = export_ops_evidence.build_evidence_report(
        _reads(readiness_status="blocked"),
        base_url="http://api.test",
        lookback_hours=24,
        history_limit=20,
    )

    assert report["status"] == "blocked"
    assert report["summary"]["blocked"] is True
    assert export_ops_evidence.exit_code_for_report(report) == 1


def test_endpoint_read_failure_exits_nonzero_and_is_sanitized() -> None:
    reads = _reads(readiness_status="ready")
    reads[2] = export_ops_evidence.EndpointRead(
        name="ops_overview",
        path="/ops/overview?lookback_hours=24",
        status="fail",
        http_status=503,
        error=(
            "authorization=secret-token failed at "
            "https://api.example.test/ops?token=secret-token"
        ),
    )

    report = export_ops_evidence.build_evidence_report(
        reads,
        base_url="http://api.test",
        lookback_hours=24,
        history_limit=20,
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "error"
    assert report["summary"]["endpoint_failures_count"] == 1
    assert export_ops_evidence.exit_code_for_report(report) == 1
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "api.example.test" not in encoded


def test_endpoint_read_failure_takes_precedence_over_blocked_readiness() -> None:
    reads = _reads(readiness_status="blocked")
    reads[0] = export_ops_evidence.EndpointRead(
        name="health",
        path="/health",
        status="fail",
        http_status=503,
        error="health unavailable",
    )

    report = export_ops_evidence.build_evidence_report(
        reads,
        base_url="http://api.test",
        lookback_hours=24,
        history_limit=20,
    )

    assert report["status"] == "error"
    assert report["summary"]["readiness_status"] == "blocked"
    assert report["summary"]["blocked"] is True
    assert report["summary"]["endpoint_failures_count"] == 1
    assert export_ops_evidence.exit_code_for_report(report) == 1


def test_redaction_and_bounds_are_recursive() -> None:
    long_value = "safe " * 200
    payload = {
        "token": "secret-token",
        "safe": (
            "token=secret-token Bearer ABCDEFGHIJKLMNOPQRSTUVWX "
            "https://api.example.test/path"
        ),
        "nested": {
            "domain": "api.example.test",
            "notes": long_value,
            "rows": [{"source": "eastmoney", "text": "ok"} for _ in range(25)],
        },
        **{f"item_{index}": index for index in range(45)},
    }

    sanitized = export_ops_evidence.sanitize_value(payload)
    encoded = json.dumps(sanitized, ensure_ascii=False)

    assert sanitized["token"] == "<redacted>"
    assert sanitized["nested"]["domain"] == "<redacted>"
    assert sanitized["nested"]["notes"].endswith("...<truncated>")
    assert len(sanitized["nested"]["rows"]) == 21
    assert sanitized["nested"]["rows"][-1]["_truncated"] is True
    assert sanitized["_truncated"] is True
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "api.example.test" not in encoded


def test_main_prints_json_by_default(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        export_ops_evidence,
        "collect_ops_evidence",
        lambda *args, **kwargs: _reads(readiness_status="ready"),
    )

    exit_code = export_ops_evidence.main(["--base-url", "http://api.test"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["report_type"] == "ops_evidence"
    assert payload["status"] == "ok"


def test_main_writes_json_output_for_blocked_state(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        export_ops_evidence,
        "collect_ops_evidence",
        lambda *args, **kwargs: _reads(readiness_status="blocked"),
    )
    output_path = tmp_path / "ops-evidence.json"

    exit_code = export_ops_evidence.main(["--json-output", str(output_path)])
    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert captured.out == ""
    assert payload["status"] == "blocked"


def _reads(
    *,
    readiness_status: str,
    checks: list[dict[str, object]] | None = None,
    alerts: list[dict[str, object]] | None = None,
    failure_summary: list[dict[str, object]] | None = None,
):
    return [
        export_ops_evidence.EndpointRead(
            name="health",
            path="/health",
            status="ok",
            payload={"status": "ok"},
        ),
        export_ops_evidence.EndpointRead(
            name="health_ready",
            path="/health/ready",
            status="ok",
            payload={"status": "ready"},
        ),
        export_ops_evidence.EndpointRead(
            name="ops_overview",
            path="/ops/overview?lookback_hours=24",
            status="ok",
            payload={
                "server": {
                    "cpu_usage_percent": 12.5,
                    "memory_used_percent": 40.0,
                },
                "alerts": alerts or [],
            },
        ),
        export_ops_evidence.EndpointRead(
            name="ops_history",
            path="/ops/history?lookback_hours=24&limit=20",
            status="ok",
            payload={
                "failure_summary": failure_summary or [],
                "recent_events": [
                    {
                        "kind": "provider",
                        "status": "failed",
                        "title": "fetch failed",
                        "metadata": {"url": "https://api.example.test/raw"},
                    },
                    {
                        "kind": "data_quality",
                        "status": "warning",
                        "title": "missing fields",
                    },
                ],
            },
        ),
        export_ops_evidence.EndpointRead(
            name="ops_readiness",
            path="/ops/readiness?lookback_hours=24",
            status="ok",
            payload={"status": readiness_status, "checks": checks or []},
        ),
    ]
