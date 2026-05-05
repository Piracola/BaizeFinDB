# 当前 API 文档

本文档记录当前已经可用的 API。示例默认 API 地址为 `http://127.0.0.1:8000`。

## 1. 调用顺序

从空数据库到看到雷达结果，推荐顺序：

```text
GET  /health/ready
GET  /ops/overview
GET  /ops/history
GET  /ops/trends
GET  /ops/readiness
GET  /providers/akshare/endpoints
GET  /providers/tushare/endpoints
GET  /providers/tushare/status
GET  /providers/tushare/readiness
POST /providers/tushare/fetch/stock-basic
POST /providers/tushare/fetch/announcements
POST /providers/tushare/fetch/stock-company
GET  /providers/tushare/fetch-logs
GET  /providers/tushare/snapshots/latest
POST /providers/akshare/fetch/minimal
GET  /providers/akshare/status
POST /radar/scans/run
GET  /radar/scans/latest
GET  /radar/overview
GET  /radar/signals
GET  /radar/signals/{signal_id}
GET  /radar/signals/{signal_id}/analysis
GET  /portfolio/holdings
POST /portfolio/holdings
GET  /portfolio/watchlist
POST /portfolio/watchlist
POST /reports/from-signal
GET  /reports
GET  /reports/periodic
POST /scores/signals/{signal_id}
GET  /scores/signals/{signal_id}
POST /radar/signals/{signal_id}/review
GET  /radar/signals/{signal_id}/share-preview
GET  /radar/signals/{signal_id}/share-payload
GET  /telegram/status
POST /telegram/webhook
GET  /telegram/bindings
POST /telegram/bindings
PATCH /telegram/bindings/{chat_id}
POST /telegram/push/latest
GET  /telegram/push/logs
```

## 2. 健康检查

### `GET /health`

用途：只检查 API 进程是否存活，不检查数据库和 Redis。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

示例响应：

```json
{
  "status": "ok",
  "service": "BaizeFinDB",
  "environment": "local"
}
```

### `GET /health/ready`

用途：检查 API、PostgreSQL、Redis 是否都可用。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

成功示例：

```json
{
  "status": "ready",
  "service": "BaizeFinDB",
  "checks": {
    "database": {"status": "ok"},
    "redis": {"status": "ok"}
  }
}
```

失败时返回 `503`，并在 `checks` 中说明具体依赖错误。

### `GET /ops/overview`

用途：读取只读运行状态汇总，用于本地排障、服务器 smoke check 和后续监控接入。该接口不触发采集、扫描、推送或模型调用，只聚合已有数据库记录。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/overview?lookback_hours=24"
```

响应重点：

- `radar`：最新扫描 ID、状态、开始/完成时间、耗时、最近扫描数、失败数、失败率、是否超过 2 个调度间隔未更新。
- `server`：API 进程 ID、启动时间、运行时长、Python/平台摘要、磁盘检查路径、磁盘总量/已用/可用和可用空间比例、CPU 使用率/逻辑核心/load average、内存总量/已用/可用比例；指标不可用时返回对应 `*_error`，不会触发采集或调度。
- `provider_fetch`：最近 Provider 拉取状态计数，`success` 以外计入 unhealthy。
- `data_quality`：最近数据质量状态计数，`ok` 以外计入 unhealthy。
- `telegram_push`：最近 Telegram 推送状态计数，`sent`、`preview`、`skipped` 视为健康。
- `model_calls`：最近模型调用审计状态计数，`degraded`、`fallback` 等会计入 unhealthy。
- `alerts`：根据扫描停滞、扫描失败率、磁盘/CPU/内存压力和各类 unhealthy 计数生成的只读告警摘要。

查询参数：

- `lookback_hours`：统计窗口，范围 1 到 168，默认 24。

相关环境变量：

- `OPS_DISK_CHECK_PATH`：磁盘空间检查路径，默认 `.`。
- `OPS_DISK_FREE_PERCENT_ALERT_THRESHOLD`：磁盘可用空间告警阈值百分比，默认 `10`。
- `OPS_CPU_USAGE_PERCENT_ALERT_THRESHOLD`：CPU 使用率告警阈值百分比，默认 `90`。
- `OPS_MEMORY_USED_PERCENT_ALERT_THRESHOLD`：内存使用率告警阈值百分比，默认 `90`。

### `GET /ops/history`

用途：读取只读运维历史，用于定位最近扫描、Provider、数据质量、Telegram 推送和模型调用异常。该接口不触发采集、扫描、推送或模型调用。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/history?lookback_hours=24&limit=20"
```

响应重点：

- `recent_events`：按时间倒序返回最近运维事件。雷达扫描包含所有状态；Provider、数据质量、Telegram 推送和模型调用只返回 unhealthy / failure / degraded 类事件。
- `failure_summary`：按类型和 key 汇总最近异常次数，例如 Provider 端点失败、数据质量降级、推送失败、模型 fallback。

查询参数：

- `lookback_hours`：统计窗口，范围 1 到 168，默认 24。
- `limit`：最多返回事件数，范围 1 到 100，默认 30。

### `GET /ops/trends`

