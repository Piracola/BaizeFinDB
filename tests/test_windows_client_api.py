import io
import json
from urllib.error import HTTPError, URLError

import pytest

from clients.windows import client_api


class FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload.encode("utf-8")


def test_normalize_base_url_defaults_and_strips_trailing_slash() -> None:
    assert client_api.normalize_base_url(None) == "http://127.0.0.1:8000"
    assert client_api.normalize_base_url(" 127.0.0.1:8000/ ") == "http://127.0.0.1:8000"
    assert client_api.normalize_base_url("https://example.com/api/") == "https://example.com/api"


def test_normalize_base_url_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        client_api.normalize_base_url("ftp://example.com")


def test_build_url_preserves_base_path_and_adds_query() -> None:
    url = client_api.build_url(
        "https://example.com/api/",
        "/radar/signals",
        {"priority": "P1", "limit": 20, "empty": None},
    )

    assert url == "https://example.com/api/radar/signals?priority=P1&limit=20"


def test_get_json_uses_mockable_opener() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["timeout"] = timeout
        calls["accept"] = request.get_header("Accept")
        return FakeResponse('{"status":"ok"}')

    payload = client_api.get_json("http://localhost:8000", "/health", opener=opener)

    assert payload == {"status": "ok"}
    assert calls == {
        "url": "http://localhost:8000/health",
        "timeout": client_api.DEFAULT_TIMEOUT_SECONDS,
        "accept": "application/json",
    }


def test_get_json_can_send_telegram_secret_header() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["secret"] = _telegram_secret_header(request)
        return FakeResponse('{"status":"ok"}')

    client_api.get_json(
        "http://localhost:8000",
        "/telegram/bindings",
        secret_token="hook-secret",
        opener=opener,
    )

    assert calls["secret"] == "hook-secret"


def test_get_json_raises_api_error_with_parsed_http_payload() -> None:
    def opener(request: object, *, timeout: int) -> FakeResponse:
        raise HTTPError(
            request.full_url,
            503,
            "Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(b'{"detail":"database unavailable"}'),
        )

    with pytest.raises(client_api.BaizeApiError) as exc_info:
        client_api.get_json("http://localhost:8000", "/health/ready", opener=opener)

    assert exc_info.value.status_code == 503
    assert exc_info.value.payload == {"detail": "database unavailable"}
    assert "database unavailable" in str(exc_info.value)


def test_get_json_wraps_url_errors() -> None:
    def opener(request: object, *, timeout: int) -> FakeResponse:
        raise URLError("connection refused")

    with pytest.raises(client_api.BaizeApiError, match="无法连接 API"):
        client_api.get_json("http://localhost:8000", "/health", opener=opener)


def test_fetch_ops_overview_uses_lookback_query() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        return FakeResponse(
            json.dumps(
                {
                    "generated_at": "2026-05-03T09:30:00Z",
                    "lookback_hours": 12,
                    "radar": {},
                    "provider_fetch": {},
                    "data_quality": {},
                    "telegram_push": {},
                    "model_calls": {},
                },
            ),
        )

    payload = client_api.fetch_ops_overview(
        "http://localhost:8000",
        lookback_hours=12,
        opener=opener,
    )

    assert calls["url"] == "http://localhost:8000/ops/overview?lookback_hours=12"
    assert payload["lookback_hours"] == 12


def test_fetch_ops_history_uses_lookback_and_limit_query() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        return FakeResponse(
            json.dumps(
                {
                    "generated_at": "2026-05-04T09:30:00Z",
                    "lookback_hours": 12,
                    "limit": 5,
                    "recent_events": [],
                    "failure_summary": [],
                },
            ),
        )

    payload = client_api.fetch_ops_history(
        "http://localhost:8000",
        lookback_hours=12,
        limit=5,
        opener=opener,
    )

    assert calls["url"] == "http://localhost:8000/ops/history?lookback_hours=12&limit=5"
    assert payload["limit"] == 5


