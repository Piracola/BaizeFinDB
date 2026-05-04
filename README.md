# BaizeFinDB

个人 AI 金融雷达与投研辅助系统。当前已完成 M5 A 股 5 分钟资金主线雷达 MVP 验收项，进入生产化验证和真实数据增强阶段。

当前状态详见 [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)。

## 开发文档

- [开发文档导航](docs/README.md)
- [本地开发 Runbook](docs/runbooks/local-dev.md)
- [Linux 服务端部署骨架 Runbook](docs/runbooks/linux-server.md)
- [Windows 客户端 MVP Runbook](docs/runbooks/windows-client.md)
- [当前 API 文档](docs/api/current-api.md)
- [当前数据模型说明](docs/specs/current-data-model.md)
- [M5 A 股 5 分钟资金主线雷达 MVP PRD](docs/prd/m5-next-step.md)

## 当前包含

- FastAPI 后端入口
- `/health` 存活检查
- `/health/ready` PostgreSQL / Redis 就绪检查
- `/ops/overview` 只读运行状态汇总：服务端进程、磁盘/CPU/内存资源、最近扫描、失败率、Provider 拉取、数据质量、Telegram 推送、模型降级和告警摘要
- `/ops/history` 只读运维历史：最近扫描、Provider 异常、数据质量异常、Telegram 推送异常、模型降级/失败事件和异常汇总
- `/ops/readiness` 只读运行就绪自检：基于服务端磁盘/CPU/内存、雷达新鲜度、扫描失败率、Provider、数据质量、推送和模型调用给出 `ready` / `warning` / `blocked`
- AKShare 最小 Provider：A 股行情、行业板块、概念板块
- AKShare 情绪 Provider：涨停股池、跌停股池、炸板股池
- Tushare Provider：可查看 token 配置状态和计划端点，`stock_basic`、`anns_d` 和 `stock_company` 已支持手动抓取并写入 Provider 快照；`anns_d` 中明显重大风险公告可在后续雷达扫描中映射为 risk P0；可选 `anns_d` Celery Beat 调度默认关闭，启用前先跑 enablement checklist 和离线/no-token 预调度校验，再显式配置
- Provider 拉取日志、快照和数据质量表
- `/providers/akshare/endpoints` 查看已封装接口
- `/providers/tushare/endpoints` 查看计划接入的 Tushare 补充源端点
- `/providers/tushare/status` 查看 Tushare token 是否配置，不返回 token 原文
- `/providers/tushare/readiness` 查看 Tushare 手动抓取和后续调度准入自检，并反映 `anns_d` Beat 开关，不触发真实抓取
- `/providers/tushare/fetch/stock-basic` 手动触发 Tushare 股票基础信息抓取
- `/providers/tushare/fetch/announcements` 手动触发 Tushare 公告抓取
- `/providers/tushare/fetch/stock-company` 手动触发 Tushare 上市公司基本信息抓取
- `/providers/tushare/fetch-logs` 查看 Tushare 抓取日志
- `/providers/tushare/snapshots/latest` 查看 Tushare 最新快照摘要
- `/providers/akshare/fetch/minimal` 手动触发最小采集
- `/providers/akshare/status` 查看每个接口最新采集状态
- `/providers/akshare/fetch-logs` 查看最新采集日志
- `/providers/akshare/snapshots/latest` 查看最新快照摘要
- `/portfolio/holdings` 手动维护持仓，成本价和仓位比例可选
- `/portfolio/watchlist` 手动维护自选关注项
- `/reports/from-signal` 从雷达信号生成 quick/standard 模板报告，生成前复用审查
- `/reports` 查看当前 `user_key` 的报告列表
- `/reports/periodic` 按日/周生成当前 `user_key` 的雷达汇总报告
- `/scores/signals/{signal_id}` 生成或查看 1d/3d/5d/10d 综合评分
- 静态 Web 雷达终端工作台可查看运行状态、服务端磁盘/CPU/内存摘要、运维历史、运行就绪自检、Tushare 状态、雷达总览、优先级和生命周期分布、市场情绪摘要、个股回推证据、信号详情，维护默认 `user_key` 的持仓/自选，生成/查看 quick/standard 报告、日报/周报汇总和单信号 v2 综合评分明细，并维护 Telegram chat 绑定/白名单
- 雷达扫描批次、候选信号、证据链和审查记录基础表
- `/radar/scans/run` 基于最新 Provider 快照生成雷达候选信号
- `/radar/scans/latest` 查看最新一次雷达扫描
- `/radar/scans/{scan_id}` 按批次查看雷达扫描结果
- `/radar/overview` 查看最新雷达总览、优先级聚合、生命周期分布、个股回推证据、市场情绪摘要和去重当前视图
- `/radar/signals` 查看候选信号列表
- `/radar/signals/{signal_id}` 查看候选信号和证据
- `/radar/signals/{signal_id}/review` 对单个雷达信号执行轻量规则审查
- `/radar/signals/{signal_id}/reviews` 查看单个雷达信号的审查历史
- `/radar/signals/{signal_id}/share-preview` 内部分享预检：查看脱源脱敏预览和发布前阻断理由
- `/radar/signals/{signal_id}/share-payload` 公开分享 payload：仅在审查通过且分享策略安全时返回公开字段
- Telegram Bot MVP Webhook 模块：只消费健康检查、运行状态、运维历史、运行就绪自检、Tushare 数据源状态和准入自检、雷达、报告和评分后端结果，`/ops` 展示后端运行状态摘要，`/ops_history` 展示只读运维异常历史，`/ops_ready` 展示运行就绪自检，`/tushare` 展示 Tushare 只读配置状态，`/tushare_ready` 展示 Tushare 抓取/调度准入自检，`/radar` 展示后端市场情绪摘要，不重新计算 P0/P1/P2 或评分
- `/telegram/status` 查看 Telegram 配置状态，不泄露 token 或 secret
- `/telegram/webhook` 接收 Telegram update，支持 `/help`、`/id`、`/health`、`/ops`、`/ops_history`、`/ops_ready`、`/tushare`、`/tushare_ready`、`/radar`、`/signals`、`/signal <id>`、`/holding`、`/watchlist`、`/reports`、`/daily`、`/weekly`、`/score <id>`；`/health` 展示最近扫描状态，`/ops` 展示运行状态摘要，`/ops_history` 展示只读运维异常历史，`/ops_ready` 展示运行就绪自检，`/tushare` 只读展示 Tushare token 配置和端点实现状态，`/tushare_ready` 展示 Tushare token、最新抓取和数据质量准入状态，`/score` 展示后端 v2 评分档位和组件明细
- `/telegram/bindings` 管理 Telegram chat 与 `user_key` 的绑定、白名单和禁用状态
- `/telegram/push/latest` 按最新扫描生成 P0/P1/P2 折叠推送，复用审查过滤 blocked，并写入 `push_logs`
- `/telegram/push/logs` 查看当前 `user_key` 的 Telegram 推送记录
- Windows 客户端 MVP：用 Python 标准库 + Tkinter 连接本地或服务器 API，查看健康状态、运行状态、服务端磁盘/CPU/内存摘要、运维历史、运行就绪自检、Tushare 数据源状态和准入自检、雷达总览、生命周期分布、市场情绪摘要、个股回推证据、信号列表、持仓、自选、报告摘要、日报/周报、单信号 v2 评分明细，维护 Telegram chat 绑定/白名单并打开 Web 面板
- Celery 5 分钟调度 MVP：`baizefindb.radar.collect_and_scan` 顺序执行 AKShare 最小采集、雷达扫描，并在 `TELEGRAM_PUSH_ENABLED=true` 时触发 Telegram 折叠推送；Tushare `anns_d` Beat 调度默认不加入，只有 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 时才额外启用
- 雷达连续扫描记忆：记录同一板块前后变化、连续 P1 次数和生命周期转移
- P2 7 天观察窗口：当前总览和默认信号列表隐藏超出观察期的 P2，历史排查可显式包含
- 雷达扫描会携带 Provider 数据质量摘要和涨停/跌停/炸板池情绪摘要，信号和证据也会保留对应质量标签
- 雷达扫描失败会记录 `failure`、`error_message` 和失败摘要，避免普通异常留下 `running` 批次
- 轻量审查层：拦截诱导交易语言、证据缺失、低置信度证据、失败/降级数据质量，并标记证据冲突、重复触发和来源过期
- 分享预览安全门：内部预检输出阻断原因；公开 payload 只输出脱源脱敏摘要和公开标签
- `golden_cases` 规则黄金样例，用于锁定基础 P0/P1/P2 判定、误报场景、审查结果和分享安全
- Pydantic 配置
- SQLAlchemy 2.0 异步数据库连接
- Alembic 迁移框架
- Celery Worker / Beat 调度入口
- Docker Compose 的 PostgreSQL / Redis 配置
- Linux 服务端部署骨架：API Dockerfile、server compose overlay、worker/beat、部署预检脚本、只读 M5 smoke check（含 `/ops/overview` 和 Tushare 状态契约）、运行采样验证脚本、PostgreSQL 备份/恢复脚本、systemd 示例和 nginx HTTPS 反代示例
- pytest 冒烟测试

