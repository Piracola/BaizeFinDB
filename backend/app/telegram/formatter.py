from datetime import UTC, datetime

from app.ops.schemas import OpsHistoryRead, OpsOverviewRead, OpsReadinessRead
from app.portfolio.schemas import HoldingRead, WatchlistItemRead
from app.providers.schemas import TushareProviderStatusResponse, TushareReadinessResponse
from app.radar.schemas import (
    RadarLifecycleStage,
    RadarOverviewRead,
    RadarReviewStatus,
    RadarScanRead,
    RadarScanStatus,
    RadarSignalDetail,
    RadarSignalRead,
)
from app.reports.schemas import PeriodicReportRead, ReportRead
from app.scores.schemas import ScoreRunRead

MAX_MESSAGE_LENGTH = 3500
SIGNALS_PREVIEW_LIMIT = 5
PORTFOLIO_PREVIEW_LIMIT = 8
REPORT_PREVIEW_LIMIT = 5
EVIDENCE_PREVIEW_LIMIT = 3
PUSH_PREVIEW_LIMIT_PER_PRIORITY = 5
STOCK_BACKTRACE_PREVIEW_LIMIT = 3
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

LIFECYCLE_ORDER = (
    RadarLifecycleStage.IGNITION,
    RadarLifecycleStage.DEVELOPING,
    RadarLifecycleStage.DIVERGENCE,
    RadarLifecycleStage.RETURNING,
    RadarLifecycleStage.CLIMAX,
    RadarLifecycleStage.FADING,
    RadarLifecycleStage.EXTINGUISHED,
)

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


def format_help() -> str:
    return _trim_message(
        "\n".join(
            [
                "BaizeFinDB 雷达 Bot",
                "",
                "可用命令：",
                "/help - 查看命令说明",
                "/id - 查看当前聊天 ID，用于绑定白名单",
                "/health - 查看 API、数据库、Redis 和最近扫描状态",
                "/ops - 查看最近运行状态、失败率和降级摘要",
                "/ops_history - 查看最近运维异常历史",
                "/ops_ready - 查看部署/运行就绪自检",
                "/tushare - 查看 Tushare 数据源配置状态",
                "/tushare_ready - 查看 Tushare 抓取/调度准入自检",
                "/radar - 查看雷达总览",
                "/signals - 查看最近信号折叠摘要",
                "/signal <id> - 查看单个信号复盘",
                "/holding - 查看当前聊天绑定的手动持仓",
                "/watchlist - 查看当前聊天绑定的自选关注",
                "/reports - 查看当前聊天绑定的报告列表",
                "/daily - 查看当前聊天绑定的日报汇总",
                "/weekly - 查看当前聊天绑定的周报汇总",
                "/score <id> - 生成并查看单个信号的 1d/3d/5d/10d 综合评分",
                "",
                DISCLAIMER,
            ],
        ),
    )


def format_health(
    checks: dict[str, dict[str, str]],
    latest_scan: RadarScanRead | None = None,
) -> str:
    database = _check_label(checks.get("database", {}))
    redis = _check_label(checks.get("redis", {}))
    lines = [
        "健康状态",
        "API：正常",
        f"数据库：{database}",
        f"Redis：{redis}",
    ]

    if latest_scan is None:
        lines.append("最近扫描：暂无")
    else:
        lines.extend(
            [
                (
                    "最近扫描："
                    f"#{latest_scan.id} {_scan_status_label(latest_scan.status)}，"
                    f"信号 {len(latest_scan.signals)} 条"
                ),
                f"开始时间：{_format_time(latest_scan.started_at)}",
            ],
        )
        if latest_scan.error_message:
            lines.append(f"扫描错误：{latest_scan.error_message}")

    lines.extend(["", DISCLAIMER])
    return _trim_message("\n".join(lines))


