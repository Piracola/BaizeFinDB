from fastapi.testclient import TestClient

from app.main import create_app


def test_frontend_index_returns_static_page() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "BaizeFinDB" in response.text
    assert "雷达" in response.text
    assert "Radar Terminal" in response.text
    assert "DATA" in response.text
    assert "OPS" in response.text
    assert "command-input" in response.text
    assert "market / data / dailydata" in response.text
    assert "market-data-panel" in response.text
    assert "Tushare 日线行情" in response.text
    assert "单数据源模式" in response.text
    assert "daily-source-summary" in response.text
    assert "daily-fetch-form" in response.text
    assert "daily-snapshot" in response.text
    assert "daily-fetch-logs" in response.text
    assert "持仓 / 自选" in response.text
    assert "报告列表" in response.text
    assert "周期汇总 / 综合评分" in response.text
    assert "Telegram 绑定 / 白名单" in response.text
    assert "设置 / API 配置" in response.text
    assert "ops / settings / trend / warn" in response.text
    assert "tushare / radar" in response.text
    assert "ops-overview" in response.text
    assert "ops-history" in response.text
    assert "ops-trends" in response.text
    assert "OPS 趋势" in response.text
    assert "ops-readiness" in response.text
    assert "OPS 告警钻取" in response.text
    assert "ops-warning-drilldown" in response.text
    assert "tushare-status" in response.text
    assert "settings-panel" in response.text
    assert "settings-status" in response.text
    assert "settings-form" in response.text
    assert "settings-test-result" in response.text
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
    assert "loadOpsHistory" in js_response.text
    assert "loadOpsTrends" in js_response.text
    assert "loadOpsReadiness" in js_response.text
    assert "loadOpsWarningDrilldown" in js_response.text
    assert "renderOpsWarningDrilldown" in js_response.text
    assert "renderOpsTrendChart" in js_response.text
    assert "ops-trend-chart" in js_response.text
    assert "trend-scan" in js_response.text
    assert "trend-failure" in js_response.text
    assert "trend-unhealthy" in js_response.text
    assert "/ops/overview" in js_response.text
    assert "/ops/history" in js_response.text
    assert "/ops/trends" in js_response.text
    assert "/ops/readiness" in js_response.text
    assert "/ops/overview?lookback_hours=24" in js_response.text
    assert "/ops/history?lookback_hours=24&limit=8" in js_response.text
    assert "/ops/trends?lookback_hours=24&bucket_count=12" in js_response.text
    assert "/ops/readiness?lookback_hours=24" in js_response.text
    assert 'trend: () => {' in js_response.text
    assert 'trends: () => {' in js_response.text
    assert 'scrollToPanel("ops-trends")' in js_response.text
    assert 'warn: () => {' in js_response.text
    assert 'warning: () => {' in js_response.text
    assert 'scrollToPanel("ops-warning-drilldown")' in js_response.text
    assert "formatOpsAlerts" in js_response.text
    assert "formatOpsServerDetail" in js_response.text
    assert "formatOpsServerResources" in js_response.text
    assert "disk_free_percent" in js_response.text
    assert "cpu_usage_percent" in js_response.text
    assert "memory_used_percent" in js_response.text
    assert "loadTushareStatus" in js_response.text
    assert "loadTushareDailyConsole" in js_response.text
    assert "fetchTushareDaily" in js_response.text
    assert "buildDailyFetchQuery" in js_response.text
    assert "renderDailySourceSummary" in js_response.text
    assert "renderDailySnapshot" in js_response.text
    assert "renderDailyFetchLogs" in js_response.text
    assert "/providers/tushare/status" in js_response.text
    assert "/providers/tushare/readiness" in js_response.text
    assert "/providers/tushare/fetch/daily" in js_response.text
    assert "/providers/tushare/snapshots/latest?endpoint=daily" in js_response.text
    assert "/providers/tushare/fetch-logs?endpoint=daily&limit=8" in js_response.text
    assert "loadSettingsStatus" in js_response.text
    assert "/settings/status" in js_response.text
    assert "/settings/editable" in js_response.text
    assert "/settings/connection-test" in js_response.text
    assert "saveSettings" in js_response.text
    assert "testSettingsConnection" in js_response.text
    assert "X-BaizeFinDB-Settings-Token" in js_response.text
    assert "renderSettingsStatus" in js_response.text
    assert "settings: () =>" in js_response.text
    assert "config: () =>" in js_response.text
    assert "market: () =>" in js_response.text
    assert "dailydata: () =>" in js_response.text
    assert "renderTushareStatus" in js_response.text
    assert "statusCardClass" in js_response.text
    assert "loadPortfolio" in js_response.text
    assert "createReport" in js_response.text
    assert "createDeepReport" in js_response.text
    assert "loadPeriodicReport" in js_response.text
    assert "scoreSelectedSignal" in js_response.text
    assert "renderScoreComponents" in js_response.text
    assert "score_band" in js_response.text
    assert "/radar/signals/${signalId}/analysis" in js_response.text
    model_draft_endpoint = (
        "/radar/signals/${encodeURIComponent(state.selectedSignalId)}/model-analysis-draft"
    )
    assert model_draft_endpoint in js_response.text
    assert "renderSignalAnalysisBrief" in js_response.text
    assert "renderModelAnalysisDraft" in js_response.text
    assert "createModelAnalysisDraft" in js_response.text
    assert "metric_highlights" in js_response.text
    assert "risk_flags" in js_response.text
    assert "evidence_summary" in js_response.text
    assert "review_summary" in js_response.text
    assert "agent_assessments" in js_response.text
    assert "renderAgentAssessments" in js_response.text
    assert "next_actions" in js_response.text
    assert "data_quality" in js_response.text
    assert "renderLifecycleCounts" in js_response.text
    assert "lifecycle_counts" in js_response.text
    assert "renderMarketSentiment" in js_response.text
    assert "market_sentiment" in js_response.text
    assert "renderStockBacktraceEvidences" in js_response.text
    assert "stock_backtrace_evidences" in js_response.text
    assert "loadTelegramBindings" in js_response.text
    assert "/telegram/status" in js_response.text
    assert "renderTelegramBindingStatus" in js_response.text
    assert "require_binding" in js_response.text
    assert "allowed_chat_count" in js_response.text
    assert "binding_count" in js_response.text
    assert "active_binding_count" in js_response.text
    assert "saveTelegramBinding" in js_response.text
    assert "executeCommand" in js_response.text
    assert "scrollToPanel" in js_response.text
    assert css_response.status_code == 200
    assert "terminal-shell" in css_response.text
    assert "status-panel" in css_response.text
    assert "ops-grid" in css_response.text
    assert "ops-trends-list" in css_response.text
    assert "ops-trend-chart" in css_response.text
    assert "ops-trend-chart-bucket" in css_response.text
    assert "ops-trend-legend" in css_response.text
    assert "ops-trend-table" in css_response.text
    assert "ops-warning-drilldown" in css_response.text
    assert "ops-drilldown-section" in css_response.text
    assert "tushare-grid" in css_response.text
    assert "market-data-panel" in css_response.text
    assert "market-summary-grid" in css_response.text
    assert "market-console" in css_response.text
    assert "market-table" in css_response.text
    assert "quote-form-grid" in css_response.text
    assert "status-warning" in css_response.text
    assert "portfolio-panel" in css_response.text
    assert "reports-panel" in css_response.text
    assert "analytics-panel" in css_response.text
    assert "settings-panel" in css_response.text
    assert "settings-grid" in css_response.text
    assert "settings-status" in css_response.text
    assert "settings-form-grid" in css_response.text
    assert "settings-test-bar" in css_response.text
    assert "settings-test-result" in css_response.text
    assert "telegram-panel" in css_response.text
    assert "score-grid" in css_response.text
    assert "score-components" in css_response.text
    assert "lifecycle-grid" in css_response.text
    assert "sentiment-grid" in css_response.text
    assert "backtrace-list" in css_response.text
    assert "analysis-brief" in css_response.text
    assert "model-draft-card" in css_response.text
    assert "analysis-grid" in css_response.text
    assert "analysis-agent-grid" in css_response.text
    assert "analysis-agent-list" in css_response.text


