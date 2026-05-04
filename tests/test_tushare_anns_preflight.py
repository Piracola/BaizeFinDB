import importlib.util
import json
import sys
from pathlib import Path

from app.providers.tushare_anns_preflight import validate_anns_d_preflight_cases

ROOT_DIR = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT_DIR / "golden_cases" / "tushare_anns_d_preflight.json"
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
