const state = {
  selectedSignalId: null,
};

const elements = {
  refreshButton: document.querySelector("#refresh-button"),
  runScanButton: document.querySelector("#run-scan-button"),
  fetchAkshareButton: document.querySelector("#fetch-akshare-button"),
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
};

document.addEventListener("DOMContentLoaded", () => {
  elements.refreshButton.addEventListener("click", refreshAll);
  elements.runScanButton.addEventListener("click", runRadarScan);
  elements.fetchAkshareButton.addEventListener("click", fetchMinimalAkshare);
  elements.portfolioUserKey.addEventListener("change", loadPortfolio);
  elements.holdingForm.addEventListener("submit", addHolding);
  elements.watchlistForm.addEventListener("submit", addWatchlistItem);
  refreshAll();
});

async function refreshAll() {
  setButtonsBusy(true);
  showMessage("info", "正在刷新 API 状态、雷达总览和信号列表。");

  const isReady = await loadReadyStatus();
  if (isReady) {
    await Promise.all([loadOverview(), loadSignals(), loadPortfolio()]);
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

function renderRadarUnavailable(reason) {
  elements.priorityCounts.innerHTML = emptyState(reason);
  elements.latestScan.innerHTML = emptyState("依赖服务恢复后，先触发采集或运行雷达扫描。");
  elements.currentSubjects.innerHTML = emptyState("暂无当前主题。");
  elements.signalsList.innerHTML = emptyState("暂无信号列表。");
  elements.holdingsList.innerHTML = emptyState("依赖服务恢复后再读取持仓。");
  elements.watchlistList.innerHTML = emptyState("依赖服务恢复后再读取自选。");
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

async function postJson(path, payload) {
  return fetchJson(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
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
  elements.holdingForm.querySelector("button").disabled = isBusy;
  elements.watchlistForm.querySelector("button").disabled = isBusy;
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