用途：读取只读 OPS 趋势快照，用固定数量时间桶汇总已有运行表，作为后续趋势图和监控接入的后端基础。该接口只读取雷达扫描批次、Provider 拉取日志、数据质量检查、Telegram 推送日志和模型调用日志，并附带当前服务端资源快照；它不持久化资源采样，也不触发采集、扫描、推送、模型调用、报告生成或 evidence 写入。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/trends?lookback_hours=24&bucket_count=12"
```

响应重点：

- `server`：当前服务端磁盘、CPU、内存和进程上下文，复用 `/ops/overview` 的后端资源字段。
- `buckets`：按时间从旧到新排列的固定桶。每个桶包含 radar scan / radar failure、Provider fetch total / unhealthy、data quality total / unhealthy、Telegram push total / unhealthy、model call total / unhealthy 计数。

查询参数：

- `lookback_hours`：统计窗口，范围 1 到 168，默认 24。
- `bucket_count`：时间桶数量，范围 1 到 48，默认 12。

### `GET /ops/readiness`

用途：读取只读运行就绪自检，用于部署验收和日常巡检。该接口基于 `/ops/overview` 的已有聚合结果，不触发采集、扫描、推送或模型调用。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/readiness?lookback_hours=24"
```

响应重点：

- `status`：整体结果，`ready` 表示核心运行条件满足，`warning` 表示可运行但存在警告，`blocked` 表示至少一个关键检查失败。
- `checks`：逐项检查服务端磁盘、CPU、内存、雷达新鲜度、扫描失败率、Provider、数据质量、Telegram 推送和模型调用。

查询参数：

- `lookback_hours`：统计窗口，范围 1 到 168，默认 24。

## 3. Provider API

### `GET /providers/akshare/endpoints`

用途：查看当前封装的 AKShare 最小接口。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/providers/akshare/endpoints
```

响应字段：

| 字段 | 含义 |
| --- | --- |
| `endpoint` | 内部接口名 |
| `title` | 展示名称 |
| `market` | 市场 |
| `snapshot_type` | 快照类型 |
| `required_fields` | 标准化时要求存在的字段 |

### `POST /providers/akshare/fetch/minimal`

用途：手动触发最小 AKShare 采集，写入快照、采集日志和数据质量记录。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/providers/akshare/fetch/minimal
```

示例响应结构：

```json
{
  "provider_name": "akshare",
  "results": [
    {
      "endpoint": "stock_zh_a_spot_em",
      "status": "success",
      "row_count": 5000,
      "quality_status": "ok",
      "confidence": 0.95,
      "missing_fields": [],
      "fetch_log_id": 1,
      "snapshot_id": 1,
      "error_message": null
    }
  ]
}
```

注意：AKShare 可能因为网络、接口变化、非交易时段导致部分接口失败。失败应记录为单个 endpoint 的 `failure`，不应该拖垮整个 API。

### `GET /providers/tushare/endpoints`

用途：查看计划接入的 Tushare 补充源端点。当前 `stock_basic`、`anns_d` 和 `stock_company` 都已支持手动抓取。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/providers/tushare/endpoints
```

当前预留：

- `anns_d`：公告快讯，后续用于重大公告、风险事件和持仓/自选催化，当前 `implemented=true`，可手动抓取并写入 Provider 快照和质量记录。
- `stock_company`：上市公司基本信息，当前 `implemented=true`，可按交易所手动抓取并写入 Provider 快照和质量记录。
- `stock_basic`：股票基础信息，当前 `implemented=true`，可手动抓取并写入 Provider 快照和质量记录。

响应字段比 AKShare endpoint 多：

| 字段 | 含义 |
| --- | --- |
| `purpose` | 接入目的 |
| `permission_note` | token、权限或积分提示 |
| `implemented` | 当前是否已实现真实抓取 |

### `GET /providers/tushare/status`

用途：查看 `TUSHARE_TOKEN` 是否配置和 Tushare Provider 是否启用真实抓取。该接口不返回 token 原文。当前 `stock_basic`、`anns_d` 和 `stock_company` 已实现，`fetch_enabled=true` 还要求 token 已配置。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/providers/tushare/status
```

示例响应：

```json
{
  "provider_name": "tushare",
  "token_configured": false,
  "fetch_enabled": false,
  "endpoint_count": 3,
  "implemented_endpoint_count": 3,
  "status": "not_configured",
  "message": "TUSHARE_TOKEN is required before enabling Tushare fetch."
}
```

### `GET /providers/tushare/readiness`

用途：查看 Tushare 端点是否具备手动抓取和后续调度准入条件。该接口只读取配置、最近抓取日志、数据质量记录和显式调度开关，不返回 token 原文，不触发真实抓取，也不会自行启用 Celery 调度。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/providers/tushare/readiness
```

响应重点：

- `status`：整体结果，`ready` 表示端点已有成功抓取和 `ok` 质量样例，`warning` 表示仍缺样例或存在降级，`blocked` 表示 token 缺失或最近失败。
- `scheduler_enabled`：反映 `.env` 中 `TUSHARE_ANNS_D_BEAT_ENABLED` 是否显式启用；默认 `false`。
- `scheduler_ready_endpoint_count`：具备成功抓取、非空行数和 `ok` 质量记录的已实现端点数量。
- `scheduler_policy`：当前调度策略说明；默认 `anns_d` Celery Beat 关闭，只有设置 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 才会加入 Beat。
- `endpoints[].checks`：逐端点检查 token、实现状态、必需字段、默认查询、最近抓取、数据质量；`anns_d` 还标记重大风险公告映射已接入。

### `POST /providers/tushare/fetch/stock-basic`

用途：手动触发 Tushare `stock_basic` 抓取，写入 `market_snapshots`、`provider_fetch_logs` 和 `data_quality_checks`。该接口不进入 Celery 5 分钟调度，适合先验证 token、权限和字段稳定性。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/providers/tushare/fetch/stock-basic
```

