from datetime import UTC, datetime

from app.radar.schemas import (
    RadarLifecycleStage,
    RadarOverviewRead,
    RadarReviewStatus,
    RadarScanStatus,
    RadarSignalDetail,
    RadarSignalRead,
)

MAX_MESSAGE_LENGTH = 3500
SIGNALS_PREVIEW_LIMIT = 5
EVIDENCE_PREVIEW_LIMIT = 3
DISCLAIMER = "说明：仅用于关注、观察、风险和复盘，不构成投资建议。"

LIFECYCLE_LABELS = {
    RadarLifecycleStage.IGNITION: "启动观察",
    RadarLifecycleStage.DEVELOPING: "发展观察",
    RadarLifecycleStage.DIVERGENCE: "分歧风险",
    RadarLifecycleStage.RETURNING: "回流观察",
    RadarLifecycleStage.CLIMAX: "高位风险",
    RadarLifecycleStage.FADING: "降温观察",
    RadarLifecycleStage.EXTINGUISHED: "结束复盘",
}

REVIEW_LABELS = {
    RadarReviewStatus.CANDIDATE: "候选待审",
    RadarReviewStatus.APPROVED: "审查通过",
    RadarReviewStatus.BLOCKED: "审查阻断",
    RadarReviewStatus.NEEDS_HUMAN_REVIEW: "需要人工复核",
}

SCAN_STATUS_LABELS = {
    RadarScanStatus.RUNNING: "运行中",
    RadarScanStatus.SUCCESS: "完成",
    RadarScanStatus.NO_DATA: "暂无数据",
    RadarScanStatus.FAILURE: "异常",
}

EVIDENCE_TYPE_LABELS = {
    "market_snapshot": "市场快照",
}

FRESHNESS_LABELS = {
    "snapshot_latest": "最新快照",
    "unknown": "未知",
}


def format_help() -> str:
    return _trim_message(
        "\n".join(
            [
                "BaizeFinDB 雷达 Bot",
                "",
                "可用命令：",
                "/help - 查看命令说明",
                "/health - 查看 API、数据库、Redis 状态",
                "/radar - 查看雷达总览",
                "/signals - 查看最近信号折叠摘要",
                "/signal <id> - 查看单个信号复盘",
                "",
                DISCLAIMER,
            ],
        ),
    )


def format_health(checks: dict[str, dict[str, str]]) -> str:
    database = _check_label(checks.get("database", {}))
    redis = _check_label(checks.get("redis", {}))
    return _trim_message(
        "\n".join(
            [
                "健康状态",
                "API：正常",
                f"数据库：{database}",
                f"Redis：{redis}",
                "",
                DISCLAIMER,
            ],
        ),
    )


def format_radar_overview(overview: RadarOverviewRead) -> str:
    counts = overview.priority_counts
    lines = [
        "雷达总览",
        f"P0：{counts.get('P0', 0)} / P1：{counts.get('P1', 0)} / P2：{counts.get('P2', 0)}",
        f"当前主题：{overview.subject_count} 个",
    ]

    if overview.latest_scan is None:
        lines.extend(["最新扫描：暂无", "提示：可先采集 Provider 数据并运行雷达扫描。"])
    else:
        latest_scan = overview.latest_scan
        lines.extend(
            [
                (
                    "最新扫描："
                    f"#{latest_scan.id} {_scan_status_label(latest_scan.status)}，"
                    f"信号 {len(latest_scan.signals)} 条"
                ),
                f"开始时间：{_format_time(latest_scan.started_at)}",
            ],
        )

    lines.extend(["", DISCLAIMER])
    return _trim_message("\n".join(lines))


def format_signals(signals: list[RadarSignalRead]) -> str:
    if not signals:
        return _trim_message(
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

    lines = ["最近信号折叠摘要"]
    for signal in signals[:SIGNALS_PREVIEW_LIMIT]:
        lines.append(
            (
                f"#{signal.id} [{_value(signal.priority)}] {signal.subject_name} | "
                f"生命周期：{_lifecycle_label(signal.lifecycle_stage)} | "
                f"审查：{_review_label(signal.review_status)}"
            ),
        )

    if len(signals) > SIGNALS_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(signals) - SIGNALS_PREVIEW_LIMIT} 条更多信号。")

    lines.extend(["使用 /signal <id> 查看单条复盘。", "", DISCLAIMER])
    return _trim_message("\n".join(lines))


def format_signal_detail(signal: RadarSignalDetail) -> str:
    lines = [
        f"信号 #{signal.id} 复盘",
        f"主题：{signal.subject_name}",
        f"优先级：{_value(signal.priority)}（后端雷达判定）",
        f"生命周期：{_lifecycle_label(signal.lifecycle_stage)}",
        f"审查状态：{_review_label(signal.review_status)}",
        (
            "摘要："
            f"{signal.subject_name} 当前进入 {_value(signal.priority)} 观察队列，"
            "用于关注和复盘。"
        ),
        f"证据数量：{len(signal.evidences)} 条",
    ]

    for index, evidence in enumerate(signal.evidences[:EVIDENCE_PREVIEW_LIMIT], start=1):
        evidence_type = EVIDENCE_TYPE_LABELS.get(evidence.evidence_type, "证据摘要")
        freshness = FRESHNESS_LABELS.get(evidence.freshness, "状态待确认")
        lines.append(
            f"- 证据 {index}：{evidence_type}，来源：{evidence.source_name}，"
            f"新鲜度：{freshness}",
        )

    if len(signal.evidences) > EVIDENCE_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(signal.evidences) - EVIDENCE_PREVIEW_LIMIT} 条更多证据。")

    lines.extend(["", DISCLAIMER])
    return _trim_message("\n".join(lines))


def format_unauthorized() -> str:
    return "当前聊天未在 MVP 白名单中，已拒绝处理。"


def format_no_text() -> str:
    return "当前只支持文本命令。发送 /help 查看可用命令。"


def format_unknown_command() -> str:
    return "未识别命令。发送 /help 查看可用命令。"


def format_invalid_signal_id() -> str:
    return "请使用 /signal <id> 查看单个信号复盘。"


def format_signal_not_found(signal_id: int) -> str:
    return f"未找到 #{signal_id} 信号。"


def _check_label(check: dict[str, str]) -> str:
    if check.get("status") == "ok":
        return "正常"

    error = check.get("error")
    return f"异常（{error}）" if error else "异常"


def _lifecycle_label(value: RadarLifecycleStage | str) -> str:
    return LIFECYCLE_LABELS.get(value, _value(value))


def _review_label(value: RadarReviewStatus | str) -> str:
    return REVIEW_LABELS.get(value, _value(value))


def _scan_status_label(value: RadarScanStatus | str) -> str:
    return SCAN_STATUS_LABELS.get(value, _value(value))


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _format_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _trim_message(message: str) -> str:
    if len(message) <= MAX_MESSAGE_LENGTH:
        return message

    return f"{message[: MAX_MESSAGE_LENGTH - 12]}\n...内容已折叠"
