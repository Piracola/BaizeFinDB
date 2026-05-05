const state = {
  selectedSignalId: null,
};

const SCORE_COMPONENT_ORDER = [
  "priority",
  "lifecycle",
  "review",
  "evidence",
  "continuity",
  "data_quality",
  "timeliness",
];

const LIFECYCLE_ORDER = [
  "ignition",
  "developing",
  "divergence",
  "returning",
  "climax",
  "fading",
  "extinguished",
];

const elements = {
  refreshButton: document.querySelector("#refresh-button"),
  runScanButton: document.querySelector("#run-scan-button"),
  fetchAkshareButton: document.querySelector("#fetch-akshare-button"),
  dailyReportButton: document.querySelector("#daily-report-button"),
  weeklyReportButton: document.querySelector("#weekly-report-button"),
  scoreSignalButton: document.querySelector("#score-signal-button"),
  telegramBindingForm: document.querySelector("#telegram-binding-form"),
  telegramRefreshButton: document.querySelector("#telegram-refresh-button"),
  telegramDisableButton: document.querySelector("#telegram-disable-button"),
  telegramSecret: document.querySelector("#telegram-secret"),
  telegramBindingsList: document.querySelector("#telegram-bindings-list"),
  commandInput: document.querySelector("#command-input"),
  commandRunButton: document.querySelector("#command-run-button"),
  lastUpdated: document.querySelector("#last-updated"),
  readyStatus: document.querySelector("#ready-status"),
  opsOverview: document.querySelector("#ops-overview"),
  opsHistory: document.querySelector("#ops-history"),
  opsTrends: document.querySelector("#ops-trends"),
  opsReadiness: document.querySelector("#ops-readiness"),
  opsWarningDrilldown: document.querySelector("#ops-warning-drilldown"),
  tushareStatus: document.querySelector("#tushare-status"),
  actionMessage: document.querySelector("#action-message"),
  priorityCounts: document.querySelector("#priority-counts"),
  lifecycleCounts: document.querySelector("#lifecycle-counts"),
  marketSentiment: document.querySelector("#market-sentiment"),
  latestScan: document.querySelector("#latest-scan"),
  stockBacktraceEvidences: document.querySelector("#stock-backtrace-evidences"),
  currentSubjects: document.querySelector("#current-subjects"),
  signalsList: document.querySelector("#signals-list"),
  signalDetail: document.querySelector("#signal-detail"),
  portfolioUserKey: document.querySelector("#portfolio-user-key"),
  holdingForm: document.querySelector("#holding-form"),
  watchlistForm: document.querySelector("#watchlist-form"),
  holdingsList: document.querySelector("#holdings-list"),
  watchlistList: document.querySelector("#watchlist-list"),
  reportsList: document.querySelector("#reports-list"),
  periodicReport: document.querySelector("#periodic-report"),
  scoreRun: document.querySelector("#score-run"),
};

document.addEventListener("DOMContentLoaded", () => {
  elements.refreshButton.addEventListener("click", refreshAll);
  elements.runScanButton.addEventListener("click", runRadarScan);
  elements.fetchAkshareButton.addEventListener("click", fetchMinimalAkshare);
  elements.dailyReportButton.addEventListener("click", () => loadPeriodicReport("daily"));
  elements.weeklyReportButton.addEventListener("click", () => loadPeriodicReport("weekly"));
  elements.scoreSignalButton.addEventListener("click", scoreSelectedSignal);
  elements.telegramRefreshButton.addEventListener("click", loadTelegramBindings);
  elements.telegramDisableButton.addEventListener("click", disableTelegramBinding);
  elements.commandRunButton.addEventListener("click", executeCommand);
  elements.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      executeCommand();
    }
  });
  document.querySelectorAll("[data-scroll-target]").forEach((button) => {
    button.addEventListener("click", () => scrollToPanel(button.dataset.scrollTarget));
  });
  elements.portfolioUserKey.addEventListener("change", () => {
    loadPortfolio();
    loadReports();
    loadPeriodicReport("daily");
  });
  elements.holdingForm.addEventListener("submit", addHolding);
  elements.watchlistForm.addEventListener("submit", addWatchlistItem);
  elements.telegramBindingForm.addEventListener("submit", saveTelegramBinding);
  refreshAll();
});

async function refreshAll() {
  setButtonsBusy(true);
  showMessage("info", "正在刷新 API 状态、运行状态、雷达总览和信号列表。");

  const isReady = await loadReadyStatus();
  if (isReady) {
    await Promise.all([
      loadOpsOverview(),
      loadOpsHistory(),
      loadOpsTrends(),
      loadOpsReadiness(),
      loadOpsWarningDrilldown({ silent: true }),
      loadTushareStatus(),
      loadOverview(),
      loadSignals(),
      loadPortfolio(),
      loadReports(),
      loadPeriodicReport("daily", { silent: true }),
      loadTelegramBindings({ silent: true }),
    ]);
    showMessage("info", "刷新完成。");
  } else {
    renderRadarUnavailable("API 依赖未就绪。确认 PostgreSQL、Redis 和迁移状态后再刷新。");
    showMessage("error", "API 依赖未就绪，暂不读取雷达数据。");
  }

  elements.lastUpdated.textContent = `最近刷新：${formatDate(new Date().toISOString())}`;
  setButtonsBusy(false);
}

async function loadReadyStatus() {
  try {
    const response = await fetch("/health/ready");
    const payload = await readPayload(response);
    renderReadyStatus(response.ok, payload);
    return response.ok;
  } catch (error) {
    elements.readyStatus.innerHTML = emptyState(`无法连接 API：${formatError(error)}`);
    renderOpsUnavailable("无法连接 API。");
    renderOpsHistoryUnavailable("无法连接 API。");
    renderOpsTrendsUnavailable("无法连接 API。");
    renderOpsReadinessUnavailable("无法连接 API。");
    renderOpsWarningDrilldownUnavailable("无法连接 API。");
    return false;
  }
}

async function loadOpsOverview() {
  try {
    const overview = await fetchJson("/ops/overview?lookback_hours=24");
    renderOpsOverview(overview);
  } catch (error) {
    renderOpsUnavailable(`运行状态暂不可用：${formatError(error)}`);
  }
}

async function loadOpsHistory() {
  try {
    const history = await fetchJson("/ops/history?lookback_hours=24&limit=8");
    renderOpsHistory(history);
  } catch (error) {
    renderOpsHistoryUnavailable(`运维历史暂不可用：${formatError(error)}`);
  }
}

async function loadOpsTrends() {
  try {
    const trends = await fetchJson("/ops/trends?lookback_hours=24&bucket_count=12");
    renderOpsTrends(trends);
  } catch (error) {
    renderOpsTrendsUnavailable(`OPS 趋势暂不可用：${formatError(error)}`);
  }
}

async function loadOpsReadiness() {
  try {
    const readiness = await fetchJson("/ops/readiness?lookback_hours=24");
    renderOpsReadiness(readiness);
  } catch (error) {
    renderOpsReadinessUnavailable(`就绪自检暂不可用：${formatError(error)}`);
  }
}

async function loadOpsWarningDrilldown(options = {}) {
  try {
    const [readiness, overview, history] = await Promise.all([
      fetchJson("/ops/readiness?lookback_hours=24"),
      fetchJson("/ops/overview?lookback_hours=24"),
      fetchJson("/ops/history?lookback_hours=24&limit=8"),
    ]);
    renderOpsWarningDrilldown(readiness, overview, history);
    if (!options.silent) {
      showMessage("info", "OPS 告警钻取已刷新。");
    }
  } catch (error) {
    renderOpsWarningDrilldownUnavailable(`OPS 告警钻取暂不可用：${formatError(error)}`);
    if (!options.silent) {
      showMessage("error", `OPS 告警钻取失败：${formatError(error)}`);
    }
  }
}

async function loadTushareStatus() {
  try {
    const [status, readiness] = await Promise.all([
      fetchJson("/providers/tushare/status"),
      fetchJson("/providers/tushare/readiness"),
    ]);
    renderTushareStatus(status, readiness);
  } catch (error) {
    renderTushareUnavailable(`Tushare 状态暂不可用：${formatError(error)}`);
  }
}

async function loadOverview() {
  try {
    const overview = await fetchJson("/radar/overview");
    const latestScan = overview.latest_scan;
    renderPriorityCounts(overview.priority_counts || {});
    renderLifecycleCounts(overview.lifecycle_counts || {});
    renderMarketSentiment(latestScan?.summary?.market_sentiment);
    renderLatestScan(latestScan);
    renderStockBacktraceEvidences(overview.stock_backtrace_evidences || []);
    renderCurrentSubjects(overview.current_subjects || []);
  } catch (error) {
    elements.priorityCounts.innerHTML = emptyState(`雷达总览暂不可用：${formatError(error)}`);
    elements.lifecycleCounts.innerHTML = emptyState("暂无生命周期分布。");
    elements.marketSentiment.innerHTML = emptyState("暂无市场情绪摘要。");
    elements.latestScan.innerHTML = emptyState("确认数据库迁移和依赖服务后再刷新。");
    elements.stockBacktraceEvidences.innerHTML = emptyState("暂无个股回推证据。");
    elements.currentSubjects.innerHTML = emptyState("暂无当前主题。可先触发采集，再运行雷达扫描。");
  }
}