当前标准化字段：

- `ts_code`
- `symbol`
- `name`
- `area`
- `industry`
- `market`
- `exchange`
- `list_status`
- `list_date`
- `is_hs`

如果 `TUSHARE_TOKEN` 未配置、依赖不可用、权限不足或接口异常，接口会记录一条 `provider_fetch_logs.status=failure` 和 `data_quality_checks.status=failed`，并在响应里返回 `quality_status=failed` 和错误摘要。

### `POST /providers/tushare/fetch/announcements`

用途：手动触发 Tushare `anns_d` 公告抓取，写入 `market_snapshots`、`provider_fetch_logs` 和 `data_quality_checks`。该接口不进入 AKShare+雷达 5 分钟调度，也不会在抓取阶段直接生成风险 P0；后续运行雷达扫描时，明显重大风险公告标题会按 risk P0 候选映射，普通公告不会生成信号。可选的 `anns_d` Celery Beat 调度默认关闭，需显式配置环境变量后才会启用。

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/providers/tushare/fetch/announcements?ann_date=20260503"
```

查询参数：

| 参数 | 说明 |
| --- | --- |
| `ann_date` | 可选，公告日期，`YYYYMMDD`；不传时使用当天日期 |

当前标准化字段：

- `ann_date`
- `ts_code`
- `name`
- `title`
- `url`
- `rec_time`

注意：公告 `url` 只允许留在内部 Provider 快照中，不能进入公开分享 payload。

### `POST /providers/tushare/fetch/stock-company`

用途：手动触发 Tushare `stock_company` 上市公司基本信息抓取，写入 `market_snapshots`、`provider_fetch_logs` 和 `data_quality_checks`。该接口按交易所抓取，不假装一次覆盖全市场。

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/providers/tushare/fetch/stock-company?exchange=SZSE"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/providers/tushare/fetch/stock-company?exchange=SSE"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/providers/tushare/fetch/stock-company?exchange=BSE"
```

查询参数：

| 参数 | 说明 |
| --- | --- |
| `exchange` | 可选，`SSE`、`SZSE`、`BSE`，默认 `SZSE` |

当前标准化字段：

- `ts_code`
- `exchange`
- `chairman`
- `manager`
- `secretary`
- `reg_capital`
- `setup_date`
- `province`
- `city`
- `website`
- `email`
- `office`
- `employees`
- `main_business`
- `business_scope`

### `GET /providers/tushare/fetch-logs`

用途：查看最近 Tushare 抓取日志。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/providers/tushare/fetch-logs?limit=20"
Invoke-RestMethod "http://127.0.0.1:8000/providers/tushare/fetch-logs?endpoint=stock_basic"
Invoke-RestMethod "http://127.0.0.1:8000/providers/tushare/fetch-logs?endpoint=anns_d"
Invoke-RestMethod "http://127.0.0.1:8000/providers/tushare/fetch-logs?endpoint=stock_company"
```

### `GET /providers/tushare/snapshots/latest`

用途：查看 Tushare 最新快照摘要和预览行。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/providers/tushare/snapshots/latest
Invoke-RestMethod "http://127.0.0.1:8000/providers/tushare/snapshots/latest?endpoint=stock_basic"
```

### `GET /providers/akshare/status`

用途：查看每个 AKShare endpoint 最近一次采集状态。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/providers/akshare/status
```

重点看：

- `latest_status`
- `latest_quality_status`
- `last_success_at`
- `last_failure_at`
- `row_count`
- `missing_fields`
- `error_message`

### `GET /providers/akshare/fetch-logs`

用途：查看最近采集日志。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/providers/akshare/fetch-logs?limit=20"
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `endpoint` | 只看某个 AKShare endpoint |
| `limit` | 1 到 100，默认 20 |

### `GET /providers/akshare/snapshots/latest`

用途：查看每个 endpoint 最新快照摘要和预览行。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/providers/akshare/snapshots/latest
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `endpoint` | 只看某个 AKShare endpoint |

## 4. Radar API

### `POST /radar/scans/run`

用途：基于最新 Provider 快照生成雷达扫描批次、候选信号和证据。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/radar/scans/run
```

示例响应结构：

```json
{
  "id": 1,
  "status": "success",
  "started_at": "2026-04-30T09:30:00Z",
  "finished_at": "2026-04-30T09:30:03Z",
  "source_snapshot_ids": [1, 2, 3],
  "summary": {
    "signal_count": 3,
    "priority_counts": {"P0": 0, "P1": 1, "P2": 2}
  },
  "error_message": null,
  "signals": []
}
```

状态说明：

| 状态 | 含义 |
| --- | --- |
| `running` | 扫描创建但未完成 |
| `success` | 扫描完成且可能有信号 |
| `no_data` | 缺少可用快照 |
| `failure` | 扫描异常并已记录错误 |

### `GET /radar/scans/latest`

用途：查看最新一次扫描及其信号。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/scans/latest
```

如果没有任何扫描，返回 `404`。

### `GET /radar/scans/{scan_id}`

用途：按批次查看历史扫描。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/scans/1
```

### `GET /radar/overview`

