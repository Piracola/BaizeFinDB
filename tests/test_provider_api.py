from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.providers.schemas import DataQualityStatus, ProviderEndpointResult, ProviderStatus


def test_akshare_endpoint_list() -> None:
    client = TestClient(create_app())

    response = client.get("/providers/akshare/endpoints")

    assert response.status_code == 200
    payload = response.json()
    assert {item["endpoint"] for item in payload} == {
        "stock_zh_a_spot_em",
        "stock_board_industry_name_em",
        "stock_board_concept_name_em",
        "stock_zt_pool_em",
        "stock_zt_pool_dtgc_em",
        "stock_zt_pool_zbgc_em",
    }


def test_tushare_endpoint_list_is_registered() -> None:
    client = TestClient(create_app())

    response = client.get("/providers/tushare/endpoints")

    assert response.status_code == 200
    payload = response.json()
    assert {item["endpoint"] for item in payload} == {
        "daily",
        "anns_d",
        "stock_company",
        "stock_basic",
    }
    implemented = {item["endpoint"]: item["implemented"] for item in payload}
    assert implemented == {
        "daily": True,
        "anns_d": True,
        "stock_company": True,
        "stock_basic": True,
    }
    assert all(item["required_fields"] for item in payload)


def test_tushare_status_does_not_leak_token(monkeypatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    get_settings.cache_clear()
    client = TestClient(create_app())

    try:
        response = client.get("/providers/tushare/status")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "provider_name": "tushare",
        "token_configured": True,
        "fetch_enabled": True,
        "endpoint_count": 4,
        "implemented_endpoint_count": 4,
        "status": "configured",
        "message": "Tushare token is configured and implemented endpoints can be enabled.",
    }
    assert "secret-token" not in response.text


def test_tushare_stock_basic_fetch_route_uses_service(monkeypatch) -> None:
    async def fake_collect_tushare_stock_basic(session) -> ProviderEndpointResult:
        return ProviderEndpointResult(
            endpoint="stock_basic",
            status=ProviderStatus.SUCCESS,
            row_count=1,
            quality_status=DataQualityStatus.OK,
            confidence=0.95,
            fetch_log_id=10,
            snapshot_id=20,
        )

    monkeypatch.setattr(
        "app.api.routes.providers.collect_tushare_stock_basic",
        fake_collect_tushare_stock_basic,
    )
    client = TestClient(create_app())

    response = client.post("/providers/tushare/fetch/stock-basic")

    assert response.status_code == 200
    assert response.json()["endpoint"] == "stock_basic"
    assert response.json()["status"] == "success"
    assert response.json()["fetch_log_id"] == 10


def test_tushare_daily_fetch_route_uses_service(monkeypatch) -> None:
    calls = []

    async def fake_collect_tushare_daily(
        session,
        *,
        trade_date=None,
        ts_code=None,
        start_date=None,
        end_date=None,
    ) -> ProviderEndpointResult:
        calls.append(
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        return ProviderEndpointResult(
            endpoint="daily",
            status=ProviderStatus.SUCCESS,
            row_count=2,
            quality_status=DataQualityStatus.OK,
            confidence=0.95,
            fetch_log_id=13,
            snapshot_id=23,
        )

    monkeypatch.setattr(
        "app.api.routes.providers.collect_tushare_daily",
        fake_collect_tushare_daily,
    )
    client = TestClient(create_app())

    response = client.post(
        "/providers/tushare/fetch/daily?ts_code=000001.SZ&start_date=20260501"
        "&end_date=20260504"
    )

    assert response.status_code == 200
    assert response.json()["endpoint"] == "daily"
    assert response.json()["row_count"] == 2
    assert response.json()["snapshot_id"] == 23
    assert calls == [
        {
            "trade_date": None,
            "ts_code": "000001.SZ",
            "start_date": "20260501",
            "end_date": "20260504",
        }
    ]


def test_tushare_daily_fetch_route_rejects_unbounded_date_range() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/providers/tushare/fetch/daily?start_date=20260501&end_date=20260504"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "ts_code is required when using start_date/end_date."


def test_tushare_announcements_fetch_route_uses_service(monkeypatch) -> None:
    calls = []

    async def fake_collect_tushare_announcements(session, ann_date=None) -> ProviderEndpointResult:
        calls.append(ann_date)
        return ProviderEndpointResult(
            endpoint="anns_d",
            status=ProviderStatus.SUCCESS,
            row_count=2,
            quality_status=DataQualityStatus.OK,
            confidence=0.95,
            fetch_log_id=11,
            snapshot_id=21,
        )

    monkeypatch.setattr(
        "app.api.routes.providers.collect_tushare_announcements",
        fake_collect_tushare_announcements,
    )
    client = TestClient(create_app())

    response = client.post("/providers/tushare/fetch/announcements?ann_date=20260503")

    assert response.status_code == 200
    assert response.json()["endpoint"] == "anns_d"
    assert response.json()["row_count"] == 2
    assert response.json()["snapshot_id"] == 21
    assert calls == ["20260503"]


def test_tushare_stock_company_fetch_route_uses_service(monkeypatch) -> None:
    calls = []

    async def fake_collect_tushare_stock_company(
        session,
        exchange="SZSE",
    ) -> ProviderEndpointResult:
        calls.append(exchange)
        return ProviderEndpointResult(
            endpoint="stock_company",
            status=ProviderStatus.SUCCESS,
            row_count=3,
            quality_status=DataQualityStatus.OK,
            confidence=0.95,
            fetch_log_id=12,
            snapshot_id=22,
        )

    monkeypatch.setattr(
        "app.api.routes.providers.collect_tushare_stock_company",
        fake_collect_tushare_stock_company,
    )
    client = TestClient(create_app())

    response = client.post("/providers/tushare/fetch/stock-company?exchange=SSE")

    assert response.status_code == 200
    assert response.json()["endpoint"] == "stock_company"
    assert response.json()["row_count"] == 3
    assert response.json()["snapshot_id"] == 22
    assert calls == ["SSE"]