async function loadSignals() {
  try {
    const signals = await fetchJson("/radar/signals");
    renderSignals(signals);
  } catch (error) {
    elements.signalsList.innerHTML = emptyState(`信号列表暂不可用：${formatError(error)}`);
  }
}

async function loadPortfolio() {
  try {
    const userQuery = portfolioQuery();
    const [holdings, watchlistItems] = await Promise.all([
      fetchJson(`/portfolio/holdings${userQuery}`),
      fetchJson(`/portfolio/watchlist${userQuery}`),
    ]);
    renderHoldings(holdings);
    renderWatchlistItems(watchlistItems);
  } catch (error) {
    elements.holdingsList.innerHTML = emptyState(`持仓暂不可用：${formatError(error)}`);
    elements.watchlistList.innerHTML = emptyState(`自选暂不可用：${formatError(error)}`);
  }
}

async function loadReports() {
  try {
    const reports = await fetchJson(`/reports${portfolioQuery()}`);
    renderReports(reports);
  } catch (error) {
    elements.reportsList.innerHTML = emptyState(`报告列表暂不可用：${formatError(error)}`);
  }
}

async function loadTelegramBindings(options = {}) {
  try {
    const headers = telegramHeaders();
    const [status, bindings] = await Promise.all([
      fetchJson("/telegram/status", { headers }),
      fetchJson("/telegram/bindings?limit=50", { headers }),
    ]);
    renderTelegramBindings(bindings, status);
    if (!options.silent) {
      showMessage("info", "Telegram 绑定已刷新。");
    }
  } catch (error) {
    elements.telegramBindingsList.innerHTML = emptyState(`Telegram 绑定暂不可用：${formatError(error)}`);
    if (!options.silent) {
      showMessage("error", `读取 Telegram 绑定失败：${formatError(error)}`);
    }
  }
}

async function loadPeriodicReport(period, options = {}) {
  try {
    const report = await fetchJson(`/reports/periodic${periodicQuery(period)}`);
    renderPeriodicReport(report);
    if (!options.silent) {
      showMessage("info", `${period === "weekly" ? "周报" : "日报"}汇总已生成。`);
    }
  } catch (error) {
    elements.periodicReport.innerHTML = emptyState(`周期汇总暂不可用：${formatError(error)}`);
    if (!options.silent) {
      showMessage("error", `周期汇总失败：${formatError(error)}`);
    }
  }
}

function renderRadarUnavailable(reason) {
  renderOpsUnavailable("依赖服务恢复后再读取运行状态。");
  renderOpsHistoryUnavailable("依赖服务恢复后再读取运维历史。");
  renderOpsTrendsUnavailable("依赖服务恢复后再读取 OPS 趋势。");
  renderOpsReadinessUnavailable("依赖服务恢复后再读取就绪自检。");
  renderOpsWarningDrilldownUnavailable("依赖服务恢复后再读取 OPS 告警钻取。");
  renderTushareUnavailable("依赖服务恢复后再读取 Tushare 状态。");
  elements.priorityCounts.innerHTML = emptyState(reason);
  elements.lifecycleCounts.innerHTML = emptyState("暂无生命周期分布。");
  elements.marketSentiment.innerHTML = emptyState("暂无市场情绪摘要。");
  elements.latestScan.innerHTML = emptyState("依赖服务恢复后，先触发采集或运行雷达扫描。");
  elements.stockBacktraceEvidences.innerHTML = emptyState("暂无个股回推证据。");
  elements.currentSubjects.innerHTML = emptyState("暂无当前主题。");
  elements.signalsList.innerHTML = emptyState("暂无信号列表。");
  elements.holdingsList.innerHTML = emptyState("依赖服务恢复后再读取持仓。");
  elements.watchlistList.innerHTML = emptyState("依赖服务恢复后再读取自选。");
  elements.reportsList.innerHTML = emptyState("依赖服务恢复后再读取报告。");
  elements.periodicReport.innerHTML = emptyState("依赖服务恢复后再读取周期汇总。");
  elements.scoreRun.innerHTML = emptyState("依赖服务恢复后再读取评分。");
  elements.telegramBindingsList.innerHTML = emptyState("依赖服务恢复后再读取 Telegram 绑定。");
}

async function loadSignalDetail(signalId) {
  state.selectedSignalId = signalId;
  elements.signalDetail.classList.remove("empty-state");
  elements.signalDetail.innerHTML = emptyState("正在读取信号详情。");

  try {
    const [detailResult, analysisResult] = await Promise.allSettled([
      fetchJson(`/radar/signals/${signalId}`),
      fetchJson(`/radar/signals/${signalId}/analysis`),
    ]);

    if (detailResult.status === "rejected") {
      throw detailResult.reason;
    }

    renderSignalDetail(
      detailResult.value,
      analysisResult.status === "fulfilled" ? analysisResult.value : null,
      analysisResult.status === "rejected" ? analysisResult.reason : null,
    );
  } catch (error) {
    elements.signalDetail.innerHTML = emptyState(`信号详情暂不可用：${formatError(error)}`);
  }
}