def test_fetch_ops_readiness_uses_lookback_query() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        return FakeResponse(
            json.dumps(
                {
                    "generated_at": "2026-05-04T09:30:00Z",
                    "lookback_hours": 12,
                    "status": "ready",
                    "checks": [],
                },
            ),
        )

    payload = client_api.fetch_ops_readiness(
        "http://localhost:8000",
        lookback_hours=12,
        opener=opener,
    )

    assert calls["url"] == "http://localhost:8000/ops/readiness?lookback_hours=12"
    assert payload["status"] == "ready"


def test_fetch_ops_trends_uses_lookback_and_bucket_count_query() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        return FakeResponse(
            json.dumps(
                {
                    "generated_at": "2026-05-04T09:30:00Z",
                    "lookback_hours": 12,
                    "bucket_count": 12,
                    "buckets": [],
                },
            ),
        )

    payload = client_api.fetch_ops_trends(
        "http://localhost:8000",
        lookback_hours=12,
        bucket_count=12,
        opener=opener,
    )

    assert calls["url"] == "http://localhost:8000/ops/trends?lookback_hours=12&bucket_count=12"
    assert payload["bucket_count"] == 12


def test_fetch_tushare_status_uses_provider_status_endpoint() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        return FakeResponse(
            json.dumps(
                {
                    "provider": "tushare",
                    "status": "configured",
                    "token_configured": True,
                    "fetch_enabled": True,
                    "endpoint_count": 3,
                    "implemented_endpoint_count": 3,
                },
            ),
        )

    payload = client_api.fetch_tushare_status("http://localhost:8000", opener=opener)

    assert calls["url"] == "http://localhost:8000/providers/tushare/status"
    assert payload["provider"] == "tushare"


def test_fetch_tushare_readiness_uses_provider_readiness_endpoint() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        return FakeResponse(
            json.dumps(
                {
                    "provider_name": "tushare",
                    "status": "warning",
                    "token_configured": True,
                    "fetch_enabled": True,
                    "scheduler_ready_endpoint_count": 0,
                    "implemented_endpoint_count": 3,
                    "scheduler_policy": "manual_only",
                    "message": "Need samples.",
                    "endpoints": [],
                },
            ),
        )

    payload = client_api.fetch_tushare_readiness("http://localhost:8000", opener=opener)

    assert calls["url"] == "http://localhost:8000/providers/tushare/readiness"
    assert payload["provider_name"] == "tushare"


def test_format_health_outputs_dependency_statuses() -> None:
    text = client_api.format_health(
        {
            "status": "not_ready",
            "service": "BaizeFinDB",
            "checks": {
                "database": {"status": "ok"},
                "redis": {"status": "failure", "error": "redis down"},
            },
        },
    )

    assert "健康状态" in text
    assert "整体：未就绪" in text
    assert "数据库：正常" in text
    assert "Redis：失败（redis down）" in text
    assert "不构成投资建议" in text


def test_format_ops_overview_outputs_runtime_summary() -> None:
    text = client_api.format_ops_overview(
        {
            "generated_at": "2026-05-03T09:30:00Z",
            "lookback_hours": 24,
            "radar": {
                "latest_scan_id": 7,
                "latest_scan_status": "success",
                "latest_scan_age_seconds": 330,
                "is_latest_scan_stale": False,
                "recent_scan_count": 8,
                "recent_scan_failure_count": 1,
                "recent_scan_failure_rate": 0.125,
            },
            "server": {
                "process_uptime_seconds": 7200,
                "disk_free_percent": 42.5,
                "disk_free_bytes": 4_194_304,
                "disk_total_bytes": 10_485_760,
                "is_disk_space_low": False,
                "cpu_logical_count": 8,
                "cpu_usage_percent": 18.5,
                "is_cpu_pressure_high": False,
                "memory_total_bytes": 16_777_216,
                "memory_available_bytes": 8_388_608,
                "memory_used_percent": 50.0,
                "is_memory_pressure_high": False,
            },
            "provider_fetch": {
                "total_count": 6,
                "unhealthy_count": 1,
                "latest_status": "failure",
            },
            "data_quality": {
                "total_count": 6,
                "unhealthy_count": 2,
                "latest_status": "degraded",
            },
            "telegram_push": {
                "total_count": 3,
                "unhealthy_count": 0,
                "latest_status": "sent",
            },
            "model_calls": {
                "total_count": 2,
                "unhealthy_count": 1,
                "latest_status": "fallback",
            },
            "alerts": [
                {
                    "severity": "warning",
                    "code": "provider_fetch_unhealthy",
                    "message": "Provider 拉取存在 1 条异常记录。",
                }
            ],
        },
    )

    assert "运行状态" in text
    assert "统计窗口：最近 24 小时" in text
    assert "雷达扫描：#7 成功 | 新鲜度：6 分钟 | 正常" in text
    assert "扫描失败率：12.5% (1/8)" in text
    assert "服务端：运行=2 小时 / 磁盘可用=42.5% / CPU=18.5% / 内存=50%" in text
    assert "Provider：异常=1 / 总数=6 / 最新=失败" in text
    assert "模型调用：异常=1 / 总数=2 / 最新=降级切换" in text
    assert "告警：Provider 拉取存在 1 条异常记录。" in text
    assert "只读取已有运行记录" in text


