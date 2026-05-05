import importlib.util
import json
import sys
from pathlib import Path

from app.providers.tushare_anns_preflight import (
    validate_anns_d_preflight_cases,
    validate_radar_risk_announcement_golden_cases,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT_DIR / "golden_cases" / "tushare_anns_d_preflight.json"
RADAR_RISK_CASE_PATH = ROOT_DIR / "golden_cases" / "radar_m5_risk_announcements.json"
SCRIPT_PATH = ROOT_DIR / "infra" / "scripts" / "verify_tushare_anns_d_preflight.py"
SPEC = importlib.util.spec_from_file_location("verify_tushare_anns_d_preflight", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
verify_tushare_anns_d_preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify_tushare_anns_d_preflight
SPEC.loader.exec_module(verify_tushare_anns_d_preflight)


def test_default_golden_cases_pass_preflight() -> None:
    cases = json.loads(CASE_PATH.read_text(encoding="utf-8"))

    report = validate_anns_d_preflight_cases(cases)

    assert report.ok
    assert report.endpoint == "anns_d"
    assert report.required_fields == ["ann_date", "ts_code", "title"]
    assert {result.case_id: result.actual_risk_priority for result in report.results} == {
        "major-risk-investigation-p0": "P0",
        "ordinary-board-resolution-no-risk": None,
    }
    major = next(
        result for result in report.results if result.case_id == "major-risk-investigation-p0"
    )
    assert "立案调查" in major.matched_keywords


def test_missing_required_field_fails_preflight() -> None:
    report = validate_anns_d_preflight_cases(
        [
            {
                "case_id": "missing-title",
                "expected_risk_priority": "none",
                "row": {
                    "ann_date": "20260503",
                    "ts_code": "000002.SZ",
                    "name": "普通样例",
                },
            },
            {
                "case_id": "major-risk-investigation-p0",
                "expected_risk_priority": "P0",
                "row": {
                    "ann_date": "20260503",
                    "ts_code": "000001.SZ",
                    "title": "关于收到中国证监会立案调查通知书的公告",
                },
            },
        ]
    )

    assert not report.ok
    assert {
        "case_id": "missing-title",
        "code": "missing_required_field",
        "message": "required normalized anns_d field is missing or empty: title",
    } in [issue.__dict__ for issue in report.issues]


def test_false_positive_expectation_fails_preflight() -> None:
    report = validate_anns_d_preflight_cases(
        [
            {
                "case_id": "ordinary-labeled-but-risky-title",
                "expected_risk_priority": "none",
                "row": {
                    "ann_date": "20260503",
                    "ts_code": "000001.SZ",
                    "title": "关于收到中国证监会立案调查通知书的公告",
                },
            },
            {
                "case_id": "major-risk-investigation-p0",
                "expected_risk_priority": "P0",
                "row": {
                    "ann_date": "20260503",
                    "ts_code": "000001.SZ",
                    "title": "关于收到中国证监会立案调查通知书的公告",
                },
            },
        ]
    )

    assert not report.ok
    assert any(issue.code == "risk_false_positive_mismatch" for issue in report.issues)


def test_true_positive_expectation_fails_preflight() -> None:
    report = validate_anns_d_preflight_cases(
        [
            {
                "case_id": "major-risk-labeled-but-ordinary-title",
                "expected_risk_priority": "P0",
                "row": {
                    "ann_date": "20260503",
                    "ts_code": "SAMPLE-P0.SZ",
                    "title": "董事会决议公告",
                },
            },
            {
                "case_id": "ordinary-board-resolution-no-risk",
                "expected_risk_priority": "none",
                "row": {
                    "ann_date": "20260503",
                    "ts_code": "SAMPLE-NONE.SZ",
                    "title": "董事会决议公告",
                },
            },
        ]
    )

    assert not report.ok
    assert any(issue.code == "risk_true_positive_mismatch" for issue in report.issues)


def test_unsupported_expected_priority_fails_preflight() -> None:
    report = validate_anns_d_preflight_cases(
        [
            {
                "case_id": "unsupported-priority",
                "expected_risk_priority": "P1",
                "row": {
                    "ann_date": "20260503",
                    "ts_code": "SAMPLE-NONE.SZ",
                    "title": "董事会决议公告",
                },
            },
            {
                "case_id": "major-risk-investigation-p0",
                "expected_risk_priority": "P0",
                "row": {
                    "ann_date": "20260503",
                    "ts_code": "SAMPLE-P0.SZ",
                    "title": "关于收到中国证监会立案调查通知书的公告",
                },
            },
        ]
    )

    assert not report.ok
    assert any(issue.code == "unsupported_expected_risk_priority" for issue in report.issues)


def test_default_radar_risk_golden_cases_pass_preflight() -> None:
    cases = json.loads(RADAR_RISK_CASE_PATH.read_text(encoding="utf-8"))

    report = validate_radar_risk_announcement_golden_cases(cases)

    assert report.ok
    assert report.endpoint == "anns_d"
    assert report.case_count == 3
    by_case = {result.case_id: result for result in report.results}
    investigation = by_case["major_investigation_announcement_maps_to_risk_p0"]
    assert investigation.actual_status == "success"
    assert investigation.actual_candidate_count == 1
    assert investigation.actual_priority_counts == {"P0": 1}
    assert investigation.signals[0].risk_event_type == "major_announcement"
    assert "立案调查" in investigation.signals[0].announcement_keywords
    ordinary = by_case["ordinary_announcements_do_not_create_radar_signals"]
    assert ordinary.actual_status == "no_data"
    assert ordinary.actual_candidate_count == 0


def test_radar_risk_golden_case_false_positive_fails() -> None:
    report = validate_radar_risk_announcement_golden_cases(
        [
            {
                "name": "ordinary_expected_but_risky_title",
                "rows": [
                    {
                        "ann_date": "20260503",
                        "ts_code": "000001.SZ",
                        "name": "风险样例",
                        "title": "关于收到中国证监会立案调查通知书的公告",
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
    )

    assert not report.ok
    assert any(issue.code == "radar_status_mismatch" for issue in report.issues)
    assert any(
        issue.code == "radar_candidate_count_mismatch" for issue in report.issues
    )


def test_radar_risk_golden_case_true_positive_drift_fails() -> None:
    report = validate_radar_risk_announcement_golden_cases(
        [
            {
                "name": "risk_expected_but_ordinary_title",
                "rows": [
                    {
                        "ann_date": "20260503",
                        "ts_code": "000001.SZ",
                        "name": "普通样例",
                        "title": "董事会决议公告",
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
                            "subject_name": "董事会决议公告",
                            "risk_event_type": "major_announcement",
                            "severity": "major",
                            "announcement_keywords": ["立案调查"],
                            "rule_reasons": ["risk_event_type_major_announcement"],
                        }
                    ],
                },
            }
        ]
    )

    assert not report.ok
    assert any(issue.code == "expected_signal_missing" for issue in report.issues)
    assert any(issue.code == "radar_status_mismatch" for issue in report.issues)


def test_radar_risk_golden_case_shape_errors_fail() -> None:
    report = validate_radar_risk_announcement_golden_cases(
        [{"name": "bad-shape", "rows": {}, "expected": []}]
    )

    assert not report.ok
    assert {issue.code for issue in report.issues} >= {
        "invalid_rows",
        "invalid_expected",
        "unsupported_expected_status",
        "invalid_expected_candidate_count",
        "invalid_expected_priority_counts",
        "invalid_expected_signals",
    }


def test_cli_reports_default_preflight_success(capsys) -> None:
    exit_code = verify_tushare_anns_d_preflight.main([])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["mode"] == "offline_no_token"
    assert "\\u7acb\\u6848\\u8c03\\u67e5" in captured.out


def test_cli_returns_nonzero_for_invalid_case_file(tmp_path: Path, capsys) -> None:
    case_path = tmp_path / "invalid.json"
    case_path.write_text("{}", encoding="utf-8")

    exit_code = verify_tushare_anns_d_preflight.main(["--cases", str(case_path)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["status"] == "fail"
    assert "must contain a JSON array" in payload["error"]
