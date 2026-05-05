"""Deterministic sanitizer for future model-generated analysis drafts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from app.governance.review import matched_unsafe_trading_terms
from app.governance.sanitization import redact_source_locators, truncate_text
from app.reports.schemas import ReportSuggestionLabel

MODEL_ANALYSIS_OUTPUT_VERSION = "model_analysis_output:v1"
MAX_ADVISORY_SUMMARY_LENGTH = 500
MAX_DRAFT_ITEMS = 5
MAX_DRAFT_ITEM_LENGTH = 220

ModelAnalysisDraftStatus = Literal["ok", "blocked", "degraded"]


@dataclass(frozen=True)
class ModelAnalysisDraft:
    status: ModelAnalysisDraftStatus
    advisory_summary: str = ""
    observations: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    suggested_attention_label: ReportSuggestionLabel | None = None
    blocked_terms: list[str] = field(default_factory=list)
    error_type: str | None = None
    output_version: str = MODEL_ANALYSIS_OUTPUT_VERSION


def parse_model_analysis_draft(content: str) -> ModelAnalysisDraft:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return ModelAnalysisDraft(status="degraded", error_type="json_decode_error")

    if not isinstance(payload, dict):
        return ModelAnalysisDraft(status="degraded", error_type="invalid_payload_type")

    blocked_terms = matched_unsafe_trading_terms(_payload_text(payload))
    if blocked_terms:
        return ModelAnalysisDraft(status="blocked", blocked_terms=blocked_terms)

    return ModelAnalysisDraft(
        status="ok",
        advisory_summary=_bounded_text(
            payload.get("advisory_summary"),
            MAX_ADVISORY_SUMMARY_LENGTH,
        ),
        observations=_bounded_text_list(payload.get("observations")),
        risk_notes=_bounded_text_list(payload.get("risk_notes")),
        follow_up_questions=_bounded_text_list(payload.get("follow_up_questions")),
        suggested_attention_label=_suggested_attention_label(
            payload.get("suggested_attention_label"),
        ),
    )


def _payload_text(value: object) -> str:
    if isinstance(value, dict):
        return "\n".join(_payload_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_payload_text(item) for item in value)
    if isinstance(value, str):
        return value
    return ""


def _bounded_text(value: object, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    redacted = redact_source_locators(value)
    return truncate_text(redacted, max_length)


def _bounded_text_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items: list[object] = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []

    bounded: list[str] = []
    for item in items:
        text = _bounded_text(item, MAX_DRAFT_ITEM_LENGTH)
        if text:
            bounded.append(text)
        if len(bounded) >= MAX_DRAFT_ITEMS:
            break
    return bounded


def _suggested_attention_label(value: object) -> ReportSuggestionLabel | None:
    if not isinstance(value, str):
        return None
    try:
        return ReportSuggestionLabel(value.strip())
    except ValueError:
        return None