def test_format_ops_history_outputs_recent_events() -> None:
    text = client_api.format_ops_history(
        {
            "generated_at": "2026-05-04T09:30:00Z",
            "lookback_hours": 24,
            "limit": 10,
            "recent_events": [
                {
                    "id": 3,
                    "kind": "model_call",
                    "status": "fallback",
                    "occurred_at": "2026-05-04T09:25:00Z",
                    "title": "模型调用 review",
                    "detail": "RateLimitError",
                    "metadata": {"error_type": "RateLimitError"},
                }
            ],
            "failure_summary": [
                {"kind": "model_call", "key": "review/fallback/RateLimitError", "count": 1}
            ],
        },
    )

    assert "运维历史" in text
    assert "统计窗口：最近 24 小时" in text
    assert "异常汇总：模型 review/fallback/RateLimitError=1" in text
    assert "- 模型 #3 降级切换 | 2026-05-04T09:25:00Z | RateLimitError" in text
    assert "只读取已有运行记录" in text


def test_format_ops_readiness_outputs_checks() -> None:
    text = client_api.format_ops_readiness(
        {
            "generated_at": "2026-05-04T09:30:00Z",
            "lookback_hours": 24,
            "status": "warning",
            "checks": [
                {
                    "name": "radar_freshness",
                    "status": "warning",
                    "message": "最新雷达扫描已超过预期调度间隔。",
                    "metadata": {"latest_scan_id": 7},
                },
                {
                    "name": "server_cpu",
                    "status": "warning",
                    "message": "服务端 CPU 压力偏高。",
                    "metadata": {"cpu_usage_percent": 95.0},
                }
            ],
        },
    )

    assert "运行就绪自检" in text
    assert "状态：有警告" in text
    assert "雷达新鲜度：警告，最新雷达扫描已超过预期调度间隔。" in text
    assert "服务端 CPU：警告，服务端 CPU 压力偏高。" in text
    assert "只读取已有运行记录" in text


def test_format_ops_warning_drilldown_prioritizes_backend_warning_fields() -> None:
    text = client_api.format_ops_warning_drilldown(
        {
            "lookback_hours": 6,
            "status": "warning",
            "checks": [
                {"name": "radar_freshness", "status": "ok", "message": "fresh"},
                {
                    "name": "provider_fetch",
                    "status": "warning",
                    "message": "Provider 拉取存在异常。",
                },
                {
                    "name": "data_quality",
                    "status": "fail",
                    "message": "数据质量检查失败。",
                },
            ],
        },
        {
            "lookback_hours": 6,
            "alerts": [
                {
                    "severity": "warning",
                    "code": "provider_fetch_unhealthy",
                    "message": "Provider 拉取存在 2 条异常记录。",
                }
            ],
        },
        {
            "lookback_hours": 6,
            "failure_summary": [
                {"kind": "model_call", "key": "review/fallback", "count": 3},
                {"kind": "data_quality", "key": "akshare/degraded", "count": 1},
                {"kind": "provider_fetch", "key": "akshare/failure", "count": 2},
            ],
            "recent_events": [
                {
                    "id": 9,
                    "kind": "provider_fetch",
                    "status": "failure",
                    "occurred_at": "2026-05-04T09:25:00Z",
                    "title": "AKShare minimal fetch",
                    "detail": "timeout",
                }
            ],
        },
    )

    provider_check_pos = text.index("Provider (provider_fetch): 警告")
    data_quality_check_pos = text.index("数据质量 (data_quality): 失败")
    alert_pos = text.index("provider_fetch_unhealthy")
    provider_summary_pos = text.index("Provider akshare/failure=2")
    data_quality_summary_pos = text.index("数据质量 akshare/degraded=1")
    model_summary_pos = text.index("模型 review/fallback=3")
    event_pos = text.index("AKShare minimal fetch")

    assert "就绪状态：有警告" in text
    assert "radar_freshness" not in text
    assert (
        provider_check_pos
        < data_quality_check_pos
        < alert_pos
        < provider_summary_pos
        < data_quality_summary_pos
        < model_summary_pos
        < event_pos
    )
    assert "timeout" in text
    assert "不触发采集、扫描、推送、模型调用或证据写入" in text


