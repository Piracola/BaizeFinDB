from collections.abc import Callable
from typing import Any

import pytest

from clients.windows import baizefindb_client


class FakeVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def _app_with_lookback(value: str) -> baizefindb_client.BaizeFinDBClientApp:
    app = object.__new__(baizefindb_client.BaizeFinDBClientApp)
    app.server_url = FakeVar("http://localhost:8000")
    app.user_key = FakeVar("analyst")
    app.ops_lookback_hours = FakeVar(value)
    app.telegram_secret = FakeVar("hook-secret")
    return app


@pytest.mark.parametrize("raw_value,expected", [("1", 1), (" 24 ", 24), ("168", 168)])
def test_parse_ops_lookback_hours_accepts_backend_range(
    raw_value: str,
    expected: int,
) -> None:
    assert baizefindb_client.parse_ops_lookback_hours(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["", "0", "169", "abc", "1.5"])
def test_parse_ops_lookback_hours_rejects_invalid_values(raw_value: str) -> None:
    with pytest.raises(ValueError, match="1 到 168"):
        baizefindb_client.parse_ops_lookback_hours(raw_value)


def test_view_ops_overview_blocks_invalid_lookback_before_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("0")
    errors: list[tuple[str, str]] = []

    def fail_run_worker(*args: object, **kwargs: object) -> None:
        raise AssertionError("worker should not start for invalid lookback")

    def fake_showerror(title: str, message: str) -> None:
        errors.append((title, message))

    monkeypatch.setattr(baizefindb_client.messagebox, "showerror", fake_showerror)
    monkeypatch.setattr(app, "_run_worker", fail_run_worker)

    app.view_ops_overview()

    assert errors == [
        (
            baizefindb_client.WINDOW_TITLE,
            "OPS Lookback 必须是 1 到 168 之间的整数小时。",
        ),
    ]


def test_first_use_smoke_check_blocks_invalid_lookback_before_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("169")
    errors: list[tuple[str, str]] = []

    def fail_run_worker(*args: object, **kwargs: object) -> None:
        raise AssertionError("worker should not start for invalid lookback")

    def fake_showerror(title: str, message: str) -> None:
        errors.append((title, message))

    monkeypatch.setattr(baizefindb_client.messagebox, "showerror", fake_showerror)
    monkeypatch.setattr(app, "_run_worker", fail_run_worker)

    app.run_first_use_smoke_check()

    assert errors == [
        (
            baizefindb_client.WINDOW_TITLE,
            "OPS Lookback 必须是 1 到 168 之间的整数小时。",
        ),
    ]


def test_ops_warning_drilldown_blocks_invalid_lookback_before_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("abc")
    errors: list[tuple[str, str]] = []

    def fail_run_worker(*args: object, **kwargs: object) -> None:
        raise AssertionError("worker should not start for invalid lookback")

    def fake_showerror(title: str, message: str) -> None:
        errors.append((title, message))

    monkeypatch.setattr(baizefindb_client.messagebox, "showerror", fake_showerror)
    monkeypatch.setattr(app, "_run_worker", fail_run_worker)

    app.view_ops_warning_drilldown()

    assert errors == [
        (
            baizefindb_client.WINDOW_TITLE,
            "OPS Lookback 必须是 1 到 168 之间的整数小时。",
        ),
    ]


def test_ops_trends_blocks_invalid_lookback_before_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("0")
    errors: list[tuple[str, str]] = []

    def fail_run_worker(*args: object, **kwargs: object) -> None:
        raise AssertionError("worker should not start for invalid lookback")

    def fake_showerror(title: str, message: str) -> None:
        errors.append((title, message))

    monkeypatch.setattr(baizefindb_client.messagebox, "showerror", fake_showerror)
    monkeypatch.setattr(app, "_run_worker", fail_run_worker)

    app.view_ops_trends()

    assert errors == [
        (
            baizefindb_client.WINDOW_TITLE,
            "OPS Lookback 必须是 1 到 168 之间的整数小时。",
        ),
    ]


