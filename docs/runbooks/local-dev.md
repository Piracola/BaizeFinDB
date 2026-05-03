# 本地开发 Runbook

这份文档用于把一台新机器或一个新克隆仓库跑到可开发状态，并说明常见调试动作。默认环境是 Windows + PowerShell + Docker Desktop Linux engine。

## 1. 前置要求

| 工具 | 要求 | 验证命令 |
| --- | --- | --- |
| Python | 3.12.x | `python --version` |
| uv | 已安装 | `uv --version` |
| Docker Desktop | Linux engine running | `docker version` |
| Git | 已安装 | `git --version` |

Docker Desktop 需要启用 Linux engine。验证输出里应看到：

```text
Context: desktop-linux
Server: Docker Desktop
OS/Arch: linux/amd64
```

## 2. 首次启动

在仓库根目录执行：

```powershell
uv python install 3.12
uv sync --dev
Copy-Item .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

启动后检查：

浏览器打开静态 Web 雷达终端工作台：

```text
http://127.0.0.1:8000/
```

Web 终端工作台当前可查看 API 状态、运行状态、雷达总览、优先级和生命周期分布、市场情绪摘要、个股回推证据、信号列表/详情，维护指定 `user_key` 的持仓和自选，并从信号详情生成 quick/standard 报告、日报/周报汇总、单信号 v2 综合评分明细和 Telegram chat 绑定/白名单。顶部命令栏支持 `ops`、`radar`、`scan`、`fetch`、`signals`、`portfolio`、`reports`、`daily`、`weekly`、`score`、`telegram` 等轻量命令；这些命令只触发已有后端 API 或页面跳转，不在前端重算雷达等级、生命周期、市场情绪、运行状态、个股回推或评分。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-RestMethod "http://127.0.0.1:8000/ops/overview?lookback_hours=24"
```

期望：

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

## 3. 日常开发启动顺序

推荐每次开发按这个顺序：

```powershell
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

另开一个 PowerShell 跑质量检查：

```powershell
uv run pytest
uv run ruff check .
uv run alembic heads
uv run alembic upgrade head --sql
```

## 4. 数据采集到雷达扫描

### 4.1 验证 AKShare 接口，不写数据库

```powershell
uv run python infra/scripts/verify_akshare_minimal.py
```

只验证某个接口：

```powershell
uv run python infra/scripts/verify_akshare_minimal.py --endpoint stock_zh_a_spot_em
```

### 4.2 采集最小 AKShare 数据并写入数据库

```powershell
uv run python infra/scripts/collect_akshare_minimal.py
```

也可以走 API：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/providers/akshare/fetch/minimal
```

### 4.3 基于最新快照运行雷达扫描

```powershell
uv run python infra/scripts/run_radar_scan.py
```

也可以走 API：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/radar/scans/run
```

### 4.4 查看扫描结果

```powershell
Invoke-RestMethod http://127.0.0.1:8000/radar/scans/latest
Invoke-RestMethod http://127.0.0.1:8000/radar/overview
Invoke-RestMethod http://127.0.0.1:8000/radar/signals
```

### 4.5 手动维护持仓和自选

持仓和自选是单用户 MVP 能力，按 `user_key` 隔离。默认 `user_key` 是 `default`：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/portfolio/holdings `
  -ContentType "application/json" `
  -Body '{"instrument_code":"600000","instrument_name":"浦发银行","market":"A_SHARE","cost_price":10.25,"position_ratio":0.2}'

Invoke-RestMethod -Method Post http://127.0.0.1:8000/portfolio/watchlist `
  -ContentType "application/json" `
  -Body '{"instrument_code":"SZ000001","instrument_name":"平安银行","market":"A_SHARE","note":"观察风险变化"}'
```

