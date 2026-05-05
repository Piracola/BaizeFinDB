from collections import Counter
from dataclasses import dataclass

from app.providers.tushare import TUSHARE_ENDPOINTS
from app.radar.schemas import RadarPriority
from app.radar.service import classify_tushare_announcement_risk

EXPECTED_NO_RISK_SIGNAL = "none"
EXPECTED_RISK_P0 = "P0"
RADAR_RISK_CASE_TYPE_TRUE_POSITIVE_MAJOR = "true_positive_major_risk"
RADAR_RISK_CASE_TYPE_TRUE_POSITIVE_CRITICAL = "true_positive_critical_risk"
RADAR_RISK_CASE_TYPE_FALSE_POSITIVE_GUARD = "false_positive_guard"
RADAR_RISK_CASE_TYPE_FALSE_NEGATIVE_GUARD = "false_negative_guard"
RADAR_RISK_CASE_TYPE_ORDINARY_NO_SIGNAL = "ordinary_no_signal"
RADAR_RISK_CASE_TYPES = {
    RADAR_RISK_CASE_TYPE_TRUE_POSITIVE_MAJOR,
    RADAR_RISK_CASE_TYPE_TRUE_POSITIVE_CRITICAL,
    RADAR_RISK_CASE_TYPE_FALSE_POSITIVE_GUARD,
    RADAR_RISK_CASE_TYPE_FALSE_NEGATIVE_GUARD,
    RADAR_RISK_CASE_TYPE_ORDINARY_NO_SIGNAL,
}
RADAR_RISK_TRUE_POSITIVE_CASE_TYPES = {
    RADAR_RISK_CASE_TYPE_TRUE_POSITIVE_MAJOR,
    RADAR_RISK_CASE_TYPE_TRUE_POSITIVE_CRITICAL,
}
RADAR_RISK_EXPECTED_SIGNAL_CASE_TYPES = {
    *RADAR_RISK_TRUE_POSITIVE_CASE_TYPES,
    RADAR_RISK_CASE_TYPE_FALSE_NEGATIVE_GUARD,
}
RADAR_RISK_NO_SIGNAL_CASE_TYPES = {
    RADAR_RISK_CASE_TYPE_FALSE_POSITIVE_GUARD,
    RADAR_RISK_CASE_TYPE_ORDINARY_NO_SIGNAL,
}
RADAR_RISK_FEEDBACK_GUARD_CASE_TYPES = {
    RADAR_RISK_CASE_TYPE_FALSE_POSITIVE_GUARD,
    RADAR_RISK_CASE_TYPE_FALSE_NEGATIVE_GUARD,
}


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


@dataclass(frozen=True)
class RadarRiskGoldenSignalResult:
    priority: str
    subject_type: str
    subject_code: str | None
    subject_name: str
    risk_event_type: str
    severity: str
    announcement_keywords: list[str]
    rule_reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "priority": self.priority,
            "subject_type": self.subject_type,
            "subject_code": self.subject_code,
            "subject_name": self.subject_name,
            "risk_event_type": self.risk_event_type,
            "severity": self.severity,
            "announcement_keywords": self.announcement_keywords,
            "rule_reasons": self.rule_reasons,
        }


@dataclass(frozen=True)
class RadarRiskGoldenCaseResult:
    case_id: str
    case_type: str | None
    source: str | None
    notes: str | None
    expected_status: str
    actual_status: str
    expected_candidate_count: int | None
    actual_candidate_count: int
    expected_priority_counts: dict[str, int]
    actual_priority_counts: dict[str, int]
    signals: list[RadarRiskGoldenSignalResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "source": self.source,
            "notes": self.notes,
            "expected_status": self.expected_status,
            "actual_status": self.actual_status,
            "expected_candidate_count": self.expected_candidate_count,
            "actual_candidate_count": self.actual_candidate_count,
            "expected_priority_counts": self.expected_priority_counts,
            "actual_priority_counts": self.actual_priority_counts,
            "signals": [signal.to_dict() for signal in self.signals],
        }


@dataclass(frozen=True)
class RadarRiskGoldenReport:
    status: str
    endpoint: str
    case_count: int
    results: list[RadarRiskGoldenCaseResult]
    issues: list[PreflightIssue]

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "endpoint": self.endpoint,
            "case_count": self.case_count,
            "results": [result.to_dict() for result in self.results],
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