def test_format_ops_trends_uses_backend_bucket_counts_only() -> None:
    text = client_api.format_ops_trends(
        {
            "lookback_hours": 12,
            "bucket_count": 12,
            "buckets": [
                {
                    "bucket_started_at": "2026-05-04T07:00:00Z",
                    "bucket_finished_at": "2026-05-04T08:00:00Z",
                    "radar_scan_count": 1,
                    "radar_failure_count": 0,
                    "provider_fetch_unhealthy_count": 1,
                    "data_quality_unhealthy_count": 0,
                    "telegram_push_unhealthy_count": 0,
                    "model_call_unhealthy_count": 0,
                    "recent_scan_failure_rate": 0.0,
                    "status": "ready",
                },
                {
                    "bucket_started_at": "2026-05-04T08:00:00Z",
                    "bucket_finished_at": "2026-05-04T09:00:00Z",
                    "radar_scan_count": 2,
                    "radar_failure_count": 1,
                    "provider_fetch_unhealthy_count": 2,
                    "data_quality_unhealthy_count": 3,
                    "telegram_push_unhealthy_count": 4,
                    "model_call_unhealthy_count": 5,
                    "alerts": [{"message": "do not inspect"}],
                    "status": "blocked",
                },
            ],
        },
    )

    assert "OPS 趋势" in text
    assert "统计窗口：最近 12 小时" in text
    assert "趋势桶：12 桶" in text
    assert "扫描：2 / 失败 1" in text
    assert "Provider=2 / 数据质量=3 / Telegram 推送=4 / 模型调用=5" in text
    assert "扫描=1 | 失败=0 | Provider=1 | 数据质量=0 | 推送=0 | 模型=0" in text
    assert "不本地推导 OPS readiness 或状态" in text
    assert "recent_scan_failure_rate" not in text
    assert "blocked" not in text
    assert "do not inspect" not in text


def test_format_tushare_status_outputs_read_only_provider_state() -> None:
    text = client_api.format_tushare_status(
        {
            "provider": "tushare",
            "status": "configured",
            "token_configured": True,
            "fetch_enabled": True,
            "endpoint_count": 3,
            "implemented_endpoint_count": 3,
            "message": "Tushare fetch is enabled.",
        },
    )

    assert "Tushare 状态" in text
    assert "状态：已配置" in text
    assert "Token：已配置" in text
    assert "手动抓取：开启" in text
    assert "已实现端点：3/3" in text
    assert "不触发真实抓取" in text
    assert "不构成投资建议" in text


def test_format_tushare_readiness_outputs_read_only_gate_state() -> None:
    text = client_api.format_tushare_readiness(
        {
            "provider_name": "tushare",
            "status": "warning",
            "token_configured": True,
            "fetch_enabled": True,
            "scheduler_ready_endpoint_count": 1,
            "implemented_endpoint_count": 3,
            "scheduler_policy": "manual_only_until_verified",
            "message": "Need more samples.",
            "endpoints": [
                {
                    "endpoint": "stock_basic",
                    "title": "股票基础信息",
                    "status": "ready",
                    "scheduler_eligible": True,
                    "checks": [{"name": "data_quality", "status": "ok", "message": "ok"}],
                },
                {
                    "endpoint": "anns_d",
                    "title": "公告快讯",
                    "status": "warning",
                    "scheduler_eligible": False,
                    "checks": [
                        {
                            "name": "latest_fetch",
                            "status": "warning",
                            "message": "暂无真实抓取记录。",
                        }
                    ],
                },
            ],
        },
    )

    assert "Tushare 准入自检" in text
    assert "状态：有警告" in text
    assert "调度准入样例：1/3" in text
    assert "股票基础信息：可运行 / 可评审调度" in text
    assert "公告快讯：有警告 / 仅手动验证，暂无真实抓取记录。" in text
    assert "不触发真实抓取或调度" in text
    assert "不构成投资建议" in text


