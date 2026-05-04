import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit

import pytest

from clients.windows import smoke_check


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_smoke_check_ready_path_uses_get_only() -> None:
    methods: list[str] = []
    paths: list[str] = []
    urls: list[str] = []
    payloads = _ready_payloads()
    payloads["/radar/overview"] = {
        "priority_counts": {"P0": 1, "P1": 0, "P2": 0},
        "current_subjects": [{"name": "semiconductor"}],
        "active_signals": [{"id": 1}],
    }
    payloads["/radar/signals"] = [{"id": 1, "priority": "P0"}]
    payloads["/telegram/bindings"] = [{"chat_id": 1001, "is_allowed": True}]

    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="default",
        importer=lambda name: object(),
        opener=_opener(payloads, methods=methods, paths=paths, urls=urls),
    )

    assert report.exit_code() == 0
    assert report.status == "warning"
    assert "tkinter" in _check_names(report)
    assert "health_ready" in _check_names(report)
    assert "ops_readiness" in _check_names(report)
    assert report.warnings == [
        (
            "user_scoped_reads: Skipped portfolio/watchlist/report/periodic endpoints for user_key "
            "d*** because current GET handlers can create user rows."
        ),
    ]
    assert methods
    assert set(methods) == {"GET"}
    assert set(paths) == {
        "/health",
        "/health/ready",
        "/ops/readiness",
        "/ops/overview",
        "/ops/history",
        "/providers/tushare/status",
        "/providers/tushare/readiness",
        "/radar/overview",
        "/radar/signals",
        "/telegram/bindings",
    }
    assert "http://localhost:8000/ops/readiness?lookback_hours=24" in urls
    assert not set(paths).intersection(smoke_check.SKIPPED_USER_SCOPED_ENDPOINTS)


def test_smoke_check_passes_custom_ops_readiness_lookback() -> None:
    urls: list[str] = []

    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="default",
        ops_readiness_lookback_hours=6,
        importer=lambda name: object(),
        opener=_opener(_ready_payloads(), urls=urls),
    )

    assert report.exit_code() == 0
    assert "http://localhost:8000/ops/readiness?lookback_hours=6" in urls


@pytest.mark.parametrize("lookback_hours", [0, 169])
def test_smoke_check_blocks_invalid_ops_readiness_lookback(lookback_hours: int) -> None:
    called = False

    def opener(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal called
        called = True
        return FakeResponse({})

    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="default",
        ops_readiness_lookback_hours=lookback_hours,
        importer=lambda name: object(),
        opener=opener,
    )

    assert report.exit_code() == 1
    assert report.status == "blocked"
    assert any("ops_readiness_lookback_hours" in blocker for blocker in report.blockers)
    assert called is False


def test_smoke_check_warning_only_empty_first_use_data_exits_zero() -> None:
    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="default",
        importer=lambda name: object(),
        opener=_opener(_ready_payloads()),
    )

    assert report.exit_code() == 0
    assert report.status == "warning"
    assert report.blockers == []
    assert any("radar_overview" in warning for warning in report.warnings)
    assert any("signals" in warning for warning in report.warnings)
    assert any("user_scoped_reads" in warning for warning in report.warnings)


def test_smoke_check_strict_warning_exit_code_is_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="default",
        importer=lambda name: object(),
        opener=_opener(_ready_payloads()),
    )

    assert report.exit_code() == 0
    assert report.exit_code(fail_on_warning=True) == 1

    monkeypatch.setattr(smoke_check, "run_smoke_check", lambda **kwargs: report)
    assert smoke_check.main(["--fail-on-warning"]) == 1