def format_ops_overview(overview: OpsOverviewRead) -> str:
    radar = overview.radar
    latest_scan_id = radar.latest_scan_id
    latest_scan_ref = f"#{latest_scan_id}" if latest_scan_id is not None else "暂无"
    lines = [
        "运行状态",
        f"统计窗口：最近 {overview.lookback_hours} 小时",
        (
            "雷达扫描："
            f"{latest_scan_ref} {_ops_status_label(radar.latest_scan_status)} | "
            f"新鲜度：{_duration_label(radar.latest_scan_age_seconds)} | "
            f"{_stale_label(radar.is_latest_scan_stale)}"
        ),
        (
            "扫描失败率："
            f"{_rate_label(radar.recent_scan_failure_rate)} "
            f"({radar.recent_scan_failure_count}/{radar.recent_scan_count})"
        ),
        _ops_server_text(overview.server),
        _ops_count_text("Provider", overview.provider_fetch),
        _ops_count_text("数据质量", overview.data_quality),
        _ops_count_text("推送", overview.telegram_push),
        _ops_count_text("模型", overview.model_calls),
        f"告警：{_ops_alerts_text(overview.alerts)}",
        "该视图只读取已有运行记录，不触发采集、扫描、推送或模型调用。",
        "",
        DISCLAIMER,
    ]
    return _trim_message("\n".join(lines))


def format_ops_history(history: OpsHistoryRead) -> str:
    lines = [
        "运维历史",
        f"统计窗口：最近 {history.lookback_hours} 小时",
        f"事件：{len(history.recent_events)} 条 / Top {history.limit}",
    ]

    if history.failure_summary:
        lines.append(
            "异常汇总："
            + " / ".join(
                f"{_ops_kind_label(item.kind)} {item.key}={item.count}"
                for item in history.failure_summary[:5]
            ),
        )
    else:
        lines.append("异常汇总：暂无")

    if history.recent_events:
        lines.append("最近事件：")
        for event in history.recent_events[:5]:
            detail = f" | {event.detail}" if event.detail else ""
            lines.append(
                (
                    f"- {_ops_kind_label(event.kind)} #{event.id} "
                    f"{_ops_status_label(event.status)} | "
                    f"{_format_time(event.occurred_at)}{detail}"
                ),
            )
    else:
        lines.append("最近事件：暂无")

    lines.extend(["该视图只读取已有运行记录，不触发采集、扫描、推送或模型调用。", "", DISCLAIMER])
    return _trim_message("\n".join(lines))


def format_ops_readiness(readiness: OpsReadinessRead) -> str:
    lines = [
        "运行就绪自检",
        f"状态：{_readiness_status_label(readiness.status)}",
        f"统计窗口：最近 {readiness.lookback_hours} 小时",
    ]
    for check in readiness.checks:
        lines.append(
            (
                f"- {_ops_check_label(check.name)}："
                f"{_readiness_check_label(check.status)}，{check.message}"
            ),
        )

    lines.extend(["该视图只读取已有运行记录，不触发采集、扫描、推送或模型调用。", "", DISCLAIMER])
    return _trim_message("\n".join(lines))


def format_tushare_status(status: TushareProviderStatusResponse) -> str:
    lines = [
        "Tushare 状态",
        f"状态：{_tushare_status_label(status.status)}",
        f"Token：{_configured_label(status.token_configured)}",
        f"手动抓取：{_enabled_label(status.fetch_enabled)}",
        f"已实现端点：{status.implemented_endpoint_count}/{status.endpoint_count}",
        f"说明：{status.message}",
        "该视图只读取 Provider 配置状态，不触发真实抓取。",
        "",
        DISCLAIMER,
    ]
    return _trim_message("\n".join(lines))