用途：查看当前雷达总览、活跃信号、优先级聚合、生命周期分布、市场情绪摘要、个股回推证据和按板块/概念去重视图。默认当前视图不展示超过 7 天观察窗口的 P2。

`latest_scan.summary.market_sentiment` 会透传后端从涨停、跌停和炸板池快照计算的情绪摘要；主线信号的 `metrics.market_sentiment` 和 `metrics.sentiment_confirmation` 只由后端雷达生成，Web、Telegram 和 Windows 客户端只展示，不重算。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/radar/overview?limit=50"
```

响应重点：

- `latest_scan`
- `active_signals`
- `current_subjects`
- `stock_backtrace_evidences`：从后端信号 metrics 派生的领涨个股、涨幅和反推主题，不由前端重算。
- `latest_scan.summary.market_sentiment`：涨停数、跌停数、炸板数、净涨停压力和情绪偏向。
- `priority_counts`
- `lifecycle_counts`
- `subject_count`

### `GET /radar/signals`

用途：查看候选信号列表。
部署预检 `server_deploy_check.py --check-m5-smoke` 会用 `limit=1` 只读采样该列表；
空列表只产生 warning，用于提示还无法抽样验证单信号分析摘要，不阻断新服务器预检。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/signals
Invoke-RestMethod "http://127.0.0.1:8000/radar/signals?priority=P1&limit=20"
Invoke-RestMethod "http://127.0.0.1:8000/radar/signals?priority=P2&include_expired_p2=true"
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `priority` | `P0`、`P1`、`P2` |
| `limit` | 1 到 100，默认 50 |
| `include_expired_p2` | 默认 `false`；`true` 时包含超过 7 天观察窗口的历史 P2 |

### `GET /radar/signals/{signal_id}`

用途：查看单个信号详情和证据链。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/signals/1
```

重点字段：

- `priority`
- `lifecycle_stage`
- `review_status`
- `metrics`
- `evidences`

### `GET /radar/signals/{signal_id}/analysis`

用途：查看后端生成的单信号只读研究摘要。该接口只使用已有
signal/evidence/review 数据，不调用 LLM，不改变规则定级、生命周期或审查状态。
当前返回确定性多 agent scaffold，用于提前稳定 Web、Windows、Telegram 和后续
LLM agent 编排的消费契约；它不是实时 LLM 多 agent 分析。
Web 信号详情、Windows 客户端 `查看分析` 按钮和 Telegram `/analysis <id>` 都只消费该后端摘要，不在入口层重新生成分析；Web 和 Telegram 已展示后端返回的确定性 `agent_assessments`，Windows 当前仍可只展示既有摘要字段。
部署预检 `server_deploy_check.py --check-m5-smoke` 在 `/radar/signals?limit=1` 返回
信号时会抽样校验该接口的必需字段；如果没有任何信号，则只记录 warning。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/signals/1/analysis
```

重点字段：

- `analysis_title`
- `key_points`
- `metric_highlights`
- `risk_flags`
- `evidence_summary`
- `review_summary`
- `agent_inputs`
- `agent_assessments`
- `next_actions`

`agent_assessments` 固定返回 5 个角色，顺序为：

- `data_quality_agent`
- `risk_agent`
- `momentum_agent`
- `evidence_agent`
- `report_agent`

每个 assessment 包含 `agent_id`、`label`、`status`、`summary`、`findings`
和 `next_actions`。`status` 只允许 `ok`、`warning`、`blocked` 或
`not_applicable`，这些状态只解释当前分析上下文，不覆盖信号的
`priority`、`lifecycle_stage`、`review_status` 或报告发布门禁。

安全边界：

- 不返回原始 URL、source domain、`source_ref`、`raw_excerpt` 或原始 evidence details。
- 不返回精确 confidence，只返回 `high` / `medium` / `low` 桶。
- 不返回个人持仓、成本价、仓位比例。
- 不输出交易指令；所有 `next_actions` 只用于研究关注、审查和复盘流程。

## 5. Portfolio / 持仓自选 API

Portfolio API 是单用户 MVP 能力，当前通过 `user_key` 查询参数做个人数据隔离，默认值为 `default`。它不接券商、不保存交易密码、不导入持仓截图。

持仓和自选只影响后续个人提醒、展示排序和报告上下文，不改变市场主线 P0/P1/P2。

### `GET /portfolio/holdings`

用途：查看某个 `user_key` 下的手动持仓。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/portfolio/holdings
Invoke-RestMethod "http://127.0.0.1:8000/portfolio/holdings?user_key=telegram-1001"
```

### `POST /portfolio/holdings`

用途：新增持仓。`cost_price` 和 `position_ratio` 可为空；`position_ratio` 使用 0 到 1 的比例。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/portfolio/holdings `
  -ContentType "application/json" `
  -Body '{"instrument_code":"600000","instrument_name":"浦发银行","market":"A_SHARE","cost_price":10.25,"position_ratio":0.2}'
```

重复的 `user_key + market + instrument_code` 返回 `409`。

### `PATCH /portfolio/holdings/{holding_id}`

用途：更新持仓名称、备注、成本价、仓位比例或提醒开关。

```powershell
Invoke-RestMethod -Method Patch http://127.0.0.1:8000/portfolio/holdings/1 `
  -ContentType "application/json" `
  -Body '{"note":"降低提醒频率","alert_enabled":false}'
```

