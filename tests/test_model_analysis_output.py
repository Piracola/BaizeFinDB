import json
from pathlib import Path

from app.ai.analysis_output import (
    MAX_DRAFT_ITEM_LENGTH,
    MAX_DRAFT_ITEMS,
    ModelAnalysisDraft,
    parse_model_analysis_draft,
)
from app.governance.review import matched_unsafe_trading_terms
from app.reports.schemas import ReportSuggestionLabel


def test_valid_model_analysis_draft_is_sanitized_and_bounded() -> None:
    payload = {
        "advisory_summary": "主线仍需观察，参考 https://example.com/raw。",
        "observations": [
            "资金扩散较快，详见 news.example.com。",
            "后续需要看成交额持续性。",
        ],
        "risk_notes": ["公告风险来自 www.example.cn/source。"],
        "follow_up_questions": ["下一轮扫描是否仍有板块宽度？"],
        "suggested_attention_label": "继续观察",
        "unknown_field": "ignored",
    }

    draft = parse_model_analysis_draft(json.dumps(payload, ensure_ascii=False))

    assert draft.status == "ok"
    assert draft.advisory_summary == "主线仍需观察，参考 [source omitted]。"
    assert draft.observations == [
        "资金扩散较快，详见 [source omitted]。",
        "后续需要看成交额持续性。",
    ]
    assert draft.risk_notes == ["公告风险来自 [source omitted]。"]
    assert draft.follow_up_questions == ["下一轮扫描是否仍有板块宽度？"]
    assert draft.suggested_attention_label == ReportSuggestionLabel.WATCH
    assert draft.blocked_terms == []


def test_malformed_or_non_object_model_output_degrades_without_raise() -> None:
    malformed = parse_model_analysis_draft("{bad json")
    non_object = parse_model_analysis_draft(json.dumps(["not", "object"]))

    assert malformed == ModelAnalysisDraft(status="degraded", error_type="json_decode_error")
    assert non_object == ModelAnalysisDraft(status="degraded", error_type="invalid_payload_type")


def test_direct_trading_language_blocks_model_analysis_draft() -> None:
    draft = parse_model_analysis_draft(
        json.dumps(
            {
                "advisory_summary": "建议马上买入并满仓跟着买。",
                "observations": ["这是买入信号。"],
            },
            ensure_ascii=False,
        ),
    )

    assert draft.status == "blocked"
    assert draft.advisory_summary == ""
    assert draft.observations == []
    assert draft.blocked_terms == ["马上买入", "满仓", "跟着买", "买入信号"]


def test_safely_negated_trading_warning_is_not_blocked() -> None:
    draft = parse_model_analysis_draft(
        json.dumps(
            {
                "advisory_summary": "风险提示：不建议马上买入，不宜满仓，不是买入信号。",
                "risk_notes": ["不能跟着买，仍需等后续证据。"],
                "suggested_attention_label": "谨慎跟踪",
            },
            ensure_ascii=False,
        ),
    )

    assert draft.status == "ok"
    assert draft.blocked_terms == []
    assert draft.suggested_attention_label == ReportSuggestionLabel.CAUTIOUS


def test_unknown_label_and_missing_optional_fields_use_defaults() -> None:
    draft = parse_model_analysis_draft(
        json.dumps(
            {
                "advisory_summary": "只保留结构化摘要。",
                "suggested_attention_label": "立刻行动",
            },
            ensure_ascii=False,
        ),
    )

    assert draft.status == "ok"
    assert draft.advisory_summary == "只保留结构化摘要。"
    assert draft.observations == []
    assert draft.risk_notes == []
    assert draft.follow_up_questions == []
    assert draft.suggested_attention_label is None


def test_list_fields_are_limited_and_items_are_truncated() -> None:
    long_item = "风险" * 200
    draft = parse_model_analysis_draft(
        json.dumps(
            {
                "observations": [f"{index}-{long_item}" for index in range(MAX_DRAFT_ITEMS + 2)],
            },
            ensure_ascii=False,
        ),
    )

    assert draft.status == "ok"
    assert len(draft.observations) == MAX_DRAFT_ITEMS
    assert all(len(item) <= MAX_DRAFT_ITEM_LENGTH for item in draft.observations)
    assert draft.observations[0].endswith("...")


def test_public_trading_language_helper_preserves_existing_negation_behavior() -> None:
    assert matched_unsafe_trading_terms("建议马上买入并保证收益") == [
        "马上买入",
        "保证收益",
    ]
    assert matched_unsafe_trading_terms("不建议马上买入，不保证收益") == []


def test_model_analysis_output_module_has_no_provider_or_delivery_dependencies() -> None:
    source = Path("backend/app/ai/analysis_output.py").read_text(encoding="utf-8")

    assert "app.ai.model_client" not in source
    assert "app.radar" not in source
    assert "app.telegram" not in source
    assert "app.providers" not in source