def test_first_use_smoke_check_passes_current_gui_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("6")
    calls: dict[str, Any] = {}

    def fake_run_worker(action: str, worker: Callable[[], str]) -> None:
        calls["action"] = action
        calls["result"] = worker()

    def fake_run_smoke_check(**kwargs: object) -> object:
        calls["smoke_kwargs"] = kwargs
        return {"status": "ok"}

    def fake_format_summary(report: object) -> str:
        calls["summary_report"] = report
        return "formatted smoke summary"

    monkeypatch.setattr(app, "_run_worker", fake_run_worker)
    monkeypatch.setattr(baizefindb_client.smoke_check, "run_smoke_check", fake_run_smoke_check)
    monkeypatch.setattr(baizefindb_client.smoke_check, "format_summary", fake_format_summary)

    app.run_first_use_smoke_check()

    assert calls["action"] == "运行首用诊断"
    assert calls["smoke_kwargs"] == {
        "server_url": "http://localhost:8000",
        "user_key": "analyst",
        "ops_readiness_lookback_hours": 6,
    }
    assert calls["summary_report"] == {"status": "ok"}
    assert calls["result"] == "formatted smoke summary"


def test_ops_warning_drilldown_reads_three_ops_endpoints_with_selected_lookback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("6")
    calls: dict[str, Any] = {"fetches": []}

    def fake_run_worker(action: str, worker: Callable[[], str]) -> None:
        calls["action"] = action
        calls["result"] = worker()

    def fake_fetch_readiness(base_url: str, **kwargs: object) -> dict[str, object]:
        calls["fetches"].append(("readiness", base_url, kwargs))
        return {"status": "warning"}

    def fake_fetch_overview(base_url: str, **kwargs: object) -> dict[str, object]:
        calls["fetches"].append(("overview", base_url, kwargs))
        return {"alerts": []}

    def fake_fetch_history(base_url: str, **kwargs: object) -> dict[str, object]:
        calls["fetches"].append(("history", base_url, kwargs))
        return {"recent_events": []}

    def fake_format(
        readiness: object,
        overview: object,
        history: object,
    ) -> str:
        calls["format_payloads"] = (readiness, overview, history)
        return "formatted drilldown"

    monkeypatch.setattr(app, "_run_worker", fake_run_worker)
    monkeypatch.setattr(
        baizefindb_client.client_api,
        "fetch_ops_readiness",
        fake_fetch_readiness,
    )
    monkeypatch.setattr(
        baizefindb_client.client_api,
        "fetch_ops_overview",
        fake_fetch_overview,
    )
    monkeypatch.setattr(
        baizefindb_client.client_api,
        "fetch_ops_history",
        fake_fetch_history,
    )
    monkeypatch.setattr(
        baizefindb_client.client_api,
        "format_ops_warning_drilldown",
        fake_format,
    )

    app.view_ops_warning_drilldown()

    assert calls["action"] == "读取 OPS 告警钻取"
    assert calls["fetches"] == [
        ("readiness", "http://localhost:8000", {"lookback_hours": 6}),
        ("overview", "http://localhost:8000", {"lookback_hours": 6}),
        ("history", "http://localhost:8000", {"lookback_hours": 6, "limit": 20}),
    ]
    assert calls["format_payloads"] == (
        {"status": "warning"},
        {"alerts": []},
        {"recent_events": []},
    )
    assert calls["result"] == "formatted drilldown"


def test_ops_trends_reads_endpoint_with_selected_lookback_and_default_bucket_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("6")
    calls: dict[str, Any] = {}

    def fake_run_worker(action: str, worker: Callable[[], str]) -> None:
        calls["action"] = action
        calls["result"] = worker()

    def fake_fetch(base_url: str, **kwargs: object) -> dict[str, object]:
        calls["base_url"] = base_url
        calls["kwargs"] = kwargs
        return {"bucket_count": 12}

    def fake_format(payload: object) -> str:
        calls["format_payload"] = payload
        return "formatted trends"

    monkeypatch.setattr(app, "_run_worker", fake_run_worker)
    monkeypatch.setattr(baizefindb_client.client_api, "fetch_ops_trends", fake_fetch)
    monkeypatch.setattr(baizefindb_client.client_api, "format_ops_trends", fake_format)

    app.view_ops_trends()

    assert calls["action"] == "读取 OPS 趋势"
    assert calls["base_url"] == "http://localhost:8000"
    assert calls["kwargs"] == {"lookback_hours": 6, "bucket_count": 12}
    assert calls["format_payload"] == {"bucket_count": 12}
    assert calls["result"] == "formatted trends"


