import io
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
