# 当前 API 文档

本文档记录当前已经可用的 API。示例默认 API 地址为 `http://127.0.0.1:8000`。

## 1. 调用顺序

从空数据库到看到雷达结果，推荐顺序：

```text
GET  /health/ready
GET  /providers/akshare/endpoints
POST /providers/akshare/fetch/minimal
GET  /providers/akshare/status
POST /radar/scans/run
GET  /radar/scans/latest
GET  /radar/overview
GET  /radar/signals
GET  /radar/signals/{signal_id}
GET  /portfolio/holdings
POST /portfolio/holdings
GET  /portfolio/watchlist
POST /portfolio/watchlist
POST /radar/signals/{signal_id}/review
GET  /radar/signals/{signal_id}/share-preview
GET  /radar/signals/{signal_id}/share-payload
GET  /telegram/status
POST /telegram/webhook
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

用途：查看当前雷达总览、活跃信号、优先级聚合和按板块/概念去重视图。

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/radar/overview?limit=50"
```

响应重点：

- `latest_scan`
- `active_signals`
- `current_subjects`
- `priority_counts`
- `subject_count`

### `GET /radar/signals`

用途：查看候选信号列表。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/signals
Invoke-RestMethod "http://127.0.0.1:8000/radar/signals?priority=P1&limit=20"
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `priority` | `P0`、`P1`、`P2` |
| `limit` | 1 到 100，默认 50 |

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

## 6. Governance / 分享安全 API

### `POST /radar/signals/{signal_id}/review`

用途：对单个信号执行轻量规则审查，并写入审查记录。

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

## 7. Telegram Bot API

Telegram Bot MVP 是 Webhook 模式，适合后续 Linux + HTTPS 部署。Telegram 只消费健康检查和雷达后端结果，不重新计算 P0/P1/P2、生命周期或审查状态。

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
  "webhook_secret_enabled": false
}
```

### `POST /telegram/webhook`

用途：接收 Telegram update JSON，处理 `message.text` 命令。

支持命令：

| 命令 | 说明 |
| --- | --- |
| `/start`、`/help` | 查看命令说明和免责声明 |
| `/health` | 查看 API、数据库、Redis 简要状态 |
| `/radar` | 查看雷达总览：P0/P1/P2、最新扫描、主题数量 |
| `/signals` | 查看最近信号折叠摘要 |
| `/signal <id>` | 查看单个信号复盘、生命周期、审查状态和证据摘要 |

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

## 8. 错误码约定

| 错误码 | 常见原因 | 调用方处理 |
| --- | --- | --- |
| `404` | 扫描或信号不存在；未知 endpoint | 提示用户资源不存在，必要时刷新列表 |
| `409` | 信号不满足公开分享条件 | 调用 `share-preview` 查看阻断原因 |
| `409` | 持仓或自选重复 | 刷新列表或改用 PATCH 更新已有记录 |
| `403` | Telegram webhook secret 不匹配 | 检查 `TELEGRAM_WEBHOOK_SECRET` 和请求 header |
| `503` | PostgreSQL 或 Redis 不可用 | 检查 Docker、迁移和 `/health/ready` |

## 9. 接 Telegram / Web / 报告时的推荐用法

- 首页/总览：用 `GET /radar/overview`。
- 信号列表：用 `GET /radar/signals`，按 `priority` 过滤。
- 信号详情：用 `GET /radar/signals/{signal_id}`。
- 持仓/自选：用 `GET /portfolio/holdings` 和 `GET /portfolio/watchlist`，只作为个人上下文。
- 内部调试：用 `share-preview`。
- 公开展示：只能用 `share-payload`。
- 触发扫描：先保证 Provider 有最新快照，再调用 `POST /radar/scans/run`。