def test_frontend_daily_data_console_uses_tushare_daily_contract() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")

    assert js_response.status_code == 200
    js_text = js_response.text
    load_start = js_text.index("async function loadTushareDailyConsole")
    load_end = js_text.index("async function loadSettingsStatus")
    load_block = js_text[load_start:load_end]
    fetch_start = js_text.index("async function fetchTushareDaily")
    fetch_end = js_text.index("async function fetchMinimalAkshare")
    fetch_block = js_text[fetch_start:fetch_end]
    query_start = js_text.index("function buildDailyFetchQuery")
    query_end = js_text.index("function formPayload")
    query_block = js_text[query_start:query_end]

    assert 'fetchJson("/providers/tushare/status")' in load_block
    assert 'fetchJson("/providers/tushare/readiness")' in load_block
    assert 'fetchJson("/providers/tushare/snapshots/latest?endpoint=daily")' in load_block
    assert 'fetchJson("/providers/tushare/fetch-logs?endpoint=daily&limit=8")' in load_block
    assert "renderDailySourceSummary(status, readiness, latestSnapshot, dailyLogs[0])" in load_block
    assert "renderDailySnapshot(latestSnapshot)" in load_block
    assert "renderDailyFetchLogs(dailyLogs)" in load_block
    assert "`/providers/tushare/fetch/daily${suffix}`" in fetch_block
    assert "loadTushareStatus()" in fetch_block
    assert "loadTushareDailyConsole({ silent: true })" in fetch_block
    assert "TUSHARE_DATE_PATTERN" in query_block
    assert "TUSHARE_TS_CODE_PATTERN" in query_block
    assert "交易日不能和开始/结束日期同时填写" in query_block
    assert "按区间抓取时必须填写股票代码" in query_block
    assert 'params.set("trade_date", tradeDate)' in query_block
    assert 'params.set("ts_code", tsCode)' in query_block
    assert "TUSHARE_TOKEN" not in query_block
    assert "token" not in query_block.lower()


