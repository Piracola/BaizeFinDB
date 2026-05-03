from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


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
    assert all(item["implemented"] is False for item in payload)
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
        "fetch_enabled": False,
        "endpoint_count": 3,
        "implemented_endpoint_count": 0,
        "status": "configured",
        "message": "Tushare provider shell is registered; real fetch is not implemented yet.",
    }
    assert "secret-token" not in response.text