### `DELETE /portfolio/holdings/{holding_id}`

用途：删除持仓。删除其他 `user_key` 的记录会返回 `404`。

```powershell
Invoke-RestMethod -Method Delete http://127.0.0.1:8000/portfolio/holdings/1
```

### `GET /portfolio/watchlist`

用途：查看某个 `user_key` 下的自选关注项。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/portfolio/watchlist
```

### `POST /portfolio/watchlist`

用途：新增自选关注项。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/portfolio/watchlist `
  -ContentType "application/json" `
  -Body '{"instrument_code":"SZ000001","instrument_name":"平安银行","market":"A_SHARE","note":"观察风险变化"}'
```

### `PATCH /portfolio/watchlist/{item_id}`

用途：更新自选名称、备注或提醒开关。

```powershell
Invoke-RestMethod -Method Patch http://127.0.0.1:8000/portfolio/watchlist/1 `
  -ContentType "application/json" `
  -Body '{"alert_enabled":false}'
```

### `DELETE /portfolio/watchlist/{item_id}`

用途：删除自选关注项。

```powershell
Invoke-RestMethod -Method Delete http://127.0.0.1:8000/portfolio/watchlist/1
```

## 6. Reports / 报告 API

报告 API 当前是 MVP 模板生成，不调用模型。quick/standard 可从普通报告入口生成；deep 只能走专门手动入口并二次确认。报告只用于关注、观察、风险和复盘，不构成投资建议。

### `POST /reports/from-signal`

用途：从雷达信号生成 quick/standard 报告。生成前会执行轻量规则审查：

- `blocked`：返回 `409`，不生成报告。
- `needs_human_review`：生成报告，但 `status` 标记为 `needs_human_review`。
- `approved`：生成 `generated` 报告。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/reports/from-signal `
  -ContentType "application/json" `
  -Body '{"signal_id":1,"report_type":"quick"}'
```

可选查询参数：

| 参数 | 说明 |
| --- | --- |
| `user_key` | 单用户 MVP 隔离键，默认 `default` |

`report_type` 当前只接受 `quick` 和 `standard`。传入 `deep` 会返回 `422`，不会创建报告；`deep` 只能通过专门手动入口触发并二次确认。

### `POST /reports/deep/from-signal`

用途：从雷达信号手动生成 deep 模板报告。必须显式确认，不自动触发，不调用模型。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/reports/deep/from-signal `
  -ContentType "application/json" `
  -Body '{"signal_id":1,"confirm_deep_report":true}'
```

请求体：

| 字段 | 说明 |
| --- | --- |
| `signal_id` | 雷达信号 ID，必须大于 0 |
| `confirm_deep_report` | 必须为 `true`；缺失或 `false` 返回 `400` 且不创建报告 |

审查行为与 quick/standard 一致：blocked 返回 `409`，missing signal 返回 `404`，needs_human_review 会生成报告但标记为 `needs_human_review`。

### `GET /reports`

用途：查看当前 `user_key` 的报告列表。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/reports
Invoke-RestMethod "http://127.0.0.1:8000/reports?user_key=telegram-1001&report_type=standard"
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `user_key` | 单用户 MVP 隔离键，默认 `default` |
| `report_type` | `quick`、`standard` 或 `deep` |
| `limit` | 1 到 100，默认 50 |

### `GET /reports/{report_id}`

用途：查看单个报告。读取其他 `user_key` 的报告返回 `404`。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/reports/1
```

报告正文使用 `body_markdown` 返回。当前模板不会输出原始证据摘录、交易指令或保证收益语言。

### `GET /reports/periodic`

用途：按日或周生成当前 `user_key` 的雷达汇总报告。该接口实时读取周期内的雷达信号、当前用户报告和 Telegram 推送日志，不创建新的 `reports` 表记录。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/reports/periodic?user_key=telegram-1001&period=daily"
Invoke-RestMethod "http://127.0.0.1:8000/reports/periodic?user_key=telegram-1001&period=weekly"
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `user_key` | 单用户 MVP 隔离键，默认 `default` |
| `period` | `daily` 或 `weekly`，默认 `daily` |

响应重点：

- `priority_counts`：周期内雷达信号的 P0/P1/P2 计数。
- `review_counts`：周期内审查状态计数。
- `lifecycle_counts`：周期内生命周期分布。
- `report_count`：当前 `user_key` 在周期内生成的报告数量。
- `push_count`：当前 `user_key` 在周期内记录的 Telegram 推送数量。
- `body_markdown`：日报/周报正文摘要，不包含原始证据摘录、URL、域名、持仓成本或交易指令。

## 7. Scores / 评分 API

### `POST /scores/signals/{signal_id}`

用途：为单个雷达信号生成或刷新 1d/3d/5d/10d 综合评分记录。评分不是价格回测，也不是交易建议；当前 MVP 综合优先级、生命周期、审查状态、证据数量、连续触发、Provider 数据质量和信号时效性。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/scores/signals/1
```

响应返回四个窗口：

- `window_days`：1、3、5、10。
- `score_status`：`generated` 表示窗口已结束；`pending_window` 表示窗口尚未结束但可先记录当前综合评分。
- `composite_score`：0 到 100 区间的综合分。
- `components`：各维度评分。
- `details`：评分版本、窗口结束时间、方法、权重、评分档位和校准输入说明。

### `GET /scores/signals/{signal_id}`

