import pytest

from app.providers.schemas import DataQualityStatus, ProviderStatus
from app.providers.service import collect_akshare_endpoint


class FakeSession:
    def __init__(self) -> None:
        self.objects = []
        self._next_id = 1
        self.committed = False
        self.rolled_back = False

    def add(self, obj) -> None:
        self.objects.append(obj)

    async def flush(self) -> None:
        for obj in self.objects:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FailingProvider:
    async def fetch(self, endpoint: str):
        raise RuntimeError("upstream unavailable")


@pytest.mark.asyncio
async def test_provider_failure_is_recorded_without_raising() -> None:
    session = FakeSession()

    result = await collect_akshare_endpoint(session, FailingProvider(), "stock_zh_a_spot_em")

    assert result.status == ProviderStatus.FAILURE
    assert result.quality_status == DataQualityStatus.FAILED
    assert result.fetch_log_id == 1
    assert result.error_message is not None
    assert session.rolled_back is True
    assert session.committed is True
    assert len(session.objects) == 2

