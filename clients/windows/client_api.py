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
REPORT_PREVIEW_LIMIT = 20
TELEGRAM_BINDING_PREVIEW_LIMIT = 20
OPS_HISTORY_PREVIEW_LIMIT = 12
MAX_TEXT_LENGTH = 12000
DISCLAIMER = "说明：仅用于关注、观察、风险和复盘，不构成投资建议。"
TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
STOCK_BACKTRACE_PREVIEW_LIMIT = 5

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
LIFECYCLE_ORDER = (
    "ignition",
    "developing",
    "divergence",
    "returning",
    "climax",
    "fading",
    "extinguished",
)

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

TUSHARE_STATUS_LABELS = {
    "configured": "已配置",
    "not_configured": "未配置",
    "unknown": "未知",
}

PERIOD_LABELS = {
    "daily": "日报",
    "weekly": "周报",
}

SCORE_STATUS_LABELS = {
    "generated": "已生成",
    "pending_window": "窗口未结束",
}
SCORE_BAND_LABELS = {
    "strong_attention": "强关注",
    "watch": "观察",
    "weak_watch": "弱观察",
    "low_signal_quality": "低质量",
}
SCORE_COMPONENT_LABELS = {
    "priority": "优先级",
    "lifecycle": "生命周期",
    "review": "审查",
    "evidence": "证据",
    "continuity": "连续性",
    "data_quality": "数据质量",
    "timeliness": "时效性",
}
SCORE_COMPONENT_ORDER = (
    "priority",
    "lifecycle",
    "review",
    "evidence",
    "continuity",
    "data_quality",
    "timeliness",
)


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
    secret_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    opener: UrlOpener | None = None,
) -> JsonPayload:
    """GET an API endpoint and parse the JSON response."""

    url = build_url(base_url, path, query)
    request = Request(url, headers=_request_headers(secret_token), method="GET")
    return _send_json_request(request, url, timeout=timeout, opener=opener)


def post_json(
    base_url: str | None,
    path: str,
    *,
    query: Mapping[str, str | int | None] | None = None,
    json_body: JsonPayload | None = None,
    secret_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    opener: UrlOpener | None = None,
) -> JsonPayload:
    """POST an API endpoint and parse the JSON response."""

    url = build_url(base_url, path, query)
    headers = _request_headers(secret_token)
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")

    request = Request(url, data=data, headers=headers, method="POST")
    return _send_json_request(request, url, timeout=timeout, opener=opener)


def patch_json(
    base_url: str | None,
    path: str,
    *,
    query: Mapping[str, str | int | None] | None = None,
    json_body: JsonPayload | None = None,
    secret_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    opener: UrlOpener | None = None,
) -> JsonPayload:
    """PATCH an API endpoint and parse the JSON response."""

    url = build_url(base_url, path, query)
    headers = _request_headers(secret_token)
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")

    request = Request(url, data=data, headers=headers, method="PATCH")
    return _send_json_request(request, url, timeout=timeout, opener=opener)