def test_gui_declares_ops_trends_button() -> None:
    source = baizefindb_client.BaizeFinDBClientApp._build_ui.__code__.co_consts

    assert "OPS 趋势" in source


def test_view_telegram_bindings_reads_status_before_formatting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("24")
    calls: dict[str, Any] = {}

    def fake_run_worker(action: str, worker: Callable[[], str]) -> None:
        calls["action"] = action
        calls["result"] = worker()

    def fake_fetch_status(base_url: str, **kwargs: object) -> dict[str, object]:
        calls["status_call"] = (base_url, kwargs)
        return {"require_binding": True}

    def fake_fetch_bindings(base_url: str, **kwargs: object) -> list[dict[str, object]]:
        calls["bindings_call"] = (base_url, kwargs)
        return [{"chat_id": 1001}]

    def fake_format(bindings: object, status: object = None) -> str:
        calls["format_payloads"] = (bindings, status)
        return "formatted telegram bindings"

    monkeypatch.setattr(app, "_run_worker", fake_run_worker)
    monkeypatch.setattr(
        baizefindb_client.client_api,
        "fetch_telegram_status",
        fake_fetch_status,
    )
    monkeypatch.setattr(
        baizefindb_client.client_api,
        "fetch_telegram_bindings",
        fake_fetch_bindings,
    )
    monkeypatch.setattr(baizefindb_client.client_api, "format_telegram_bindings", fake_format)

    app.view_telegram_bindings()

    assert calls["action"] == "读取 Telegram 绑定"
    assert calls["status_call"] == (
        "http://localhost:8000",
        {"secret_token": "hook-secret"},
    )
    assert calls["bindings_call"] == (
        "http://localhost:8000",
        {"secret_token": "hook-secret"},
    )
    assert calls["format_payloads"] == ([{"chat_id": 1001}], {"require_binding": True})
    assert calls["result"] == "formatted telegram bindings"


@pytest.mark.parametrize(
    "method_name,fetch_name,format_name,expected_action",
    [
        ("view_ops_overview", "fetch_ops_overview", "format_ops_overview", "读取运行状态"),
        ("view_ops_history", "fetch_ops_history", "format_ops_history", "读取运维历史"),
        ("view_ops_trends", "fetch_ops_trends", "format_ops_trends", "读取 OPS 趋势"),
        (
            "view_ops_readiness",
            "fetch_ops_readiness",
            "format_ops_readiness",
            "读取运行就绪自检",
        ),
    ],
)
def test_ops_views_pass_selected_lookback_to_api_helpers(
    method_name: str,
    fetch_name: str,
    format_name: str,
    expected_action: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_lookback("6")
    calls: dict[str, Any] = {}

    def fake_run_worker(action: str, worker: Callable[[], str]) -> None:
        calls["action"] = action
        calls["result"] = worker()

    def fake_fetch(base_url: str, **kwargs: object) -> dict[str, object]:
        calls["base_url"] = base_url
        calls["kwargs"] = kwargs
        return {"status": "ok"}

    monkeypatch.setattr(app, "_run_worker", fake_run_worker)
    monkeypatch.setattr(baizefindb_client.client_api, fetch_name, fake_fetch)
    monkeypatch.setattr(
        baizefindb_client.client_api,
        format_name,
        lambda payload: f"formatted:{payload['status']}",
    )

    getattr(app, method_name)()

    assert calls["action"] == expected_action
    assert calls["base_url"] == "http://localhost:8000"
    assert calls["kwargs"]["lookback_hours"] == 6
    if method_name == "view_ops_history":
        assert calls["kwargs"]["limit"] == 20
    if method_name == "view_ops_trends":
        assert calls["kwargs"]["bucket_count"] == 12
    assert calls["result"] == "formatted:ok"