## 当前进度

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| M1 工程骨架 | 已完成 | 后端可启动、可测试，PostgreSQL / Redis / Alembic / Docker Compose 基础就绪。 |
| M2 数据底座 | 已完成早期闭环 | AKShare 最小 Provider、采集入库、质量标签、查询 API、Celery 采集壳已完成；Tushare `stock_basic`、`anns_d` 和 `stock_company` 已支持手动抓取、日志和快照查询，`anns_d` 重大风险公告可被后续雷达扫描映射为 risk P0；`anns_d` Beat 调度有默认关闭的显式开关。 |
| M3 雷达核心 | 已完成早期闭环 | 可基于板块/概念快照生成候选信号、证据链、生命周期、连续 P1 标记、扫描失败状态和雷达总览。 |
| M4 审查层 | 已完成 | 已有轻量规则审查 API、审查记录表、数据质量审查、审查/分享黄金样例、内部分享预检和公开分享 payload，先不接复杂 Agent/LLM。 |
| M5 | 验收项完成 | 已有静态 Web 终端工作台、Telegram Bot MVP、Windows 客户端 MVP、5 分钟采集后扫描调度、持仓/自选最小 API、quick/standard 报告、日报/周报、1d/3d/5d/10d v2 综合评分、Telegram 折叠推送、P0 推送后 standard report、风险 P0、Review Agent 范围控制、模型降级审计和只读 M5 smoke check；后续进入生产化验证和真实数据增强。 |

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