def validate_radar_risk_announcement_golden_cases(
    cases: list[dict[str, object]],
) -> RadarRiskGoldenReport:
    required_fields = list(TUSHARE_ENDPOINTS["anns_d"].required_fields)
    issues: list[PreflightIssue] = []
    results: list[RadarRiskGoldenCaseResult] = []
    saw_true_positive_risk_case = False
    saw_no_signal_guard_case = False
    saw_feedback_guard_case = False

    for index, case in enumerate(cases, start=1):
        case_id = _text(case.get("name") or case.get("case_id"), f"case-{index}")
        case_type = _radar_risk_case_type(case, case_id, issues)
        if case_type in RADAR_RISK_TRUE_POSITIVE_CASE_TYPES:
            saw_true_positive_risk_case = True
        if case_type in RADAR_RISK_NO_SIGNAL_CASE_TYPES:
            saw_no_signal_guard_case = True
        if case_type in RADAR_RISK_FEEDBACK_GUARD_CASE_TYPES:
            saw_feedback_guard_case = True
        rows = _case_rows(case, case_id, issues)
        expected = _case_expected(case, case_id, issues)
        expected_status = _expected_status(expected, case_id, issues)
        expected_candidate_count = _expected_candidate_count(expected, case_id, issues)
        expected_priority_counts = _expected_priority_counts(expected, case_id, issues)
        expected_signals = _expected_signals(expected, case_id, issues)
        actual_signals = _radar_risk_signals_for_rows(
            rows,
            case_id=case_id,
            required_fields=required_fields,
            issues=issues,
        )
        actual_status = "success" if actual_signals else "no_data"
        actual_priority_counts = dict(Counter(signal.priority for signal in actual_signals))

        results.append(
            RadarRiskGoldenCaseResult(
                case_id=case_id,
                case_type=case_type,
                source=_optional_text(case.get("source")),
                notes=_optional_text(case.get("notes")),
                expected_status=expected_status,
                actual_status=actual_status,
                expected_candidate_count=expected_candidate_count,
                actual_candidate_count=len(actual_signals),
                expected_priority_counts=expected_priority_counts,
                actual_priority_counts=actual_priority_counts,
                signals=actual_signals,
            )
        )

        _check_radar_risk_case_type_expectation(
            case_id=case_id,
            case_type=case_type,
            expected_status=expected_status,
            expected_candidate_count=expected_candidate_count,
            expected_priority_counts=expected_priority_counts,
            expected_signals=expected_signals,
            issues=issues,
        )
        _compare_radar_case_result(
            case_id=case_id,
            expected_status=expected_status,
            expected_candidate_count=expected_candidate_count,
            expected_priority_counts=expected_priority_counts,
            expected_signals=expected_signals,
            actual_status=actual_status,
            actual_signals=actual_signals,
            actual_priority_counts=actual_priority_counts,
            issues=issues,
        )

    if not saw_true_positive_risk_case:
        issues.append(
            PreflightIssue(
                case_id="__suite__",
                code="missing_true_positive_risk_case",
                message=(
                    "radar risk golden cases must include at least one "
                    "true-positive major or critical risk case"
                ),
            )
        )
    if not saw_no_signal_guard_case:
        issues.append(
            PreflightIssue(
                case_id="__suite__",
                code="missing_no_signal_guard_case",
                message=(
                    "radar risk golden cases must include at least one no-signal "
                    "guard case"
                ),
            )
        )
    if not saw_feedback_guard_case:
        issues.append(
            PreflightIssue(
                case_id="__suite__",
                code="missing_feedback_guard_case",
                message=(
                    "radar risk golden cases must include at least one "
                    "false-positive or false-negative feedback guard case"
                ),
            )
        )

    return RadarRiskGoldenReport(
        status="ok" if not issues else "fail",
        endpoint="anns_d",
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


def _radar_risk_case_type(
    case: dict[str, object],
    case_id: str,
    issues: list[PreflightIssue],
) -> str | None:
    case_type = _optional_text(case.get("case_type"))
    if case_type is None:
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="missing_case_type",
                message="radar risk golden case must declare case_type",
            )
        )
        return None

    if case_type not in RADAR_RISK_CASE_TYPES:
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="unsupported_case_type",
                message=(
                    "radar risk golden case_type must be one of "
                    f"{sorted(RADAR_RISK_CASE_TYPES)}"
                ),
            )
        )
        return None

    return case_type


