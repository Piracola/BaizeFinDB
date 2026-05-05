import importlib.util
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "infra" / "scripts" / "check_tushare_anns_d_beat_enablement.py"
SPEC = importlib.util.spec_from_file_location("check_tushare_anns_d_beat_enablement", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
check_tushare_anns_d_beat_enablement = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_tushare_anns_d_beat_enablement
SPEC.loader.exec_module(check_tushare_anns_d_beat_enablement)


def test_default_no_token_behavior_is_offline_warning(monkeypatch, capsys) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_ANNS_D_BEAT_ENABLED", raising=False)
    monkeypatch.delenv("TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS", raising=False)

    exit_code = check_tushare_anns_d_beat_enablement.main([])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    by_id = {item["id"]: item for item in payload["checklist"]}

    assert exit_code == 0
    assert payload["status"] == "warn"
    assert payload["mode"] == "offline_no_token"
    assert payload["live_tushare_called"] is False
    assert payload["database_mutated"] is False
    assert "\\u" not in captured.out
    assert by_id["offline_sample_preflight"]["status"] == "pass"
    assert by_id["radar_risk_announcement_golden_cases"]["status"] == "pass"
    assert by_id["tushare_token"]["status"] == "warn"
    assert by_id["tushare_token"]["details"]["configured"] is False
    assert by_id["beat_enabled_state"]["status"] == "pass"
    assert by_id["readiness_live_data"]["details"]["checked"] is False


def test_enabled_env_behavior_is_visible_warning() -> None:
    payload = check_tushare_anns_d_beat_enablement.build_report(
        environ={
            "TUSHARE_TOKEN": "secret-token",
            "TUSHARE_ANNS_D_BEAT_ENABLED": "true",
            "TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS": "1800",
        }
    )
    by_id = {item["id"]: item for item in payload["checklist"]}

    assert payload["status"] == "warn"
    assert by_id["tushare_token"]["status"] == "pass"
    assert by_id["tushare_token"]["details"]["value"] == "redacted"
    assert by_id["beat_enabled_state"]["status"] == "warn"
    assert by_id["beat_enabled_state"]["details"]["enabled"] is True
    assert by_id["beat_interval"]["status"] == "pass"
    assert by_id["beat_interval"]["details"]["interval_seconds"] == 1800
    assert payload["safe_to_enable_beat"] is False


def test_readiness_opt_in_does_not_make_checklist_safe_without_live_verify(monkeypatch) -> None:
    def fake_fetch_json(url: str, timeout_seconds: float) -> dict[str, object]:
        assert url == "http://example.test/readiness"
        assert timeout_seconds == 1.5
        return {
            "status": "ready",
            "scheduler_enabled": False,
        }

    monkeypatch.setattr(check_tushare_anns_d_beat_enablement, "_fetch_json", fake_fetch_json)

    payload = check_tushare_anns_d_beat_enablement.build_report(
        environ={
            "TUSHARE_TOKEN": "secret-token",
            "TUSHARE_ANNS_D_BEAT_ENABLED": "false",
            "TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS": "1800",
        },
        check_readiness=True,
        readiness_url="http://example.test/readiness",
        timeout_seconds=1.5,
    )
    by_id = {item["id"]: item for item in payload["checklist"]}

    assert payload["mode"] == "readiness_opt_in"
    assert by_id["readiness_live_data"]["status"] == "pass"
    assert by_id["live_tushare_verify"]["status"] == "warn"
    assert payload["safe_to_enable_beat"] is False
    assert "secret-token" not in json.dumps(payload)


def test_disabled_env_behavior_uses_default_interval() -> None:
    payload = check_tushare_anns_d_beat_enablement.build_report(
        environ={"TUSHARE_ANNS_D_BEAT_ENABLED": "false"}
    )
    by_id = {item["id"]: item for item in payload["checklist"]}

    assert by_id["beat_enabled_state"]["status"] == "pass"
    assert by_id["beat_enabled_state"]["details"]["enabled"] is False
    assert by_id["beat_interval"]["status"] == "pass"
    assert by_id["beat_interval"]["details"]["interval_seconds"] == 3600
    assert by_id["beat_interval"]["details"]["source"] == "default"


def test_invalid_interval_fails_and_returns_nonzero(monkeypatch, capsys) -> None:
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS", "0")

    exit_code = check_tushare_anns_d_beat_enablement.main(
        ["--cases", str(check_tushare_anns_d_beat_enablement.DEFAULT_CASES_PATH)]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    by_id = {item["id"]: item for item in payload["checklist"]}

    assert exit_code == 1
    assert payload["status"] == "fail"
    assert by_id["beat_interval"]["status"] == "fail"
    assert "positive" in by_id["beat_interval"]["message"]


def test_json_output_writes_same_report_as_stdout(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "nested" / "tushare-beat-checklist.json"
    token_value = "dummy-redaction-value"
    monkeypatch.setenv("TUSHARE_TOKEN", token_value)

    exit_code = check_tushare_anns_d_beat_enablement.main(
        ["--json-output", str(output)]
    )

    captured = capsys.readouterr()
    stdout_payload = json.loads(captured.out)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert file_payload == stdout_payload
    assert output.read_text(encoding="utf-8") == captured.out
    assert token_value not in captured.out
    assert token_value not in output.read_text(encoding="utf-8")


def test_json_output_writes_failing_report_before_nonzero_exit(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "tushare-beat-checklist-fail.json"
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS", "0")

    exit_code = check_tushare_anns_d_beat_enablement.main(
        ["--json-output", str(output)]
    )

    captured = capsys.readouterr()
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in file_payload["checklist"]}
    assert exit_code == 1
    assert file_payload == json.loads(captured.out)
    assert file_payload["status"] == "fail"
    assert by_id["beat_interval"]["status"] == "fail"


def test_missing_radar_risk_cases_file_fails_checklist(tmp_path: Path) -> None:
    payload = check_tushare_anns_d_beat_enablement.build_report(
        environ={},
        radar_risk_cases_path=tmp_path / "missing-radar-cases.json",
    )
    by_id = {item["id"]: item for item in payload["checklist"]}

    assert payload["status"] == "fail"
    assert by_id["radar_risk_announcement_golden_cases"]["status"] == "fail"
    assert "FileNotFoundError" in by_id["radar_risk_announcement_golden_cases"][
        "details"
    ]["error"]


def test_cli_accepts_custom_radar_risk_cases_path(tmp_path: Path, capsys) -> None:
    case_path = tmp_path / "radar-risk-cases.json"
    case_path.write_text(
        json.dumps(
            [
                {
                    "name": "major_investigation_announcement_maps_to_risk_p0",
                    "case_type": "true_positive_major_risk",
                    "rows": [
                        {
                            "ann_date": "20260503",
                            "ts_code": "000001.SZ",
                            "name": "风险样例",
                            "title": "关于收到中国证监会立案调查通知书的公告",
                        }
                    ],
                    "expected": {
                        "status": "success",
                        "candidate_count": 1,
                        "priority_counts": {"P0": 1},
                        "signals": [
                            {
                                "priority": "P0",
                                "subject_type": "announcements",
                                "subject_code": "000001.SZ",
                                "subject_name": "关于收到中国证监会立案调查通知书的公告",
                                "risk_event_type": "major_announcement",
                                "severity": "major",
                                "announcement_keywords": ["立案调查"],
                                "rule_reasons": ["risk_event_type_major_announcement"],
                            }
                        ],
                    },
                },
                {
                    "name": "ordinary_announcements_do_not_create_radar_signals",
                    "case_type": "false_positive_guard",
                    "rows": [
                        {
                            "ann_date": "20260503",
                            "ts_code": "000004.SZ",
                            "name": "普通样例一",
                            "title": "董事会决议公告",
                        }
                    ],
                    "expected": {
                        "status": "no_data",
                        "candidate_count": 0,
                        "priority_counts": {},
                        "signals": [],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    exit_code = check_tushare_anns_d_beat_enablement.main(
        ["--radar-risk-cases", str(case_path)]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    by_id = {item["id"]: item for item in payload["checklist"]}
    assert exit_code == 0
    assert by_id["radar_risk_announcement_golden_cases"]["status"] == "pass"
    assert by_id["radar_risk_announcement_golden_cases"]["details"][
        "cases_path"
    ] == str(case_path)


def test_output_contract_contains_expected_gate_ids() -> None:
    payload = check_tushare_anns_d_beat_enablement.build_report(environ={})
    gate_ids = [item["id"] for item in payload["checklist"]]

    assert payload["endpoint"] == "anns_d"
    assert payload["generated_by"] == "check_tushare_anns_d_beat_enablement"
    assert payload["summary"] == {"pass": 4, "warn": 3, "fail": 0}
    assert payload["safe_to_enable_beat"] is False
    assert gate_ids == [
        "offline_sample_preflight",
        "radar_risk_announcement_golden_cases",
        "tushare_token",
        "beat_enabled_state",
        "beat_interval",
        "live_tushare_verify",
        "readiness_live_data",
    ]
    assert {item["status"] for item in payload["checklist"]} <= {"pass", "warn", "fail"}