def test_frontend_settings_panel_uses_editable_settings_contract() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")

    assert js_response.status_code == 200
    js_text = js_response.text
    load_start = js_text.index("async function loadSettingsStatus")
    load_end = js_text.index("async function saveSettings")
    load_block = js_text[load_start:load_end]
    render_start = js_text.index("function renderSettingsStatus")
    render_end = js_text.index("function renderSettingsStatusUnavailable")
    render_block = js_text[render_start:render_end]
    save_start = js_text.index("async function saveSettings")
    save_end = js_text.index("async function testSettingsConnection")
    save_block = js_text[save_start:save_end]
    test_start = js_text.index("async function testSettingsConnection")
    test_end = js_text.index("async function loadOverview")
    test_block = js_text[test_start:test_end]

    assert 'fetchJson("/settings/status")' in load_block
    assert 'fetchJson("/settings/editable")' in load_block
    assert "renderSettingsStatus(status)" in load_block
    assert "renderSettingsEditor(editable)" in load_block
    assert 'fetchJson("/settings/editable"' in save_block
    assert "collectSettingsPayload()" in save_block
    assert "X-BaizeFinDB-Settings-Token" in save_block
    assert 'fetchJson("/settings/connection-test"' in test_block
    assert "renderSettingsConnectionTest(result)" in test_block
    assert "settings-grid" in render_block
    assert "token_configured" in render_block
    assert "bot_token_configured" in render_block
    assert "openai_api_key_configured" in render_block
    assert "model_api_key_configured" in render_block
    assert "read_only_boundary" in render_block
    assert "可编辑表单不会回显真实密钥" in render_block
    assert "TUSHARE_TOKEN" not in render_block
    assert "TELEGRAM_BOT_TOKEN" not in render_block
    assert "TELEGRAM_WEBHOOK_SECRET" not in render_block
    assert "MODEL_API_KEY" not in render_block
    assert "OPENAI_API_KEY" not in render_block
    assert "Authorization" not in render_block


