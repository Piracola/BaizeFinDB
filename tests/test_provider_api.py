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
        "anns_d",
        "stock_company",
        "stock_basic",
    }
    implemented = {item["endpoint"]: item["implemented"] for item in payload}
    assert implemented == {
        "anns_d": False,
        "stock_company": False,
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
        "endpoint_count": 3,
        "implemented_endpoint_count": 1,
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

