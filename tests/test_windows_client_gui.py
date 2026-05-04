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
    app.ops_lookback_hours = FakeVar(value)
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


@pytest.mark.parametrize(
    "method_name,fetch_name,format_name,expected_action",
    [
        ("view_ops_overview", "fetch_ops_overview", "format_ops_overview", "读取运行状态"),
        ("view_ops_history", "fetch_ops_history", "format_ops_history", "读取运维历史"),
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
    assert calls["result"] == "formatted:ok"
