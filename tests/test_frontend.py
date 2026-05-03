from fastapi.testclient import TestClient

from app.main import create_app


def test_frontend_index_returns_static_page() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "BaizeFinDB" in response.text
    assert "雷达" in response.text
    assert "持仓 / 自选" in response.text
    assert "报告列表" in response.text


def test_frontend_assets_are_served() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")
    css_response = client.get("/assets/styles.css")

    assert js_response.status_code == 200
    assert "refreshAll" in js_response.text
    assert "loadPortfolio" in js_response.text
    assert "createReport" in js_response.text
    assert css_response.status_code == 200
    assert "status-panel" in css_response.text
    assert "portfolio-panel" in css_response.text
    assert "reports-panel" in css_response.text