用途：查看某个信号已经生成过的评分记录。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/scores/signals/1
```

如果信号不存在，返回 `404`。如果信号存在但尚未评分，返回空 `records`。

## 8. Governance / 分享安全 API

### `POST /radar/signals/{signal_id}/review`

用途：对 M5 范围内的单个信号执行轻量规则审查，并写入审查记录。信号候选审查只接受 P0、连续 P1 快报候选、risk 候选、holding/watchlist 相关候选；普通 P2 或非快报 P1 返回 `409` 且不写入审查记录。报告发布前审查由报告接口内部强制执行，不受这个候选范围限制。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/radar/signals/1/review
```

审查结果：

| 状态 | 含义 |
| --- | --- |
| `approved` | 可继续用于内部展示或进入分享预检 |
| `blocked` | 存在硬阻断原因 |
| `needs_human_review` | 需要人工复核 |

常见原因：

- `not_m5_review_target`：信号不在 M5 候选审查范围内，返回 `409` 且不写入审查记录。
- 诱导交易语言。
- 证据缺失。
- 低置信度证据。
- 数据质量失败或降级。
- 证据冲突。
- 重复触发。
- 来源过期。

### `GET /radar/signals/{signal_id}/reviews`

用途：查看单个信号审查历史。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/signals/1/reviews
```

### `GET /radar/signals/{signal_id}/share-preview`

用途：内部分享预检。这个接口给系统和调试后台看，可以返回阻断原因和脱敏记录。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/signals/1/share-preview
```

响应重点：

- `share_status`
- `review_status`
- `blocked_reasons`
- `sanitization_notes`
- `public_payload`

### `GET /radar/signals/{signal_id}/share-payload`

用途：公开分享 payload。只有审查通过且分享策略安全时才返回公开字段。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/signals/1/share-payload
```

如果不可分享，返回 `409`，调用方应该退回内部 `share-preview` 查看原因。

公开 payload 只允许包含：

- 标题。
- 摘要。
- 标的名称。
- 公开优先级标签。
- 生命周期标签。
- 证据摘要标签。
- 免责声明。

公开 payload 不允许包含：

- 原始 URL。
- 源网站域名。
- 原文摘录。
- 内部证据详情。
- 原始枚举值。
- 精确置信度。
- 来源时间。

## 9. Telegram Bot API

Telegram Bot MVP 是 Webhook 模式，适合后续 Linux + HTTPS 部署。Telegram 只消费健康检查、运行状态、OPS 趋势桶、OPS 告警钻取、Tushare 数据源状态、Tushare 准入自检、雷达和单信号分析摘要等后端结果，不重新计算 P0/P1/P2、生命周期、市场情绪、运行状态、OPS readiness、数据源状态、审查状态或分析摘要。

### `GET /telegram/status`

用途：查看 Telegram 配置是否启用，不返回 token 或 secret 原文。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/telegram/status
```

示例响应：

```json
{
  "bot_token_configured": false,
  "allowed_chat_count": 0,
  "binding_count": 0,
  "active_binding_count": 0,
  "require_binding": false,
  "webhook_secret_enabled": false,
  "push_enabled": false
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `allowed_chat_count` | `.env` 中 `TELEGRAM_ALLOWED_CHAT_IDS` 的数量；配置后仍作为硬过滤 |
| `binding_count` | 数据库 `telegram_bindings` 记录总数 |
| `active_binding_count` | 当前允许的绑定数量 |
| `require_binding` | `TELEGRAM_REQUIRE_BINDING` 是否开启；开启后无环境白名单且无 active 绑定的 chat 不再使用本地开放模式 |

部署预检 `server_deploy_check.py --check-telegram-strict-binding` 会只读调用该接口：
`require_binding=true` 为通过；`require_binding=false` 但存在环境白名单或 active 绑定也为通过；
`require_binding=false` 且无环境白名单、无 active 绑定时记录 warning。该预检只消费上述汇总字段，
不读取 `.env` 明文、不调用 `/telegram/bindings`，也不输出 token、secret 或 raw chat id。

### `POST /telegram/webhook`

用途：接收 Telegram update JSON，处理 `message.text` 命令。

支持命令：

| 命令 | 说明 |
| --- | --- |
| `/start`、`/help` | 查看命令说明和免责声明 |
| `/id`、`/chatid` | 查看当前聊天 ID；未进入白名单时也允许返回这个 ID，便于绑定 |
| `/health` | 查看 API、数据库、Redis 和最近一次雷达扫描摘要 |
| `/ops` | 查看服务端运行时、磁盘/CPU/内存、最近运行状态、扫描失败率、Provider、数据质量、推送和模型调用摘要 |
| `/ops_history` | 查看最近运维异常历史和异常汇总 |
| `/ops_trends` | 查看只读 OPS 趋势摘要；固定使用 Telegram 24 小时窗口和 `bucket_count=12`，只调用后端 `get_ops_trends` 并展示趋势桶扫描、失败和 unhealthy 计数，不重算 OPS readiness 或运行状态 |
| `/ops_ready` | 查看运行就绪自检 |
| `/ops_warn` | 查看只读 OPS 告警钻取；固定使用 Telegram 24 小时窗口和有界历史条数，复用 `/ops/readiness`、`/ops/overview` 和 `/ops/history`，优先展示后端 readiness、非 OK 检查、alerts、failure_summary 和有界 recent events |
| `/tushare` | 查看 Tushare token 配置、手动抓取启用状态和已实现端点数；不返回 token 原文，不触发真实抓取 |
| `/tushare_ready` | 查看 Tushare token、端点、最近抓取和数据质量准入状态；不返回 token 原文，不触发真实抓取或调度 |
| `/radar` | 查看雷达总览：P0/P1/P2、生命周期分布、最新扫描、主题数量 |
| `/signals` | 查看最近信号折叠摘要 |
| `/signal <id>` | 查看单个信号复盘、生命周期、审查状态和证据摘要 |
| `/holding`、`/holdings` | 查看当前聊天对应 `user_key=telegram-<chat_id>` 的手动持仓 |
| `/watchlist` | 查看当前聊天对应 `user_key=telegram-<chat_id>` 的自选关注 |
| `/reports` | 查看当前聊天对应 `user_key=telegram-<chat_id>` 的报告列表 |
| `/daily` | 查看当前聊天对应 `user_key=telegram-<chat_id>` 的日报汇总 |
| `/weekly` | 查看当前聊天对应 `user_key=telegram-<chat_id>` 的周报汇总 |
| `/score <id>` | 生成并查看单个信号的 1d/3d/5d/10d 综合评分、评分档位和组件明细 |

本地不配置 `TELEGRAM_BOT_TOKEN` 时，接口返回 `preview`，不会调用 Telegram Bot API：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":1,"message":{"message_id":1,"chat":{"id":1001},"text":"/signals"}}'
```