查询：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/portfolio/holdings
Invoke-RestMethod "http://127.0.0.1:8000/portfolio/watchlist?user_key=default"
```

当前 API 不接券商、不保存交易密码、不导入持仓截图；持仓/自选只影响后续个人提醒、展示排序和报告上下文，不改变市场级 P0/P1/P2。

### 4.6 从信号生成报告

报告生成前会复用轻量审查。blocked 信号不会生成报告：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/reports/from-signal `
  -ContentType "application/json" `
  -Body '{"signal_id":1,"report_type":"quick"}'

Invoke-RestMethod http://127.0.0.1:8000/reports
```

当前只支持 quick / standard 模板报告；deep report 后续只能手动触发并二次确认。

生成日报/周报汇总：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/reports/periodic?period=daily"
Invoke-RestMethod "http://127.0.0.1:8000/reports/periodic?period=weekly&user_key=telegram-1001"
```

生成信号评分：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/scores/signals/1
Invoke-RestMethod http://127.0.0.1:8000/scores/signals/1
```

## 5. Telegram Bot MVP 本地调试

`.env` 支持这些 Telegram 可选配置：

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_PUSH_ENABLED=false
MODEL_AUDIT_STORE_RAW_PROMPT=false
```

本地开发时可以先不填 `TELEGRAM_BOT_TOKEN`。此时 webhook 不会调用 Telegram Bot API，而是返回 `preview`，方便直接看 Bot 会发送的中文内容。

查看配置状态，确认不会泄露 token 或 secret：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/telegram/status
```

维护本地 Telegram chat 绑定和白名单：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/bindings `
  -ContentType "application/json" `
  -Body '{"chat_id":1001,"user_key":"telegram-1001","display_name":"local preview","is_allowed":true}'

Invoke-RestMethod http://127.0.0.1:8000/telegram/bindings
```

如果 `.env` 未配置 `TELEGRAM_ALLOWED_CHAT_IDS` 且数据库没有任何绑定，本地 webhook 仍保持开放模式；一旦存在绑定，未绑定 chat 默认会被拒绝。配置 `TELEGRAM_ALLOWED_CHAT_IDS` 后，环境白名单仍是硬过滤。

也可以在 Web 工作台的 `Telegram 绑定 / 白名单` 面板维护绑定。服务器配置 `TELEGRAM_WEBHOOK_SECRET` 时，在该面板的 `Webhook Secret` 输入框临时填写同一个值；前端不会保存该 secret。

本地 preview `/help`：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":1,"message":{"message_id":1,"chat":{"id":1001},"text":"/help"}}'
```

本地 preview `/health` 会返回 API、数据库、Redis 和最近一次雷达扫描摘要：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":10,"message":{"message_id":10,"chat":{"id":1001},"text":"/health"}}'
```

本地 preview `/id`，用于拿到绑定白名单时需要填写的 chat id：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":11,"message":{"message_id":11,"chat":{"id":1001},"text":"/id"}}'
```

本地 preview `/ops` 会返回最近运行状态、扫描失败率、Provider、数据质量、推送和模型调用摘要：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":11,"message":{"message_id":11,"chat":{"id":1001},"text":"/ops"}}'
```

本地 preview `/radar`：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":2,"message":{"message_id":2,"chat":{"id":1001},"text":"/radar"}}'
```

本地 preview 日报/评分：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":20,"message":{"message_id":20,"chat":{"id":1001},"text":"/daily"}}'

Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":21,"message":{"message_id":21,"chat":{"id":1001},"text":"/score 1"}}'
```

如果启用了 `TELEGRAM_WEBHOOK_SECRET`，本地请求也要带 header：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -Headers @{ "X-Telegram-Bot-Api-Secret-Token" = "<same-as-TELEGRAM_WEBHOOK_SECRET>" } `
  -ContentType "application/json" `
  -Body '{"update_id":3,"message":{"message_id":3,"chat":{"id":1001},"text":"/signals"}}'
```

部署到公网 HTTPS 后设置 webhook：

