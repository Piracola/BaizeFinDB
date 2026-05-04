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


def test_output_contract_contains_expected_gate_ids() -> None:
    payload = check_tushare_anns_d_beat_enablement.build_report(environ={})
    gate_ids = [item["id"] for item in payload["checklist"]]

    assert payload["endpoint"] == "anns_d"
    assert payload["generated_by"] == "check_tushare_anns_d_beat_enablement"
    assert payload["summary"] == {"pass": 3, "warn": 3, "fail": 0}
    assert payload["safe_to_enable_beat"] is False
    assert gate_ids == [
        "offline_sample_preflight",
        "tushare_token",
        "beat_enabled_state",
        "beat_interval",
        "live_tushare_verify",
        "readiness_live_data",
    ]
    assert {item["status"] for item in payload["checklist"]} <= {"pass", "warn", "fail"}