def _request_headers(secret_token: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    normalized_secret = (secret_token or "").strip()
    if normalized_secret:
        headers[TELEGRAM_SECRET_HEADER] = normalized_secret
    return headers


def _send_json_request(
    request: Request,
    url: str,
    *,
    timeout: int,
    opener: UrlOpener | None,
) -> JsonPayload:
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


def fetch_ops_overview(
    base_url: str | None,
    *,
    lookback_hours: int = 24,
    opener: UrlOpener | None = None,
) -> JsonObject:
    payload = get_json(
        base_url,
        "/ops/overview",
        query={"lookback_hours": _positive_int(lookback_hours, "lookback_hours")},
        opener=opener,
    )
    return _expect_object(payload, "/ops/overview")


def fetch_ops_history(
    base_url: str | None,
    *,
    lookback_hours: int = 24,
    limit: int = 20,
    opener: UrlOpener | None = None,
) -> JsonObject:
    payload = get_json(
        base_url,
        "/ops/history",
        query={
            "lookback_hours": _positive_int(lookback_hours, "lookback_hours"),
            "limit": _positive_int(limit, "limit"),
        },
        opener=opener,
    )
    return _expect_object(payload, "/ops/history")


def fetch_ops_readiness(
    base_url: str | None,
    *,
    lookback_hours: int = 24,
    opener: UrlOpener | None = None,
) -> JsonObject:
    payload = get_json(
        base_url,
        "/ops/readiness",
        query={"lookback_hours": _positive_int(lookback_hours, "lookback_hours")},
        opener=opener,
    )
    return _expect_object(payload, "/ops/readiness")


def fetch_tushare_status(
    base_url: str | None,
    *,
    opener: UrlOpener | None = None,
) -> JsonObject:
    payload = get_json(base_url, "/providers/tushare/status", opener=opener)
    return _expect_object(payload, "/providers/tushare/status")


def fetch_tushare_readiness(
    base_url: str | None,
    *,
    opener: UrlOpener | None = None,
) -> JsonObject:
    payload = get_json(base_url, "/providers/tushare/readiness", opener=opener)
    return _expect_object(payload, "/providers/tushare/readiness")


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


def fetch_reports(
    base_url: str | None,
    *,
    user_key: str = DEFAULT_USER_KEY,
    report_type: str | None = None,
    limit: int = REPORT_PREVIEW_LIMIT,
    opener: UrlOpener | None = None,
) -> list[JsonObject]:
    payload = get_json(
        base_url,
        "/reports",
        query={
            "user_key": _user_key(user_key),
            "report_type": report_type,
            "limit": limit,
        },
        opener=opener,
    )
    if not isinstance(payload, list):
        msg = "/reports did not return a list"
        raise BaizeApiError(msg, payload=payload)
    return [_expect_object(item, "/reports item") for item in payload]


def fetch_periodic_report(
    base_url: str | None,
    *,
    user_key: str = DEFAULT_USER_KEY,
    period: str = "daily",
    opener: UrlOpener | None = None,
) -> JsonObject:
    payload = get_json(
        base_url,
        "/reports/periodic",
        query={
            "user_key": _user_key(user_key),
            "period": period,
        },
        opener=opener,
    )
    return _expect_object(payload, "/reports/periodic")


def score_signal(
    base_url: str | None,
    signal_id: int,
    *,
    opener: UrlOpener | None = None,
) -> JsonObject:
    normalized_signal_id = _positive_int(signal_id, "signal_id")
    payload = post_json(
        base_url,
        f"/scores/signals/{normalized_signal_id}",
        opener=opener,
    )
    return _expect_object(payload, "/scores/signals/{signal_id}")


def fetch_signal_scores(
    base_url: str | None,
    signal_id: int,
    *,
    opener: UrlOpener | None = None,
) -> JsonObject:
    normalized_signal_id = _positive_int(signal_id, "signal_id")
    payload = get_json(
        base_url,
        f"/scores/signals/{normalized_signal_id}",
        opener=opener,
    )
    return _expect_object(payload, "/scores/signals/{signal_id}")


def fetch_telegram_bindings(
    base_url: str | None,
    *,
    secret_token: str | None = None,
    limit: int = TELEGRAM_BINDING_PREVIEW_LIMIT,
    opener: UrlOpener | None = None,
) -> list[JsonObject]:
    payload = get_json(
        base_url,
        "/telegram/bindings",
        query={"limit": limit},
        secret_token=secret_token,
        opener=opener,
    )
    if not isinstance(payload, list):
        msg = "/telegram/bindings did not return a list"
        raise BaizeApiError(msg, payload=payload)
    return [_expect_object(item, "/telegram/bindings item") for item in payload]


def upsert_telegram_binding(
    base_url: str | None,
    *,
    chat_id: int,
    user_key: str = DEFAULT_USER_KEY,
    display_name: str = "",
    is_allowed: bool = True,
    secret_token: str | None = None,
    opener: UrlOpener | None = None,
) -> JsonObject:
    normalized_chat_id = _nonzero_int(chat_id, "chat_id")
    payload = post_json(
        base_url,
        "/telegram/bindings",
        json_body={
            "chat_id": normalized_chat_id,
            "user_key": _user_key(user_key),
            "display_name": display_name.strip(),
            "is_allowed": is_allowed,
        },
        secret_token=secret_token,
        opener=opener,
    )
    return _expect_object(payload, "/telegram/bindings")


def update_telegram_binding(
    base_url: str | None,
    *,
    chat_id: int,
    is_allowed: bool,
    secret_token: str | None = None,
    opener: UrlOpener | None = None,
) -> JsonObject:
    normalized_chat_id = _nonzero_int(chat_id, "chat_id")
    payload = patch_json(
        base_url,
        f"/telegram/bindings/{normalized_chat_id}",
        json_body={"is_allowed": is_allowed},
        secret_token=secret_token,
        opener=opener,
    )
    return _expect_object(payload, "/telegram/bindings/{chat_id}")


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


def format_ops_overview(payload: Mapping[str, Any]) -> str:
    radar = _mapping(payload.get("radar"))
    lines = [
        "运行状态",
        f"统计窗口：最近 {_int_text(payload.get('lookback_hours'))} 小时",
        (
            "雷达扫描："
            f"#{_text(radar.get('latest_scan_id'), '暂无')} "
            f"{_ops_status_label(radar.get('latest_scan_status'))} | "
            f"新鲜度：{_duration_text(radar.get('latest_scan_age_seconds'))} | "
            f"{_stale_label(radar.get('is_latest_scan_stale'))}"
        ),
        (
            "扫描失败率："
            f"{_rate_text(radar.get('recent_scan_failure_rate'))} "
            f"({_int_text(radar.get('recent_scan_failure_count'))}/"
            f"{_int_text(radar.get('recent_scan_count'))})"
        ),
        _ops_server_text(_mapping(payload.get("server"))),
        _ops_count_text("Provider", _mapping(payload.get("provider_fetch"))),
        _ops_count_text("数据质量", _mapping(payload.get("data_quality"))),
        _ops_count_text("Telegram 推送", _mapping(payload.get("telegram_push"))),
        _ops_count_text("模型调用", _mapping(payload.get("model_calls"))),
        f"告警：{_ops_alerts_text(_sequence(payload.get('alerts')))}",
    ]

    lines.extend(
        [
            "该视图只读取已有运行记录，不触发采集、扫描、推送或模型调用。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def format_ops_history(payload: Mapping[str, Any]) -> str:
    events = _sequence(payload.get("recent_events"))
    failure_summary = _sequence(payload.get("failure_summary"))
    lines = [
        "运维历史",
        f"统计窗口：最近 {_int_text(payload.get('lookback_hours'))} 小时",
        f"事件：{len(events)} 条 / Top {_int_text(payload.get('limit'))}",
        f"异常汇总：{_ops_failure_summary_text(failure_summary)}",
    ]

    if events:
        lines.append("最近事件：")
        for event in events[:OPS_HISTORY_PREVIEW_LIMIT]:
            event_map = _mapping(event)
            detail = _text(event_map.get("detail"), "")
            detail_suffix = f" | {detail}" if detail else ""
            lines.append(
                (
                    f"- {_ops_kind_label(event_map.get('kind'))} "
                    f"#{_text(event_map.get('id'), '-')} "
                    f"{_ops_status_label(event_map.get('status'))} | "
                    f"{_text(event_map.get('occurred_at'), '未返回')}"
                    f"{detail_suffix}"
                ),
            )
    else:
        lines.append("最近事件：暂无")

    lines.extend(
        [
            "该视图只读取已有运行记录，不触发采集、扫描、推送或模型调用。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def format_ops_readiness(payload: Mapping[str, Any]) -> str:
    checks = _sequence(payload.get("checks"))
    lines = [
        "运行就绪自检",
        f"状态：{_readiness_status_label(payload.get('status'))}",
        f"统计窗口：最近 {_int_text(payload.get('lookback_hours'))} 小时",
    ]

    for check in checks:
        check_map = _mapping(check)
        lines.append(
            (
                f"- {_ops_check_label(check_map.get('name'))}："
                f"{_readiness_check_label(check_map.get('status'))}，"
                f"{_text(check_map.get('message'), '未返回检查说明')}"
            ),
        )

    if not checks:
        lines.append("检查项：暂无")

    lines.extend(
        [
            "该视图只读取已有运行记录，不触发采集、扫描、推送或模型调用。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def format_tushare_status(payload: Mapping[str, Any]) -> str:
    lines = [
        "Tushare 状态",
        f"状态：{_tushare_status_label(payload.get('status'))}",
        f"Token：{_configured_label(payload.get('token_configured'))}",
        f"手动抓取：{_enabled_label(payload.get('fetch_enabled'))}",
        (
            "已实现端点："
            f"{_int_text(payload.get('implemented_endpoint_count'))}/"
            f"{_int_text(payload.get('endpoint_count'))}"
        ),
        f"说明：{_text(payload.get('message'), '未返回状态说明')}",
        "该视图只读取 Tushare Provider 配置状态，不触发真实抓取。",
        "",
        DISCLAIMER,
    ]
    return _trim_text("\n".join(lines))


def format_tushare_readiness(payload: Mapping[str, Any]) -> str:
    endpoints = _sequence(payload.get("endpoints"))
    lines = [
        "Tushare 准入自检",
        f"状态：{_readiness_status_label(payload.get('status'))}",
        f"Token：{_configured_label(payload.get('token_configured'))}",
        f"手动抓取：{_enabled_label(payload.get('fetch_enabled'))}",
        (
            "调度准入样例："
            f"{_int_text(payload.get('scheduler_ready_endpoint_count'))}/"
            f"{_int_text(payload.get('implemented_endpoint_count'))}"
        ),
        f"策略：{_text(payload.get('scheduler_policy'), '未返回')}",
        f"说明：{_text(payload.get('message'), '未返回状态说明')}",
    ]

    if endpoints:
        lines.append("端点：")
        for endpoint in endpoints[:SUBJECTS_PREVIEW_LIMIT]:
            endpoint_map = _mapping(endpoint)
            checks = _sequence(endpoint_map.get("checks"))
            non_ok_checks = [
                _mapping(check)
                for check in checks
                if _mapping(check).get("status") != "ok"
            ]
            detail = (
                _text(non_ok_checks[0].get("message"), "未返回检查说明")
                if non_ok_checks
                else "检查项均正常"
            )
            eligibility = "可评审调度" if endpoint_map.get("scheduler_eligible") else "仅手动验证"
            title = _text(endpoint_map.get("title"), _text(endpoint_map.get("endpoint"), "-"))
            lines.append(
                (
                    f"- {title}："
                    f"{_readiness_status_label(endpoint_map.get('status'))} / "
                    f"{eligibility}，{detail}"
                ),
            )
    else:
        lines.append("端点：暂无")

    lines.extend(
        [
            "该视图只读取配置和已有抓取/质量记录，不触发真实抓取或调度。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def format_radar_overview(overview: Mapping[str, Any]) -> str:
    counts = _mapping(overview.get("priority_counts"))
    lifecycle_counts = _mapping(overview.get("lifecycle_counts"))
    stock_backtrace_evidences = _sequence(overview.get("stock_backtrace_evidences"))
    latest_scan = _mapping(overview.get("latest_scan"))
    latest_summary = _mapping(latest_scan.get("summary"))
    market_sentiment = _mapping(latest_summary.get("market_sentiment"))
    current_subjects = _sequence(overview.get("current_subjects"))
    lines = [
        "雷达总览",
        (
            "后端优先级计数："
            f"P0={_int_text(counts.get('P0'))} / "
            f"P1={_int_text(counts.get('P1'))} / "
            f"P2={_int_text(counts.get('P2'))}"
        ),
        f"后端生命周期分布：{_lifecycle_counts_text(lifecycle_counts)}",
        f"后端市场情绪：{_market_sentiment_text(market_sentiment)}",
        f"后端个股回推：{_stock_backtrace_text(stock_backtrace_evidences)}",
        f"当前主题：{_int_text(overview.get('subject_count'))} 个",
    ]

    if latest_scan:
        lines.extend(
            [
                (
                    "最新扫描："
                    f"#{_text(latest_scan.get('id'), '-')} "
                    f"{_scan_status_label(latest_scan.get('status'))}"
                ),
                f"开始时间：{_text(latest_scan.get('started_at'), '未返回')}",
                f"完成时间：{_text(latest_scan.get('finished_at'), '未返回')}",
                f"信号数量：{_int_text(latest_summary.get('signal_count'))}",
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


def format_reports(reports: Sequence[Mapping[str, Any]]) -> str:
    if not reports:
        return _trim_text(
            "\n".join(
                [
                    "报告列表",
                    "暂无报告。",
                    "报告只用于关注、观察、风险和复盘，不构成投资建议。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = ["报告列表"]
    for report in reports[:REPORT_PREVIEW_LIMIT]:
        lines.extend(
            [
                (
                    f"#{_text(report.get('id'), '-')} "
                    f"[{_text(report.get('report_type'), '-')}] "
                    f"{_text(report.get('title'), '未命名报告')}"
                ),
                (
                    "  "
                    f"状态：{_text(report.get('status'), '-')} | "
                    f"审查：{_review_label(report.get('review_status'))} | "
                    f"标签：{_text(report.get('suggestion_label'), '-')}"
                ),
                f"  {_text(report.get('summary'), '暂无摘要。')}",
            ],
        )

    if len(reports) > REPORT_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(reports) - REPORT_PREVIEW_LIMIT} 份更多报告。")

    lines.extend(
        [
            "报告正文请在 Web/API 中查看；Windows 客户端只展示摘要。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def format_periodic_report(report: Mapping[str, Any]) -> str:
    report_type = _text(report.get("report_type"), "daily")
    period_label = PERIOD_LABELS.get(report_type, report_type)
    counts = _mapping(report.get("priority_counts"))
    top_subjects = _sequence(report.get("top_subjects"))

    lines = [
        f"{period_label}汇总",
        (
            f"周期：{_text(report.get('period_start'), '未返回')} 至 "
            f"{_text(report.get('period_end'), '未返回')}"
        ),
        _text(report.get("summary"), "暂无摘要。"),
        (
            "优先级计数："
            f"P0={_int_text(counts.get('P0'))} / "
            f"P1={_int_text(counts.get('P1'))} / "
            f"P2={_int_text(counts.get('P2'))}"
        ),
        (
            f"信号：{_int_text(report.get('signal_count'))} 条 | "
            f"报告：{_int_text(report.get('report_count'))} 份 | "
            f"Telegram 推送：{_int_text(report.get('push_count'))} 次"
        ),
    ]

    if top_subjects:
        lines.extend(["", "重点主题："])
        for subject in top_subjects[:REPORT_PREVIEW_LIMIT]:
            subject_map = _mapping(subject)
            lines.append(
                (
                    f"- #{_text(subject_map.get('signal_id'), '-')} "
                    f"[{_text(subject_map.get('priority'), '-')}] "
                    f"{_text(subject_map.get('subject_name'), '未命名主题')} | "
                    f"生命周期：{_lifecycle_label(subject_map.get('lifecycle_stage'))} | "
                    f"审查：{_review_label(subject_map.get('review_status'))}"
                ),
            )
        if len(top_subjects) > REPORT_PREVIEW_LIMIT:
            lines.append(f"已折叠 {len(top_subjects) - REPORT_PREVIEW_LIMIT} 个更多主题。")
    else:
        lines.append("重点主题：暂无。")

    lines.extend(
        [
            "周期汇总由后端生成；Windows 客户端只展示摘要。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def format_scores(score_run: Mapping[str, Any]) -> str:
    signal_id = _text(score_run.get("signal_id"), "-")
    records = _sequence(score_run.get("records"))
    if not records:
        return _trim_text(
            "\n".join(
                [
                    f"信号 #{signal_id} 综合评分",
                    "暂无评分记录。可生成评分后再查看。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = [f"信号 #{signal_id} 综合评分"]
    for record in records:
        record_map = _mapping(record)
        status = _text(record_map.get("score_status"), "")
        details = _mapping(record_map.get("details"))
        score_band = _text(details.get("score_band"), "")
        band_label = SCORE_BAND_LABELS.get(score_band, score_band)
        band_suffix = f" / {band_label}" if band_label else ""
        lines.append(
            (
                f"- {_int_text(record_map.get('window_days'))}d："
                f"{_score_text(record_map.get('composite_score'))} "
                f"（{SCORE_STATUS_LABELS.get(status, _text(status, '-'))}{band_suffix}）"
            ),
        )
        component_text = _score_components_text(record_map.get("components"))
        if component_text:
            lines.append(f"  组件：{component_text}")

    lines.extend(
        [
            "评分综合优先级、生命周期、审查、证据、连续性、数据质量和时效性；不是价格回测或交易建议。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_text("\n".join(lines))


def _score_components_text(value: Any) -> str:
    components = _mapping(value)
    parts = [
        f"{SCORE_COMPONENT_LABELS.get(name, name)}={_score_text(components[name])}"
        for name in SCORE_COMPONENT_ORDER
        if name in components
    ]
    return " / ".join(parts)


def _lifecycle_counts_text(counts: Mapping[str, Any]) -> str:
    parts = [
        f"{_lifecycle_label(name)}={_int_text(counts.get(name))}"
        for name in LIFECYCLE_ORDER
        if counts.get(name)
    ]
    return " / ".join(parts) if parts else "暂无"


def _stock_backtrace_text(evidences: Sequence[Any]) -> str:
    if not evidences:
        return "暂无"

    parts = []
    for evidence in evidences[:STOCK_BACKTRACE_PREVIEW_LIMIT]:
        evidence_map = _mapping(evidence)
        parts.append(
            (
                f"{_text(evidence_map.get('stock_name'), '未命名个股')} "
                f"{_signed_percent(evidence_map.get('stock_pct_change'))} -> "
                f"{_text(evidence_map.get('subject_name'), '未命名主题')}"
            ),
        )

    if len(evidences) > STOCK_BACKTRACE_PREVIEW_LIMIT:
        parts.append(f"等 {len(evidences)} 条")

    return " / ".join(parts)


def _market_sentiment_text(sentiment: Mapping[str, Any]) -> str:
    if not sentiment:
        return "暂无"

    return (
        f"涨停={_int_text(sentiment.get('limit_up_count'))} / "
        f"跌停={_int_text(sentiment.get('limit_down_count'))} / "
        f"炸板={_int_text(sentiment.get('broken_limit_up_count'))} / "
        f"净压力={_int_text(sentiment.get('net_limit_pressure'))} / "
        f"偏向={_sentiment_bias_label(sentiment.get('sentiment_bias'))}"
    )


def _sentiment_bias_label(value: Any) -> str:
    labels = {
        "positive": "偏强",
        "negative": "偏弱",
        "mixed": "分歧",
        "unknown": "未知",
    }
    return labels.get(_text(value, "unknown"), _text(value, "unknown"))


def _ops_count_text(name: str, summary: Mapping[str, Any]) -> str:
    return (
        f"{name}："
        f"异常={_int_text(summary.get('unhealthy_count'))} / "
        f"总数={_int_text(summary.get('total_count'))} / "
        f"最新={_ops_status_label(summary.get('latest_status'))}"
    )


def _ops_status_label(value: Any) -> str:
    labels = {
        "success": "成功",
        "failure": "失败",
        "ok": "正常",
        "degraded": "降级",
        "failed": "失败",
        "fallback": "降级切换",
        "sent": "已发送",
        "preview": "预览",
        "skipped": "跳过",
    }
    return labels.get(_text(value, ""), _text(value, "暂无"))


def _ops_alerts_text(alerts: Sequence[Any]) -> str:
    if not alerts:
        return "暂无"

    return " / ".join(
        _text(_mapping(alert).get("message"), "未返回告警说明") for alert in alerts
    )


def _ops_failure_summary_text(items: Sequence[Any]) -> str:
    if not items:
        return "暂无"

    parts = []
    for item in items[:OPS_HISTORY_PREVIEW_LIMIT]:
        item_map = _mapping(item)
        parts.append(
            (
                f"{_ops_kind_label(item_map.get('kind'))} "
                f"{_text(item_map.get('key'), 'unknown')}="
                f"{_int_text(item_map.get('count'))}"
            ),
        )
    return " / ".join(parts)


def _ops_kind_label(value: Any) -> str:
    labels = {
        "radar_scan": "雷达",
        "provider_fetch": "Provider",
        "data_quality": "数据质量",
        "telegram_push": "推送",
        "model_call": "模型",
    }
    return labels.get(_text(value, ""), _text(value, "-"))


def _ops_check_label(value: Any) -> str:
    labels = {
        "server_disk": "服务端磁盘",
        "server_cpu": "服务端 CPU",
        "server_memory": "服务端内存",
        "radar_freshness": "雷达新鲜度",
        "radar_failure_rate": "扫描失败率",
        "provider_fetch": "Provider",
        "data_quality": "数据质量",
        "telegram_push": "推送",
        "model_calls": "模型",
    }
    return labels.get(_text(value, ""), _text(value, "-"))


def _readiness_status_label(value: Any) -> str:
    labels = {
        "ready": "可运行",
        "warning": "有警告",
        "blocked": "阻断",
    }
    return labels.get(_text(value, ""), _text(value, "-"))


def _readiness_check_label(value: Any) -> str:
    labels = {
        "ok": "正常",
        "warning": "警告",
        "fail": "失败",
    }
    return labels.get(_text(value, ""), _text(value, "-"))


def _ops_server_text(server: Mapping[str, Any]) -> str:
    disk_error = _text(server.get("disk_error"), "")
    if disk_error:
        disk_text = "磁盘检查失败"
    else:
        disk_text = f"磁盘可用={_percent_text(server.get('disk_free_percent'))}"

    cpu_error = _text(server.get("cpu_error"), "")
    if cpu_error:
        cpu_text = "CPU=不可用"
    else:
        cpu_text = f"CPU={_percent_text(server.get('cpu_usage_percent'))}"

    memory_error = _text(server.get("memory_error"), "")
    if memory_error:
        memory_text = "内存=不可用"
    else:
        memory_text = f"内存={_percent_text(server.get('memory_used_percent'))}"

    return (
        "服务端："
        f"运行={_duration_text(server.get('process_uptime_seconds'))} / "
        f"{disk_text} / "
        f"{cpu_text} / "
        f"{memory_text}"
    )


def _percent_text(value: Any) -> str:
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return "-"

    return f"{percent:.1f}".rstrip("0").rstrip(".") + "%"


def format_telegram_bindings(bindings: Sequence[Mapping[str, Any]]) -> str:
    if not bindings:
        return _trim_text(
            "\n".join(
                [
                    "Telegram 绑定",
                    "暂无数据库绑定。未配置环境白名单时，本地 webhook 仍保持开放模式。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = ["Telegram 绑定"]
    for binding in bindings[:TELEGRAM_BINDING_PREVIEW_LIMIT]:
        lines.extend(
            [
                (
                    f"#{_text(binding.get('id'), '-')} "
                    f"chat={_text(binding.get('chat_id'), '-')} "
                    f"user_key={_text(binding.get('user_key'), '-')}"
                ),
                (
                    "  "
                    f"状态：{_allowed_label(binding.get('is_allowed'))} | "
                    f"来源：{_text(binding.get('source'), '-')} | "
                    f"备注：{_text(binding.get('display_name'), '无')}"
                ),
            ],
        )

    if len(bindings) > TELEGRAM_BINDING_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(bindings) - TELEGRAM_BINDING_PREVIEW_LIMIT} 条更多绑定。")

    lines.extend(
        [
            "环境白名单存在时仍会先过滤；数据库绑定只在硬过滤范围内允许或禁用。",
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


def _tushare_status_label(value: Any) -> str:
    return TUSHARE_STATUS_LABELS.get(_text(value, "unknown"), _text(value, "unknown"))


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


def _rate_text(value: Any) -> str:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "-"

    return f"{rate * 100:.1f}".rstrip("0").rstrip(".") + "%"


def _duration_text(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "暂无"

    if seconds < 60:
        return f"{max(0, round(seconds))} 秒"
    if seconds < 3600:
        return f"{round(seconds / 60)} 分钟"

    return f"{seconds / 3600:.1f}".rstrip("0").rstrip(".") + " 小时"


def _stale_label(value: Any) -> str:
    return "可能停滞" if value is True else "正常"


def _signed_percent(value: Any) -> str:
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return "-"

    sign = "+" if number_value > 0 else ""
    return f"{sign}{number_value:g}%"


def _ratio_text(value: Any) -> str:
    if value is None:
        return "未填"

    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return _text(value, "未填")


def _score_text(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return _text(value, "-")


def _enabled_label(value: Any) -> str:
    return "开启" if value is True else "关闭"


def _configured_label(value: Any) -> str:
    return "已配置" if value is True else "未配置"


def _allowed_label(value: Any) -> str:
    return "允许" if value is True else "禁用"


def _user_key(value: str | None) -> str:
    normalized = (value or DEFAULT_USER_KEY).strip()
    return normalized or DEFAULT_USER_KEY


def _nonzero_int(value: int, field: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        msg = f"{field} must be a non-zero integer"
        raise ValueError(msg) from exc

    if normalized == 0:
        msg = f"{field} must be a non-zero integer"
        raise ValueError(msg)

    return normalized


def _positive_int(value: int, field: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        msg = f"{field} must be a positive integer"
        raise ValueError(msg) from exc

    if normalized <= 0:
        msg = f"{field} must be a positive integer"
        raise ValueError(msg)

    return normalized


def _trim_text(text: str) -> str:
    if len(text) <= MAX_TEXT_LENGTH:
        return text
    return f"{text[: MAX_TEXT_LENGTH - 12]}\n...内容已折叠"