def test_format_radar_overview_uses_backend_priority_counts() -> None:
    text = client_api.format_radar_overview(
        {
            "priority_counts": {"P0": 2, "P1": 1, "P2": 0},
            "lifecycle_counts": {"developing": 2, "ignition": 1},
            "stock_backtrace_evidences": [
                {
                    "stock_name": "Example AI",
                    "stock_pct_change": 7.5,
                    "subject_name": "AI Applications",
                    "priority": "P1",
                    "lifecycle_stage": "developing",
                }
            ],
            "subject_count": 3,
            "latest_scan": {
                "id": 7,
                "status": "success",
                "started_at": "2026-05-03T09:30:00Z",
                "finished_at": "2026-05-03T09:30:05Z",
                "summary": {
                    "signal_count": 9,
                    "market_sentiment": {
                        "limit_up_count": 12,
                        "limit_down_count": 2,
                        "broken_limit_up_count": 3,
                        "net_limit_pressure": 7,
                        "sentiment_bias": "positive",
                    },
                },
            },
            "current_subjects": [
                {
                    "subject_name": "AI Applications",
                    "latest_signal": {
                        "priority": "P1",
                        "lifecycle_stage": "developing",
                    },
                }
            ],
            "active_signals": [{"priority": "P0"}, {"priority": "P0"}, {"priority": "P0"}],
        },
    )

    assert "P0=2 / P1=1 / P2=0" in text
    assert "后端生命周期分布：点火=1 / 发酵=2" in text
    assert "后端市场情绪：涨停=12 / 跌停=2 / 炸板=3 / 净压力=7 / 偏向=偏强" in text
    assert "后端个股回推：Example AI +7.5% -> AI Applications" in text
    assert "最新扫描：#7 成功" in text
    assert "[P1] AI Applications" in text


def test_format_signals_lists_backend_fields_without_calculating_priority() -> None:
    text = client_api.format_signals(
        [
            {
                "id": 3,
                "priority": "P2",
                "subject_name": "Robotics",
                "lifecycle_stage": "ignition",
                "review_status": "candidate",
                "evidence_count": 2,
                "title": "Robotics enters watch queue",
            }
        ],
    )

    assert "#3 [P2] Robotics" in text
    assert "生命周期：点火" in text
    assert "审查：候选" in text
    assert "证据：2" in text


def test_fetch_signal_analysis_uses_signal_analysis_endpoint() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["timeout"] = timeout
        return FakeResponse(
            json.dumps(
                {
                    "signal_id": 7,
                    "analysis_title": "P1 research brief: AI Applications",
                    "evidence_summary": {"evidence_count": 1},
                    "review_summary": {"status": "candidate"},
                },
            ),
        )

    analysis = client_api.fetch_signal_analysis(
        "http://localhost:8000",
        7,
        opener=opener,
    )

    assert analysis["signal_id"] == 7
    assert calls == {
        "url": "http://localhost:8000/radar/signals/7/analysis",
        "timeout": client_api.DEFAULT_TIMEOUT_SECONDS,
    }