- `http://127.0.0.1:8000/` 静态 Web 雷达终端工作台
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/ready`
- `http://127.0.0.1:8000/ops/overview?lookback_hours=24`
- `http://127.0.0.1:8000/ops/history?lookback_hours=24&limit=20`
- `http://127.0.0.1:8000/ops/readiness?lookback_hours=24`

如果 PostgreSQL / Redis 还没启动，`/health` 仍会正常，`/health/ready` 会显示依赖未就绪。

更完整的本地开发、数据库重置、AKShare 采集和雷达扫描流程见 [docs/runbooks/local-dev.md](docs/runbooks/local-dev.md)。

Linux 服务器端部署骨架文件见 [docs/runbooks/linux-server.md](docs/runbooks/linux-server.md) 和 [infra/linux/](infra/linux/)。该骨架用于后续部署 API、静态 Web、Telegram webhook、Celery worker 和 Celery beat；`infra/scripts/server_deploy_check.py` 可检查 `.env`、compose 配置、容器状态、API 健康状态、只读 M5 JSON 契约、`/ops/overview` 运行状态和服务端资源契约、`/ops/history` 运维历史契约、`/ops/readiness` 就绪自检契约、Tushare 状态契约、可选 Tushare `anns_d` Beat enablement 离线/no-token checklist 和 `pg_dump` 可用性，`infra/scripts/server_runtime_check.py` 可对运行中的 API 连续采样健康、OPS 和就绪状态并生成 JSON 报告，`infra/scripts/export_ops_evidence.py` 可从同一组只读健康/OPS 端点导出脱敏 JSON evidence，用于区分历史 warning 与真正 blocker，`infra/scripts/postgres_backup.py` 可通过 server compose overlay 生成 PostgreSQL `pg_dump` 备份，`infra/scripts/postgres_restore.py` 可在显式确认后从备份恢复。不代表完整生产部署已经完成。