def format_tushare_readiness(readiness: TushareReadinessResponse) -> str:
    lines = [
        "Tushare 准入自检",
        f"状态：{_readiness_status_label(readiness.status)}",
        f"Token：{_configured_label(readiness.token_configured)}",
        f"手动抓取：{_enabled_label(readiness.fetch_enabled)}",
        (
            "调度准入样例："
            f"{readiness.scheduler_ready_endpoint_count}/"
            f"{readiness.implemented_endpoint_count}"
        ),
        f"策略：{readiness.scheduler_policy}",
        f"说明：{readiness.message}",
    ]

    for endpoint in readiness.endpoints[:5]:
        non_ok_checks = [check for check in endpoint.checks if check.status != "ok"]
        detail = non_ok_checks[0].message if non_ok_checks else "检查项均正常。"
        eligibility = "可评审调度" if endpoint.scheduler_eligible else "仅手动验证"
        lines.append(
            (
                f"- {endpoint.title}：{_readiness_status_label(endpoint.status)} / "
                f"{eligibility}，{detail}"
            ),
        )

    lines.extend(
        [
            "该视图只读取配置和已有抓取/质量记录，不触发真实抓取或调度。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_message("\n".join(lines))


def format_radar_overview(overview: RadarOverviewRead) -> str:
    counts = overview.priority_counts
    stock_backtrace_text = _stock_backtrace_text(
        getattr(overview, "stock_backtrace_evidences", []),
    )
    market_sentiment_text = _market_sentiment_text(_overview_market_sentiment(overview))
    lines = [
        "雷达总览",
        f"P0：{counts.get('P0', 0)} / P1：{counts.get('P1', 0)} / P2：{counts.get('P2', 0)}",
        f"生命周期：{_lifecycle_counts_text(overview.lifecycle_counts)}",
        f"市场情绪：{market_sentiment_text}",
        f"个股回推：{stock_backtrace_text}",
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


def format_holdings(holdings: list[HoldingRead]) -> str:
    if not holdings:
        return _trim_message(
            "\n".join(
                [
                    "手动持仓",
                    "当前聊天暂未维护持仓。",
                    "持仓只用于个人提醒、展示排序和报告上下文，不改变市场雷达等级。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = ["手动持仓", f"共 {len(holdings)} 条"]
    for holding in holdings[:PORTFOLIO_PREVIEW_LIMIT]:
        details = [
            f"市场：{holding.market}",
            f"仓位：{_ratio_label(holding.position_ratio)}",
            f"提醒：{_enabled_label(holding.alert_enabled)}",
        ]
        if holding.cost_price is not None:
            details.append(f"成本：{holding.cost_price:g}")

        lines.append(
            f"- #{holding.id} {holding.instrument_code} {holding.instrument_name} | "
            + " | ".join(details),
        )
        if holding.note:
            lines.append(f"  备注：{holding.note}")

    if len(holdings) > PORTFOLIO_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(holdings) - PORTFOLIO_PREVIEW_LIMIT} 条更多持仓。")

    lines.extend(
        [
            "持仓只用于个人提醒、展示排序和报告上下文，不改变市场雷达等级。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_message("\n".join(lines))


def format_watchlist_items(items: list[WatchlistItemRead]) -> str:
    if not items:
        return _trim_message(
            "\n".join(
                [
                    "自选关注",
                    "当前聊天暂未维护自选。",
                    "自选只用于个人提醒、展示排序和报告上下文，不改变市场雷达等级。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = ["自选关注", f"共 {len(items)} 条"]
    for item in items[:PORTFOLIO_PREVIEW_LIMIT]:
        lines.append(
            (
                f"- #{item.id} {item.instrument_code} {item.instrument_name} | "
                f"市场：{item.market} | 提醒：{_enabled_label(item.alert_enabled)}"
            ),
        )
        if item.note:
            lines.append(f"  备注：{item.note}")

    if len(items) > PORTFOLIO_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(items) - PORTFOLIO_PREVIEW_LIMIT} 条更多自选。")

    lines.extend(
        [
            "自选只用于个人提醒、展示排序和报告上下文，不改变市场雷达等级。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_message("\n".join(lines))


def format_reports(reports: list[ReportRead]) -> str:
    if not reports:
        return _trim_message(
            "\n".join(
                [
                    "报告列表",
                    "当前聊天暂未生成报告。",
                    "报告只用于关注、观察、风险和复盘，不构成投资建议。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = ["报告列表", f"共 {len(reports)} 份"]
    for report in reports[:REPORT_PREVIEW_LIMIT]:
        lines.extend(
            [
                (
                    f"- #{report.id} [{report.report_type.value}] {report.title} | "
                    f"状态：{report.status.value} | 标签：{report.suggestion_label.value}"
                ),
                f"  {report.summary}",
            ],
        )

    if len(reports) > REPORT_PREVIEW_LIMIT:
        lines.append(f"已折叠 {len(reports) - REPORT_PREVIEW_LIMIT} 份更多报告。")

    lines.extend(["报告正文请在 Web/API 中查看。", "", DISCLAIMER])
    return _trim_message("\n".join(lines))


def format_periodic_report(report: PeriodicReportRead) -> str:
    label = "日报" if report.report_type.value == "daily" else "周报"
    lines = [
        f"{label}汇总",
        report.summary,
        (
            "优先级："
            f"P0 {report.priority_counts.get('P0', 0)} / "
            f"P1 {report.priority_counts.get('P1', 0)} / "
            f"P2 {report.priority_counts.get('P2', 0)}"
        ),
        f"报告：{report.report_count} 份",
        f"Telegram 推送：{report.push_count} 次",
    ]

    if report.top_subjects:
        lines.append("")
        lines.append("重点主题：")
        for subject in report.top_subjects[:REPORT_PREVIEW_LIMIT]:
            lines.append(
                (
                    f"- #{subject.signal_id} [{subject.priority}] {subject.subject_name} | "
                    f"生命周期：{_lifecycle_label(subject.lifecycle_stage)} | "
                    f"审查：{_review_label(subject.review_status)}"
                ),
            )
    else:
        lines.append("重点主题：暂无。")

    lines.extend(["", DISCLAIMER])
    return _trim_message("\n".join(lines))


def _lifecycle_counts_text(counts: dict[str, int]) -> str:
    parts = [
        f"{_lifecycle_label(stage)} {counts.get(stage.value, 0)}"
        for stage in LIFECYCLE_ORDER
        if counts.get(stage.value, 0)
    ]
    return " / ".join(parts) if parts else "暂无"


def _stock_backtrace_text(evidences: list[object]) -> str:
    if not evidences:
        return "暂无"

    parts = [
        (
            f"{_field(evidence, 'stock_name', '未命名个股')} "
            f"{_signed_percent(_field(evidence, 'stock_pct_change', None))} -> "
            f"{_field(evidence, 'subject_name', '未命名主题')}"
        )
        for evidence in evidences[:STOCK_BACKTRACE_PREVIEW_LIMIT]
    ]
    if len(evidences) > STOCK_BACKTRACE_PREVIEW_LIMIT:
        parts.append(f"等 {len(evidences)} 条")

    return " / ".join(parts)


def _overview_market_sentiment(overview: RadarOverviewRead) -> dict[str, object]:
    latest_scan = getattr(overview, "latest_scan", None)
    if latest_scan is None:
        return {}

    summary = _field(latest_scan, "summary", {})
    if not isinstance(summary, dict):
        return {}

    sentiment = summary.get("market_sentiment")
    return sentiment if isinstance(sentiment, dict) else {}


def _market_sentiment_text(sentiment: dict[str, object]) -> str:
    if not sentiment:
        return "暂无"

    return (
        f"涨停 {_field(sentiment, 'limit_up_count', 0)} / "
        f"跌停 {_field(sentiment, 'limit_down_count', 0)} / "
        f"炸板 {_field(sentiment, 'broken_limit_up_count', 0)} / "
        f"净压力 {_field(sentiment, 'net_limit_pressure', 0)} / "
        f"偏向：{_sentiment_bias_label(_field(sentiment, 'sentiment_bias', 'unknown'))}"
    )


def _sentiment_bias_label(value: object) -> str:
    labels = {
        "positive": "偏强",
        "negative": "偏弱",
        "mixed": "分歧",
        "unknown": "未知",
    }
    return labels.get(_value(value), _value(value))


def _ops_count_text(name: str, summary: object) -> str:
    return (
        f"{name}："
        f"异常 {_field(summary, 'unhealthy_count', 0)} / "
        f"总数 {_field(summary, 'total_count', 0)} / "
        f"最新 {_ops_status_label(_field(summary, 'latest_status', None))}"
    )


def _ops_status_label(value: object) -> str:
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
        "running": "运行中",
        "no_data": "暂无数据",
    }
    raw_value = _value(value) if value is not None else "unknown"
    return labels.get(raw_value, "暂无" if value is None else raw_value)


def _ops_kind_label(value: object) -> str:
    labels = {
        "radar_scan": "雷达",
        "provider_fetch": "Provider",
        "data_quality": "数据质量",
        "telegram_push": "推送",
        "model_call": "模型",
    }
    return labels.get(_value(value), _value(value))


def _ops_check_label(value: object) -> str:
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
    return labels.get(_value(value), _value(value))


def _readiness_status_label(value: object) -> str:
    labels = {
        "ready": "可运行",
        "warning": "有警告",
        "blocked": "阻断",
    }
    return labels.get(_value(value), _value(value))


def _readiness_check_label(value: object) -> str:
    labels = {
        "ok": "正常",
        "warning": "警告",
        "fail": "失败",
    }
    return labels.get(_value(value), _value(value))


def _ops_alerts_text(alerts: list[object]) -> str:
    if not alerts:
        return "暂无"

    return " / ".join(str(_field(alert, "message", "未返回告警说明")) for alert in alerts)


def _ops_server_text(server: object) -> str:
    disk_error = _field(server, "disk_error", None)
    if disk_error:
        disk_text = "磁盘检查失败"
    else:
        disk_text = f"磁盘可用 {_percent_label(_field(server, 'disk_free_percent', None))}"

    cpu_error = _field(server, "cpu_error", None)
    if cpu_error:
        cpu_text = "CPU 指标不可用"
    else:
        cpu_text = f"CPU {_percent_label(_field(server, 'cpu_usage_percent', None))}"

    memory_error = _field(server, "memory_error", None)
    if memory_error:
        memory_text = "内存指标不可用"
    else:
        memory_text = f"内存 {_percent_label(_field(server, 'memory_used_percent', None))}"

    return (
        "服务端："
        f"运行 {_duration_label(_field(server, 'process_uptime_seconds', None))} | "
        f"{disk_text} | "
        f"{cpu_text} | "
        f"{memory_text}"
    )


def _percent_label(value: object) -> str:
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return "-"

    return f"{percent:.1f}".rstrip("0").rstrip(".") + "%"


def _rate_label(value: object) -> str:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "-"

    return f"{rate * 100:.1f}".rstrip("0").rstrip(".") + "%"


def _duration_label(value: object) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "暂无"

    if seconds < 60:
        return f"{max(0, round(seconds))} 秒"
    if seconds < 3600:
        return f"{round(seconds / 60)} 分钟"

    return f"{seconds / 3600:.1f}".rstrip("0").rstrip(".") + " 小时"


def _stale_label(value: bool) -> str:
    return "可能停滞" if value else "正常"


def format_scores(score_run: ScoreRunRead) -> str:
    if not score_run.records:
        return _trim_message(
            "\n".join(
                [
                    f"信号 #{score_run.signal_id} 评分",
                    "暂无评分记录。可稍后重试。",
                    "",
                    DISCLAIMER,
                ],
            ),
        )

    lines = [f"信号 #{score_run.signal_id} 综合评分"]
    for record in score_run.records:
        status_label = "已完成" if record.score_status.value == "generated" else "窗口未结束"
        score_band = str(record.details.get("score_band", "")).strip()
        band_label = SCORE_BAND_LABELS.get(score_band, score_band)
        band_suffix = f" / {band_label}" if band_label else ""
        lines.append(
            (
                f"- {record.window_days}d：{record.composite_score:.2f} "
                f"({status_label}{band_suffix})"
            ),
        )
        component_text = _score_components_text(record.components)
        if component_text:
            lines.append(f"  组件：{component_text}")

    lines.extend(
        [
            "评分综合优先级、生命周期、审查、证据、连续性、数据质量和时效性；不是价格回测或交易建议。",
            "",
            DISCLAIMER,
        ],
    )
    return _trim_message("\n".join(lines))


def _score_components_text(components: dict[str, object]) -> str:
    parts = [
        f"{SCORE_COMPONENT_LABELS.get(name, name)}={_score_value(components[name])}"
        for name in SCORE_COMPONENT_ORDER
        if name in components
    ]
    return " / ".join(parts)


def format_radar_push(
    scan_id: int,
    signals: list[RadarSignalRead],
    blocked_signal_ids: list[int],
    needs_human_review_signal_ids: list[int],
    priority_counts: dict[str, int],
) -> str:
    lines = [
        "雷达折叠推送",
        f"扫描批次：#{scan_id}",
        (
            "折叠计数："
            f"P0 {priority_counts.get('P0', 0)} / "
            f"P1 {priority_counts.get('P1', 0)} / "
            f"P2 {priority_counts.get('P2', 0)}"
        ),
    ]

    if not signals:
        lines.append("本轮没有通过审查且需要推送的雷达信号。")

    human_review_ids = set(needs_human_review_signal_ids)
    for priority in ("P0", "P1", "P2"):
        priority_signals = [signal for signal in signals if _value(signal.priority) == priority]
        if not priority_signals:
            continue

        lines.append("")
        lines.append(f"{priority}：{len(priority_signals)} 条")
        for signal in priority_signals[:PUSH_PREVIEW_LIMIT_PER_PRIORITY]:
            human_review_label = " | 需人工复核" if signal.id in human_review_ids else ""
            lines.append(
                (
                    f"- #{signal.id} {signal.subject_name} | "
                    f"生命周期：{_lifecycle_label(signal.lifecycle_stage)} | "
                    f"审查：{_review_label(signal.review_status)}"
                    f"{human_review_label}"
                ),
            )

        folded_count = len(priority_signals) - PUSH_PREVIEW_LIMIT_PER_PRIORITY
        if folded_count > 0:
            lines.append(f"  已折叠 {folded_count} 条更多 {priority} 信号。")

    if blocked_signal_ids:
        lines.append("")
        lines.append(f"已过滤 {len(blocked_signal_ids)} 条审查阻断信号。")

    if signals:
        lines.append("使用 /signal <id> 查看单条复盘。")

    lines.extend(["", DISCLAIMER])
    return _trim_message("\n".join(lines))


def format_unauthorized() -> str:
    return "当前聊天未在 MVP 白名单中，已拒绝处理。"


def format_no_text() -> str:
    return "当前只支持文本命令。发送 /help 查看可用命令。"


def format_unknown_command() -> str:
    return "未识别命令。发送 /help 查看可用命令。"


def format_chat_identity(chat_id: int) -> str:
    return _trim_message(
        "\n".join(
            [
                "Telegram Chat ID",
                f"当前聊天 ID：{chat_id}",
                "可在 Web/Windows/API 的 Telegram 绑定中使用这个 ID。",
                "",
                DISCLAIMER,
            ],
        ),
    )


def format_invalid_signal_id() -> str:
    return "请使用 /signal <id> 查看单个信号复盘。"


def format_invalid_score_signal_id() -> str:
    return "请使用 /score <id> 生成并查看单个信号评分。"


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


def _enabled_label(value: bool) -> str:
    return "开启" if value else "关闭"


def _configured_label(value: bool) -> str:
    return "已配置" if value else "未配置"


def _tushare_status_label(value: str) -> str:
    labels = {
        "configured": "已配置",
        "not_configured": "未配置",
        "unknown": "未知",
    }
    return labels.get(value, value)


def _ratio_label(value: float | None) -> str:
    if value is None:
        return "未填"

    return f"{value:.0%}"


def _score_value(value: object) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return _value(value)


def _signed_percent(value: object) -> str:
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return "-"

    sign = "+" if number_value > 0 else ""
    text = f"{number_value:g}"
    return f"{sign}{text}%"


def _field(value: object, name: str, default: object) -> object:
    if isinstance(value, dict):
        return value.get(name, default)

    return getattr(value, name, default)


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
