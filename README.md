# BaizeFinDB

个人 AI 金融雷达与投研辅助系统。当前已完成 M4 轻量审查层闭环。

当前状态详见 [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)。

## 开发文档

- [开发文档导航](docs/README.md)
- [本地开发 Runbook](docs/runbooks/local-dev.md)
- [当前 API 文档](docs/api/current-api.md)
- [当前数据模型说明](docs/specs/current-data-model.md)
- [M5 A 股 5 分钟资金主线雷达 MVP PRD](docs/prd/m5-next-step.md)

## 当前包含

- FastAPI 后端入口
- `/health` 存活检查
- `/health/ready` PostgreSQL / Redis 就绪检查
- AKShare 最小 Provider：A 股行情、行业板块、概念板块
- AKShare 情绪 Provider：涨停股池、跌停股池、炸板股池
- Provider 拉取日志、快照和数据质量表
- `/providers/akshare/endpoints` 查看已封装接口
- `/providers/akshare/fetch/minimal` 手动触发最小采集
- `/providers/akshare/status` 查看每个接口最新采集状态
- `/providers/akshare/fetch-logs` 查看最新采集日志
- `/providers/akshare/snapshots/latest` 查看最新快照摘要
- 雷达扫描批次、候选信号、证据链和审查记录基础表
- `/radar/scans/run` 基于最新 Provider 快照生成雷达候选信号
- `/radar/scans/latest` 查看最新一次雷达扫描
- `/radar/scans/{scan_id}` 按批次查看雷达扫描结果
- `/radar/overview` 查看最新雷达总览、优先级聚合和去重当前视图
- `/radar/signals` 查看候选信号列表
- `/radar/signals/{signal_id}` 查看候选信号和证据
- `/radar/signals/{signal_id}/review` 对单个雷达信号执行轻量规则审查
- `/radar/signals/{signal_id}/reviews` 查看单个雷达信号的审查历史
- `/radar/signals/{signal_id}/share-preview` 内部分享预检：查看脱源脱敏预览和发布前阻断理由
- `/radar/signals/{signal_id}/share-payload` 公开分享 payload：仅在审查通过且分享策略安全时返回公开字段
- Telegram Bot MVP Webhook 模块：只消费健康检查和雷达后端结果，不重新计算 P0/P1/P2
- `/telegram/status` 查看 Telegram 配置状态，不泄露 token 或 secret
- `/telegram/webhook` 接收 Telegram update，支持 `/help`、`/health`、`/radar`、`/signals`、`/signal <id>`
- 雷达连续扫描记忆：记录同一板块前后变化、连续 P1 次数和生命周期转移
- 雷达扫描会携带 Provider 数据质量摘要，信号和证据也会保留对应质量标签
- 雷达扫描失败会记录 `failure`、`error_message` 和失败摘要，避免普通异常留下 `running` 批次
- 轻量审查层：拦截诱导交易语言、证据缺失、低置信度证据、失败/降级数据质量，并标记证据冲突、重复触发和来源过期
- 分享预览安全门：内部预检输出阻断原因；公开 payload 只输出脱源脱敏摘要和公开标签
- `golden_cases` 规则黄金样例，用于锁定基础 P0/P1/P2 判定、误报场景、审查结果和分享安全
- Pydantic 配置
- SQLAlchemy 2.0 异步数据库连接
- Alembic 迁移框架
- Celery Worker / Beat 配置壳
- Docker Compose 的 PostgreSQL / Redis 配置
- pytest 冒烟测试

## 当前进度

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| M1 工程骨架 | 已完成 | 后端可启动、可测试，PostgreSQL / Redis / Alembic / Docker Compose 基础就绪。 |
| M2 数据底座 | 已完成早期闭环 | AKShare 最小 Provider、采集入库、质量标签、查询 API、Celery 采集壳已完成。 |
| M3 雷达核心 | 已完成早期闭环 | 可基于板块/概念快照生成候选信号、证据链、生命周期、连续 P1 标记、扫描失败状态和雷达总览。 |
| M4 审查层 | 已完成 | 已有轻量规则审查 API、审查记录表、数据质量审查、审查/分享黄金样例、内部分享预检和公开分享 payload，先不接复杂 Agent/LLM。 |
| M5 | 进行中 | 已有静态 Web 和 Telegram Bot MVP 消费后端雷达结果；后续继续补 5 分钟调度、持仓自选、报告、日报周报和评分。 |

