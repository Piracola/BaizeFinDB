import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "infra" / "scripts" / "server_monitor_check.py"
)
SPEC = importlib.util.spec_from_file_location("server_monitor_check", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_monitor_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_monitor_check
SPEC.loader.exec_module(server_monitor_check)


def test_build_monitor_summary_reports_ok() -> None:
    summary = server_monitor_check.build_monitor_summary(_runtime_report(status="ok"))

    assert summary["report_type"] == "server_monitor_summary"
    assert summary["status"] == "ok"
    assert summary["runtime_status"] == "ok"
    assert summary["summary"]["failure_count"] == 0
    assert summary["summary"]["warning_count"] == 0
    assert summary["summary"]["readiness_status_counts"] == {"ready": 1}
    assert "read-only monitor summary" in summary["boundary"]


def test_build_monitor_summary_reports_warning_without_hard_failure() -> None:
    summary = server_monitor_check.build_monitor_summary(
        _runtime_report(
            status="ok",
            warnings=[{"sample": 1, "kind": "readiness_warning", "status": "warning"}],
        )
    )

    assert summary["status"] == "warning"
    assert summary["runtime_status"] == "ok"
    assert summary["strict_warning_failure"] is False
    assert server_monitor_check.exit_code_for_monitor_report(
        summary,
        fail_on_warning=False,
    ) == 0
    assert server_monitor_check.exit_code_for_monitor_report(
        summary,
        fail_on_warning=True,
    ) == 1


def test_build_monitor_summary_marks_strict_warning_failure() -> None:
    summary = server_monitor_check.build_monitor_summary(
        _runtime_report(
            status="fail",
            fail_on_warning=True,
            warnings=[{"sample": 1, "kind": "readiness_warning", "status": "warning"}],
        )
    )

    assert summary["status"] == "warning"
    assert summary["runtime_status"] == "fail"
    assert summary["strict_warning_failure"] is True


def test_build_monitor_summary_reports_blocked_for_failures() -> None:
    summary = server_monitor_check.build_monitor_summary(
        _runtime_report(
            status="fail",
            failures=[
                {
                    "sample": 1,
                    "endpoint": "ops_readiness",
                    "path": "/ops/readiness?lookback_hours=24",
                    "error": "ops readiness status is blocked",
                }
            ],
        )
    )

    assert summary["status"] == "blocked"
    assert summary["summary"]["failure_count"] == 1
    assert server_monitor_check.exit_code_for_monitor_report(
        summary,
        fail_on_warning=False,
    ) == 1


def test_build_monitor_summary_bounds_failures_and_warnings() -> None:
    failures = [
        {"endpoint": f"endpoint_{index}", "path": "/x", "error": "failed"}
        for index in range(6)
    ]
    warnings = [{"kind": "warning", "index": index} for index in range(12)]

    summary = server_monitor_check.build_monitor_summary(
        _runtime_report(status="fail", failures=failures, warnings=warnings),
        top_failures=2,
        top_warnings=3,
    )

    assert len(summary["top_failures"]) == 2
    assert summary["top_failures"][1]["endpoint"] == "endpoint_1"
    assert len(summary["top_warnings"]) == 3
    assert summary["top_warnings"][2]["index"] == 2


def test_main_writes_compact_and_runtime_reports(monkeypatch, tmp_path: Path, capsys) -> None:
    calls = []

    def fake_run_runtime_check(**kwargs):
        calls.append(kwargs)
        return _runtime_report(status="ok")

    monkeypatch.setattr(
        server_monitor_check.server_runtime_check,
        "run_runtime_check",
        fake_run_runtime_check,
    )
    compact_output = tmp_path / "monitor.json"
    runtime_output = tmp_path / "runtime.json"

    exit_code = server_monitor_check.main(
        [
            "--base-url",
            "https://api.example.test",
            "--samples",
            "2",
            "--interval-seconds",
            "3",
            "--lookback-hours",
            "6",
            "--history-limit",
            "7",
            "--include-ops-trends",
            "--trend-bucket-count",
            "4",
            "--timeout",
            "9",
            "--json-output",
            str(compact_output),
            "--runtime-json-output",
            str(runtime_output),
        ]
    )
    captured = capsys.readouterr()
    compact_payload = json.loads(compact_output.read_text(encoding="utf-8"))
    runtime_payload = json.loads(runtime_output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert calls == [
        {
            "base_url": "https://api.example.test",
            "samples": 2,
            "interval_seconds": 3.0,
            "lookback_hours": 6,
            "history_limit": 7,
            "include_ops_trends": True,
            "trend_bucket_count": 4,
            "timeout": 9,
            "fail_on_warning": False,
        }
    ]
    assert compact_payload["status"] == "ok"
    assert runtime_payload["status"] == "ok"
    assert "json_output=" in captured.out


def test_main_writes_no_send_alert_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        server_monitor_check.server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(
            status="ok",
            warnings=[
                {
                    "sample": 1,
                    "kind": "ops_alert",
                    "code": "server_cpu_pressure_high",
                    "message": "CPU warning",
                }
            ],
        ),
    )
    compact_output = tmp_path / "monitor.json"
    alert_output = tmp_path / "alert.json"

    exit_code = server_monitor_check.main(
        [
            "--json-output",
            str(compact_output),
            "--alert-json-output",
            str(alert_output),
        ]
    )
    payload = json.loads(alert_output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["report_type"] == "server_alert_payload"
    assert payload["status"] == "warning"
    assert payload["severity"] == "warning"
    assert payload["should_notify"] is True
    assert payload["source_monitor_summary"]["path"] == str(compact_output)
    assert payload["items"][0]["code"] == "server_cpu_pressure_high"


def test_main_alert_payload_can_suppress_warning_notify(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        server_monitor_check.server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(
            status="ok",
            warnings=[
                {"sample": index, "kind": "ops_alert", "code": f"warning_{index}"}
                for index in range(3)
            ],
        ),
    )
    alert_output = tmp_path / "alert.json"

    exit_code = server_monitor_check.main(
        [
            "--alert-json-output",
            str(alert_output),
            "--alert-max-items",
            "1",
            "--suppress-warning-alert-notify",
        ]
    )
    payload = json.loads(alert_output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["should_notify"] is False
    assert len(payload["items"]) == 1
    assert payload["items_truncated"] is True


def test_main_alert_payload_can_include_ok_notify(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        server_monitor_check.server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(status="ok"),
    )
    alert_output = tmp_path / "alert.json"

    exit_code = server_monitor_check.main(
        ["--alert-json-output", str(alert_output), "--include-ok-alert"]
    )
    payload = json.loads(alert_output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["severity"] == "info"
    assert payload["should_notify"] is True


def test_main_rejects_invalid_alert_max_items_before_runtime(monkeypatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setattr(
        server_monitor_check.server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: calls.append(kwargs),
    )
    alert_output = tmp_path / "alert.json"

    exit_code = server_monitor_check.main(
        ["--alert-json-output", str(alert_output), "--alert-max-items", "51"]
    )

    assert exit_code == 2
    assert calls == []
    assert not alert_output.exists()


def test_main_reports_alert_payload_write_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        server_monitor_check.server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(status="ok"),
    )
    blocked_parent = tmp_path / "not-a-dir"
    blocked_parent.write_text("x", encoding="utf-8")
    alert_output = blocked_parent / "alert.json"

    exit_code = server_monitor_check.main(["--alert-json-output", str(alert_output)])

    assert exit_code == 2
    assert not alert_output.exists()


def test_main_returns_nonzero_for_strict_warning(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        server_monitor_check.server_runtime_check,
        "run_runtime_check",
        lambda **kwargs: _runtime_report(
            status="fail",
            fail_on_warning=True,
            warnings=[{"sample": 1, "kind": "readiness_warning", "status": "warning"}],
        ),
    )

    exit_code = server_monitor_check.main(
        ["--fail-on-warning", "--json-output", str(tmp_path / "monitor.json")]
    )

    assert exit_code == 1


def test_main_rejects_invalid_numeric_options(capsys) -> None:
    cases = [
        ["--samples", "0"],
        ["--samples", "21"],
        ["--lookback-hours", "0"],
        ["--history-limit", "0"],
        ["--trend-bucket-count", "0"],
        ["--trend-bucket-count", "49"],
        ["--timeout", "0"],
    ]

    for argv in cases:
        exit_code = server_monitor_check.main(argv)
        assert exit_code == 2

    captured = capsys.readouterr()
    assert "[FAIL]" in captured.out


def _runtime_report(
    *,
    status: str,
    fail_on_warning: bool = False,
    failures: list[dict[str, object]] | None = None,
    warnings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "base_url": "http://api.test",
        "sample_count": 1,
        "started_at": "2026-05-05T00:00:00+00:00",
        "finished_at": "2026-05-05T00:00:01+00:00",
        "status": status,
        "fail_on_warning": fail_on_warning,
        "readiness_status_counts": {"ready": 1},
        "alert_counts": {"server_cpu_pressure_high": 1} if warnings else {},
        "latest_server": {"cpu_usage_percent": 12.5},
        "latest_trend": {"bucket_count": 12, "radar_failure_count": 0},
        "failures": failures or [],
        "warnings": warnings or [],
    }