def _case_rows(
    case: dict[str, object],
    case_id: str,
    issues: list[PreflightIssue],
) -> list[dict[str, object]]:
    rows = case.get("rows")
    if not isinstance(rows, list):
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="invalid_rows",
                message="radar golden case rows must be a JSON array",
            )
        )
        return []

    valid_rows: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="invalid_row",
                    message=f"radar golden case row #{index} must be a JSON object",
                )
            )
            continue
        valid_rows.append(row)
    return valid_rows


def _case_expected(
    case: dict[str, object],
    case_id: str,
    issues: list[PreflightIssue],
) -> dict[str, object]:
    expected = case.get("expected")
    if not isinstance(expected, dict):
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="invalid_expected",
                message="radar golden case expected must be a JSON object",
            )
        )
        return {}
    return expected


def _expected_status(
    expected: dict[str, object],
    case_id: str,
    issues: list[PreflightIssue],
) -> str:
    status = _text(expected.get("status"), "")
    if status not in {"success", "no_data"}:
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="unsupported_expected_status",
                message="expected status must be success or no_data",
            )
        )
    return status


def _expected_candidate_count(
    expected: dict[str, object],
    case_id: str,
    issues: list[PreflightIssue],
) -> int | None:
    candidate_count = _non_negative_int(expected.get("candidate_count"))
    if candidate_count is None:
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="invalid_expected_candidate_count",
                message="expected candidate_count must be a non-negative integer",
            )
        )
    return candidate_count


def _expected_priority_counts(
    expected: dict[str, object],
    case_id: str,
    issues: list[PreflightIssue],
) -> dict[str, int]:
    raw_counts = expected.get("priority_counts")
    if not isinstance(raw_counts, dict):
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="invalid_expected_priority_counts",
                message="expected priority_counts must be a JSON object",
            )
        )
        return {}

    counts: dict[str, int] = {}
    for priority, raw_count in raw_counts.items():
        count = _non_negative_int(raw_count)
        priority_text = str(priority)
        if count is None:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="invalid_expected_priority_count",
                    message=f"expected priority count for {priority_text} must be non-negative",
                )
            )
            continue
        counts[priority_text] = count
    return counts


def _expected_signals(
    expected: dict[str, object],
    case_id: str,
    issues: list[PreflightIssue],
) -> list[dict[str, object]]:
    raw_signals = expected.get("signals")
    if not isinstance(raw_signals, list):
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="invalid_expected_signals",
                message="expected signals must be a JSON array",
            )
        )
        return []

    signals: list[dict[str, object]] = []
    for index, signal in enumerate(raw_signals, start=1):
        if not isinstance(signal, dict):
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="invalid_expected_signal",
                    message=f"expected signal #{index} must be a JSON object",
                )
            )
            continue
        signals.append(signal)
    return signals


def _radar_risk_signals_for_rows(
    rows: list[dict[str, object]],
    *,
    case_id: str,
    required_fields: list[str],
    issues: list[PreflightIssue],
) -> list[RadarRiskGoldenSignalResult]:
    signals: list[RadarRiskGoldenSignalResult] = []
    for index, row in enumerate(rows, start=1):
        for field in _missing_required_fields(row, required_fields):
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="missing_required_field",
                    message=(
                        f"row #{index} missing required normalized anns_d field: {field}"
                    ),
                )
            )

        metrics, rule_result = classify_tushare_announcement_risk(row)
        if rule_result is None:
            continue

        signals.append(
            RadarRiskGoldenSignalResult(
                priority=rule_result.priority.value,
                subject_type="announcements",
                subject_code=_optional_text(row.get("ts_code")),
                subject_name=_text(
                    row.get("announcement_title") or row.get("title") or row.get("name"),
                    "unknown risk event",
                ),
                risk_event_type=_text(metrics.get("risk_event_type"), ""),
                severity=_text(metrics.get("severity"), ""),
                announcement_keywords=_string_list(metrics.get("announcement_keywords")),
                rule_reasons=list(rule_result.reasons),
            )
        )
    return signals