def test_frontend_manual_deep_report_action_uses_confirmed_backend_endpoint() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")

    assert js_response.status_code == 200
    js_text = js_response.text
    quick_start = js_text.index("async function createReport")
    quick_end = js_text.index("async function createDeepReport")
    quick_block = js_text[quick_start:quick_end]
    deep_start = js_text.index("async function createDeepReport")
    deep_end = js_text.index("async function scoreSelectedSignal")
    deep_block = js_text[deep_start:deep_end]
    detail_start = js_text.index("function renderSignalDetail")
    detail_end = js_text.index("function renderSignalAnalysisBrief")
    detail_block = js_text[detail_start:detail_end]

    assert 'postJson(`/reports/from-signal${portfolioQuery()}`' in quick_block
    assert 'report_type: reportType' in quick_block
    assert "deep" not in quick_block.lower()
    assert "window.confirm" in deep_block
    assert 'postJson(`/reports/deep/from-signal${portfolioQuery()}`' in deep_block
    assert "confirm_deep_report: true" in deep_block
    assert "report_type" not in deep_block
    assert "loadReports()" in deep_block
    assert 'data-deep-report="true"' in detail_block
    assert 'data-report-type="quick"' in detail_block
    assert 'data-report-type="standard"' in detail_block
    assert "createDeepReport" in detail_block
    assert 'createReport("deep")' not in js_text


def test_frontend_ops_warning_drilldown_keeps_backend_owned_status_boundary() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")

    assert js_response.status_code == 200
    js_text = js_response.text
    drilldown_start = js_text.index("function renderOpsWarningDrilldown")
    drilldown_end = js_text.index("function renderTushareStatus")
    drilldown_block = js_text[drilldown_start:drilldown_end]

    assert "check.status !== \"ok\"" in drilldown_block
    assert "readinessStatusLabel(readiness?.status" in drilldown_block
    assert "overview?.alerts" in drilldown_block
    assert "history?.failure_summary" in drilldown_block
    assert "history?.recent_events" in drilldown_block
    assert "slice(0, 8)" in drilldown_block
    assert "alerts.length > 0" not in drilldown_block
    assert "unhealthy_count" not in drilldown_block
    assert "recent_scan_failure_count" not in drilldown_block
    assert "is_cpu_pressure_high" not in drilldown_block
    assert "is_memory_pressure_high" not in drilldown_block


def test_frontend_signal_analysis_uses_backend_brief_without_raw_fields() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")

    assert js_response.status_code == 200
    js_text = js_response.text
    load_start = js_text.index("async function loadSignalDetail")
    load_end = js_text.index("async function runRadarScan")
    load_block = js_text[load_start:load_end]
    render_start = js_text.index("function renderSignalAnalysisBrief")
    render_end = js_text.index("function renderHoldings")
    render_block = js_text[render_start:render_end]

    assert "Promise.allSettled" in load_block
    assert "fetchJson(`/radar/signals/${signalId}`)" in load_block
    assert "fetchJson(`/radar/signals/${signalId}/analysis`)" in load_block
    assert "renderSignalDetail(" in load_block
    assert "analysis_title" in render_block
    assert "key_points" in render_block
    assert "metric_highlights" in render_block
    assert "risk_flags" in render_block
    assert "evidence_summary" in render_block
    assert "review_summary" in render_block
    assert "agent_assessments" in render_block
    assert "renderAgentAssessments" in render_block
    assert "item.agent_id" in render_block
    assert "item.status" in render_block
    assert "item.findings" in render_block
    assert "next_actions" in render_block
    assert "item.next_actions" in render_block
    assert "priorityBadgeClass(analysis.priority)" in render_block
    assert "label(analysis.lifecycle_stage)" in render_block
    assert "label(analysis.review_status)" in render_block
    assert "raw_excerpt" not in render_block
    assert "source_ref" not in render_block
    assert "source_url" not in render_block
    assert "details" not in render_block
    assert "position_ratio" not in render_block
    assert "cost_price" not in render_block
    assert "buy" not in render_block.lower()
    assert "sell" not in render_block.lower()
    assert "买入" not in render_block
    assert "卖出" not in render_block


