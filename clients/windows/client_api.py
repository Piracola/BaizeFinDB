"""Stdlib-only helpers for the BaizeFinDB Windows client."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_USER_KEY = "default"
DEFAULT_TIMEOUT_SECONDS = 10
SIGNALS_PREVIEW_LIMIT = 20
PORTFOLIO_PREVIEW_LIMIT = 20
SUBJECTS_PREVIEW_LIMIT = 8
MAX_TEXT_LENGTH = 12000
DISCLAIMER = "说明：仅用于关注、观察、风险和复盘，不构成投资建议。"

JsonObject = dict[str, Any]
JsonPayload = JsonObject | list[Any]
UrlOpener = Callable[..., Any]

LIFECYCLE_LABELS = {
    "ignition": "点火",
    "developing": "发酵",
    "divergence": "分歧",
    "returning": "回流",
    "climax": "高潮",
    "fading": "退潮",
    "extinguished": "熄火",
}

REVIEW_LABELS = {
    "candidate": "候选",
    "approved": "已通过",
    "blocked": "已阻断",
    "needs_human_review": "需人工复核",
}

SCAN_STATUS_LABELS = {
    "running": "运行中",
    "success": "成功",
    "no_data": "暂无数据",
    "failure": "失败",
}

DEPENDENCY_LABELS = {
    "failure": "失败",
    "ok": "正常",
    "ready": "就绪",
    "not_ready": "未就绪",
    "unknown": "未知",
}


class BaizeApiError(RuntimeError):
    """API request failure with optional parsed response payload."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: JsonPayload | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.url = url


def normalize_base_url(raw_url: str | None) -> str:
    """Normalize a BaizeFinDB API root URL."""

    value = (raw_url or DEFAULT_SERVER_URL).strip()
    if not value:
        value = DEFAULT_SERVER_URL

    if "://" not in value:
        value = f"http://{value}"

    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        msg = "server URL must use http or https"
        raise ValueError(msg)

    if not parts.netloc:
        msg = "server URL must include a host"
        raise ValueError(msg)

    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc, path, "", ""))


def build_url(
    base_url: str | None,
    path: str,
    query: Mapping[str, str | int | None] | None = None,
) -> str:
    """Join a normalized base URL, endpoint path, and optional query values."""

    base = normalize_base_url(base_url)
    base_parts = urlsplit(base)
    endpoint_path = f"/{path.lstrip('/')}"
    full_path = f"{base_parts.path.rstrip('/')}{endpoint_path}"
    query_values = {
        key: value for key, value in (query or {}).items() if value is not None
    }
    return urlunsplit(
        (
            base_parts.scheme,
            base_parts.netloc,
            full_path,
            urlencode(query_values),
            "",
        ),
    )


def get_json(
    base_url: str | None,
    path: str,
    *,
    query: Mapping[str, str | int | None] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    opener: UrlOpener | None = None,
) -> JsonPayload:
    """GET an API endpoint and parse the JSON response."""

    url = build_url(base_url, path, query)
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    open_url = opener or urlopen

    try:
        with open_url(request, timeout=timeout) as response:
            return _read_json(response, url)
    except HTTPError as exc:
        payload = _read_json(exc, url)
        raise BaizeApiError(
            _http_error_message(exc.code, payload),
            status_code=exc.code,
            payload=payload,
            url=url,
        ) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise BaizeApiError(f"无法连接 API：{reason}", url=url) from exc
    except TimeoutError as exc:
        raise BaizeApiError("请求 API 超时", url=url) from exc
    except OSError as exc:
        raise BaizeApiError(f"请求 API 失败：{exc}", url=url) from exc


def fetch_health(base_url: str | None, *, opener: UrlOpener | None = None) -> JsonObject:
    payload = get_json(base_url, "/health/ready", opener=opener)
    return _expect_object(payload, "/health/ready")


def fetch_radar_overview(
    base_url: str | None,
    *,
    limit: int = 50,
    opener: UrlOpener | None = None,
) -> JsonObject:
    payload = get_json(base_url, "/radar/overview", query={"limit": limit}, opener=opener)
    return _expect_object(payload, "/radar/overview")


def fetch_signals(
    base_url: str | None,
    *,
    priority: str | None = None,
    limit: int = 50,
    opener: UrlOpener | None = None,
) -> list[JsonObject]:
    payload = get_json(
        base_url,
        "/radar/signals",
        query={"priority": priority, "limit": limit},
        opener=opener,
    )
    if not isinstance(payload, list):
        msg = "/radar/signals did not return a list"
        raise BaizeApiError(msg, payload=payload)
    return [_expect_object(item, "/radar/signals item") for item in payload]


def fetch_holdings(
    base_url: str | None,
    *,
    user_key: str = DEFAULT_USER_KEY,
    opener: UrlOpener | None = None,
) -> list[JsonObject]:
    payload = get_json(
        base_url,
        "/portfolio/holdings",
        query={"user_key": _user_key(user_key)},
        opener=opener,
    )
    if not isinstance(payload, list):
        msg = "/portfolio/holdings did not return a list"
        raise BaizeApiError(msg, payload=payload)
    return [_expect_object(item, "/portfolio/holdings item") for item in payload]