async function runRadarScan() {
  setButtonsBusy(true);
  showMessage("info", "正在请求后端运行雷达扫描。");

  try {
    const scan = await fetchJson("/radar/scans/run", { method: "POST" });
    const signalCount = Number(scan.summary?.signal_count ?? scan.signals?.length ?? 0);
    showMessage("info", `雷达扫描已返回：${label(scan.status)}，信号数 ${signalCount}。`);
    await Promise.all([loadOverview(), loadSignals()]);
  } catch (error) {
    showMessage("error", `雷达扫描失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function fetchMinimalAkshare() {
  setButtonsBusy(true);
  showMessage("info", "正在请求 AKShare 最小采集。接口受网络和数据源状态影响，失败会直接显示。");

  try {
    const payload = await fetchJson("/providers/akshare/fetch/minimal", { method: "POST" });
    const results = payload.results || [];
    const successCount = results.filter((item) => item.status === "success").length;
    const failureCount = results.filter((item) => item.status === "failure").length;
    showMessage("info", `AKShare 采集返回：成功 ${successCount} 个，失败 ${failureCount} 个。`);
    await Promise.all([loadOverview(), loadSignals()]);
  } catch (error) {
    showMessage("error", `AKShare 采集失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function addHolding(event) {
  event.preventDefault();
  setButtonsBusy(true);
  showMessage("info", "正在添加持仓。");

  try {
    await postJson(`/portfolio/holdings${portfolioQuery()}`, formPayload(elements.holdingForm));
    elements.holdingForm.reset();
    elements.holdingForm.elements.market.value = "A_SHARE";
    showMessage("info", "持仓已添加。");
    await loadPortfolio();
  } catch (error) {
    showMessage("error", `添加持仓失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function addWatchlistItem(event) {
  event.preventDefault();
  setButtonsBusy(true);
  showMessage("info", "正在添加自选。");

  try {
    await postJson(`/portfolio/watchlist${portfolioQuery()}`, formPayload(elements.watchlistForm));
    elements.watchlistForm.reset();
    elements.watchlistForm.elements.market.value = "A_SHARE";
    showMessage("info", "自选已添加。");
    await loadPortfolio();
  } catch (error) {
    showMessage("error", `添加自选失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function deleteHolding(holdingId) {
  await deletePortfolioItem(`/portfolio/holdings/${holdingId}${portfolioQuery()}`, "持仓");
}

async function deleteWatchlistItem(itemId) {
  await deletePortfolioItem(`/portfolio/watchlist/${itemId}${portfolioQuery()}`, "自选");
}

async function deletePortfolioItem(path, labelText) {
  setButtonsBusy(true);
  showMessage("info", `正在删除${labelText}。`);

  try {
    await fetchJson(path, { method: "DELETE" });
    showMessage("info", `${labelText}已删除。`);
    await loadPortfolio();
  } catch (error) {
    showMessage("error", `删除${labelText}失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function createReport(reportType) {
  if (!state.selectedSignalId) {
    showMessage("error", "请先选择一个信号。");
    return;
  }

  setButtonsBusy(true);
  showMessage("info", `正在生成 ${reportType} report。`);

  try {
    const report = await postJson(`/reports/from-signal${portfolioQuery()}`, {
      signal_id: Number(state.selectedSignalId),
      report_type: reportType,
    });
    showMessage("info", `报告已生成：#${report.id} ${report.title}`);
    await loadReports();
  } catch (error) {
    showMessage("error", `生成报告失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function createDeepReport() {
  if (!state.selectedSignalId) {
    showMessage("error", "请先选择一个信号。");
    return;
  }

  const confirmed = window.confirm(
    "Deep Report 会生成更长的研究记录。确认手动生成当前信号的 Deep Report？",
  );
  if (!confirmed) {
    showMessage("info", "已取消 Deep Report 生成。");
    return;
  }

  setButtonsBusy(true);
  showMessage("info", `正在生成信号 #${state.selectedSignalId} Deep Report。`);

  try {
    const report = await postJson(`/reports/deep/from-signal${portfolioQuery()}`, {
      signal_id: Number(state.selectedSignalId),
      confirm_deep_report: true,
    });
    showMessage("info", `Deep Report 已生成：#${report.id} ${report.title}`);
    await loadReports();
  } catch (error) {
    showMessage("error", `生成 Deep Report 失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function scoreSelectedSignal() {
  if (!state.selectedSignalId) {
    showMessage("error", "请先选择一个信号。");
    return;
  }

  setButtonsBusy(true);
  showMessage("info", `正在生成信号 #${state.selectedSignalId} 综合评分。`);

  try {
    const scoreRun = await postJson(`/scores/signals/${encodeURIComponent(state.selectedSignalId)}`);
    renderScores(scoreRun);
    showMessage("info", `信号 #${state.selectedSignalId} 综合评分已生成。`);
  } catch (error) {
    elements.scoreRun.innerHTML = emptyState(`评分暂不可用：${formatError(error)}`);
    showMessage("error", `生成评分失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function saveTelegramBinding(event) {
  event.preventDefault();
  const payload = telegramBindingPayload();
  if (!payload) {
    return;
  }

  setButtonsBusy(true);
  showMessage("info", `正在绑定 Telegram chat ${payload.chat_id}。`);

  try {
    await fetchJson("/telegram/bindings", {
      method: "POST",
      headers: telegramHeaders({ json: true }),
      body: JSON.stringify(payload),
    });
    showMessage("info", `Telegram chat ${payload.chat_id} 已绑定。`);
    await loadTelegramBindings({ silent: true });
  } catch (error) {
    showMessage("error", `绑定 Telegram chat 失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

async function disableTelegramBinding() {
  const chatId = telegramChatId();
  if (chatId === null) {
    return;
  }

  setButtonsBusy(true);
  showMessage("info", `正在禁用 Telegram chat ${chatId}。`);

  try {
    await fetchJson(`/telegram/bindings/${encodeURIComponent(chatId)}`, {
      method: "PATCH",
      headers: telegramHeaders({ json: true }),
      body: JSON.stringify({ is_allowed: false }),
    });
    showMessage("info", `Telegram chat ${chatId} 已禁用。`);
    await loadTelegramBindings({ silent: true });
  } catch (error) {
    showMessage("error", `禁用 Telegram chat 失败：${formatError(error)}`);
  } finally {
    setButtonsBusy(false);
  }
}

function executeCommand() {
  const command = elements.commandInput.value.trim().toLowerCase();
  if (!command) {
    showMessage("info", "可执行命令：ops、trend、warn、ready、history、tushare、radar、scan、fetch、signals、portfolio、reports、daily、weekly、score、telegram。");
    return;
  }

  const [name] = command.split(/\s+/);
  const commands = {
    ops: () => scrollToPanel("status-panel"),
    status: () => scrollToPanel("status-panel"),
    warn: () => {
      scrollToPanel("ops-warning-drilldown");
      loadOpsWarningDrilldown();
    },
    warning: () => {
      scrollToPanel("ops-warning-drilldown");
      loadOpsWarningDrilldown();
    },
    warnings: () => {
      scrollToPanel("ops-warning-drilldown");
      loadOpsWarningDrilldown();
    },
    opswarn: () => {
      scrollToPanel("ops-warning-drilldown");
      loadOpsWarningDrilldown();
    },
    history: () => {
      scrollToPanel("status-panel");
      loadOpsHistory();
    },
    opshistory: () => {
      scrollToPanel("status-panel");
      loadOpsHistory();
    },
    trend: () => {
      scrollToPanel("ops-trends");
      loadOpsTrends();
    },
    trends: () => {
      scrollToPanel("ops-trends");
      loadOpsTrends();
    },
    ready: () => {
      scrollToPanel("status-panel");
      loadOpsReadiness();
    },
    readiness: () => {
      scrollToPanel("status-panel");
      loadOpsReadiness();
    },
    tushare: () => {
      scrollToPanel("status-panel");
      loadTushareStatus();
    },
    provider: () => {
      scrollToPanel("status-panel");
      loadTushareStatus();
    },
    radar: refreshAll,
    refresh: refreshAll,
    scan: runRadarScan,
    fetch: fetchMinimalAkshare,
    akshare: fetchMinimalAkshare,
    signals: () => scrollToPanel("signals-panel"),
    signal: () => scrollToPanel("signals-panel"),
    detail: () => scrollToPanel("detail-panel"),
    portfolio: () => scrollToPanel("portfolio-panel"),
    holding: () => scrollToPanel("portfolio-panel"),
    watchlist: () => scrollToPanel("portfolio-panel"),
    reports: () => scrollToPanel("reports-panel"),
    report: () => scrollToPanel("reports-panel"),
    daily: () => loadPeriodicReport("daily"),
    weekly: () => loadPeriodicReport("weekly"),
    score: scoreSelectedSignal,
    analytics: () => scrollToPanel("analytics-panel"),
    summary: () => scrollToPanel("analytics-panel"),
    telegram: () => scrollToPanel("telegram-panel"),
    bindings: () => scrollToPanel("telegram-panel"),
    help: () =>
      showMessage(
        "info",
        "可执行命令：ops、trend、warn、ready、history、tushare、radar、scan、fetch、signals、portfolio、reports、daily、weekly、score、telegram。",
      ),
  };

  const action = commands[name];
  if (!action) {
    showMessage("error", `未知命令：${command}`);
    return;
  }

  action();
}

function scrollToPanel(panelId) {
  const target = document.querySelector(`#${panelId}`);
  if (!target) {
    return;
  }

  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.classList.add("panel-focus");
  window.setTimeout(() => target.classList.remove("panel-focus"), 900);
}

function renderReadyStatus(ok, payload) {
  const checks = payload?.checks || {};
  const cards = [
    {
      name: "API",
      status: ok ? payload.status : "not_ready",
      detail: payload?.service || "BaizeFinDB",
    },
    {
      name: "数据库",
      status: checks.database?.status || "unknown",
      detail: checks.database?.error || "PostgreSQL",
    },
    {
      name: "Redis",
      status: checks.redis?.status || "unknown",
      detail: checks.redis?.error || "缓存与队列",
    },
  ];

  elements.readyStatus.innerHTML = cards
    .map((card) => {
      const healthy = card.status === "ok" || card.status === "ready";
      return `
        <article class="status-card ${healthy ? "status-ok" : "status-fail"}">
          <strong>${escapeHtml(card.name)}</strong>
          <div>${escapeHtml(label(card.status))}</div>
          <div class="muted">${escapeHtml(card.detail)}</div>
        </article>
      `;
    })
    .join("");
}

function renderOpsOverview(overview) {
  const radar = overview?.radar || {};
  const server = overview?.server || {};
  const providerFetch = overview?.provider_fetch || {};
  const dataQuality = overview?.data_quality || {};
  const telegramPush = overview?.telegram_push || {};
  const modelCalls = overview?.model_calls || {};
  const alerts = Array.isArray(overview?.alerts) ? overview.alerts : [];
  const cards = [
    {
      name: "扫描新鲜度",
      status: radar.is_latest_scan_stale ? "fail" : "ok",
      value:
        radar.latest_scan_age_seconds === null || radar.latest_scan_age_seconds === undefined
          ? "暂无"
          : formatDuration(radar.latest_scan_age_seconds),
      detail: radar.is_latest_scan_stale ? "扫描可能停滞" : "扫描节奏正常",
    },
    {
      name: "扫描失败率",
      status: Number(radar.recent_scan_failure_count || 0) > 0 ? "fail" : "ok",
      value: formatRate(radar.recent_scan_failure_rate),
      detail: `近 24h ${radar.recent_scan_count ?? 0} 次 / 失败 ${radar.recent_scan_failure_count ?? 0}`,
    },
    {
      name: "告警",
      status: alerts.length > 0 ? "fail" : "ok",
      value: `${alerts.length} 条`,
      detail: formatOpsAlerts(alerts),
    },
    {
      name: "服务端",
      status:
        server.is_disk_space_low ||
        server.disk_error ||
        server.is_cpu_pressure_high ||
        server.cpu_error ||
        server.is_memory_pressure_high ||
        server.memory_error
          ? "fail"
          : "ok",
      value: formatOpsServerResources(server),
      detail: formatOpsServerDetail(server),
    },
    opsCountCard("Provider", providerFetch),
    opsCountCard("数据质量", dataQuality),
    opsCountCard("推送", telegramPush),
    opsCountCard("模型", modelCalls),
  ];
  elements.opsOverview.innerHTML = cards
    .map((card) => {
      return `
        <article class="status-card ${card.status === "ok" ? "status-ok" : "status-fail"}">
          <strong>${escapeHtml(card.name)}</strong>
          <div>${escapeHtml(card.value)}</div>
          <div class="muted">${escapeHtml(card.detail)}</div>
        </article>
      `;
    })
    .join("");
}

function formatOpsAlerts(alerts) {
  if (!alerts.length) {
    return "暂无告警";
  }

  return alerts.map((alert) => alert.message || alert.code || "未返回告警说明").join(" / ");
}

function formatOpsServerResources(server) {
  return [
    `磁盘 ${server.disk_error ? "不可用" : formatPercent(server.disk_free_percent)}`,
    `CPU ${server.cpu_error ? "不可用" : formatPercent(server.cpu_usage_percent)}`,
    `内存 ${server.memory_error ? "不可用" : formatPercent(server.memory_used_percent)}`,
  ].join(" / ");
}

function formatOpsServerDetail(server) {
  const parts = [`运行 ${formatDuration(server.process_uptime_seconds)}`];
  if (server.disk_error) {
    parts.push(`磁盘：${server.disk_error}`);
  } else {
    parts.push(
      `磁盘可用 ${formatBytes(server.disk_free_bytes)}/${formatBytes(server.disk_total_bytes)}`,
    );
  }

  if (server.cpu_error) {
    parts.push(`CPU：${server.cpu_error}`);
  } else {
    parts.push(`CPU 核心 ${server.cpu_logical_count ?? "-"}`);
  }

  if (server.memory_error) {
    parts.push(`内存：${server.memory_error}`);
  } else {
    parts.push(
      `内存可用 ${formatBytes(server.memory_available_bytes)}/${formatBytes(server.memory_total_bytes)}`,
    );
  }

  return parts.join(" / ");
}

function renderOpsUnavailable(reason) {
  elements.opsOverview.innerHTML = emptyState(reason);
}

function renderOpsHistory(history) {
  const events = Array.isArray(history?.recent_events) ? history.recent_events : [];
  const summary = Array.isArray(history?.failure_summary) ? history.failure_summary : [];
  const summaryText = summary.length
    ? summary
        .slice(0, 6)
        .map((item) => `${opsKindLabel(item.kind)} ${item.key || "unknown"}=${item.count ?? 0}`)
        .join(" / ")
    : "暂无异常汇总";

  const eventHtml = events.length
    ? events
        .map((event) => {
          const detail = event.detail ? `<div class="muted">${escapeHtml(event.detail)}</div>` : "";
          return `
            <article class="detail-card">
              <strong>${escapeHtml(opsKindLabel(event.kind))} #${escapeHtml(event.id)}</strong>
              <div>${escapeHtml(label(event.status))} / ${escapeHtml(formatDate(event.occurred_at))}</div>
              ${detail}
            </article>
          `;
        })
        .join("")
    : emptyState("暂无运维历史事件。");

  elements.opsHistory.innerHTML = `
    <article class="detail-card">
      <strong>异常汇总</strong>
      <div class="muted">${escapeHtml(summaryText)}</div>
    </article>
    ${eventHtml}
  `;
}

function renderOpsHistoryUnavailable(reason) {
  elements.opsHistory.innerHTML = emptyState(reason);
}

function renderOpsTrends(trends) {
  const buckets = Array.isArray(trends?.buckets) ? trends.buckets : [];
  if (buckets.length === 0) {
    elements.opsTrends.innerHTML = emptyState("后端 /ops/trends 未返回趋势桶。");
    return;
  }

  const latest = buckets[buckets.length - 1];
  const recentBuckets = buckets.slice(-6).reverse();
  const chartBuckets = buckets.slice(-12);
  elements.opsTrends.innerHTML = `
    <article class="detail-card">
      <div class="meta-row">
        <span class="badge">最近 ${escapeHtml(trends?.lookback_hours ?? 24)} 小时</span>
        <span class="badge">${escapeHtml(trends?.bucket_count ?? buckets.length)} 桶</span>
        <span class="badge">后端趋势计数</span>
      </div>
      <h3>最新桶</h3>
      <p class="summary">
        扫描 ${escapeHtml(latest.radar_scan_count ?? 0)} / 失败 ${escapeHtml(latest.radar_failure_count ?? 0)}
        · Provider ${escapeHtml(latest.provider_fetch_unhealthy_count ?? 0)}
        · 数据质量 ${escapeHtml(latest.data_quality_unhealthy_count ?? 0)}
        · 推送 ${escapeHtml(latest.telegram_push_unhealthy_count ?? 0)}
        · 模型 ${escapeHtml(latest.model_call_unhealthy_count ?? 0)}
      </p>
      <div class="muted">${escapeHtml(formatBucketRange(latest))}</div>
      ${renderOpsTrendChart(chartBuckets)}
    </article>
    <div class="ops-trend-table" role="table" aria-label="最近 OPS 趋势桶">
      <div class="ops-trend-row ops-trend-head" role="row">
        <span role="columnheader">时间桶</span>
        <span role="columnheader">扫描</span>
        <span role="columnheader">失败</span>
        <span role="columnheader">Provider</span>
        <span role="columnheader">数据质量</span>
        <span role="columnheader">推送</span>
        <span role="columnheader">模型</span>
      </div>
      ${recentBuckets.map(renderOpsTrendBucket).join("")}
    </div>
  `;
}

function renderOpsTrendChart(buckets) {
  const maxCount = Math.max(
    1,
    ...buckets.map((bucket) =>
      Math.max(
        bucketCount(bucket.radar_scan_count),
        bucketCount(bucket.radar_failure_count),
        bucketUnhealthyCount(bucket),
      ),
    ),
  );

  return `
    <div class="ops-trend-chart-wrap">
      <div
        class="ops-trend-chart"
        role="img"
        aria-label="OPS 趋势图，展示后端返回的扫描、失败和异常计数"
      >
        ${buckets.map((bucket) => renderOpsTrendChartBucket(bucket, maxCount)).join("")}
      </div>
      <div class="ops-trend-legend" aria-label="OPS 趋势图图例">
        <span><i class="trend-scan"></i>扫描</span>
        <span><i class="trend-failure"></i>失败</span>
        <span><i class="trend-unhealthy"></i>异常</span>
      </div>
    </div>
  `;
}

function renderOpsTrendChartBucket(bucket, maxCount) {
  const scanCount = bucketCount(bucket.radar_scan_count);
  const failureCount = bucketCount(bucket.radar_failure_count);
  const unhealthyCount = bucketUnhealthyCount(bucket);
  const labelText = `#${bucket.bucket_index ?? "-"}`;
  const titleText = `${formatBucketRange(bucket)}：扫描 ${scanCount}，失败 ${failureCount}，异常 ${unhealthyCount}`;

  return `
    <div class="ops-trend-chart-bucket" title="${escapeHtml(titleText)}">
      <div class="ops-trend-bars" aria-hidden="true">
        ${renderOpsTrendBar("trend-scan", scanCount, maxCount)}
        ${renderOpsTrendBar("trend-failure", failureCount, maxCount)}
        ${renderOpsTrendBar("trend-unhealthy", unhealthyCount, maxCount)}
      </div>
      <span>${escapeHtml(labelText)}</span>
    </div>
  `;
}

function renderOpsTrendBar(className, value, maxCount) {
  const height = Math.max(3, Math.round((bucketCount(value) / Math.max(1, maxCount)) * 100));
  return `
    <i
      class="${escapeHtml(className)}"
      style="height: ${escapeHtml(height)}%"
    ></i>
  `;
}

function renderOpsTrendBucket(bucket) {
  return `
    <div class="ops-trend-row" role="row">
      <span role="cell">${escapeHtml(formatBucketRange(bucket))}</span>
      <span role="cell">${escapeHtml(bucket.radar_scan_count ?? 0)}</span>
      <span role="cell">${escapeHtml(bucket.radar_failure_count ?? 0)}</span>
      <span role="cell">${escapeHtml(bucket.provider_fetch_unhealthy_count ?? 0)}</span>
      <span role="cell">${escapeHtml(bucket.data_quality_unhealthy_count ?? 0)}</span>
      <span role="cell">${escapeHtml(bucket.telegram_push_unhealthy_count ?? 0)}</span>
      <span role="cell">${escapeHtml(bucket.model_call_unhealthy_count ?? 0)}</span>
    </div>
  `;
}

function formatBucketRange(bucket) {
  return `${formatDate(bucket?.bucket_started_at)} - ${formatDate(bucket?.bucket_finished_at)}`;
}

function bucketUnhealthyCount(bucket) {
  return (
    bucketCount(bucket.provider_fetch_unhealthy_count) +
    bucketCount(bucket.data_quality_unhealthy_count) +
    bucketCount(bucket.telegram_push_unhealthy_count) +
    bucketCount(bucket.model_call_unhealthy_count)
  );
}

function bucketCount(value) {
  const count = Number(value);
  if (!Number.isFinite(count) || count < 0) {
    return 0;
  }

  return count;
}

function renderOpsTrendsUnavailable(reason) {
  elements.opsTrends.innerHTML = emptyState(reason);
}

function renderOpsReadiness(readiness) {
  const checks = Array.isArray(readiness?.checks) ? readiness.checks : [];
  const cards = [
    `
      <article class="detail-card">
        <strong>总体状态</strong>
        <div>${escapeHtml(readinessStatusLabel(readiness?.status || "unknown"))}</div>
        <div class="muted">最近 ${escapeHtml(readiness?.lookback_hours ?? 24)} 小时</div>
      </article>
    `,
    ...checks.map((check) => {
      return `
        <article class="detail-card">
          <strong>${escapeHtml(opsCheckLabel(check.name))}</strong>
          <div>${escapeHtml(readinessCheckLabel(check.status))}</div>
          <div class="muted">${escapeHtml(check.message || "未返回检查说明")}</div>
        </article>
      `;
    }),
  ];

  elements.opsReadiness.innerHTML = cards.join("");
}

function renderOpsReadinessUnavailable(reason) {
  elements.opsReadiness.innerHTML = emptyState(reason);
}

function renderOpsWarningDrilldown(readiness, overview, history) {
  const checks = Array.isArray(readiness?.checks) ? readiness.checks : [];
  const nonOkChecks = checks.filter((check) => check.status !== "ok");
  const alerts = Array.isArray(overview?.alerts) ? overview.alerts : [];
  const failureSummary = Array.isArray(history?.failure_summary) ? history.failure_summary.slice(0, 8) : [];
  const recentEvents = Array.isArray(history?.recent_events) ? history.recent_events.slice(0, 8) : [];

  elements.opsWarningDrilldown.innerHTML = `
    <article class="detail-card">
      <div class="meta-row">
        <span class="badge">${escapeHtml(readinessStatusLabel(readiness?.status || "unknown"))}</span>
        <span class="badge">最近 ${escapeHtml(readiness?.lookback_hours ?? 24)} 小时</span>
        <span class="badge">后端 readiness</span>
      </div>
      <h3>就绪状态</h3>
      <p class="summary">状态来自 /ops/readiness；前端只展示后端结果。</p>
    </article>
    <section class="ops-drilldown-section">
      <h4>非 OK 检查</h4>
      ${renderOpsWarningChecks(nonOkChecks)}
    </section>
    <section class="ops-drilldown-section">
      <h4>Overview alerts</h4>
      ${renderOpsWarningAlerts(alerts)}
    </section>
    <section class="ops-drilldown-section">
      <h4>Failure summary</h4>
      ${renderOpsWarningFailureSummary(failureSummary)}
    </section>
    <section class="ops-drilldown-section">
      <h4>Recent events</h4>
      ${renderOpsWarningEvents(recentEvents)}
    </section>
  `;
}

function renderOpsWarningChecks(checks) {
  if (checks.length === 0) {
    return emptyState("后端 readiness 未返回非 OK 检查。");
  }

  return checks
    .map((check) => {
      return `
        <article class="detail-card ${statusCardClass(check.status)}">
          <strong>${escapeHtml(opsCheckLabel(check.name))}</strong>
          <div>${escapeHtml(readinessCheckLabel(check.status))}</div>
          <div class="muted">${escapeHtml(check.message || "未返回检查说明")}</div>
        </article>
      `;
    })
    .join("");
}

function renderOpsWarningAlerts(alerts) {
  if (alerts.length === 0) {
    return emptyState("后端 overview 未返回 alerts。");
  }

  return alerts
    .slice(0, 8)
    .map((alert) => {
      return `
        <article class="detail-card status-warning">
          <strong>${escapeHtml(alert.code || "alert")}</strong>
          <div>${escapeHtml(label(alert.severity || "warning"))}</div>
          <div class="muted">${escapeHtml(alert.message || "未返回告警说明")}</div>
        </article>
      `;
    })
    .join("");
}

function renderOpsWarningFailureSummary(summary) {
  if (summary.length === 0) {
    return emptyState("后端 history 未返回 failure_summary。");
  }

  return summary
    .map((item) => {
      return `
        <article class="detail-card">
          <strong>${escapeHtml(opsKindLabel(item.kind))}</strong>
          <div>${escapeHtml(item.key || "unknown")}</div>
          <div class="muted">count=${escapeHtml(item.count ?? 0)}</div>
        </article>
      `;
    })
    .join("");
}

function renderOpsWarningEvents(events) {
  if (events.length === 0) {
    return emptyState("后端 history 未返回最近异常事件。");
  }

  return events
    .map((event) => {
      const detail = event.detail ? `<div class="muted">${escapeHtml(event.detail)}</div>` : "";
      return `
        <article class="detail-card">
          <strong>${escapeHtml(opsKindLabel(event.kind))} #${escapeHtml(event.id)}</strong>
          <div>${escapeHtml(label(event.status))} / ${escapeHtml(formatDate(event.occurred_at))}</div>
          ${detail}
        </article>
      `;
    })
    .join("");
}

function renderOpsWarningDrilldownUnavailable(reason) {
  elements.opsWarningDrilldown.innerHTML = emptyState(reason);
}

function renderTushareStatus(status, readiness) {
  const tokenConfigured = Boolean(status?.token_configured);
  const fetchEnabled = Boolean(status?.fetch_enabled);
  const endpointCount = Number(status?.endpoint_count ?? 0);
  const implementedCount = Number(status?.implemented_endpoint_count ?? 0);
  const readinessStatus = readiness?.status || "unknown";
  const schedulerReadyCount = Number(readiness?.scheduler_ready_endpoint_count ?? 0);
  const endpoints = Array.isArray(readiness?.endpoints) ? readiness.endpoints : [];
  const cards = [
    {
      name: "Tushare Token",
      status: tokenConfigured ? "ok" : "fail",
      value: tokenConfigured ? "已配置" : "未配置",
      detail: "前端不显示 token 原文",
    },
    {
      name: "Tushare 抓取",
      status: fetchEnabled ? "ok" : "fail",
      value: fetchEnabled ? "可手动抓取" : "未启用",
      detail: `已实现 ${implementedCount}/${endpointCount} 个端点`,
    },
    {
      name: "Tushare 状态",
      status: status?.status === "configured" ? "ok" : "fail",
      value: label(status?.status || "unknown"),
      detail: status?.message || "未返回状态说明",
    },
    {
      name: "调度准入",
      status: readinessStatus,
      value: label(readinessStatus),
      detail: `准入样例 ${schedulerReadyCount}/${implementedCount}；当前仍保持手动模式`,
    },
  ];

  const endpointCards = endpoints.map((endpoint) => {
    const failedChecks = (endpoint.checks || [])
      .filter((check) => check.status !== "ok")
      .map((check) => check.message)
      .slice(0, 2);
    const detail = failedChecks.length
      ? failedChecks.join("；")
      : `最近 ${label(endpoint.latest_status || "success")} / 质量 ${label(endpoint.latest_quality_status || "ok")}`;

    return {
      name: endpoint.title || endpoint.endpoint,
      status: endpoint.status,
      value: endpoint.scheduler_eligible ? "可评审调度" : "仅手动验证",
      detail,
    };
  });

  elements.tushareStatus.innerHTML = [...cards, ...endpointCards]
    .map((card) => {
      return `
        <article class="status-card ${statusCardClass(card.status)}">
          <strong>${escapeHtml(card.name)}</strong>
          <div>${escapeHtml(card.value)}</div>
          <div class="muted">${escapeHtml(card.detail)}</div>
        </article>
      `;
    })
    .join("");
}

function renderTushareUnavailable(reason) {
  elements.tushareStatus.innerHTML = emptyState(reason);
}

function statusCardClass(status) {
  const value = String(status || "").toLowerCase();
  if (["ok", "ready", "configured", "success"].includes(value)) {
    return "status-ok";
  }
  if (["warning", "degraded"].includes(value)) {
    return "status-warning";
  }
  return "status-fail";
}

function opsCountCard(name, summary) {
  const unhealthyCount = Number(summary?.unhealthy_count ?? 0);
  const totalCount = Number(summary?.total_count ?? 0);
  return {
    name,
    status: unhealthyCount > 0 ? "fail" : "ok",
    value: `异常 ${unhealthyCount}`,
    detail: `近 24h ${totalCount} 条 / 最新 ${label(summary?.latest_status)}`,
  };
}

function opsKindLabel(value) {
  const labels = {
    radar_scan: "雷达",
    provider_fetch: "Provider",
    data_quality: "数据质量",
    telegram_push: "推送",
    model_call: "模型",
  };
  return labels[value] || value || "-";
}

function opsCheckLabel(value) {
  const labels = {
    server_disk: "服务端磁盘",
    radar_freshness: "雷达新鲜度",
    radar_failure_rate: "扫描失败率",
    provider_fetch: "Provider",
    data_quality: "数据质量",
    telegram_push: "推送",
    model_calls: "模型",
  };
  return labels[value] || value || "-";
}

function readinessStatusLabel(value) {
  const labels = {
    ready: "可运行",
    warning: "有警告",
    blocked: "阻断",
  };
  return labels[value] || value || "-";
}

function readinessCheckLabel(value) {
  const labels = {
    ok: "正常",
    warning: "警告",
    fail: "失败",
  };
  return labels[value] || value || "-";
}

function renderPriorityCounts(counts) {
  elements.priorityCounts.innerHTML = ["P0", "P1", "P2"]
    .map((priority) => {
      const value = counts[priority] ?? 0;
      return `
        <article class="priority-card">
          <strong>${priority}</strong>
          <div class="priority-number priority-${priority.toLowerCase()}">${escapeHtml(value)}</div>
          <div class="muted">后端返回计数</div>
        </article>
      `;
    })
    .join("");
}

function renderLifecycleCounts(counts) {
  const visibleStages = LIFECYCLE_ORDER.filter((stage) => Number(counts[stage] ?? 0) > 0);
  const stages = visibleStages.length > 0 ? visibleStages : LIFECYCLE_ORDER.slice(0, 3);
  elements.lifecycleCounts.innerHTML = stages
    .map((stage) => {
      const value = counts[stage] ?? 0;
      return `
        <article class="priority-card">
          <strong>${escapeHtml(label(stage))}</strong>
          <div class="priority-number">${escapeHtml(value)}</div>
          <div class="muted">生命周期计数</div>
        </article>
      `;
    })
    .join("");
}

function renderMarketSentiment(sentiment) {
  if (!sentiment || typeof sentiment !== "object") {
    elements.marketSentiment.innerHTML = emptyState("暂无市场情绪摘要。");
    return;
  }

  const cards = [
    ["涨停", sentiment.limit_up_count ?? 0, "涨停池"],
    ["跌停", sentiment.limit_down_count ?? 0, "跌停池"],
    ["炸板", sentiment.broken_limit_up_count ?? 0, "炸板池"],
    ["净压力", sentiment.net_limit_pressure ?? 0, "涨停-跌停-炸板"],
    ["偏向", sentimentBiasLabel(sentiment.sentiment_bias), "后端判定"],
  ];
  elements.marketSentiment.innerHTML = cards
    .map(([name, value, note]) => {
      return `
        <article class="priority-card">
          <strong>${escapeHtml(name)}</strong>
          <div class="priority-number">${escapeHtml(value)}</div>
          <div class="muted">${escapeHtml(note)}</div>
        </article>
      `;
    })
    .join("");
}

function renderLatestScan(scan) {
  if (!scan) {
    elements.latestScan.innerHTML = emptyState("暂无扫描记录。先触发 AKShare 最小采集，再运行雷达扫描。");
    return;
  }

  const summary = scan.summary || {};
  elements.latestScan.innerHTML = `
    <div class="meta-row">
      <span class="badge">批次 #${escapeHtml(scan.id)}</span>
      <span class="badge">${escapeHtml(label(scan.status))}</span>
      <span class="badge">信号 ${escapeHtml(summary.signal_count ?? scan.signals?.length ?? 0)}</span>
    </div>
    <p class="summary">开始：${escapeHtml(formatDate(scan.started_at))}</p>
    <p class="summary">完成：${escapeHtml(formatDate(scan.finished_at))}</p>
    ${
      scan.error_message
        ? `<p class="summary">错误：${escapeHtml(scan.error_message)}</p>`
        : ""
    }
  `;
}

function renderStockBacktraceEvidences(evidences) {
  if (!Array.isArray(evidences) || evidences.length === 0) {
    elements.stockBacktraceEvidences.innerHTML = emptyState("暂无个股回推证据。");
    return;
  }

  elements.stockBacktraceEvidences.innerHTML = evidences
    .map((evidence) => {
      return `
        <article class="backtrace-card">
          <div class="meta-row">
            <span class="badge ${priorityBadgeClass(evidence.priority)}">${escapeHtml(evidence.priority || "-")}</span>
            <span class="badge">${escapeHtml(label(evidence.lifecycle_stage))}</span>
            <span class="badge">${escapeHtml(label(evidence.subject_type))}</span>
          </div>
          <h3>${escapeHtml(evidence.stock_name || "未命名个股")} ${escapeHtml(formatSignedPercent(evidence.stock_pct_change))}</h3>
          <p class="summary">反推主题：${escapeHtml(evidence.subject_name || "未命名主题")}</p>
          <p class="muted">${escapeHtml(evidence.evidence_label || "后端雷达指标派生")}</p>
        </article>
      `;
    })
    .join("");
}

function renderCurrentSubjects(subjects) {
  if (subjects.length === 0) {
    elements.currentSubjects.innerHTML = emptyState("暂无当前主题。运行扫描后这里会展示后端去重结果。");
    return;
  }

  elements.currentSubjects.innerHTML = subjects
    .map((subject) => {
      const signal = subject.latest_signal || {};
      return `
        <article class="subject-card">
          <div class="meta-row">
            <span class="badge ${priorityBadgeClass(signal.priority)}">${escapeHtml(signal.priority || "-")}</span>
            <span class="badge">${escapeHtml(label(signal.lifecycle_stage))}</span>
            <span class="badge">${escapeHtml(label(subject.subject_type))}</span>
          </div>
          <h3>${escapeHtml(subject.subject_name || signal.subject_name || "未命名主题")}</h3>
          <p class="summary">${escapeHtml(signal.summary || "暂无摘要。")}</p>
        </article>
      `;
    })
    .join("");
}

function renderSignals(signals) {
  if (!Array.isArray(signals) || signals.length === 0) {
    elements.signalsList.innerHTML = emptyState("暂无信号。可先触发 AKShare 最小采集，再运行雷达扫描。");
    return;
  }

  elements.signalsList.innerHTML = signals
    .map((signal) => {
      return `
        <article class="signal-card">
          <div>
            <div class="meta-row">
              <span class="badge ${priorityBadgeClass(signal.priority)}">${escapeHtml(signal.priority)}</span>
              <span class="badge">${escapeHtml(label(signal.lifecycle_stage))}</span>
              <span class="badge">${escapeHtml(label(signal.review_status))}</span>
              <span class="badge">证据 ${escapeHtml(signal.evidence_count)}</span>
            </div>
            <h3>${escapeHtml(signal.title || signal.subject_name)}</h3>
            <p class="summary">${escapeHtml(signal.summary || "暂无摘要。")}</p>
            <p class="muted">${escapeHtml(signal.subject_name)} · ${escapeHtml(formatDate(signal.created_at))}</p>
          </div>
          <button class="secondary" type="button" data-signal-id="${escapeHtml(signal.id)}">查看详情</button>
        </article>
      `;
    })
    .join("");

  elements.signalsList.querySelectorAll("[data-signal-id]").forEach((button) => {
    button.addEventListener("click", () => loadSignalDetail(button.dataset.signalId));
  });
}

function renderSignalDetail(detail, analysis = null, analysisError = null) {
  const evidences = detail.evidences || [];
  elements.signalDetail.classList.remove("empty-state");
  elements.signalDetail.innerHTML = `
    <article class="detail-card">
      <div class="meta-row">
        <span class="badge ${priorityBadgeClass(detail.priority)}">${escapeHtml(detail.priority)}</span>
        <span class="badge">${escapeHtml(label(detail.lifecycle_stage))}</span>
        <span class="badge">${escapeHtml(label(detail.review_status))}</span>
      </div>
      <h3>${escapeHtml(detail.title || detail.subject_name)}</h3>
      <p class="summary">${escapeHtml(detail.summary || "暂无摘要。")}</p>
      <div class="report-actions">
        <button type="button" data-report-type="quick">生成 Quick Report</button>
        <button type="button" data-report-type="standard">生成 Standard Report</button>
        <button type="button" data-deep-report="true">生成 Deep Report</button>
        <button type="button" data-score-signal="true">生成综合评分</button>
      </div>
    </article>
    <div class="detail-grid">
      <div class="kv"><span>信号 ID</span>${escapeHtml(detail.id)}</div>
      <div class="kv"><span>批次 ID</span>${escapeHtml(detail.batch_id)}</div>
      <div class="kv"><span>主题</span>${escapeHtml(detail.subject_name)}</div>
      <div class="kv"><span>创建时间</span>${escapeHtml(formatDate(detail.created_at))}</div>
    </div>
    <section>
      <h3>后端指标</h3>
      <pre id="metrics-json"></pre>
    </section>
    <section>
      <h3>信号分析摘要</h3>
      ${renderSignalAnalysisBrief(analysis, analysisError)}
    </section>
    <section>
      <h3>证据摘要</h3>
      <div class="evidence-list">
        ${
          evidences.length === 0
            ? emptyState("暂无证据摘要。")
            : evidences
                .map((evidence) => {
                  return `
                    <article class="evidence-card">
                      <div class="meta-row">
                        <span class="badge">${escapeHtml(label(evidence.evidence_type))}</span>
                        <span class="badge">${escapeHtml(label(evidence.freshness))}</span>
                        <span class="badge">${escapeHtml(label(evidence.public_share_policy))}</span>
                      </div>
                      <p class="summary">${escapeHtml(evidence.normalized_summary || "暂无摘要。")}</p>
                    </article>
                  `;
                })
                .join("")
        }
      </div>
    </section>
  `;

  document.querySelector("#metrics-json").textContent = JSON.stringify(detail.metrics || {}, null, 2);
  elements.signalDetail.querySelectorAll("[data-report-type]").forEach((button) => {
    button.addEventListener("click", () => createReport(button.dataset.reportType));
  });
  elements.signalDetail.querySelector("[data-deep-report]").addEventListener("click", createDeepReport);
  elements.signalDetail.querySelector("[data-score-signal]").addEventListener("click", scoreSelectedSignal);
}

function renderSignalAnalysisBrief(analysis, analysisError) {
  if (analysisError) {
    return emptyState(`分析摘要暂不可用：${formatError(analysisError)}`);
  }

  if (!analysis) {
    return emptyState("后端暂未返回分析摘要。");
  }

  const evidenceSummary = analysis.evidence_summary || {};
  const reviewSummary = analysis.review_summary || {};
  return `
    <article class="analysis-brief detail-card">
      <div class="meta-row">
        <span class="badge ${priorityBadgeClass(analysis.priority)}">${escapeHtml(analysis.priority || "-")}</span>
        <span class="badge">${escapeHtml(label(analysis.lifecycle_stage))}</span>
        <span class="badge">${escapeHtml(label(analysis.review_status))}</span>
        <span class="badge">后端摘要</span>
      </div>
      <h3>${escapeHtml(analysis.analysis_title || "信号研究摘要")}</h3>
      ${renderAnalysisList("Key Points", analysis.key_points)}
      ${renderMetricHighlights(analysis.metric_highlights || [])}
      ${renderAnalysisList("Risk Flags", analysis.risk_flags)}
      ${renderEvidenceSummary(evidenceSummary)}
      ${renderReviewSummary(reviewSummary)}
      ${renderAnalysisList("Next Actions", analysis.next_actions)}
    </article>
  `;
}

function renderAnalysisList(title, items) {
  const values = Array.isArray(items) ? items.filter(Boolean).slice(0, 8) : [];
  if (values.length === 0) {
    return `
      <section class="analysis-section">
        <h4>${escapeHtml(title)}</h4>
        ${emptyState("后端未返回该项。")}
      </section>
    `;
  }

  return `
    <section class="analysis-section">
      <h4>${escapeHtml(title)}</h4>
      <ul class="analysis-list">
        ${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </section>
  `;
}

function renderMetricHighlights(highlights) {
  const values = Array.isArray(highlights) ? highlights.slice(0, 6) : [];
  if (values.length === 0) {
    return renderAnalysisList("Metric Highlights", []);
  }

  return `
    <section class="analysis-section">
      <h4>Metric Highlights</h4>
      <div class="analysis-grid">
        ${values
          .map((item) => {
            return `
              <article class="analysis-metric">
                <strong>${escapeHtml(label(item.label))}</strong>
                <div>${escapeHtml(item.value || "-")}</div>
                <p class="muted">${escapeHtml(item.interpretation || "后端未返回说明。")}</p>
              </article>
            `;
          })
          .join("")}
      </div>
    </section>
  `;
}

function renderEvidenceSummary(summary) {
  const evidenceTypes = Array.isArray(summary.evidence_types) ? summary.evidence_types : [];
  const freshnessLabels = Array.isArray(summary.freshness_labels) ? summary.freshness_labels : [];
  const confidenceLabels = Array.isArray(summary.confidence_labels)
    ? summary.confidence_labels
    : [];
  const summaries = Array.isArray(summary.summaries) ? summary.summaries : [];

  return `
    <section class="analysis-section">
      <h4>Evidence Summary</h4>
      <div class="meta-row">
        <span class="badge">证据 ${escapeHtml(summary.evidence_count ?? 0)}</span>
        ${evidenceTypes.map((item) => `<span class="badge">${escapeHtml(label(item))}</span>`).join("")}
        ${freshnessLabels.map((item) => `<span class="badge">${escapeHtml(label(item))}</span>`).join("")}
        ${confidenceLabels.map((item) => `<span class="badge">confidence ${escapeHtml(label(item))}</span>`).join("")}
      </div>
      ${renderAnalysisList("Evidence Notes", summaries)}
    </section>
  `;
}

function renderReviewSummary(summary) {
  const reasons = Array.isArray(summary.reasons) ? summary.reasons : [];
  return `
    <section class="analysis-section">
      <h4>Review Summary</h4>
      <div class="meta-row">
        <span class="badge">${escapeHtml(label(summary.status))}</span>
        <span class="badge">${summary.human_review_required ? "需要人工复核" : "无需人工复核"}</span>
        ${
          summary.latest_review_id === null || summary.latest_review_id === undefined
            ? ""
            : `<span class="badge">review #${escapeHtml(summary.latest_review_id)}</span>`
        }
      </div>
      ${renderAnalysisList("Review Reasons", reasons)}
    </section>
  `;
}

function renderHoldings(holdings) {
  if (!Array.isArray(holdings) || holdings.length === 0) {
    elements.holdingsList.innerHTML = emptyState("暂无手动持仓。");
    return;
  }

  elements.holdingsList.innerHTML = holdings
    .map((holding) => {
      return `
        <article class="portfolio-card">
          <div>
            <div class="meta-row">
              <span class="badge">${escapeHtml(holding.market)}</span>
              <span class="badge">仓位 ${escapeHtml(formatRatio(holding.position_ratio))}</span>
              <span class="badge">提醒 ${escapeHtml(enabledLabel(holding.alert_enabled))}</span>
            </div>
            <h3>${escapeHtml(holding.instrument_code)} ${escapeHtml(holding.instrument_name)}</h3>
            <p class="summary">${escapeHtml(holding.note || "暂无备注。")}</p>
            <p class="muted">成本：${escapeHtml(formatOptionalNumber(holding.cost_price))}</p>
          </div>
          <button class="secondary" type="button" data-holding-id="${escapeHtml(holding.id)}">删除</button>
        </article>
      `;
    })
    .join("");

  elements.holdingsList.querySelectorAll("[data-holding-id]").forEach((button) => {
    button.addEventListener("click", () => deleteHolding(button.dataset.holdingId));
  });
}

function renderWatchlistItems(items) {
  if (!Array.isArray(items) || items.length === 0) {
    elements.watchlistList.innerHTML = emptyState("暂无自选关注。");
    return;
  }

  elements.watchlistList.innerHTML = items
    .map((item) => {
      return `
        <article class="portfolio-card">
          <div>
            <div class="meta-row">
              <span class="badge">${escapeHtml(item.market)}</span>
              <span class="badge">提醒 ${escapeHtml(enabledLabel(item.alert_enabled))}</span>
            </div>
            <h3>${escapeHtml(item.instrument_code)} ${escapeHtml(item.instrument_name)}</h3>
            <p class="summary">${escapeHtml(item.note || "暂无备注。")}</p>
          </div>
          <button class="secondary" type="button" data-watchlist-id="${escapeHtml(item.id)}">删除</button>
        </article>
      `;
    })
    .join("");

  elements.watchlistList.querySelectorAll("[data-watchlist-id]").forEach((button) => {
    button.addEventListener("click", () => deleteWatchlistItem(button.dataset.watchlistId));
  });
}

function renderReports(reports) {
  if (!Array.isArray(reports) || reports.length === 0) {
    elements.reportsList.innerHTML = emptyState(
      "暂无报告。选择信号后可生成 quick、standard 或确认后的 deep report。",
    );
    return;
  }

  elements.reportsList.innerHTML = reports
    .map((report) => {
      return `
        <article class="report-card">
          <div class="meta-row">
            <span class="badge">${escapeHtml(report.report_type)}</span>
            <span class="badge">${escapeHtml(label(report.status))}</span>
            <span class="badge">${escapeHtml(report.suggestion_label)}</span>
          </div>
          <h3>#${escapeHtml(report.id)} ${escapeHtml(report.title)}</h3>
          <p class="summary">${escapeHtml(report.summary)}</p>
          <details>
            <summary>查看正文</summary>
            <pre>${escapeHtml(report.body_markdown)}</pre>
          </details>
        </article>
      `;
    })
    .join("");
}

function renderPeriodicReport(report) {
  const subjects = Array.isArray(report.top_subjects) ? report.top_subjects : [];
  const counts = report.priority_counts || {};
  elements.periodicReport.innerHTML = `
    <article class="report-card">
      <div class="meta-row">
        <span class="badge">${escapeHtml(report.report_type === "weekly" ? "周报" : "日报")}</span>
        <span class="badge">信号 ${escapeHtml(report.signal_count ?? 0)}</span>
        <span class="badge">报告 ${escapeHtml(report.report_count ?? 0)}</span>
        <span class="badge">推送 ${escapeHtml(report.push_count ?? 0)}</span>
      </div>
      <h3>${escapeHtml(report.report_type === "weekly" ? "周报汇总" : "日报汇总")}</h3>
      <p class="summary">${escapeHtml(report.summary || "暂无摘要。")}</p>
      <div class="meta-row">
        <span class="badge badge-p0">P0 ${escapeHtml(counts.P0 ?? 0)}</span>
        <span class="badge badge-p1">P1 ${escapeHtml(counts.P1 ?? 0)}</span>
        <span class="badge badge-p2">P2 ${escapeHtml(counts.P2 ?? 0)}</span>
      </div>
      ${
        subjects.length === 0
          ? emptyState("暂无重点主题。")
          : subjects
              .map((subject) => {
                return `
                  <article class="subject-card compact-subject">
                    <div class="meta-row">
                      <span class="badge ${priorityBadgeClass(subject.priority)}">${escapeHtml(subject.priority)}</span>
                      <span class="badge">${escapeHtml(label(subject.lifecycle_stage))}</span>
                      <span class="badge">${escapeHtml(label(subject.review_status))}</span>
                    </div>
                    <h3>#${escapeHtml(subject.signal_id)} ${escapeHtml(subject.subject_name)}</h3>
                  </article>
                `;
              })
              .join("")
      }
    </article>
  `;
}

function renderScores(scoreRun) {
  const records = Array.isArray(scoreRun.records) ? scoreRun.records : [];
  if (records.length === 0) {
    elements.scoreRun.innerHTML = emptyState("暂无评分记录。");
    return;
  }

  elements.scoreRun.innerHTML = `
    <article class="report-card">
      <div class="meta-row">
        <span class="badge">信号 #${escapeHtml(scoreRun.signal_id)}</span>
        <span class="badge">后端评分</span>
      </div>
      <h3>1d / 3d / 5d / 10d 综合评分</h3>
      <div class="score-grid">
        ${records
          .map((record) => {
            const scoreBand = record.details?.score_band;
            return `
              <article class="score-card">
                <strong>${escapeHtml(record.window_days)}d</strong>
                <div class="score-number">${escapeHtml(formatScore(record.composite_score))}</div>
                <div class="meta-row">
                  <span class="badge">${escapeHtml(label(record.score_status))}</span>
                  ${scoreBand ? `<span class="badge">${escapeHtml(label(scoreBand))}</span>` : ""}
                </div>
              </article>
            `;
          })
          .join("")}
      </div>
      ${renderScoreComponents(records[0])}
      <p class="summary">评分综合优先级、生命周期、审查、证据、连续性、数据质量和时效性；不是价格回测或交易建议。</p>
    </article>
  `;
}

function renderScoreComponents(record) {
  const components = record?.components && typeof record.components === "object" ? record.components : {};
  const rows = SCORE_COMPONENT_ORDER.filter((name) => components[name] !== undefined);
  if (rows.length === 0) {
    return "";
  }

  return `
    <div class="score-components">
      ${rows
        .map((name) => {
          return `
            <div class="score-component">
              <span>${escapeHtml(label(name))}</span>
              <strong>${escapeHtml(formatScore(components[name]))}</strong>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderTelegramBindings(bindings, status = null) {
  const statusSummary = renderTelegramBindingStatus(status);
  if (!Array.isArray(bindings) || bindings.length === 0) {
    const emptyMessage = status?.require_binding === true
      ? "暂无数据库绑定。严格绑定模式已开启，请先写入 active 绑定。"
      : "暂无数据库绑定。未配置环境白名单时，本地 webhook 仍保持开放模式。";
    elements.telegramBindingsList.innerHTML = `${statusSummary}${emptyState(emptyMessage)}`;
    return;
  }

  const bindingCards = bindings
    .map((binding) => {
      const isAllowed = binding.is_allowed === true;
      return `
        <article class="telegram-binding-card">
          <div class="meta-row">
            <span class="badge">${escapeHtml(isAllowed ? "允许" : "禁用")}</span>
            <span class="badge">${escapeHtml(binding.source || "manual")}</span>
          </div>
          <h3>chat=${escapeHtml(binding.chat_id)}</h3>
          <p class="summary">user_key=${escapeHtml(binding.user_key || "-")}</p>
          <p class="muted">备注：${escapeHtml(binding.display_name || "无")}</p>
        </article>
      `;
    })
    .join("");
  elements.telegramBindingsList.innerHTML = `${statusSummary}${bindingCards}`;
}

function renderTelegramBindingStatus(status) {
  const payload = status && typeof status === "object" ? status : {};
  const strictLabel = payload.require_binding === true ? "已开启" : "未开启";
  return `
    <article class="telegram-binding-card">
      <div class="meta-row">
        <span class="badge">严格绑定模式</span>
        <span class="badge">${escapeHtml(strictLabel)}</span>
      </div>
      <p class="summary">
        环境白名单数量 ${escapeHtml(payload.allowed_chat_count ?? 0)}
        / 数据库绑定 ${escapeHtml(payload.binding_count ?? 0)}
        / active ${escapeHtml(payload.active_binding_count ?? 0)}
      </p>
      <p class="muted">仅展示后端汇总计数，不展示原始环境值、bot token 或 webhook secret。</p>
    </article>
  `;
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    ...options,
  });
  const payload = await readPayload(response);

  if (!response.ok) {
    const error = new Error(response.statusText || "request failed");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

async function postJson(path, payload = null) {
  const options = {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  };

  if (payload !== null) {
    options.body = JSON.stringify(payload);
  }

  return fetchJson(path, options);
}

async function readPayload(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function setButtonsBusy(isBusy) {
  elements.refreshButton.disabled = isBusy;
  elements.runScanButton.disabled = isBusy;
  elements.fetchAkshareButton.disabled = isBusy;
  elements.dailyReportButton.disabled = isBusy;
  elements.weeklyReportButton.disabled = isBusy;
  elements.scoreSignalButton.disabled = isBusy;
  elements.telegramRefreshButton.disabled = isBusy;
  elements.telegramDisableButton.disabled = isBusy;
  elements.commandRunButton.disabled = isBusy;
  elements.holdingForm.querySelector("button").disabled = isBusy;
  elements.watchlistForm.querySelector("button").disabled = isBusy;
  elements.telegramBindingForm.querySelector("button[type='submit']").disabled = isBusy;
}

function showMessage(type, text) {
  elements.actionMessage.className = `message visible ${type}`;
  elements.actionMessage.textContent = text;
}

function emptyState(text) {
  return `<div class="empty-state">${escapeHtml(text)}</div>`;
}

function priorityBadgeClass(priority) {
  return `badge-${String(priority || "").toLowerCase()}`;
}

function label(value) {
  const labels = {
    ready: "就绪",
    warning: "有警告",
    not_ready: "未就绪",
    ok: "正常",
    unknown: "未知",
    configured: "已配置",
    not_configured: "未配置",
    running: "运行中",
    success: "成功",
    failure: "失败",
    failed: "失败",
    degraded: "降级",
    fallback: "降级切换",
    sent: "已发送",
    preview: "预览",
    skipped: "跳过",
    no_data: "暂无数据",
    candidate: "候选",
    approved: "已通过",
    blocked: "已阻断",
    needs_human_review: "需人工复核",
    generated: "已生成",
    pending_window: "窗口未结束",
    strong_attention: "强关注",
    watch: "观察",
    weak_watch: "弱观察",
    low_signal_quality: "低质量",
    priority: "优先级",
    lifecycle: "生命周期",
    review: "审查",
    evidence: "证据",
    continuity: "连续性",
    data_quality: "数据质量",
    timeliness: "时效性",
    ignition: "点火",
    developing: "发酵",
    divergence: "分歧",
    returning: "回流",
    climax: "高潮",
    fading: "退潮",
    extinguished: "熄火",
    sector_concept: "板块/概念",
    ok_to_share: "可分享摘要",
    internal_only: "内部查看",
  };

  return labels[value] || String(value ?? "-");
}

function sentimentBiasLabel(value) {
  const labels = {
    positive: "偏强",
    negative: "偏弱",
    mixed: "分歧",
    unknown: "未知",
  };

  return labels[value] || label(value);
}

function portfolioQuery() {
  const userKey = elements.portfolioUserKey.value.trim() || "default";
  return `?user_key=${encodeURIComponent(userKey)}`;
}

function periodicQuery(period) {
  return `${portfolioQuery()}&period=${encodeURIComponent(period)}`;
}

function formPayload(form) {
  const formData = new FormData(form);
  const payload = {};

  for (const [key, value] of formData.entries()) {
    const text = String(value).trim();
    if (!text) {
      continue;
    }

    if (key === "cost_price" || key === "position_ratio") {
      payload[key] = Number(text);
    } else {
      payload[key] = text;
    }
  }

  return payload;
}

function telegramBindingPayload() {
  const chatId = telegramChatId();
  if (chatId === null) {
    return null;
  }

  const formData = new FormData(elements.telegramBindingForm);
  const userKey = String(formData.get("user_key") || "").trim() || `telegram-${chatId}`;
  return {
    chat_id: chatId,
    user_key: userKey,
    display_name: String(formData.get("display_name") || "").trim(),
    is_allowed: true,
  };
}

function telegramChatId() {
  const rawValue = String(new FormData(elements.telegramBindingForm).get("chat_id") || "").trim();
  const chatId = Number(rawValue);
  if (!rawValue || !Number.isInteger(chatId) || chatId === 0) {
    showMessage("error", "Telegram Chat ID 必须是非零整数。");
    return null;
  }

  return chatId;
}

function telegramHeaders(options = {}) {
  const headers = { Accept: "application/json" };
  if (options.json) {
    headers["Content-Type"] = "application/json";
  }

  const secret = elements.telegramSecret.value.trim();
  if (secret) {
    headers["X-Telegram-Bot-Api-Secret-Token"] = secret;
  }

  return headers;
}

function enabledLabel(value) {
  return value ? "开启" : "关闭";
}

function formatRatio(value) {
  if (value === null || value === undefined) {
    return "未填";
  }

  return `${Math.round(Number(value) * 100)}%`;
}

function formatOptionalNumber(value) {
  if (value === null || value === undefined) {
    return "未填";
  }

  return Number(value).toString();
}

function formatSignedPercent(value) {
  const numberValue = Number(value);
  if (Number.isNaN(numberValue)) {
    return "-";
  }

  const text = Number.isInteger(numberValue)
    ? String(numberValue)
    : numberValue.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return `${numberValue > 0 ? "+" : ""}${text}%`;
}

function formatScore(value) {
  const score = Number(value);
  if (Number.isNaN(score)) {
    return "-";
  }

  return score.toFixed(2);
}

function formatRate(value) {
  const rate = Number(value);
  if (Number.isNaN(rate)) {
    return "-";
  }

  return `${(rate * 100).toFixed(1).replace(/\.0$/, "")}%`;
}

function formatPercent(value) {
  const percent = Number(value);
  if (Number.isNaN(percent)) {
    return "-";
  }

  return `${percent.toFixed(1).replace(/\.0$/, "")}%`;
}

function formatDuration(value) {
  const seconds = Number(value);
  if (Number.isNaN(seconds)) {
    return "-";
  }

  if (seconds < 60) {
    return `${Math.max(0, Math.round(seconds))} 秒`;
  }

  if (seconds < 3600) {
    return `${Math.round(seconds / 60)} 分钟`;
  }

  return `${(seconds / 3600).toFixed(1).replace(/\.0$/, "")} 小时`;
}

function formatBytes(value) {
  const bytes = Number(value);
  if (Number.isNaN(bytes)) {
    return "-";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = Math.max(0, bytes);
  let unitIndex = 0;
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024;
    unitIndex += 1;
  }

  const precision = amount >= 10 || unitIndex === 0 ? 0 : 1;
  return `${amount.toFixed(precision).replace(/\.0$/, "")} ${units[unitIndex]}`;
}

function formatDate(value) {
  if (!value) {
    return "未返回";
  }

  try {
    return new Intl.DateTimeFormat("zh-CN", {
      dateStyle: "short",
      timeStyle: "medium",
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}

function formatError(error) {
  const detail = error?.payload?.detail || error?.payload?.error_message;
  if (detail) {
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }

  if (error?.status) {
    return `HTTP ${error.status}`;
  }

  return error?.message || "未知错误";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
