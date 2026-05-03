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


def test_format_radar_overview_uses_backend_priority_counts() -> None:
    text = client_api.format_radar_overview(
        {
            "priority_counts": {"P0": 2, "P1": 1, "P2": 0},
            "subject_count": 3,
            "latest_scan": {
                "id": 7,
                "status": "success",
                "started_at": "2026-05-03T09:30:00Z",
                "finished_at": "2026-05-03T09:30:05Z",
                "summary": {"signal_count": 9},
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
                },
                {
                    "window_days": 3,
                    "score_status": "generated",
                    "composite_score": 76,
                },
            ],
        },
    )

    assert "信号 #7 综合评分" in text
    assert "1d：82.50" in text
    assert "窗口未结束" in text
    assert "3d：76.00" in text
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
    )

    assert "Telegram 绑定" in text
    assert "chat=1001" in text
    assert "状态：允许" in text
    assert "chat=-2002" in text
    assert "状态：禁用" in text
    assert "环境白名单存在时仍会先过滤" in text


def _telegram_secret_header(request: object) -> str | None:
    return request.get_header("X-telegram-bot-api-secret-token")