def fetch_watchlist(
    base_url: str | None,
    *,
    user_key: str = DEFAULT_USER_KEY,
    opener: UrlOpener | None = None,
) -> list[JsonObject]:
    payload = get_json(
        base_url,
        "/portfolio/watchlist",
        query={"user_key": _user_key(user_key)},
        opener=opener,
    )
    if not isinstance(payload, list):
        msg = "/portfolio/watchlist did not return a list"
        raise BaizeApiError(msg, payload=payload)
    return [_expect_object(item, "/portfolio/watchlist item") for item in payload]


def format_health(payload: Mapping[str, Any]) -> str:
    checks = _mapping(payload.get("checks"))
    lines = [
        "健康状态",
        f"服务：{_text(payload.get('service'), 'BaizeFinDB')}",
        f"整体：{_status_label(payload.get('status'))}",
    ]

    if checks:
        for name in ("database", "redis"):
            check = _mapping(checks.get(name))
            status = _status_label(check.get("status"))
            detail = _text(check.get("error"), "")
            suffix = f"（{detail}）" if detail else ""
            lines.append(f"{_dependency_name(name)}：{status}{suffix}")

    lines.extend(["", DISCLAIMER])
    return _trim_text("\n".join(lines))


def format_radar_overview(overview: Mapping[str, Any]) -> str:
    counts = _mapping(overview.get("priority_counts"))
    latest_scan = _mapping(overview.get("latest_scan"))
    current_subjects = _sequence(overview.get("current_subjects"))
    lines = [
        "雷达总览",
        (
            "后端优先级计数："
            f"P0={_int_text(counts.get('P0'))} / "
            f"P1={_int_text(counts.get('P1'))} / "
            f"P2={_int_text(counts.get('P2'))}"
        ),
        f"当前主题：{_int_text(overview.get('subject_count'))} 个",
    ]

    if latest_scan:
        summary = _mapping(latest_scan.get("summary"))
        lines.extend(
            [
                (
                    "最新扫描："
                    f"#{_text(latest_scan.get('id'), '-')} "
                    f"{_scan_status_label(latest_scan.get('status'))}"
                ),
                f"开始时间：{_text(latest_scan.get('started_at'), '未返回')}",
                f"完成时间：{_text(latest_scan.get('finished_at'), '未返回')}",
                f"信号数量：{_int_text(summary.get('signal_count'))}",
            ],
        )
        if latest_scan.get("error_message"):
            lines.append(f"错误：{_text(latest_scan.get('error_message'), '')}")
    else:
        lines.extend(["最新扫描：暂无", "提示：可先采集 Provider 数据并运行雷达扫描。"])

    if current_subjects:
        lines.append("")
        lines.append("当前主题（后端去重结果）：")
        for subject in current_subjects[:SUBJECTS_PREVIEW_LIMIT]:
            subject_map = _mapping(subject)
            signal = _mapping(subject_map.get("latest_signal"))
            subject_name = subject_map.get("subject_name") or signal.get("subject_name")
            lines.append(
                (
                    f"- [{_text(signal.get('priority'), '-')}] "
                    f"{_text(subject_name, '未命名主题')} | "
                    f"生命周期：{_lifecycle_label(signal.get('lifecycle_stage'))}"
                ),
            )
        if len(current_subjects) > SUBJECTS_PREVIEW_LIMIT:
            lines.append(f"已折叠 {len(current_subjects) - SUBJECTS_PREVIEW_LIMIT} 个更多主题。")

    lines.extend(["", DISCLAIMER])
    return _trim_text("\n".join(lines))