```powershell
$BotToken = "<telegram-bot-token>"
$WebhookUrl = "https://your-domain.example/telegram/webhook"
$WebhookSecret = "<same-as-TELEGRAM_WEBHOOK_SECRET>"

Invoke-RestMethod -Method Post "https://api.telegram.org/bot$BotToken/setWebhook" `
  -Body @{ url = $WebhookUrl; secret_token = $WebhookSecret }
```

删除 webhook：

```powershell
Invoke-RestMethod -Method Post "https://api.telegram.org/bot$BotToken/deleteWebhook"
```

Telegram 输出只用于关注、观察、风险和复盘；P0/P1/P2、生命周期和审查状态都来自后端服务结果。

Telegram 个人数据命令：

- `/holding` 读取 `user_key=telegram-<chat_id>` 的持仓。
- `/watchlist` 读取 `user_key=telegram-<chat_id>` 的自选关注。
- `/reports` 读取 `user_key=telegram-<chat_id>` 的报告列表。
- `/daily` 和 `/weekly` 读取 `user_key=telegram-<chat_id>` 的周期汇总。
- `/score <id>` 触发后端评分记录生成，并展示评分档位和组件明细；评分不改变雷达等级，不构成交易建议，Telegram 不做本地评分。

本地 preview 示例：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":4,"message":{"message_id":4,"chat":{"id":1001},"text":"/holding"}}'
```

如果要让这个命令看到数据，请先用 Portfolio API 创建 `user_key=telegram-1001` 的持仓或自选。
如果要让 `/reports` 看到数据，请先用 Reports API 创建 `user_key=telegram-1001` 的报告。

本地折叠推送 preview：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/push/latest `
  -ContentType "application/json" `
  -Body '{"chat_ids":[1001],"dry_run":true}'
```

查看推送日志：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/telegram/push/logs?user_key=telegram-1001"
```

`TELEGRAM_PUSH_ENABLED=true` 时，Celery 的 `baizefindb.radar.collect_and_scan` 会在采集和扫描后追加一次最新扫描折叠推送。推送正文按 P0/P1/P2 折叠，复用后端审查过滤 `blocked`，并对 `needs_human_review` 明确标注；P0 信号完成推送后会为对应聊天用户自动生成或复用 `standard` report。Telegram 层不重新计算雷达等级。配置 `TELEGRAM_ALLOWED_CHAT_IDS` 后，手动推送接口显式传入的 `chat_ids` 也会被白名单过滤。

## 6. Celery Worker / Beat

当前 Celery 用 Redis 作为 broker/result。Beat 默认每 300 秒触发一次 `baizefindb.radar.collect_and_scan`，顺序执行最小 AKShare 采集和雷达扫描；启用 `TELEGRAM_PUSH_ENABLED=true` 后会继续触发 Telegram 折叠推送。可通过 `.env` 调整：

```dotenv
RADAR_SCAN_INTERVAL_SECONDS=300
RADAR_CONTINUOUS_P1_TRIGGER_COUNT=3
RADAR_CONTINUITY_WINDOW_MINUTES=30
TELEGRAM_PUSH_ENABLED=false
```

需要调试后台任务时，先启动 worker：

```powershell
uv run celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
```

再另开一个 PowerShell 启动 beat：

```powershell
uv run celery -A app.tasks.celery_app.celery_app beat --loglevel=INFO
```

如果只是手动采集和扫描，可以先不用 Celery，直接跑 `infra/scripts` 或 API。不要同时运行多个 beat 实例，避免同一时间重复触发采集和扫描。

## 7. 数据库操作

### 7.1 查看容器状态

```powershell
docker compose ps
```

期望 `postgres` 和 `redis` 都是 `healthy`。

### 7.2 进入 PostgreSQL

```powershell
docker compose exec postgres psql -U baizefindb -d baizefindb
```

常用 SQL：

```sql
\dt
select * from alembic_version;
select id, endpoint, status, row_count, created_at from provider_fetch_logs order by id desc limit 10;
select id, status, started_at, finished_at from radar_scan_batches order by id desc limit 10;
```

### 7.3 重置本地数据库

