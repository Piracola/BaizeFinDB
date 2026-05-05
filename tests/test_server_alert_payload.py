import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "infra" / "scripts" / "server_alert_payload.py"
)
SPEC = importlib.util.spec_from_file_location("server_alert_payload", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_alert_payload = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_alert_payload
SPEC.loader.exec_module(server_alert_payload)


def test_build_alert_payload_maps_ok_to_info_without_notification() -> None:
    payload = server_alert_payload.build_alert_payload(_monitor_summary(status="ok"))

    assert payload["report_type"] == "server_alert_payload"
    assert payload["status"] == "ok"
    assert payload["severity"] == "info"
    assert payload["should_notify"] is False
    assert payload["items"] == []
    assert payload["dedupe_key"].startswith("baizefindb:ok:")
    assert server_alert_payload.exit_code_for_payload(payload) == 0
    assert "does not call API" in payload["boundary"]


def test_build_alert_payload_can_include_ok_notification() -> None:
    payload = server_alert_payload.build_alert_payload(
        _monitor_summary(status="ok"),
        include_ok=True,
    )

    assert payload["severity"] == "info"
    assert payload["should_notify"] is True
    assert server_alert_payload.exit_code_for_payload(payload, fail_on_notify=True) == 1


def test_build_alert_payload_maps_warning_to_notification_by_default() -> None:
    payload = server_alert_payload.build_alert_payload(
        _monitor_summary(
            status="warning",
            runtime_status="ok",
            warnings=[
                {
                    "sample": 1,
                    "kind": "ops_alert",
                    "code": "server_cpu_pressure_high",
                    "message": "CPU warning",
                }
            ],
        )
    )

    assert payload["severity"] == "warning"
    assert payload["should_notify"] is True
    assert payload["items"][0]["severity"] == "warning"
    assert payload["items"][0]["code"] == "server_cpu_pressure_high"
    assert server_alert_payload.exit_code_for_payload(payload) == 0
    assert server_alert_payload.exit_code_for_payload(payload, fail_on_notify=True) == 1


def test_build_alert_payload_can_suppress_warning_notification() -> None:
    payload = server_alert_payload.build_alert_payload(
        _monitor_summary(
            status="warning",
            warnings=[{"sample": 1, "kind": "readiness_warning", "status": "warning"}],
        ),
        suppress_warning_notify=True,
    )

    assert payload["severity"] == "warning"
    assert payload["should_notify"] is False
    assert server_alert_payload.exit_code_for_payload(payload, fail_on_notify=True) == 0


def test_build_alert_payload_maps_blocked_to_critical_exit() -> None:
    payload = server_alert_payload.build_alert_payload(
        _monitor_summary(
            status="blocked",
            runtime_status="fail",
            failures=[
                {
                    "sample": 1,
                    "endpoint": "ops_readiness",
                    "path": "/ops/readiness?lookback_hours=24",
                    "http_status": 200,
                    "error": "ops readiness status is blocked",
                }
            ],
        )
    )

    assert payload["severity"] == "critical"
    assert payload["should_notify"] is True
    assert payload["items"][0]["severity"] == "critical"
    assert payload["items"][0]["endpoint"] == "ops_readiness"
    assert server_alert_payload.exit_code_for_payload(payload) == 1


def test_build_alert_payload_bounds_items_and_sanitizes_text() -> None:
    warnings = [
        {
            "sample": index,
            "kind": "ops_alert",
            "code": "provider_warning",
            "message": (
                "token=secret-token "
                "https://provider.example.test/raw "
                + "x" * 700
            ),
        }
        for index in range(12)
    ]

    payload = server_alert_payload.build_alert_payload(
        _monitor_summary(status="warning", warnings=warnings),
        max_items=3,
    )
    encoded = json.dumps(payload, ensure_ascii=False)

    assert len(payload["items"]) == 3
    assert payload["items_truncated"] is True
    assert "secret-token" not in encoded
    assert "provider.example.test" not in encoded
    assert "https://" not in encoded
    assert "<truncated>" in encoded


def test_build_alert_payload_rejects_invalid_monitor_summary() -> None:
    invalid = {"report_type": "server_monitor_summary", "status": "bad", "summary": {}}

    try:
        server_alert_payload.build_alert_payload(invalid)
    except server_alert_payload.AlertPayloadInputError as exc:
        assert "status must be one of" in str(exc)
    else:
        raise AssertionError("expected invalid monitor summary to fail")


def test_load_monitor_summary_rejects_missing_file(tmp_path: Path) -> None:
    try:
        server_alert_payload.load_monitor_summary(tmp_path / "missing.json")
    except server_alert_payload.AlertPayloadInputError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("expected missing file to fail")


def test_main_writes_json_output_for_warning(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "monitor.json"
    output_path = tmp_path / "alert.json"
    input_path.write_text(
        json.dumps(
            _monitor_summary(
                status="warning",
                warnings=[{"sample": 1, "kind": "readiness_warning", "status": "warning"}],
            )
        ),
        encoding="utf-8",
    )

    exit_code = server_alert_payload.main(
        [str(input_path), "--json-output", str(output_path)]
    )
    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["severity"] == "warning"
    assert payload["should_notify"] is True
    assert "[WARNING]" in captured.out
    assert "json_output=" in captured.out


def test_main_invalid_input_does_not_write_output(tmp_path: Path) -> None:
    input_path = tmp_path / "monitor.json"
    output_path = tmp_path / "alert.json"
    input_path.write_text("{bad json", encoding="utf-8")

    exit_code = server_alert_payload.main(
        [str(input_path), "--json-output", str(output_path)]
    )

    assert exit_code == 2
    assert not output_path.exists()


def test_main_rejects_missing_path_and_bad_max_items(tmp_path: Path) -> None:
    input_path = tmp_path / "monitor.json"
    input_path.write_text(json.dumps(_monitor_summary(status="ok")), encoding="utf-8")

    assert server_alert_payload.main([]) == 2
    assert server_alert_payload.main([str(input_path), "--max-items", "-1"]) == 2
    assert server_alert_payload.main([str(input_path), "--max-items", "51"]) == 2


def _monitor_summary(
    *,
    status: str,
    runtime_status: str | None = None,
    failures: list[dict[str, object]] | None = None,
    warnings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    failures = failures or []
    warnings = warnings or []
    if runtime_status is None:
        runtime_status = "fail" if status == "blocked" else "ok"
    return {
        "report_type": "server_monitor_summary",
        "generated_at": "2026-05-05T00:00:00+00:00",
        "status": status,
        "runtime_status": runtime_status,
        "strict_warning_failure": False,
        "base_url": "https://api.example.test",
        "sample_count": 1,
        "started_at": "2026-05-05T00:00:00+00:00",
        "finished_at": "2026-05-05T00:00:01+00:00",
        "summary": {
            "failure_count": len(failures),
            "warning_count": len(warnings),
            "readiness_status_counts": {"ready": 1},
            "alert_counts": {"server_cpu_pressure_high": 1} if warnings else {},
            "latest_server": {"cpu_usage_percent": 12.5},
            "latest_trend": {"bucket_count": 12, "radar_failure_count": 0},
        },
        "top_failures": failures,
        "top_warnings": warnings,
        "boundary": "read-only monitor summary",
    }
