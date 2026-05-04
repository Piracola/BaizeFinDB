from dataclasses import dataclass

from app.providers.tushare import TUSHARE_ENDPOINTS
from app.radar.schemas import RadarPriority
from app.radar.service import classify_tushare_announcement_risk

EXPECTED_NO_RISK_SIGNAL = "none"
EXPECTED_RISK_P0 = "P0"


@dataclass(frozen=True)
class PreflightIssue:
    case_id: str
    code: str
    message: str


@dataclass(frozen=True)
class PreflightCaseResult:
    case_id: str
    expected_risk_priority: str
    actual_risk_priority: str | None
    matched_keywords: list[str]
    missing_required_fields: list[str]


@dataclass(frozen=True)
class PreflightReport:
    status: str
    endpoint: str
    required_fields: list[str]
    case_count: int
    results: list[PreflightCaseResult]
    issues: list[PreflightIssue]

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "endpoint": self.endpoint,
            "required_fields": self.required_fields,
            "case_count": self.case_count,
            "results": [
                {
                    "case_id": result.case_id,
                    "expected_risk_priority": result.expected_risk_priority,
                    "actual_risk_priority": result.actual_risk_priority,
                    "matched_keywords": result.matched_keywords,
                    "missing_required_fields": result.missing_required_fields,
                }
                for result in self.results
            ],
            "issues": [
                {
                    "case_id": issue.case_id,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in self.issues
            ],
        }


def validate_anns_d_preflight_cases(cases: list[dict[str, object]]) -> PreflightReport:
    spec = TUSHARE_ENDPOINTS["anns_d"]
    required_fields = list(spec.required_fields)
    issues: list[PreflightIssue] = []
    results: list[PreflightCaseResult] = []
    saw_expected_p0 = False
    saw_expected_no_signal = False

    for index, case in enumerate(cases, start=1):
        case_id = _text(case.get("case_id"), f"case-{index}")
        expected = _expected_priority(case)
        unsupported_expected = _unsupported_expected_priority(expected)
        normalized_expected = _normalized_expected_priority(expected)
        if unsupported_expected is None and normalized_expected == EXPECTED_RISK_P0:
            saw_expected_p0 = True
        if unsupported_expected is None and normalized_expected == EXPECTED_NO_RISK_SIGNAL:
            saw_expected_no_signal = True

        if unsupported_expected is not None:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="unsupported_expected_risk_priority",
                    message=(
                        "expected_risk_priority must be either P0 or none: "
                        f"{unsupported_expected}"
                    ),
                )
            )

        row = case.get("row")
        if not isinstance(row, dict):
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="invalid_row",
                    message="case row must be an object",
                )
            )
            continue

        missing_fields = _missing_required_fields(row, required_fields)
        for field in missing_fields:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="missing_required_field",
                    message=f"required normalized anns_d field is missing or empty: {field}",
                )
            )

        metrics, rule_result = classify_tushare_announcement_risk(row)
        actual_priority = rule_result.priority.value if rule_result is not None else None
        results.append(
            PreflightCaseResult(
                case_id=case_id,
                expected_risk_priority=normalized_expected,
                actual_risk_priority=actual_priority,
                matched_keywords=_string_list(metrics.get("announcement_keywords")),
                missing_required_fields=missing_fields,
            )
        )

        if unsupported_expected is not None:
            continue

        if normalized_expected == EXPECTED_RISK_P0 and actual_priority != RadarPriority.P0.value:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="risk_true_positive_mismatch",
                    message="major-risk announcement did not map to risk P0",
                )
            )
        elif normalized_expected == EXPECTED_NO_RISK_SIGNAL and actual_priority is not None:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="risk_false_positive_mismatch",
                    message="ordinary announcement unexpectedly produced a risk signal",
                )
            )

    if not saw_expected_p0:
        issues.append(
            PreflightIssue(
                case_id="__suite__",
                code="missing_p0_expectation",
                message="preflight cases must include at least one expected risk P0 sample",
            )
        )
    if not saw_expected_no_signal:
        issues.append(
            PreflightIssue(
                case_id="__suite__",
                code="missing_no_signal_expectation",
                message="preflight cases must include at least one ordinary no-risk sample",
            )
        )

    return PreflightReport(
        status="ok" if not issues else "fail",
        endpoint="anns_d",
        required_fields=required_fields,
        case_count=len(cases),
        results=results,
        issues=issues,
    )


def _expected_priority(case: dict[str, object]) -> str:
    return _text(case.get("expected_risk_priority"), EXPECTED_NO_RISK_SIGNAL)


def _unsupported_expected_priority(expected: str) -> str | None:
    if expected not in {RadarPriority.P0.value, EXPECTED_NO_RISK_SIGNAL}:
        return expected

    return None


def _normalized_expected_priority(expected: str) -> str:
    if expected == RadarPriority.P0.value:
        return EXPECTED_RISK_P0

    return EXPECTED_NO_RISK_SIGNAL


def _missing_required_fields(
    row: dict[str, object],
    required_fields: list[str],
) -> list[str]:
    return [field for field in required_fields if not _text(row.get(field), "")]


def _text(value: object, default: str) -> str:
    if value is None:
        return default

    text = str(value).strip()
    return text or default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    return [str(item) for item in value]
