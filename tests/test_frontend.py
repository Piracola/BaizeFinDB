from fastapi.testclient import TestClient

from app.main import create_app


def test_frontend_index_returns_static_page() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "BaizeFinDB" in response.text
    assert "雷达" in response.text
    assert "Radar Terminal" in response.text
    assert "OPS" in response.text
    assert "command-input" in response.text
    assert "持仓 / 自选" in response.text
    assert "报告列表" in response.text
    assert "周期汇总 / 综合评分" in response.text
    assert "Telegram 绑定 / 白名单" in response.text
    assert "daily / score" in response.text
    assert "ops-overview" in response.text
    assert "lifecycle-counts" in response.text
    assert "market-sentiment" in response.text
    assert "stock-backtrace-evidences" in response.text
    panel_order = [
        response.text.index('id="overview-panel"'),
        response.text.index('id="detail-panel"'),
        response.text.index('id="portfolio-panel"'),
        response.text.index('id="reports-panel"'),
    ]
    assert panel_order == sorted(panel_order)


def test_frontend_assets_are_served() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")
    css_response = client.get("/assets/styles.css")

    assert js_response.status_code == 200
    assert "refreshAll" in js_response.text
    assert "loadOpsOverview" in js_response.text
    assert "/ops/overview" in js_response.text
    assert "loadPortfolio" in js_response.text
    assert "createReport" in js_response.text
    assert "loadPeriodicReport" in js_response.text
    assert "scoreSelectedSignal" in js_response.text
    assert "renderScoreComponents" in js_response.text
    assert "score_band" in js_response.text
    assert "data_quality" in js_response.text
    assert "renderLifecycleCounts" in js_response.text
    assert "lifecycle_counts" in js_response.text
    assert "renderMarketSentiment" in js_response.text
    assert "market_sentiment" in js_response.text
    assert "renderStockBacktraceEvidences" in js_response.text
    assert "stock_backtrace_evidences" in js_response.text
    assert "loadTelegramBindings" in js_response.text
    assert "saveTelegramBinding" in js_response.text
    assert "executeCommand" in js_response.text
    assert "scrollToPanel" in js_response.text
    assert css_response.status_code == 200
    assert "terminal-shell" in css_response.text
    assert "status-panel" in css_response.text
    assert "ops-grid" in css_response.text
    assert "portfolio-panel" in css_response.text
    assert "reports-panel" in css_response.text
    assert "analytics-panel" in css_response.text
    assert "telegram-panel" in css_response.text
    assert "score-grid" in css_response.text
    assert "score-components" in css_response.text
    assert "lifecycle-grid" in css_response.text
    assert "sentiment-grid" in css_response.text
    assert "backtrace-list" in css_response.text
