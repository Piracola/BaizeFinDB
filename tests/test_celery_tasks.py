from types import SimpleNamespace

import pytest

from app.tasks import celery_app as celery_module


def test_celery_beat_schedules_collect_then_scan_task() -> None:
    schedule = celery_module.celery_app.conf.beat_schedule

    assert schedule == {
        "collect-and-run-radar-every-5-minutes": {
            "task": "baizefindb.radar.collect_and_scan",
            "schedule": 300.0,
        },
    }


@pytest.mark.asyncio
async def test_collect_and_run_radar_collects_before_scanning(monkeypatch) -> None:
    calls = []

    class FakeSessionContext:
        async def __aenter__(self) -> str:
            return "session"

        async def __aexit__(self, *args: object) -> None:
            return None

    async def fake_collect_minimal_akshare(session: str) -> SimpleNamespace:
        calls.append(("collect", session))
        return SimpleNamespace(model_dump=lambda mode: {"status": "collected", "mode": mode})

    async def fake_run_radar_scan(session: str) -> SimpleNamespace:
        calls.append(("scan", session))
        return SimpleNamespace(model_dump=lambda mode: {"status": "scanned", "mode": mode})

    monkeypatch.setattr(celery_module, "AsyncSessionLocal", FakeSessionContext)
    monkeypatch.setattr(celery_module, "collect_minimal_akshare", fake_collect_minimal_akshare)
    monkeypatch.setattr(celery_module, "run_radar_scan", fake_run_radar_scan)
    monkeypatch.setattr(celery_module, "settings", SimpleNamespace(telegram_push_enabled=False))

    result = await celery_module._collect_and_run_radar()

    assert calls == [("collect", "session"), ("scan", "session")]
    assert result == {
        "collection": {"status": "collected", "mode": "json"},
        "scan": {"status": "scanned", "mode": "json"},
        "telegram_push": {"push_enabled": False, "deliveries": []},
    }


@pytest.mark.asyncio
async def test_configured_telegram_push_runs_only_when_enabled(monkeypatch) -> None:
    calls = []

    async def fake_send_latest_radar_push(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(model_dump=lambda mode: {"status": "preview", "mode": mode})

    monkeypatch.setattr(
        celery_module,
        "settings",
        SimpleNamespace(telegram_push_enabled=True, telegram_bot_token=None),
    )
    monkeypatch.setattr(celery_module, "send_latest_radar_push", fake_send_latest_radar_push)

    result = await celery_module._send_configured_telegram_push("session")

    assert result == {"status": "preview", "mode": "json"}
    assert calls[0]["session"] == "session"
    assert calls[0]["respect_enabled"] is True