## Windows 客户端 MVP

Windows 客户端位于 [clients/windows/](clients/windows/)，当前是源码运行版，不是 exe 或安装包。

本地连接：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000
```

连接服务器：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl https://<your-domain>
```

客户端只消费后端 API，不重新计算 P0/P1/P2、生命周期、市场情绪、运行状态、数据源状态、审查状态或评分；Tushare 状态/自检按钮只读取 `/providers/tushare/status` 和 `/providers/tushare/readiness`，不触发真实抓取；持仓/自选/报告/日报/周报按 User Key 读取，只作为个人上下文；Telegram 绑定管理只调用后端白名单 API；不保存 token、secret、Tushare token 原文、持仓截图、报告导出或个人数据；不提供买卖建议、不接自动交易、不承诺收益。详细说明见 [docs/runbooks/windows-client.md](docs/runbooks/windows-client.md)。

## Telegram Bot MVP

`.env` 可选配置：

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_PUSH_ENABLED=false
OPS_DISK_CHECK_PATH=.
OPS_DISK_FREE_PERCENT_ALERT_THRESHOLD=10
OPS_CPU_USAGE_PERCENT_ALERT_THRESHOLD=90
OPS_MEMORY_USED_PERCENT_ALERT_THRESHOLD=90
```

- `TELEGRAM_BOT_TOKEN` 留空时，`POST /telegram/webhook` 不会调用 Telegram Bot API，而是返回 `preview`，方便本地测试。
- `TELEGRAM_ALLOWED_CHAT_IDS` 可填逗号分隔的 chat id；配置后只有白名单 chat 会被处理。
- `TELEGRAM_WEBHOOK_SECRET` 配置后，Webhook 必须携带 `X-Telegram-Bot-Api-Secret-Token`。
- `TELEGRAM_PUSH_ENABLED=true` 后，Celery 扫描任务会向白名单 chat 发送最新扫描的折叠推送；留空或 false 时只保留手动 API 调试。
- P0 信号完成折叠推送后，会为对应 `user_key=telegram-<chat_id>` 自动生成一份 `standard` report；重复推送同一扫描不会重复生成。
- `/telegram/bindings` 可把 chat id 绑定到指定 `user_key` 并控制是否允许；配置 `TELEGRAM_ALLOWED_CHAT_IDS` 时，环境白名单仍是硬过滤。
- `/health` 返回 API、数据库、Redis 和最近一次雷达扫描摘要。
- `/ops` 返回服务端运行时、磁盘/CPU/内存、最近运行状态、扫描失败率、Provider、数据质量、推送、模型调用和告警摘要。
- `/ops_history` 返回最近运维异常历史和异常汇总，不触发采集、扫描、推送或模型调用。
- `/ops_ready` 返回运行就绪自检，不触发采集、扫描、推送或模型调用。
- `/tushare` 返回 Tushare token 配置、手动抓取启用状态和已实现端点数；不返回 token 原文，不触发真实抓取。
- `/tushare_ready` 返回 Tushare token、端点、最新抓取、数据质量准入状态和 `anns_d` Beat 开关策略；不返回 token 原文，不触发真实抓取或调度。
- `/holding` 和 `/watchlist` 按聊天 id 读取 `user_key=telegram-<chat_id>` 的个人持仓/自选，只用于个人提醒和复盘上下文。
- `/reports` 按聊天 id 读取 `user_key=telegram-<chat_id>` 的报告列表。
- `/score <id>` 触发后端评分并展示 1d/3d/5d/10d 综合评分、评分档位和组件明细；Telegram 不做本地评分。

本地折叠推送 preview 示例：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/telegram/push/latest `
  -ContentType "application/json" `
  -Body '{"chat_ids":[1001],"dry_run":true}'
```

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

验证 Tushare `stock_basic`，不写数据库：