def test_format_signal_analysis_outputs_backend_brief_without_sensitive_terms() -> None:
    text = client_api.format_signal_analysis(
        {
            "signal_id": 7,
            "subject_name": "AI Applications",
            "subject_code": "GN001",
            "priority": "P1",
            "lifecycle_stage": "developing",
            "review_status": "needs_human_review",
            "analysis_title": "P1 research brief: AI Applications",
            "key_points": [
                "Backend priority is P1; lifecycle is developing.",
                "Review status requires human review.",
            ],
            "metric_highlights": [
                {
                    "label": "sector_pct_change",
                    "value": "+3.4%",
                    "interpretation": "Sector momentum is above the watch threshold.",
                }
            ],
            "risk_flags": ["provider_quality_degraded", "low_evidence_confidence"],
            "evidence_summary": {
                "evidence_count": 1,
                "evidence_types": ["market_snapshot"],
                "summaries": [
                    "Provider snapshot summary from [source omitted] with sector movement."
                ],
                "freshness_labels": ["fresh"],
                "confidence_labels": ["low", "0.123"],
                "source_ref": "https://example.com/raw",
                "raw_excerpt": "Raw source says buy now",
                "details": {"source_domain": "market.example.hk"},
            },
            "review_summary": {
                "status": "needs_human_review",
                "latest_review_id": 4,
                "reasons": ["low evidence confidence"],
                "human_review_required": True,
                "details": {"cost_price": 10.25, "position_ratio": 0.2},
            },
            "agent_inputs": {
                "guardrails": ["Do not override backend rule priority"],
            },
            "next_actions": ["Schedule human review before publishing."],
            "source_ref": "https://example.com/source",
            "raw_excerpt": "sell immediately",
            "cost_price": 10.25,
            "position_ratio": 0.2,
        },
    )

    assert "信号 #7 分析摘要" in text
    assert "AI Applications | 优先级：P1 | 生命周期：发酵 | 审查：需人工复核" in text
    assert "P1 research brief: AI Applications" in text
    assert "Backend priority is P1" in text
    assert "sector_pct_change: +3.4%" in text
    assert "provider_quality_degraded" in text
    assert "证据数量：1" in text
    assert "信心分桶：low" in text
    assert "0.123" not in text
    assert "最近审查：4" in text
    assert "Schedule human review" in text
    assert "不本地计算雷达定级" in text
    assert "source_ref" not in text
    assert "raw_excerpt" not in text
    assert "https://example.com" not in text
    assert "market.example.hk" not in text
    assert "cost_price" not in text
    assert "position_ratio" not in text
    assert "buy" not in text.lower()
    assert "sell" not in text.lower()
    assert "买入" not in text
    assert "卖出" not in text


def test_fetch_holdings_uses_user_key_query() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["timeout"] = timeout
        return FakeResponse(
            '[{"id":1,"instrument_code":"600000","instrument_name":"浦发银行"}]',
        )

    holdings = client_api.fetch_holdings(
        "http://localhost:8000",
        user_key="telegram-1001",
        opener=opener,
    )

    assert holdings[0]["instrument_name"] == "浦发银行"
    assert calls == {
        "url": "http://localhost:8000/portfolio/holdings?user_key=telegram-1001",
        "timeout": client_api.DEFAULT_TIMEOUT_SECONDS,
    }


def test_format_holdings_and_watchlist_keep_personal_context_separate() -> None:
    holdings_text = client_api.format_holdings(
        [
            {
                "id": 1,
                "instrument_code": "600000",
                "instrument_name": "浦发银行",
                "market": "A_SHARE",
                "position_ratio": 0.2,
                "cost_price": 10.25,
                "alert_enabled": True,
                "note": "核心观察仓",
            }
        ],
    )
    watchlist_text = client_api.format_watchlist(
        [
            {
                "id": 2,
                "instrument_code": "SZ000001",
                "instrument_name": "平安银行",
                "market": "A_SHARE",
                "alert_enabled": False,
                "note": "观察风险变化",
            }
        ],
    )

    assert "手动持仓" in holdings_text
    assert "600000 浦发银行" in holdings_text
    assert "仓位：20%" in holdings_text
    assert "不改变市场雷达等级" in holdings_text

    assert "自选关注" in watchlist_text
    assert "SZ000001 平安银行" in watchlist_text
    assert "提醒：关闭" in watchlist_text
    assert "不构成投资建议" in watchlist_text


def test_fetch_reports_uses_user_key_query_and_report_type() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["timeout"] = timeout
        return FakeResponse(
            '[{"id":3,"report_type":"standard","title":"Standard Report：主线"}]',
        )

    reports = client_api.fetch_reports(
        "http://localhost:8000",
        user_key="telegram-1001",
        report_type="standard",
        opener=opener,
    )

    assert reports[0]["title"] == "Standard Report：主线"
    assert calls == {
        "url": (
            "http://localhost:8000/reports?"
            "user_key=telegram-1001&report_type=standard&limit=20"
        ),
        "timeout": client_api.DEFAULT_TIMEOUT_SECONDS,
    }


