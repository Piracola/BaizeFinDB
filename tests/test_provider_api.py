from fastapi.testclient import TestClient

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