会删除本地 Docker volume 内的数据，只在开发环境使用：

```powershell
docker compose down -v
docker compose up -d postgres redis
uv run alembic upgrade head
```

## 8. Redis 操作

进入 Redis：

```powershell
docker compose exec redis redis-cli
```

清空本地 Redis：

```powershell
docker compose exec redis redis-cli FLUSHALL
```

## 9. 常见故障

### Docker Desktop 卡在 starting

先确认虚拟化已启用、Docker Desktop 是 Linux engine。然后重启 Docker Desktop。恢复后验证：

```powershell
docker desktop status
docker desktop engine ls
docker version
```

### 5432 或 6379 端口被占用

查看占用：

```powershell
Get-NetTCPConnection -LocalPort 5432,6379 -State Listen
```

如果本机已有 PostgreSQL/Redis，建议先停掉本机服务，保持项目使用 Docker Compose 的固定端口。

### `/health` 正常但 `/health/ready` 不正常

含义：

- API 进程能启动。
- PostgreSQL 或 Redis 至少一个依赖不可用。

排查顺序：

```powershell
docker compose ps
docker compose logs --tail=80 postgres
docker compose logs --tail=80 redis
uv run alembic heads
uv run alembic upgrade head
```

### 查看最近运行状态

本地或服务器 API 启动后，可以用只读运维接口查看最近扫描、失败率、Provider 拉取、数据质量、Telegram 推送和模型降级状态：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/overview?lookback_hours=24"
```

该接口只聚合已有记录，不会触发采集、扫描、推送或模型调用。

### AKShare 采集失败

AKShare 接口可能受网络、节假日、字段变更影响。先跑不写库验证：

```powershell
uv run python infra/scripts/verify_akshare_minimal.py
```

如果单个接口失败，Provider 采集应记录 `failure` 和数据质量标签，不应该拖垮主服务。

## 10. 开发完成前检查

每次提交前至少跑：

```powershell
uv run pytest
uv run ruff check .
uv run alembic heads
uv run alembic upgrade head --sql
```

涉及数据库变更时额外检查：

- 新模型是否有迁移。
- 迁移是否能从空库执行。
- 回滚方案是否清楚，至少能通过本地 `docker compose down -v` 重建。

涉及公开分享、报告、Telegram、Web 输出时额外检查：

- 是否复用 `share-preview` 或同等级审查。
- 是否隐藏原始 URL、域名、原文摘录、内部证据细节。
- 是否避免强买卖、保证收益、诱导交易语言。

### 10.1 模块阶段完成后的 git 版本管理

后续 AI 协作默认策略：模块设计或开发阶段完成后，AI 自动做 git commit，不再每次向用户确认；但不自动 push。

不要求无边界的零散编辑都提交；但即使是小的模块化更新，只要形成明确阶段边界，也必须同步更新相关开发文档并提交 git commit。执行顺序：

1. 先跑对应质量检查，例如 `uv run pytest`、`uv run ruff check .`、`uv run alembic heads`、`uv run alembic upgrade head --sql`，按本次模块实际影响选择。
2. 再查看 `git status`，确认只包含本模块相关变更。
3. 检查 staged 文件，确认没有误提交 `.env`、密钥、个人数据、原始付费数据、持仓截图、报告导出等敏感文件。
4. 如发现未识别的脏文件或疑似用户手工改动，不能自动纳入提交；要隔离并说明。
5. 按模块边界提交独立 git commit，不把多个无关模块混成一个大提交。

commit message 要能看懂模块和动作，例如：

- `docs(prd): refine radar mvp`
- `feat(radar): add scan scheduler`
- `test(radar): cover p1 continuity`
- `docs(dev): add git workflow`

文档、迁移、测试和代码要随模块一起提交；如果只完成设计文档，也要提交文档版本。

大模块按阶段拆成多个 commit：设计文档 commit、数据模型/迁移 commit、业务实现 commit、测试/文档 commit。

这是长期开发约束，适用于后续 AI 协作。