def test_format_reports_lists_report_summaries_without_body() -> None:
    text = client_api.format_reports(
        [
            {
                "id": 3,
                "report_type": "standard",
                "status": "generated",
                "title": "Standard Report：主线",
                "summary": "主线当前为 P0 观察信号。",
                "suggestion_label": "重点关注",
                "review_status": "approved",
                "body_markdown": "internal report body",
            }
        ],
    )

    assert "#3 [standard] Standard Report：主线" in text
    assert "状态：generated" in text
    assert "审查：已通过" in text
    assert "标签：重点关注" in text
    assert "主线当前为 P0 观察信号。" in text
    assert "internal report body" not in text
    assert "不构成投资建议" in text


def test_fetch_periodic_report_uses_user_key_and_period() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["timeout"] = timeout
        return FakeResponse(
            '{"report_type":"weekly","user_key":"telegram-1001","signal_count":2}',
        )

    report = client_api.fetch_periodic_report(
        "http://localhost:8000",
        user_key="telegram-1001",
        period="weekly",
        opener=opener,
    )

    assert report["report_type"] == "weekly"
    assert calls == {
        "url": (
            "http://localhost:8000/reports/periodic?"
            "user_key=telegram-1001&period=weekly"
        ),
        "timeout": client_api.DEFAULT_TIMEOUT_SECONDS,
    }


def test_format_periodic_report_lists_backend_summary_and_counts() -> None:
    text = client_api.format_periodic_report(
        {
            "report_type": "daily",
            "period_start": "2026-05-03T00:00:00Z",
            "period_end": "2026-05-03T23:59:59Z",
            "summary": "今日有 1 条雷达信号进入观察。",
            "signal_count": 1,
            "report_count": 2,
            "push_count": 1,
            "priority_counts": {"P0": 0, "P1": 1, "P2": 0},
            "top_subjects": [
                {
                    "signal_id": 9,
                    "subject_name": "AI Applications",
                    "priority": "P1",
                    "lifecycle_stage": "developing",
                    "review_status": "approved",
                }
            ],
            "body_markdown": "internal periodic body",
        },
    )

    assert "日报汇总" in text
    assert "P0=0 / P1=1 / P2=0" in text
    assert "信号：1 条 | 报告：2 份 | Telegram 推送：1 次" in text
    assert "#9 [P1] AI Applications" in text
    assert "审查：已通过" in text
    assert "internal periodic body" not in text
    assert "不构成投资建议" in text


def test_score_signal_posts_to_score_endpoint() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["method"] = request.get_method()
        calls["timeout"] = timeout
        return FakeResponse(
            '{"signal_id":7,"records":[{"window_days":1,"composite_score":82.5}]}',
        )

    score_run = client_api.score_signal(
        "http://localhost:8000",
        7,
        opener=opener,
    )

    assert score_run["signal_id"] == 7
    assert calls == {
        "url": "http://localhost:8000/scores/signals/7",
        "method": "POST",
        "timeout": client_api.DEFAULT_TIMEOUT_SECONDS,
    }


def test_format_scores_lists_score_windows_without_trading_instruction() -> None:
    text = client_api.format_scores(
        {
            "signal_id": 7,
            "records": [
                {
                    "window_days": 1,
                    "score_status": "pending_window",
                    "composite_score": 82.5,
                    "components": {
                        "priority": 85,
                        "lifecycle": 78,
                        "review": 82,
                        "evidence": 85,
                        "continuity": 82,
                        "data_quality": 87,
                        "timeliness": 58,
                    },
                    "details": {"score_band": "strong_attention"},
                },
                {
                    "window_days": 3,
                    "score_status": "generated",
                    "composite_score": 76,
                    "details": {"score_band": "watch"},
                },
            ],
        },
    )

    assert "信号 #7 综合评分" in text
    assert "1d：82.50" in text
    assert "窗口未结束" in text
    assert "强关注" in text
    assert "组件：优先级=85.00" in text
    assert "数据质量=87.00" in text
    assert "时效性=58.00" in text
    assert "3d：76.00" in text
    assert "观察" in text
    assert "不是价格回测或交易建议" in text
    assert "买入" not in text


