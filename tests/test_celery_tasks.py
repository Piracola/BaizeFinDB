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

    result = await celery_module._collect_and_run_radar()

    assert calls == [("collect", "session"), ("scan", "session")]
    assert result == {
        "collection": {"status": "collected", "mode": "json"},
        "scan": {"status": "scanned", "mode": "json"},
    }