def format_signals(signals: Sequence[Mapping[str, Any]]) -> str:
    if not signals:
        return _trim_text(
            "\n".join(
                [
                    "最近信号",
                    "暂无雷达信号。",
                    "提示：可先采集 Provider 数据并运行雷达扫描。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = ["最近信号"]
    for signal in signals[:SIGNALS_PREVIEW_LIMIT]:
        lines.extend(
            [
                (
                    f"#{_text(signal.get('id'), '-')} "
                    f"[{_text(signal.get('priority'), '-')}] "
                    f"{_text(signal.get('subject_name'), '未命名主题')}"
                ),
                (
                    "  "
                    f"生命周期：{_lifecycle_label(signal.get('lifecycle_stage'))} | "
                    f"审查：{_review_label(signal.get('review_status'))} | "
                    f"证据：{_int_text(signal.get('evidence_count'))}"
                ),
                f"  {_text(signal.get('title') or signal.get('summary'), '暂无摘要。')}",
            ],
        )

    if len(signals) > SIGNALS_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(signals) - SIGNALS_PREVIEW_LIMIT} 条更多信号。")

    lines.extend(["", DISCLAIMER])
    return _trim_text("\n".join(lines))


def format_holdings(holdings: Sequence[Mapping[str, Any]]) -> str:
    if not holdings:
        return _trim_text(
            "\n".join(
                [
                    "手动持仓",
                    "暂无手动持仓。",
                    "持仓只用于个人提醒、展示排序和报告上下文，不改变市场雷达等级。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = ["手动持仓"]
    for holding in holdings[:PORTFOLIO_PREVIEW_LIMIT]:
        lines.extend(
            [
                (
                    f"#{_text(holding.get('id'), '-')} "
                    f"{_text(holding.get('instrument_code'), '-')} "
                    f"{_text(holding.get('instrument_name'), '未命名标的')}"
                ),
                (
                    "  "
                    f"市场：{_text(holding.get('market'), '-')} | "
                    f"仓位：{_ratio_text(holding.get('position_ratio'))} | "
                    f"成本：{_number_text(holding.get('cost_price'))} | "
                    f"提醒：{_enabled_label(holding.get('alert_enabled'))}"
                ),
            ],
        )
        if holding.get("note"):
            lines.append(f"  备注：{_text(holding.get('note'), '')}")

    if len(holdings) > PORTFOLIO_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(holdings) - PORTFOLIO_PREVIEW_LIMIT} 条更多持仓。")

    lines.extend(
        [
            "持仓只用于个人提醒、展示排序和报告上下文，不改变市场雷达等级。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def format_watchlist(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return _trim_text(
            "\n".join(
                [
                    "自选关注",
                    "暂无自选关注。",
                    "自选只用于个人提醒、展示排序和报告上下文，不改变市场雷达等级。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = ["自选关注"]
    for item in items[:PORTFOLIO_PREVIEW_LIMIT]:
        lines.extend(
            [
                (
                    f"#{_text(item.get('id'), '-')} "
                    f"{_text(item.get('instrument_code'), '-')} "
                    f"{_text(item.get('instrument_name'), '未命名标的')}"
                ),
                (
                    "  "
                    f"市场：{_text(item.get('market'), '-')} | "
                    f"提醒：{_enabled_label(item.get('alert_enabled'))}"
                ),
            ],
        )
        if item.get("note"):
            lines.append(f"  备注：{_text(item.get('note'), '')}")

    if len(items) > PORTFOLIO_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(items) - PORTFOLIO_PREVIEW_LIMIT} 条更多自选。")

    lines.extend(
        [
            "自选只用于个人提醒、展示排序和报告上下文，不改变市场雷达等级。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def format_api_error(error: BaseException) -> str:
    if isinstance(error, BaizeApiError):
        details = [_text(error, "请求失败")]
        if error.status_code is not None:
            details.append(f"HTTP {error.status_code}")
        if error.url:
            details.append(error.url)
        return " | ".join(details)

    return _text(error, "请求失败")


def _read_json(response: Any, url: str) -> JsonPayload:
    raw_body = response.read()
    if isinstance(raw_body, bytes):
        text = raw_body.decode("utf-8")
    else:
        text = str(raw_body)

    if not text:
        return {}

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BaizeApiError("API 返回的不是合法 JSON", url=url) from exc

    if not isinstance(payload, dict | list):
        raise BaizeApiError("API JSON 响应必须是对象或列表", payload={"value": payload}, url=url)

    return payload


def _http_error_message(status_code: int, payload: JsonPayload | None) -> str:
    detail = None
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error") or payload.get("message")

    if detail:
        return f"API 返回 HTTP {status_code}：{detail}"

    return f"API 返回 HTTP {status_code}"


def _expect_object(payload: Any, context: str) -> JsonObject:
    if isinstance(payload, dict):
        return payload

    msg = f"{context} did not return an object"
    raise BaizeApiError(msg, payload=payload)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes) else []


def _dependency_name(name: str) -> str:
    labels = {
        "database": "数据库",
        "redis": "Redis",
    }
    return labels.get(name, name)


def _status_label(value: Any) -> str:
    return DEPENDENCY_LABELS.get(_text(value, "unknown"), _text(value, "unknown"))


def _lifecycle_label(value: Any) -> str:
    return LIFECYCLE_LABELS.get(_text(value, ""), _text(value, "-"))


def _review_label(value: Any) -> str:
    return REVIEW_LABELS.get(_text(value, ""), _text(value, "-"))


def _scan_status_label(value: Any) -> str:
    return SCAN_STATUS_LABELS.get(_text(value, ""), _text(value, "-"))


def _text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    return str(value)


def _int_text(value: Any) -> str:
    if value is None:
        return "0"
    return str(value)


def _number_text(value: Any) -> str:
    if value is None:
        return "未填"

    return str(value)


def _ratio_text(value: Any) -> str:
    if value is None:
        return "未填"

    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return _text(value, "未填")


def _enabled_label(value: Any) -> str:
    return "开启" if value is True else "关闭"


def _user_key(value: str | None) -> str:
    normalized = (value or DEFAULT_USER_KEY).strip()
    return normalized or DEFAULT_USER_KEY


def _trim_text(text: str) -> str:
    if len(text) <= MAX_TEXT_LENGTH:
        return text
    return f"{text[: MAX_TEXT_LENGTH - 12]}\n...内容已折叠"