```powershell
uv run python infra/scripts/verify_tushare_stock_basic.py --json-output evidence/tushare-stock-basic.json
uv run python infra/scripts/check_tushare_anns_d_beat_enablement.py
uv run python infra/scripts/verify_tushare_anns_d_preflight.py
uv run python infra/scripts/verify_tushare_announcements.py --ann-date 20260503 --json-output evidence/tushare-anns-20260503.json
uv run python infra/scripts/verify_tushare_stock_company.py --exchange SZSE --json-output evidence/tushare-stock-company-SZSE.json
```

`check_tushare_anns_d_beat_enablement.py` 输出 JSON checklist，默认离线/no-token，不访问 Tushare、不写数据库、不触发抓取、扫描或推送。它会汇总本地 sample gate、`TUSHARE_TOKEN`、`TUSHARE_ANNS_D_BEAT_ENABLED`、`TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS`、仍需 live verify、readiness/live data 默认未检查等状态；只有显式加 `--check-readiness` 时才会做只读 readiness HTTP GET。

部署预检需要一起检查该 checklist 时使用：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-tushare-anns-d-beat-enablement
```

该集成仍是离线/no-token 模式，输出精简摘要；`warn` 不阻断部署预检，只有 checklist `fail` 会返回失败退出码。

`verify_tushare_anns_d_preflight.py` 不需要 `TUSHARE_TOKEN`，只读取本地 golden case，检查 `anns_d` 归一化必需字段、重大风险公告应映射 risk P0，以及普通公告不应产生风险信号。它是启用 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 前的预调度门禁，但不能替代真实 `TUSHARE_TOKEN` 权限、积分消耗、实时接口字段和 `/providers/tushare/readiness` 验证。

`verify_tushare_stock_basic.py`、`verify_tushare_announcements.py` 和 `verify_tushare_stock_company.py` 都支持 `--json-output <path>`，会在真实 token 可用时保存一份脱敏 live evidence JSON；报告只保留状态、端点、查询参数、行数、质量状态、必需字段、缺失字段和少量去 URL/source/token/secret-like 字段的归一化样例，样例值会递归脱敏并截断超长文本，失败时也会写入脱敏 failure report。启用 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 前，应先保留 offline checklist / preflight 结果，再保存 announcements live evidence；`stock_basic` 和 `stock_company` evidence 用于同步留存 token 权限、积分和字段稳定性。

PostgreSQL 迁移完成后，手动采集并写入数据库：

```powershell
uv run python infra/scripts/collect_akshare_minimal.py
uv run python infra/scripts/collect_tushare_stock_basic.py
uv run python infra/scripts/collect_tushare_announcements.py --ann-date 20260503
uv run python infra/scripts/collect_tushare_stock_company.py --exchange SZSE
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

Beat 默认每 300 秒触发一次 `baizefindb.radar.collect_and_scan`，顺序执行最小 AKShare 采集和雷达扫描。可通过 `.env` 的 `RADAR_SCAN_INTERVAL_SECONDS` 调整本地/服务器调度间隔；`RADAR_CONTINUOUS_P1_TRIGGER_COUNT` 和 `RADAR_CONTINUITY_WINDOW_MINUTES` 控制连续 P1 快报候选阈值，默认 30 分钟内连续 3 次。Tushare `anns_d` 公告 Beat 调度默认关闭；只有设置 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 后才额外加入 `baizefindb.providers.collect_tushare_announcements`，间隔由 `TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS` 控制，默认 3600 秒。改成 `true` 前先执行 `check_tushare_anns_d_beat_enablement.py` 和离线 `verify_tushare_anns_d_preflight.py`，再用 `verify_tushare_announcements.py --json-output <path>` 保存脱敏 live evidence，并确认真实 token 权限、积分消耗和 `/providers/tushare/readiness`。

手动维护持仓和自选：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/portfolio/holdings `
  -ContentType "application/json" `
  -Body '{"instrument_code":"600000","instrument_name":"浦发银行","market":"A_SHARE","position_ratio":0.2}'

Invoke-RestMethod -Method Post http://127.0.0.1:8000/portfolio/watchlist `
  -ContentType "application/json" `
  -Body '{"instrument_code":"SZ000001","instrument_name":"平安银行","market":"A_SHARE","note":"观察风险变化"}'
```

当前持仓/自选按 `user_key` 做单用户 MVP 隔离，只影响个人提醒和展示上下文，不改变市场主线 P0/P1/P2。

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