def test_smoke_check_blocks_invalid_url_before_endpoint_reads() -> None:
    called = False

    def opener(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal called
        called = True
        return FakeResponse({})

    report = smoke_check.run_smoke_check(
        server_url="ftp://localhost",
        user_key="default",
        importer=lambda name: object(),
        opener=opener,
    )

    assert report.exit_code() == 1
    assert report.status == "blocked"
    assert any("server_url" in blocker for blocker in report.blockers)
    assert called is False


def test_smoke_check_blocks_missing_tkinter_without_opening_endpoints() -> None:
    called = False

    def importer(name: str) -> object:
        raise ImportError(f"missing {name}")

    def opener(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal called
        called = True
        return FakeResponse({})

    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="default",
        importer=importer,
        opener=opener,
    )

    assert report.exit_code() == 1
    assert any("tkinter" in blocker for blocker in report.blockers)
    assert called is False


def test_smoke_check_blocks_connection_failure_on_core_endpoint() -> None:
    def opener(request: object, *, timeout: int) -> FakeResponse:
        if urlsplit(request.full_url).path == "/health":
            raise URLError("connection refused")
        return FakeResponse({})

    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="default",
        importer=lambda name: object(),
        opener=opener,
    )

    assert report.exit_code() == 1
    assert any("health" in blocker for blocker in report.blockers)


def test_smoke_check_blocks_malformed_core_payload() -> None:
    payloads = _ready_payloads()
    payloads["/ops/readiness"] = []

    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="default",
        importer=lambda name: object(),
        opener=_opener(payloads),
    )

    assert report.exit_code() == 1
    assert any("ops_readiness" in blocker for blocker in report.blockers)


def test_smoke_check_writes_bounded_sanitized_json(tmp_path: Path) -> None:
    output = tmp_path / "smoke.json"
    payloads = _ready_payloads()
    payloads["/providers/tushare/status"] = {
        "provider": "tushare",
        "token_configured": True,
        "raw_token": "token=secret-value",
        "message": "x" * 700,
    }

    report = smoke_check.run_smoke_check(
        server_url="http://localhost:8000",
        user_key="personal-key",
        importer=lambda name: object(),
        opener=_opener(payloads),
    )
    smoke_check.write_json_report(report, output)

    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["user_key"] == "<redacted>"
    assert "personal-key" not in output.read_text(encoding="utf-8")
    assert "secret-value" not in output.read_text(encoding="utf-8")
    assert "<redacted>" in output.read_text(encoding="utf-8")
    assert "<truncated>" in output.read_text(encoding="utf-8")


def test_smoke_check_sanitizes_warning_and_blocker_text() -> None:
    report = smoke_check.SmokeReport(server_url="http://localhost:8000")
    report.add_warning(
        "optional",
        "request failed with token=secret-value and Bearer raw-token",
    )
    report.add_blocker(
        "core",
        "bad user_key=personal-key " + ("x" * 700),
    )

    data = smoke_check.report_to_json(report)
    summary = smoke_check.format_summary(report)
    encoded = json.dumps(data, ensure_ascii=False)

    assert "secret-value" not in encoded
    assert "raw-token" not in encoded
    assert "personal-key" not in encoded
    assert "secret-value" not in summary
    assert "raw-token" not in summary
    assert "personal-key" not in summary
    assert "<redacted>" in encoded
    assert "<truncated>" in encoded


def _check_names(report: smoke_check.SmokeReport) -> set[str]:
    return {check.name for check in report.checks}


def _opener(
    payloads: dict[str, object],
    *,
    methods: list[str] | None = None,
    paths: list[str] | None = None,
    urls: list[str] | None = None,
):
    def open_url(request: object, *, timeout: int) -> FakeResponse:
        if methods is not None:
            methods.append(request.get_method())
        if urls is not None:
            urls.append(request.full_url)
        path = urlsplit(request.full_url).path
        if paths is not None:
            paths.append(path)
        return FakeResponse(payloads[path])

    return open_url


def _ready_payloads() -> dict[str, object]:
    return {
        "/health": {"status": "ok", "service": "BaizeFinDB"},
        "/health/ready": {"status": "ready", "service": "BaizeFinDB", "checks": {}},
        "/ops/readiness": {"status": "ready", "lookback_hours": 24, "checks": []},
        "/ops/overview": {"lookback_hours": 24, "radar": {}, "alerts": []},
        "/ops/history": {"lookback_hours": 24, "limit": 10, "recent_events": []},
        "/providers/tushare/status": {"provider": "tushare", "status": "not_configured"},
        "/providers/tushare/readiness": {"provider_name": "tushare", "status": "warning"},
        "/radar/overview": {
            "priority_counts": {"P0": 0, "P1": 0, "P2": 0},
            "current_subjects": [],
            "active_signals": [],
        },
        "/radar/signals": [],
        "/telegram/bindings": [],
    }
