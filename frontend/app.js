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
  actionMessage: document.querySelector("#action-message"),
  priorityCounts: document.querySelector("#priority-counts"),
  latestScan: document.querySelector("#latest-scan"),
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
  showMessage("info", "正在刷新 API 状态、雷达总览和信号列表。");

  const isReady = await loadReadyStatus();
  if (isReady) {
    await Promise.all([
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
    return false;
  }
}

async function loadOverview() {
  try {
    const overview = await fetchJson("/radar/overview");
    renderPriorityCounts(overview.priority_counts || {});
    renderLatestScan(overview.latest_scan);
    renderCurrentSubjects(overview.current_subjects || []);
  } catch (error) {
    elements.priorityCounts.innerHTML = emptyState(`雷达总览暂不可用：${formatError(error)}`);
    elements.latestScan.innerHTML = emptyState("确认数据库迁移和依赖服务后再刷新。");
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
    const bindings = await fetchJson("/telegram/bindings?limit=50", {
      headers: telegramHeaders(),
    });
    renderTelegramBindings(bindings);
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
  elements.priorityCounts.innerHTML = emptyState(reason);
  elements.latestScan.innerHTML = emptyState("依赖服务恢复后，先触发采集或运行雷达扫描。");
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
    const detail = await fetchJson(`/radar/signals/${signalId}`);
    renderSignalDetail(detail);
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
    showMessage("info", "可执行命令：radar、scan、fetch、signals、portfolio、reports、daily、weekly、score、telegram。");
    return;
  }

  const [name] = command.split(/\s+/);
  const commands = {
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
        "可执行命令：radar、scan、fetch、signals、portfolio、reports、daily、weekly、score、telegram。",
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

function renderSignalDetail(detail) {
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
  elements.signalDetail.querySelector("[data-score-signal]").addEventListener("click", scoreSelectedSignal);
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
    elements.reportsList.innerHTML = emptyState("暂无报告。选择信号后可生成 quick 或 standard report。");
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

function renderTelegramBindings(bindings) {
  if (!Array.isArray(bindings) || bindings.length === 0) {
    elements.telegramBindingsList.innerHTML = emptyState("暂无数据库绑定。未配置环境白名单时，本地 webhook 仍保持开放模式。");
    return;
  }

  elements.telegramBindingsList.innerHTML = bindings
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
    not_ready: "未就绪",
    ok: "正常",
    unknown: "未知",
    running: "运行中",
    success: "成功",
    failure: "失败",
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

function formatScore(value) {
  const score = Number(value);
  if (Number.isNaN(score)) {
    return "-";
  }

  return score.toFixed(2);
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