def _check_radar_risk_case_type_expectation(
    *,
    case_id: str,
    case_type: str | None,
    expected_status: str,
    expected_candidate_count: int | None,
    expected_priority_counts: dict[str, int],
    expected_signals: list[dict[str, object]],
    issues: list[PreflightIssue],
) -> None:
    if case_type is None:
        return

    if case_type in RADAR_RISK_EXPECTED_SIGNAL_CASE_TYPES:
        if expected_status and expected_status != "success":
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="case_type_expectation_mismatch",
                    message=f"{case_type} cases must expect status=success",
                )
            )
        if expected_candidate_count is not None and expected_candidate_count < 1:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="case_type_expectation_mismatch",
                    message=f"{case_type} cases must expect at least one signal",
                )
            )
        if not expected_signals:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="case_type_expectation_mismatch",
                    message=f"{case_type} cases must include expected signal fields",
                )
            )
        return

    if case_type in RADAR_RISK_NO_SIGNAL_CASE_TYPES:
        if expected_status and expected_status != "no_data":
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="case_type_expectation_mismatch",
                    message=f"{case_type} cases must expect status=no_data",
                )
            )
        if expected_candidate_count not in (None, 0):
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="case_type_expectation_mismatch",
                    message=f"{case_type} cases must expect zero signals",
                )
            )
        if expected_priority_counts:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="case_type_expectation_mismatch",
                    message=f"{case_type} cases must not expect priority counts",
                )
            )
        if expected_signals:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="case_type_expectation_mismatch",
                    message=f"{case_type} cases must not expect signal fields",
                )
            )


def _compare_radar_case_result(
    *,
    case_id: str,
    expected_status: str,
    expected_candidate_count: int | None,
    expected_priority_counts: dict[str, int],
    expected_signals: list[dict[str, object]],
    actual_status: str,
    actual_signals: list[RadarRiskGoldenSignalResult],
    actual_priority_counts: dict[str, int],
    issues: list[PreflightIssue],
) -> None:
    if expected_status and expected_status != actual_status:
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="radar_status_mismatch",
                message=(
                    f"expected radar status {expected_status}, got {actual_status}"
                ),
            )
        )

    if (
        expected_candidate_count is not None
        and expected_candidate_count != len(actual_signals)
    ):
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="radar_candidate_count_mismatch",
                message=(
                    f"expected {expected_candidate_count} candidate(s), "
                    f"got {len(actual_signals)}"
                ),
            )
        )

    if expected_priority_counts != actual_priority_counts:
        issues.append(
            PreflightIssue(
                case_id=case_id,
                code="radar_priority_count_mismatch",
                message=(
                    f"expected priority_counts {expected_priority_counts}, "
                    f"got {actual_priority_counts}"
                ),
            )
        )

    for index, expected_signal in enumerate(expected_signals, start=1):
        actual_signal = _match_actual_signal(expected_signal, actual_signals)
        if actual_signal is None:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="expected_signal_missing",
                    message=f"expected radar signal #{index} was not produced",
                )
            )
            continue

        _compare_signal_fields(case_id, expected_signal, actual_signal, issues)


def _match_actual_signal(
    expected_signal: dict[str, object],
    actual_signals: list[RadarRiskGoldenSignalResult],
) -> RadarRiskGoldenSignalResult | None:
    expected_code = _optional_text(expected_signal.get("subject_code"))
    expected_name = _text(expected_signal.get("subject_name"), "")
    for actual_signal in actual_signals:
        if (
            actual_signal.subject_code == expected_code
            and actual_signal.subject_name == expected_name
        ):
            return actual_signal
    return None


def _compare_signal_fields(
    case_id: str,
    expected_signal: dict[str, object],
    actual_signal: RadarRiskGoldenSignalResult,
    issues: list[PreflightIssue],
) -> None:
    actual = actual_signal.to_dict()
    for field in (
        "priority",
        "subject_type",
        "subject_code",
        "subject_name",
        "risk_event_type",
        "severity",
    ):
        expected_value = expected_signal.get(field)
        if expected_value != actual[field]:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="signal_field_mismatch",
                    message=(
                        f"signal field {field} expected {expected_value!r}, "
                        f"got {actual[field]!r}"
                    ),
                )
            )

    for keyword in _string_list(expected_signal.get("announcement_keywords")):
        if keyword not in actual_signal.announcement_keywords:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="signal_keyword_missing",
                    message=f"expected announcement keyword missing: {keyword}",
                )
            )

    for reason in _string_list(expected_signal.get("rule_reasons")):
        if reason not in actual_signal.rule_reasons:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="signal_rule_reason_missing",
                    message=f"expected rule reason missing: {reason}",
                )
            )

    actual_text = str(actual)
    for fragment in _string_list(expected_signal.get("forbidden_evidence_fragments")):
        if fragment and fragment in actual_text:
            issues.append(
                PreflightIssue(
                    case_id=case_id,
                    code="raw_evidence_fragment_exposed",
                    message="radar golden signal result exposed a forbidden raw fragment",
                )
            )


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None

    if integer < 0:
        return None
    return integer


def _optional_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


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