配置 `TELEGRAM_WEBHOOK_SECRET` 后，请求必须携带 Telegram secret header：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -Headers @{ "X-Telegram-Bot-Api-Secret-Token" = "<same-as-TELEGRAM_WEBHOOK_SECRET>" } `
  -ContentType "application/json" `
  -Body '{"update_id":2,"message":{"message_id":2,"chat":{"id":1001},"text":"/radar"}}'
```

部署后设置 Telegram webhook：

```powershell
$BotToken = "<telegram-bot-token>"
$WebhookUrl = "https://your-domain.example/telegram/webhook"
$WebhookSecret = "<same-as-TELEGRAM_WEBHOOK_SECRET>"

Invoke-RestMethod -Method Post "https://api.telegram.org/bot$BotToken/setWebhook" `
  -Body @{ url = $WebhookUrl; secret_token = $WebhookSecret }
```

Webhook 输出只用于关注、观察、风险和复盘，不构成投资建议。

`/ops_trends`、`/ops_warn`、`/tushare`、`/tushare_ready`、`/holding`、`/watchlist`、`/reports`、`/daily`、`/weekly` 和 `/score <id>` 只读取或触发后端结果，不改变市场级雷达等级，不输出交易指令；`/ops_trends` 不触发采集、扫描、评分、报告、推送、模型调用、evidence 写入、后端修改或交易相关动作，也不从趋势桶 counts/resources 重算 OPS readiness 或运行状态；`/ops_warn` 不触发采集、扫描、评分、报告、推送、模型调用、evidence 写入、后端修改或交易相关动作，也不从 alerts/counts/resources/events 重算 OPS 状态；`/tushare` 和 `/tushare_ready` 不触发真实抓取或调度，`/score` 展示后端返回的评分档位和组件明细，不在 Telegram 层计算评分。

### `GET /telegram/bindings`

用途：查看当前数据库维护的 Telegram chat 绑定和白名单状态。配置 `TELEGRAM_WEBHOOK_SECRET` 后，请求必须携带同一个 Telegram secret header。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/telegram/bindings
```

返回字段包括：

- `chat_id`：Telegram chat id。
- `user_key`：绑定到的内部用户隔离键。
- `display_name`：本地备注名。
- `is_allowed`：是否允许 webhook 命令和推送。
- `source`：绑定来源，当前手动 API 写入为 `manual`。

### `POST /telegram/bindings`

用途：新增或更新某个 chat 的绑定。未传 `user_key` 时默认使用 `telegram-<chat_id>`。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/bindings `
  -ContentType "application/json" `
  -Body '{"chat_id":1001,"user_key":"telegram-1001","display_name":"primary chat","is_allowed":true}'
```

绑定规则：

- 如果 `.env` 没有配置 `TELEGRAM_ALLOWED_CHAT_IDS`，且数据库没有任何绑定，默认本地开发保持开放模式。
- 如果设置 `TELEGRAM_REQUIRE_BINDING=true`，无环境白名单且无 active 数据库绑定的 chat 会被拒绝；`/id` 仍可在未授权前返回 chat id，便于管理员写入绑定。
- 一旦数据库存在绑定，未绑定 chat 默认不再通过 webhook 授权。
- 如果 `.env` 配置了 `TELEGRAM_ALLOWED_CHAT_IDS`，环境白名单仍先过滤；数据库绑定只能在环境白名单允许的范围内进一步允许或禁用。

### `PATCH /telegram/bindings/{chat_id}`

用途：更新某个 chat 的备注名或禁用状态。

```powershell
Invoke-RestMethod -Method Patch http://127.0.0.1:8000/telegram/bindings/1001 `
  -ContentType "application/json" `
  -Body '{"is_allowed":false}'
```

### `POST /telegram/push/latest`

用途：基于最新雷达扫描生成一条 P0/P1/P2 折叠推送。发送前复用轻量审查：`blocked` 信号会被过滤，`needs_human_review` 会在内部推送中明确标注。接口不在 Telegram 层重新计算雷达等级。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/push/latest `
  -ContentType "application/json" `
  -Body '{"chat_ids":[1001],"dry_run":true}'
