import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "server_runtime_check.py"
)
SPEC = importlib.util.spec_from_file_location("server_runtime_check", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_runtime_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_runtime_check
SPEC.loader.exec_module(server_runtime_check)


def test_build_endpoint_path_adds_runtime_query_params() -> None:
    assert (
        server_runtime_check.build_endpoint_path(
            "/ops/history",
            ("lookback_hours", "limit"),
            lookback_hours=12,
            history_limit=5,
        )
        == "/ops/history?lookback_hours=12&limit=5"
    )

    assert (
        server_runtime_check.build_endpoint_path(
            "/health",
            (),
            lookback_hours=12,
            history_limit=5,
        )
        == "/health"
    )
    assert (
        server_runtime_check.build_endpoint_path(
            "/ops/trends",
            ("lookback_hours", "bucket_count"),
            lookback_hours=12,
            history_limit=5,
            trend_bucket_count=6,
        )
        == "/ops/trends?lookback_hours=12&bucket_count=6"
    )


def test_collect_runtime_sample_reads_only_runtime_endpoints(monkeypatch) -> None:
    calls = []

    def fake_fetch(base_url: str, name: str, path: str, *, timeout: int):
        calls.append((base_url, name, path, timeout))
        return server_runtime_check.EndpointRead(
            name=name,
            path=path,
            status="ok",
            payload={"status": "ready" if name.endswith("ready") else "ok"},
        )

    monkeypatch.setattr(server_runtime_check, "fetch_json_endpoint", fake_fetch)

    sample = server_runtime_check.collect_runtime_sample(
        "http://api.test",
        lookback_hours=24,
        history_limit=20,
        timeout=3,
    )

    assert set(sample.endpoints) == {
        "health",
        "health_ready",
        "ops_overview",
        "ops_history",
        "ops_readiness",
    }
    assert [call[2] for call in calls] == [
        "/health",
        "/health/ready",
        "/ops/overview?lookback_hours=24",
        "/ops/history?lookback_hours=24&limit=20",
        "/ops/readiness?lookback_hours=24",
    ]


def test_collect_runtime_sample_optionally_reads_ops_trends(monkeypatch) -> None:
    calls = []

    def fake_fetch(base_url: str, name: str, path: str, *, timeout: int):
        calls.append((base_url, name, path, timeout))
        return server_runtime_check.EndpointRead(
            name=name,
            path=path,
            status="ok",
            payload={"status": "ready" if name.endswith("ready") else "ok"},
        )

    monkeypatch.setattr(server_runtime_check, "fetch_json_endpoint", fake_fetch)

    sample = server_runtime_check.collect_runtime_sample(
        "http://api.test",
        lookback_hours=24,
        history_limit=20,
        include_ops_trends=True,
        trend_bucket_count=8,
        timeout=3,
    )

    assert set(sample.endpoints) == {
        "health",
        "health_ready",
        "ops_overview",
        "ops_history",
        "ops_readiness",
        "ops_trends",
    }
    assert calls[-1][2] == "/ops/trends?lookback_hours=24&bucket_count=8"


def test_runtime_report_passes_with_ready_samples() -> None:
    sample = _sample(
        readiness_status="ready",
        overview_alerts=[],
        failure_summary=[],
    )

    report = server_runtime_check.build_runtime_report(
        [sample],
        base_url="http://api.test",
        fail_on_warning=False,
    )

    assert report["status"] == "ok"
    assert report["failures"] == []
    assert report["warnings"] == []
    assert report["readiness_status_counts"] == {"ready": 1}
    assert report["latest_server"]["cpu_usage_percent"] == 12.5


def test_runtime_report_warns_on_ops_alerts_without_failing_by_default() -> None:
    sample = _sample(
        readiness_status="warning",
        overview_alerts=[
            {
                "severity": "warning",
                "code": "server_cpu_pressure_high",
                "message": "CPU pressure is high",
            },
        ],
        failure_summary=[{"kind": "provider", "key": "failed", "count": 2}],
    )

    report = server_runtime_check.build_runtime_report(
        [sample],
        base_url="http://api.test",
        fail_on_warning=False,
    )

    assert report["status"] == "ok"
    assert report["alert_counts"] == {"server_cpu_pressure_high": 1}
    assert {"sample": 1, "kind": "readiness_warning", "status": "warning"} in report[
        "warnings"
    ]
    assert any(warning["kind"] == "failure_summary" for warning in report["warnings"])


def test_runtime_report_summarizes_optional_ops_trends() -> None:
    sample = _sample(
        readiness_status="ready",
        overview_alerts=[],
        failure_summary=[],
        trend_buckets=[
            {
                "bucket_started_at": "2026-05-04T00:00:00+00:00",
                "bucket_finished_at": "2026-05-04T01:00:00+00:00",
                "radar_scan_count": 1,
                "radar_failure_count": 0,
                "provider_fetch_unhealthy_count": 0,
                "data_quality_unhealthy_count": 0,
                "telegram_push_unhealthy_count": 0,
                "model_call_unhealthy_count": 0,
            },
            {
                "bucket_started_at": "2026-05-04T01:00:00+00:00",
                "bucket_finished_at": "2026-05-04T02:00:00+00:00",
                "radar_scan_count": 2,
                "radar_failure_count": 1,
                "provider_fetch_unhealthy_count": 1,
                "data_quality_unhealthy_count": 1,
                "telegram_push_unhealthy_count": 1,
                "model_call_unhealthy_count": 1,
            },
        ],
    )

    report = server_runtime_check.build_runtime_report(
        [sample],
        base_url="http://api.test",
        fail_on_warning=False,
    )

    assert report["status"] == "ok"
    assert report["latest_trend"] == {
        "bucket_count": 2,
        "latest_bucket_started_at": "2026-05-04T01:00:00+00:00",
        "latest_bucket_finished_at": "2026-05-04T02:00:00+00:00",
        "radar_scan_count": 2,
        "radar_failure_count": 1,
        "provider_fetch_unhealthy_count": 1,
        "data_quality_unhealthy_count": 1,
        "telegram_push_unhealthy_count": 1,
        "model_call_unhealthy_count": 1,
    }


def test_runtime_report_fails_when_warning_is_strict() -> None:
    sample = _sample(
        readiness_status="warning",
        overview_alerts=[],
        failure_summary=[],
    )

    report = server_runtime_check.build_runtime_report(
        [sample],
        base_url="http://api.test",
        fail_on_warning=True,
    )

    assert report["status"] == "fail"


def test_runtime_report_fails_on_blocked_readiness() -> None:
    sample = _sample(
        readiness_status="blocked",
        overview_alerts=[],
        failure_summary=[],
    )

    report = server_runtime_check.build_runtime_report(
        [sample],
        base_url="http://api.test",
        fail_on_warning=False,
    )

    assert report["status"] == "fail"
    assert report["failures"][0]["endpoint"] == "ops_readiness"
    assert "blocked" in report["failures"][0]["error"]


def test_runtime_report_fails_when_endpoint_read_fails() -> None:
    sample = _sample(
        readiness_status="ready",
        overview_alerts=[],
        failure_summary=[],
    )
    endpoints = dict(sample.endpoints)
    endpoints["ops_overview"] = server_runtime_check.EndpointRead(
        name="ops_overview",
        path="/ops/overview?lookback_hours=24",
        status="fail",
        error="connection refused",
    )
    failed_sample = server_runtime_check.RuntimeSample(
        collected_at=sample.collected_at,
        endpoints=endpoints,
    )

    report = server_runtime_check.build_runtime_report(
        [failed_sample],
        base_url="http://api.test",
        fail_on_warning=False,
    )

    assert report["status"] == "fail"
    assert report["failures"][0]["endpoint"] == "ops_overview"


def test_runtime_report_does_not_duplicate_failed_readiness_endpoint() -> None:
    sample = _sample(
        readiness_status="ready",
        overview_alerts=[],
        failure_summary=[],
    )
    endpoints = dict(sample.endpoints)
    endpoints["ops_readiness"] = server_runtime_check.EndpointRead(
        name="ops_readiness",
        path="/ops/readiness?lookback_hours=24",
        status="fail",
        error="connection refused",
    )
    failed_sample = server_runtime_check.RuntimeSample(
        collected_at=sample.collected_at,
        endpoints=endpoints,
    )

    report = server_runtime_check.build_runtime_report(
        [failed_sample],
        base_url="http://api.test",
        fail_on_warning=False,
    )

    readiness_failures = [
        failure
        for failure in report["failures"]
        if failure["endpoint"] == "ops_readiness"
    ]
    assert len(readiness_failures) == 1


def test_fetch_json_endpoint_fails_for_non_json_response(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"not-json"

    monkeypatch.setattr(server_runtime_check, "urlopen", lambda *args, **kwargs: FakeResponse())

    result = server_runtime_check.fetch_json_endpoint(
        "http://api.test",
        "health",
        "/health",
        timeout=1,
    )

    assert result.status == "fail"
    assert not result.ok
    assert "not a JSON object" in result.error


def test_run_runtime_check_collects_requested_sample_count(monkeypatch) -> None:
    calls = []

    def fake_collect(
        base_url: str,
        *,
        lookback_hours: int,
        history_limit: int,
        include_ops_trends: bool,
        trend_bucket_count: int,
        timeout: int,
    ):
        calls.append((base_url, lookback_hours, history_limit, timeout))
        assert include_ops_trends is False
        assert trend_bucket_count == 12
        return _sample(readiness_status="ready", overview_alerts=[], failure_summary=[])

    monkeypatch.setattr(server_runtime_check, "collect_runtime_sample", fake_collect)
    monkeypatch.setattr(server_runtime_check.time, "sleep", lambda seconds: None)

    report = server_runtime_check.run_runtime_check(
        base_url="http://api.test",
        samples=3,
        interval_seconds=0.1,
        lookback_hours=12,
        history_limit=5,
        include_ops_trends=False,
        trend_bucket_count=12,
        timeout=2,
        fail_on_warning=False,
    )

    assert len(calls) == 3
    assert report["sample_count"] == 3
    assert report["readiness_status_counts"] == {"ready": 3}


def test_main_writes_ops_evidence_for_ready_runtime(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(status="ok"),
    )
    monkeypatch.setattr(
        server_runtime_check.export_ops_evidence,
        "collect_ops_evidence",
        lambda *args, **kwargs: _evidence_reads(readiness_status="ready"),
    )
    output_path = tmp_path / "ops-evidence.json"

    exit_code = server_runtime_check.main(["--ops-evidence-output", str(output_path)])
    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert captured.err == ""
    assert payload["report_type"] == "ops_evidence"
    assert payload["summary"]["readiness_status"] == "ready"
    assert "ops_evidence_status=ok" in captured.out


def test_main_writes_ops_evidence_for_warning_runtime(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(
            status="ok",
            warnings=[{"sample": 1, "kind": "readiness_warning", "status": "warning"}],
        ),
    )
    monkeypatch.setattr(
        server_runtime_check.export_ops_evidence,
        "collect_ops_evidence",
        lambda *args, **kwargs: _evidence_reads(readiness_status="warning"),
    )
    output_path = tmp_path / "ops-evidence.json"

    exit_code = server_runtime_check.main(["--ops-evidence-output", str(output_path)])
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["summary"]["warning_non_fatal"] is True


def test_main_writes_ops_evidence_for_blocked_runtime(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(
            status="fail",
            failures=[
                {
                    "sample": 1,
                    "endpoint": "ops_readiness",
                    "path": "/ops/readiness?lookback_hours=24",
                    "http_status": 200,
                    "error": "ops readiness status is blocked",
                },
            ],
        ),
    )
    monkeypatch.setattr(
        server_runtime_check.export_ops_evidence,
        "collect_ops_evidence",
        lambda *args, **kwargs: _evidence_reads(readiness_status="blocked"),
    )
    output_path = tmp_path / "ops-evidence.json"

    exit_code = server_runtime_check.main(["--ops-evidence-output", str(output_path)])
    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert "OPS evidence export returned a failing status" in captured.err
    assert payload["status"] == "blocked"
    assert payload["summary"]["blocked"] is True
    assert "ops_evidence_error=" in captured.out


def test_main_fails_when_ops_evidence_is_blocked_even_if_runtime_is_ok(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(status="ok"),
    )
    monkeypatch.setattr(
        server_runtime_check.export_ops_evidence,
        "collect_ops_evidence",
        lambda *args, **kwargs: _evidence_reads(readiness_status="blocked"),
    )
    output_path = tmp_path / "ops-evidence.json"

    exit_code = server_runtime_check.main(["--ops-evidence-output", str(output_path)])
    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert "OPS evidence export returned a failing status" in captured.err
    assert "ops_evidence_error=" in captured.out


def test_main_fails_when_ops_evidence_export_fails(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(status="ok"),
    )
    reads = _evidence_reads(readiness_status="ready")
    reads[0] = server_runtime_check.export_ops_evidence.EndpointRead(
        name="health",
        path="/health",
        status="fail",
        http_status=503,
        error="health unavailable",
    )
    monkeypatch.setattr(
        server_runtime_check.export_ops_evidence,
        "collect_ops_evidence",
        lambda *args, **kwargs: reads,
    )
    output_path = tmp_path / "ops-evidence.json"

    exit_code = server_runtime_check.main(["--ops-evidence-output", str(output_path)])
    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert payload["status"] == "error"
    assert "OPS evidence export returned a failing status" in captured.err
    assert "ops_evidence_error=" in captured.out


def _sample(
    *,
    readiness_status: str,
    overview_alerts: list[dict[str, object]],
    failure_summary: list[dict[str, object]],
    trend_buckets: list[dict[str, object]] | None = None,
):
    endpoints = {
        "health": server_runtime_check.EndpointRead(
            name="health",
            path="/health",
            status="ok",
            payload={"status": "ok"},
        ),
        "health_ready": server_runtime_check.EndpointRead(
            name="health_ready",
            path="/health/ready",
            status="ok",
            payload={"status": "ready"},
        ),
        "ops_overview": server_runtime_check.EndpointRead(
            name="ops_overview",
            path="/ops/overview?lookback_hours=24",
            status="ok",
            payload={
                "server": {
                    "process_uptime_seconds": 600.0,
                    "disk_free_percent": 80.0,
                    "cpu_usage_percent": 12.5,
                    "memory_used_percent": 40.0,
                    "is_disk_space_low": False,
                    "is_cpu_pressure_high": False,
                    "is_memory_pressure_high": False,
                },
                "alerts": overview_alerts,
            },
        ),
        "ops_history": server_runtime_check.EndpointRead(
            name="ops_history",
            path="/ops/history?lookback_hours=24&limit=20",
            status="ok",
            payload={"failure_summary": failure_summary},
        ),
        "ops_readiness": server_runtime_check.EndpointRead(
            name="ops_readiness",
            path="/ops/readiness?lookback_hours=24",
            status="ok",
            payload={"status": readiness_status, "checks": []},
        ),
    }
    if trend_buckets is not None:
        endpoints["ops_trends"] = server_runtime_check.EndpointRead(
            name="ops_trends",
            path="/ops/trends?lookback_hours=24&bucket_count=2",
            status="ok",
            payload={"bucket_count": len(trend_buckets), "buckets": trend_buckets},
        )
    return server_runtime_check.RuntimeSample(
        collected_at="2026-05-04T00:00:00+00:00",
        endpoints=endpoints,
    )


def _runtime_report(
    *,
    status: str,
    failures: list[dict[str, object]] | None = None,
    warnings: list[dict[str, object]] | None = None,
):
    return {
        "base_url": "http://api.test",
        "sample_count": 1,
        "started_at": "2026-05-04T00:00:00+00:00",
        "finished_at": "2026-05-04T00:00:00+00:00",
        "status": status,
        "fail_on_warning": False,
        "readiness_status_counts": {"ready": 1},
        "alert_counts": {},
        "latest_server": None,
        "latest_trend": None,
        "failures": failures or [],
        "warnings": warnings or [],
    }


def _evidence_reads(*, readiness_status: str):
    return [
        server_runtime_check.export_ops_evidence.EndpointRead(
            name="health",
            path="/health",
            status="ok",
            payload={"status": "ok"},
        ),
        server_runtime_check.export_ops_evidence.EndpointRead(
            name="health_ready",
            path="/health/ready",
            status="ok",
            payload={"status": "ready"},
        ),
        server_runtime_check.export_ops_evidence.EndpointRead(
            name="ops_overview",
            path="/ops/overview?lookback_hours=24",
            status="ok",
            payload={"alerts": []},
        ),
        server_runtime_check.export_ops_evidence.EndpointRead(
            name="ops_history",
            path="/ops/history?lookback_hours=24&limit=20",
            status="ok",
            payload={"failure_summary": [], "recent_events": []},
        ),
        server_runtime_check.export_ops_evidence.EndpointRead(
            name="ops_readiness",
            path="/ops/readiness?lookback_hours=24",
            status="ok",
            payload={"status": readiness_status, "checks": []},
        ),
    ]
