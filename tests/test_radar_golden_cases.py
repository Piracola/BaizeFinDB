import json
from datetime import UTC, datetime
from pathlib import Path

from app.db.radar_models import RadarSignal, RadarSignalReview, SignalEvidence
from app.governance.review import evaluate_radar_signal
from app.governance.share import build_signal_share_preview
from app.radar.rules import classify_sector_movement

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_radar_sector_rule_golden_cases() -> None:
    case_path = ROOT_DIR / "golden_cases" / "radar_m3_2_sector_rules.json"
    cases = json.loads(case_path.read_text(encoding="utf-8"))

    for case in cases:
        result = classify_sector_movement(case["metrics"])
        expected_priority = case["expected_priority"]
        expected_lifecycle_stage = case["expected_lifecycle_stage"]

        expects_no_signal = expected_priority is None and expected_lifecycle_stage is None
        has_partial_expectation = expected_priority is None or expected_lifecycle_stage is None

        assert not has_partial_expectation or expects_no_signal, case["name"]

        if expects_no_signal:
            assert result is None, case["name"]
            continue

        assert result is not None, case["name"]
        assert result.priority == expected_priority, case["name"]
        assert result.lifecycle_stage == expected_lifecycle_stage, case["name"]


def test_radar_review_rule_golden_cases() -> None:
    case_path = ROOT_DIR / "golden_cases" / "radar_m4_review_rules.json"
    cases = json.loads(case_path.read_text(encoding="utf-8"))

    for case in cases:
        decision = evaluate_radar_signal(
            _golden_signal(case["name"], case["signal"]),
            [
                _golden_evidence(case["name"], evidence)
                for evidence in case["evidences"]
            ],
        )

        assert decision.review_status == case["expected_status"], case["name"]
        for reason in case["expected_reasons"]:
            assert reason in decision.reasons, case["name"]
        for detail_key in case.get("expected_detail_keys", []):
            assert detail_key in decision.details, case["name"]


def test_radar_share_preview_golden_cases() -> None:
    case_path = ROOT_DIR / "golden_cases" / "radar_m4_share_preview.json"
    cases = json.loads(case_path.read_text(encoding="utf-8"))

    for case in cases:
        preview = build_signal_share_preview(
            _golden_share_signal(case["name"], case["signal"]),
            [
                _golden_share_evidence(case["name"], evidence)
                for evidence in case["evidences"]
            ],
            _golden_review(case["latest_review"]),
        )
        serialized = preview.model_dump_json()

        assert preview.share_status == case["expected_share_status"], case["name"]
        assert preview.blocked_reasons == case["expected_blocked_reasons"], case["name"]
        assert preview.evidences[0].evidence_label == case["expected_evidence_label"], (
            case["name"]
        )
        assert preview.evidences[0].confidence_label == case["expected_confidence_label"], (
            case["name"]
        )
        assert preview.evidences[0].freshness_label == case["expected_freshness_label"], (
            case["name"]
        )
        for fragment in case["forbidden_fragments"]:
            assert fragment not in serialized, case["name"]


def _golden_signal(name: str, data: dict[str, object]) -> RadarSignal:
    return RadarSignal(
        id=1,
        batch_id=1,
        signal_key=f"golden:{name}",
        subject_type="sector_concept",
        subject_code="GN001",
        subject_name="Golden Case",
        priority=str(data["priority"]),
        lifecycle_stage="developing",
        review_status="candidate",
        title=f"{data['priority']} radar candidate: Golden Case",
        summary=str(data["summary"]),
        metrics=dict(data["metrics"]),
        evidence_count=int(data["evidence_count"]),
    )


def _golden_share_signal(name: str, data: dict[str, object]) -> RadarSignal:
    return RadarSignal(
        id=1,
        batch_id=1,
        signal_key=f"golden:share:{name}",
        subject_type="sector_concept",
        subject_code="GN001",
        subject_name="Golden Case",
        priority=str(data["priority"]),
        lifecycle_stage=str(data["lifecycle_stage"]),
        review_status=str(data["review_status"]),
        title=str(data["title"]),
        summary=str(data["summary"]),
        metrics={},
        evidence_count=1,
    )


def _golden_evidence(name: str, data: dict[str, object]) -> SignalEvidence:
    now = datetime.now(UTC)
    return SignalEvidence(
        signal_id=1,
        evidence_type="market_snapshot",
        source_name="akshare",
        source_ref=f"golden:{name}",
        source_time=None,
        collected_at=now,
        raw_excerpt="Golden evidence fixture.",
        normalized_summary="Provider snapshot shows sector movement.",
        confidence=float(data["confidence"]),
        freshness=str(data.get("freshness", "snapshot_latest")),
        details=dict(data["details"]),
        public_share_policy="internal_summary_only",
    )


def _golden_share_evidence(name: str, data: dict[str, object]) -> SignalEvidence:
    now = datetime.now(UTC)
    return SignalEvidence(
        id=1,
        signal_id=1,
        evidence_type=str(data["evidence_type"]),
        source_name="akshare",
        source_ref=f"golden:share:{name}",
        source_time=now,
        collected_at=now,
        raw_excerpt="Golden share raw excerpt.",
        normalized_summary=str(data["normalized_summary"]),
        confidence=float(data["confidence"]),
        freshness=str(data["freshness"]),
        details={"source": "golden"},
        public_share_policy=str(data["public_share_policy"]),
    )


def _golden_review(data: dict[str, object] | None) -> RadarSignalReview | None:
    if data is None:
        return None

    return RadarSignalReview(
        id=1,
        signal_id=1,
        review_status=str(data["review_status"]),
        reviewer="golden_review",
        rule_version="golden",
        reasons=["rule_review_passed"],
        details={},
    )