def test_fetch_telegram_bindings_uses_secret_and_limit() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["secret"] = _telegram_secret_header(request)
        return FakeResponse('[{"id":1,"chat_id":1001,"user_key":"telegram-1001"}]')

    bindings = client_api.fetch_telegram_bindings(
        "http://localhost:8000",
        secret_token="hook-secret",
        limit=10,
        opener=opener,
    )

    assert bindings[0]["chat_id"] == 1001
    assert calls == {
        "url": "http://localhost:8000/telegram/bindings?limit=10",
        "secret": "hook-secret",
    }


def test_fetch_telegram_status_uses_secret_header() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["secret"] = _telegram_secret_header(request)
        return FakeResponse(
            '{"require_binding":true,"allowed_chat_count":2,'
            '"binding_count":3,"active_binding_count":1}',
        )

    status = client_api.fetch_telegram_status(
        "http://localhost:8000",
        secret_token="hook-secret",
        opener=opener,
    )

    assert status["require_binding"] is True
    assert calls == {
        "url": "http://localhost:8000/telegram/status",
        "secret": "hook-secret",
    }


def test_upsert_telegram_binding_posts_payload() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["method"] = request.get_method()
        calls["payload"] = json.loads(request.data.decode("utf-8"))
        calls["secret"] = _telegram_secret_header(request)
        return FakeResponse(
            '{"id":1,"chat_id":1001,"user_key":"telegram-1001","is_allowed":true}',
        )

    binding = client_api.upsert_telegram_binding(
        "http://localhost:8000",
        chat_id=1001,
        user_key="telegram-1001",
        display_name="desktop",
        secret_token="hook-secret",
        opener=opener,
    )

    assert binding["is_allowed"] is True
    assert calls == {
        "url": "http://localhost:8000/telegram/bindings",
        "method": "POST",
        "payload": {
            "chat_id": 1001,
            "user_key": "telegram-1001",
            "display_name": "desktop",
            "is_allowed": True,
        },
        "secret": "hook-secret",
    }


def test_update_telegram_binding_patches_allowed_state() -> None:
    calls = {}

    def opener(request: object, *, timeout: int) -> FakeResponse:
        calls["url"] = request.full_url
        calls["method"] = request.get_method()
        calls["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            '{"id":1,"chat_id":1001,"user_key":"telegram-1001","is_allowed":false}',
        )

    binding = client_api.update_telegram_binding(
        "http://localhost:8000",
        chat_id=1001,
        is_allowed=False,
        opener=opener,
    )

    assert binding["is_allowed"] is False
    assert calls == {
        "url": "http://localhost:8000/telegram/bindings/1001",
        "method": "PATCH",
        "payload": {"is_allowed": False},
    }


def test_format_telegram_bindings_lists_allowed_state() -> None:
    text = client_api.format_telegram_bindings(
        [
            {
                "id": 1,
                "chat_id": 1001,
                "user_key": "telegram-1001",
                "display_name": "primary chat",
                "is_allowed": True,
                "source": "manual",
            },
            {
                "id": 2,
                "chat_id": -2002,
                "user_key": "telegram--2002",
                "display_name": "blocked group",
                "is_allowed": False,
                "source": "manual",
            },
        ],
        {
            "require_binding": True,
            "allowed_chat_count": 2,
            "binding_count": 2,
            "active_binding_count": 1,
            "telegram_bot_token": "secret-token",
            "webhook_secret": "secret-hook",
        },
    )

    assert "Telegram 绑定" in text
    assert "严格绑定模式：开启" in text
    assert "环境白名单=2" in text
    assert "数据库绑定=2" in text
    assert "active=1" in text
    assert "chat=1001" in text
    assert "状态：允许" in text
    assert "chat=-2002" in text
    assert "状态：禁用" in text
    assert "环境白名单存在时仍会先过滤" in text
    assert "secret-token" not in text
    assert "secret-hook" not in text


def _telegram_secret_header(request: object) -> str | None:
    return request.get_header("X-telegram-bot-api-secret-token")