def test_frontend_model_analysis_draft_is_manual_and_sanitized() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")

    assert js_response.status_code == 200
    js_text = js_response.text
    load_start = js_text.index("async function loadSignalDetail")
    load_end = js_text.index("async function runRadarScan")
    load_block = js_text[load_start:load_end]
    action_start = js_text.index("async function createModelAnalysisDraft")
    action_end = js_text.index("async function scoreSelectedSignal")
    action_block = js_text[action_start:action_end]
    detail_start = js_text.index("function renderSignalDetail")
    detail_end = js_text.index("function renderSignalAnalysisBrief")
    detail_block = js_text[detail_start:detail_end]
    render_start = js_text.index("function renderModelAnalysisDraft")
    render_end = js_text.index("function renderHoldings")
    render_block = js_text[render_start:render_end]

    assert "model-analysis-draft" not in load_block
    assert "Promise.allSettled" in load_block
    assert "fetchJson(`/radar/signals/${signalId}`)" in load_block
    assert "fetchJson(`/radar/signals/${signalId}/analysis`)" in load_block
    assert 'data-model-draft="true"' in detail_block
    assert "生成模型草稿" in detail_block
    assert "createModelAnalysisDraft" in detail_block
    assert "postJson(" in action_block
    model_draft_endpoint = (
        "/radar/signals/${encodeURIComponent(state.selectedSignalId)}/model-analysis-draft"
    )
    assert model_draft_endpoint in action_block
    assert "renderModelAnalysisDraft(draft)" in action_block
    assert "model_status" in render_block
    assert "draft_status" in render_block
    assert "advisory_summary" in render_block
    assert "observations" in render_block
    assert "risk_notes" in render_block
    assert "follow_up_questions" in render_block
    assert "suggested_attention_label" in render_block
    assert "blocked_terms.length" in render_block
    assert "payload.blocked_terms" in render_block
    assert "boundary" in render_block
    assert "raw_prompt" not in render_block
    assert "response_excerpt" not in render_block
    assert "source_ref" not in render_block
    assert "raw_excerpt" not in render_block
    assert "source_url" not in render_block
    assert "position_ratio" not in render_block
    assert "cost_price" not in render_block
    assert "api_key" not in render_block.lower()
    assert "authorization" not in render_block.lower()
    assert "买入" not in render_block
    assert "卖出" not in render_block
    assert "buy" not in render_block.lower()
    assert "sell" not in render_block.lower()


def test_frontend_ops_trends_uses_backend_bucket_counts_only() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")

    assert js_response.status_code == 200
    js_text = js_response.text
    trends_start = js_text.index("function renderOpsTrends")
    trends_end = js_text.index("function renderOpsReadiness")
    trends_block = js_text[trends_start:trends_end]

    assert "radar_scan_count" in trends_block
    assert "radar_failure_count" in trends_block
    assert "provider_fetch_unhealthy_count" in trends_block
    assert "data_quality_unhealthy_count" in trends_block
    assert "telegram_push_unhealthy_count" in trends_block
    assert "model_call_unhealthy_count" in trends_block
    assert "renderOpsTrendChart(chartBuckets)" in trends_block
    assert "bucketUnhealthyCount(bucket)" in trends_block
    assert "role=\"img\"" in trends_block
    assert "readinessStatusLabel" not in trends_block
    assert "statusCardClass" not in trends_block
    assert "alerts.length" not in trends_block
    assert "recent_scan_failure_rate" not in trends_block


def test_frontend_telegram_bindings_loads_status_with_secret_header_contract() -> None:
    client = TestClient(create_app())

    js_response = client.get("/assets/app.js")

    assert js_response.status_code == 200
    js_text = js_response.text
    load_start = js_text.index("async function loadTelegramBindings")
    load_end = js_text.index("async function loadPeriodicReport")
    load_block = js_text[load_start:load_end]
    render_start = js_text.index("function renderTelegramBindings")
    render_end = js_text.index("async function fetchJson")
    render_block = js_text[render_start:render_end]

    assert "const headers = telegramHeaders()" in load_block
    assert 'fetchJson("/telegram/status", { headers })' in load_block
    assert 'fetchJson("/telegram/bindings?limit=50", { headers })' in load_block
    assert "renderTelegramBindings(bindings, status)" in load_block
    assert "require_binding" in render_block
    assert "allowed_chat_count" in render_block
    assert "binding_count" in render_block
    assert "active_binding_count" in render_block
    assert "TELEGRAM_ALLOWED_CHAT_IDS" not in render_block
    assert "TELEGRAM_BOT_TOKEN" not in render_block
    assert "TELEGRAM_WEBHOOK_SECRET" not in render_block