```

请求字段：

| 字段 | 说明 |
| --- | --- |
| `chat_ids` | 可选，最多 20 个 chat id；为空时使用 `TELEGRAM_ALLOWED_CHAT_IDS` 或 active 数据库绑定；配置白名单后，显式传入的 chat id 也会被白名单过滤；`TELEGRAM_REQUIRE_BINDING=true` 且无白名单/绑定时不会产生隐式收件人 |
| `dry_run` | `true` 时只返回 preview，不写入 `push_logs`，不调用 Telegram API |

响应重点：

- `included_signal_ids`：本轮推送正文纳入的信号。
- `blocked_signal_ids`：审查阻断并过滤的信号。
- `needs_human_review_signal_ids`：需要人工复核并在推送中标注的信号。
- `priority_counts`：推送正文中的 P0/P1/P2 折叠计数。
- `deliveries`：每个 chat 的 `sent`、`preview`、`push_log_id`、`generated_report_ids` 和错误信息。

非 `dry_run` 且未配置 `TELEGRAM_BOT_TOKEN` 时，接口会返回 `preview` 并写入 `push_logs`，用于本地和服务器 dry-run 之外的审计调试。P0 信号完成 `sent` 或 `preview` 后，会为对应 `user_key=telegram-<chat_id>` 生成或复用一份 `standard` report，并在 `generated_report_ids` 返回。同一个 `user_key + chat + scan` 已有 `sent` 或 `preview` 记录时，会跳过重复投递；失败记录允许后续重试。

配置 `TELEGRAM_WEBHOOK_SECRET` 后，请求必须携带同一个 Telegram secret header。

### `GET /telegram/push/logs`

用途：查看某个 `user_key` 的 Telegram 推送记录，默认 `user_key=default`。当前仍是单用户/白名单 MVP，不作为公开多租户 API。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/telegram/push/logs?user_key=telegram-1001&limit=20"
```

返回字段包括推送来源批次、投递状态、折叠后的正文、包含/过滤/人工复核信号 id 和非敏感投递元数据。返回内容不得包含 Telegram token、webhook secret、原始证据摘录、原始 URL 或来源域名。

## 10. 错误码约定

| 错误码 | 常见原因 | 调用方处理 |
| --- | --- | --- |
| `404` | 扫描或信号不存在；未知 endpoint | 提示用户资源不存在，必要时刷新列表 |
| `409` | 信号不满足公开分享条件 | 调用 `share-preview` 查看阻断原因 |
| `409` | 持仓或自选重复 | 刷新列表或改用 PATCH 更新已有记录 |
| `409` | 报告生成前审查阻断 | 查看返回的审查原因，必要时人工复核 |
| `403` | Telegram webhook secret 不匹配 | 检查 `TELEGRAM_WEBHOOK_SECRET` 和请求 header |
| `503` | PostgreSQL 或 Redis 不可用 | 检查 Docker、迁移和 `/health/ready` |

## 11. 接 Telegram / Web / 报告时的推荐用法

- 状态面板：用 `GET /health/ready`、`GET /ops/overview`、`GET /ops/history` 和 `GET /ops/readiness`，展示依赖就绪、服务端磁盘/CPU/内存摘要、扫描新鲜度、失败率、数据质量、推送、模型调用、最近运维异常历史、运行就绪自检和只读 OPS 告警钻取。Web 和 Telegram `/ops_warn` 告警钻取沿用 24 小时窗口，展示后端 readiness、非 OK 检查、overview alerts、history `failure_summary` 和有界 recent events；不要在浏览器或 Telegram 层从 alerts/counts/resources/events 重算 OPS 状态。
- 首页/总览：用 `GET /radar/overview`，展示后端返回的优先级、生命周期、当前主题和 `stock_backtrace_evidences`。
- 信号列表：用 `GET /radar/signals`，按 `priority` 过滤。
- 信号详情：用 `GET /radar/signals/{signal_id}`。
- 单信号解释摘要：用 `GET /radar/signals/{signal_id}/analysis`，展示后端 bounded key points、metric highlights、risk flags 和 review/evidence summary；Web 信号详情、Windows `查看分析` 和 Telegram `/analysis <id>` 已接入该接口。不要在前端、Windows 客户端或 Telegram 重新生成雷达定级、分析摘要或交易建议。
- 持仓/自选：用 `GET /portfolio/holdings` 和 `GET /portfolio/watchlist`，只作为个人上下文。
- 报告：用 `POST /reports/from-signal` 从已审查的雷达信号生成 quick/standard 模板报告；deep 报告只能由明确用户动作调用 `POST /reports/deep/from-signal?user_key=<key>` 并发送 `confirm_deep_report=true`；用 `GET /reports/periodic` 展示日报/周报。Web 和 Windows 客户端都必须先确认再调用 deep endpoint，不能在入口层生成报告正文、审查状态或建议标签。
- 评分：用 `POST /scores/signals/{signal_id}` 生成单信号 1d/3d/5d/10d 综合评分，再展示后端返回的评分档位和组件明细。
- 内部调试：用 `share-preview`。
- 公开展示：只能用 `share-payload`。
- 触发扫描：先保证 Provider 有最新快照，再调用 `POST /radar/scans/run`。