## 本地启动

先准备 Python 3.12：

```powershell
uv python install 3.12
uv sync --dev
```

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

只启动 API：

```powershell
uv run uvicorn app.main:app --reload
```

访问：

- `http://127.0.0.1:8000/` 静态 Web 雷达面板
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/ready`

如果 PostgreSQL / Redis 还没启动，`/health` 仍会正常，`/health/ready` 会显示依赖未就绪。

更完整的本地开发、数据库重置、AKShare 采集和雷达扫描流程见 [docs/runbooks/local-dev.md](docs/runbooks/local-dev.md)。

## Telegram Bot MVP

`.env` 可选配置：

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_WEBHOOK_SECRET=
```

- `TELEGRAM_BOT_TOKEN` 留空时，`POST /telegram/webhook` 不会调用 Telegram Bot API，而是返回 `preview`，方便本地测试。
- `TELEGRAM_ALLOWED_CHAT_IDS` 可填逗号分隔的 chat id；配置后只有白名单 chat 会被处理。
- `TELEGRAM_WEBHOOK_SECRET` 配置后，Webhook 必须携带 `X-Telegram-Bot-Api-Secret-Token`。

本地 preview 示例：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/webhook `
  -ContentType "application/json" `
  -Body '{"update_id":1,"message":{"message_id":1,"chat":{"id":1001},"text":"/radar"}}'
```

部署到公网 HTTPS 后，用占位 token 设置 Telegram webhook：

```powershell
$BotToken = "<telegram-bot-token>"
$WebhookUrl = "https://your-domain.example/telegram/webhook"
$WebhookSecret = "<same-as-TELEGRAM_WEBHOOK_SECRET>"

Invoke-RestMethod -Method Post "https://api.telegram.org/bot$BotToken/setWebhook" `
  -Body @{ url = $WebhookUrl; secret_token = $WebhookSecret }
```

## 启动依赖服务

安装 Docker 后执行：

```powershell
docker compose up -d postgres redis
```

执行数据库迁移：

```powershell
uv run alembic upgrade head
```

验证 AKShare 最小接口，不写数据库：

```powershell
uv run python infra/scripts/verify_akshare_minimal.py
```

PostgreSQL 迁移完成后，手动采集并写入数据库：

```powershell
uv run python infra/scripts/collect_akshare_minimal.py
```

基于已入库快照手动运行雷达扫描：

```powershell
uv run python infra/scripts/run_radar_scan.py
```

启动 Celery Worker：

```powershell
uv run celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
```

启动 Celery Beat：

```powershell
uv run celery -A app.tasks.celery_app.celery_app beat --loglevel=INFO
```

## 测试

```powershell
uv run pytest
uv run ruff check .
uv run alembic heads
uv run alembic upgrade head --sql
```

## 开发边界

当前已完成 M4 轻量审查层闭环：只基于已入库 AKShare 快照生成候选信号、总览、规则审查结果和脱源脱敏分享预览，连续 P1 只标记为快报候选；不接自动交易，不提供交易建议。M5 的真实 MVP 是 A 股 5 分钟资金主线雷达，Telegram、Web、报告、持仓自选、日报周报和评分只消费雷达结果或向后端发命令。

当前真实数据表与未来规划表的边界见 [docs/specs/current-data-model.md](docs/specs/current-data-model.md)。进入 M5 前先阅读 [docs/prd/m5-next-step.md](docs/prd/m5-next-step.md)，按雷达优先顺序推进，不再按 Telegram/报告/Web 三选一拆分下一阶段。
