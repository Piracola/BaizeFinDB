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
- `/ops/trends` 只读 OPS 趋势快照：按固定时间桶聚合已有运行表的扫描、Provider、数据质量、Telegram 推送和模型调用计数，并附带当前服务端资源上下文；它是后续趋势图和监控接入基础，不持久化资源采样，也不是完整监控系统
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
- `/reports/deep/from-signal` 手动生成 deep 模板报告，需要 `confirm_deep_report=true` 二次确认，不自动触发、不调用模型
- `/reports` 查看当前 `user_key` 的报告列表，可按 quick/standard/deep 过滤
- `/reports/periodic` 按日/周生成当前 `user_key` 的雷达汇总报告
- `/scores/signals/{signal_id}` 生成或查看 1d/3d/5d/10d 综合评分
- 静态 Web 雷达终端工作台可查看运行状态、服务端磁盘/CPU/内存摘要、运维历史、只读 OPS 趋势摘要和趋势图、运行就绪自检、OPS 告警钻取、Tushare 状态、雷达总览、优先级和生命周期分布、市场情绪摘要、个股回推证据、信号详情、后端单信号分析摘要和确定性 agent assessments，维护默认 `user_key` 的持仓/自选，生成/查看 quick/standard 报告、确认后手动生成 deep 报告、日报/周报汇总和单信号 v2 综合评分明细，并维护 Telegram chat 绑定/白名单；Telegram 面板会读取 `/telegram/status`，展示严格绑定模式和白名单/绑定汇总计数，但不展示原始环境值、bot token 或 webhook secret；命令栏支持 `trend` / `trends` 滚动并刷新 `/ops/trends?lookback_hours=24&bucket_count=12` 的后端趋势桶计数，也支持 `warn` / `warning` 滚动并刷新 OPS 告警钻取。趋势摘要和趋势图只展示后端返回的扫描、失败和 unhealthy 桶计数；告警钻取只读复用 `/ops/readiness`、`/ops/overview` 和 `/ops/history` 的 24 小时窗口结果，展示后端 readiness、非 OK 检查、alerts、failure_summary 和有界 recent events，不在浏览器重算 OPS 状态或触发采集、扫描、评分、报告、Telegram mutation、模型调用、evidence 写入或交易相关动作
- 雷达扫描批次、候选信号、证据链和审查记录基础表
- `/radar/scans/run` 基于最新 Provider 快照生成雷达候选信号
- `/radar/scans/latest` 查看最新一次雷达扫描
- `/radar/scans/{scan_id}` 按批次查看雷达扫描结果
- `/radar/overview` 查看最新雷达总览、优先级聚合、生命周期分布、个股回推证据、市场情绪摘要和去重当前视图
- `/radar/signals` 查看候选信号列表
- `/radar/signals/{signal_id}` 查看候选信号和证据
- `/radar/signals/{signal_id}/analysis` 查看后端生成的只读研究摘要：基于已有信号、证据和审查数据，输出 bounded key points、metric highlights、risk flags、evidence/review summary、agent inputs、确定性 `agent_assessments` 和 next actions；当前 agent assessments 是后端规则化多 agent scaffold，不调用 LLM、不做真实多模型编排，不改变规则定级，不输出原始来源定位、raw excerpt、精确信心值、个人持仓成本或交易指令
- `infra/scripts/model_provider_readiness.py --json-output <path>` 可做未来 LLM-backed 多 agent 接入前的只读配置自检；`server_deploy_check.py --check-model-provider-readiness --model-provider-readiness-json-output <path>` 可把同一检查纳入 Linux 部署预检；默认 `MODEL_ANALYSIS_ENABLED=false` / `MODEL_PROVIDER=disabled`，不会调用模型、验证 token、读取数据库、生成报告、发送 Telegram 或输出 API key。启用前可配置 `MODEL_PROVIDER=openai` + `MODEL_PRIMARY_MODEL` + `OPENAI_API_KEY`，或 `MODEL_PROVIDER=custom` + `MODEL_PRIMARY_MODEL` + `MODEL_API_BASE_URL` + `MODEL_API_KEY`
- `app.ai.model_client` 已提供默认关闭的 OpenAI-compatible 模型客户端和审计包装器：启用后可向 `openai` 或 `custom` provider 的 `/chat/completions` 发送 `model`、`messages` 和可选 `response_format`，主模型成功不写审计，主模型失败会按配置尝试 fallback，fallback/degraded 结果写入 `model_call_logs`；该模块当前尚未接入 `/radar/signals/{signal_id}/analysis`，不会修改雷达优先级、生命周期、审查状态、报告、Telegram、Provider 或其他业务表
- `app.ai.analysis_output` 已提供未来模型分析草稿的输出净化契约：只解析模型返回的 JSON 文本，允许 bounded advisory summary、observations、risk notes、follow-up questions 和固定建议标签，自动脱源 URL/domain、限制长度和条数，遇到 malformed JSON 返回 degraded，遇到直接交易语言返回 blocked；该模块不调用模型、不写数据库、不接 API、不改变雷达或报告
- `/radar/signals/{signal_id}/review` 对单个雷达信号执行轻量规则审查
- `/radar/signals/{signal_id}/reviews` 查看单个雷达信号的审查历史
- `/radar/signals/{signal_id}/share-preview` 内部分享预检：查看脱源脱敏预览和发布前阻断理由
- `/radar/signals/{signal_id}/share-payload` 公开分享 payload：仅在审查通过且分享策略安全时返回公开字段
- Telegram Bot MVP Webhook 模块：只消费健康检查、运行状态、运维历史、OPS 趋势桶、运行就绪自检、OPS 告警钻取、Tushare 数据源状态和准入自检、雷达、报告、单信号后端分析摘要和评分后端结果，`/ops` 展示后端运行状态摘要，`/ops_history` 展示只读运维异常历史，`/ops_trends` 固定读取 24 小时 / 12 桶后端趋势计数，展示扫描、失败和 unhealthy 桶摘要，不重算 OPS readiness 或状态，`/ops_ready` 展示运行就绪自检，`/ops_warn` 展示只读 OPS 告警钻取，`/tushare` 展示 Tushare 只读配置状态，`/tushare_ready` 展示 Tushare 抓取/调度准入自检，`/radar` 展示后端市场情绪摘要，`/analysis <id>` 展示后端单信号研究摘要和确定性 agent assessments，不重新计算 P0/P1/P2、OPS 状态、分析摘要、agent 状态或评分
- `/telegram/status` 查看 Telegram 配置状态，不泄露 token 或 secret
- `/telegram/webhook` 接收 Telegram update，支持 `/help`、`/id`、`/health`、`/ops`、`/ops_history`、`/ops_trends`、`/ops_ready`、`/ops_warn`、`/tushare`、`/tushare_ready`、`/radar`、`/signals`、`/signal <id>`、`/analysis <id>`、`/holding`、`/watchlist`、`/reports`、`/daily`、`/weekly`、`/score <id>`；`/health` 展示最近扫描状态，`/ops` 展示运行状态摘要，`/ops_history` 展示只读运维异常历史，`/ops_trends` 用 Telegram 24 小时窗口和 12 个桶只读展示后端 OPS 趋势桶计数，不从桶计数推导 readiness 或运行状态，`/ops_ready` 展示运行就绪自检，`/ops_warn` 用 Telegram 24 小时窗口只读复用 `/ops/readiness`、`/ops/overview` 和 `/ops/history`，优先展示后端 readiness、非 OK 检查、alerts、failure_summary 和有界 recent events，`/tushare` 只读展示 Tushare token 配置和端点实现状态，`/tushare_ready` 展示 Tushare token、最新抓取和数据质量准入状态，`/analysis` 展示后端单信号研究摘要，`/score` 展示后端 v2 评分档位和组件明细
- `/telegram/bindings` 管理 Telegram chat 与 `user_key` 的绑定、白名单和禁用状态
- `/telegram/push/latest` 按最新扫描生成 P0/P1/P2 折叠推送，复用审查过滤 blocked，并写入 `push_logs`
- `/telegram/push/logs` 查看当前 `user_key` 的 Telegram 推送记录
- Windows 客户端 MVP：用 Python 标准库 + Tkinter 连接本地或服务器 API，查看健康状态、运行状态、服务端磁盘/CPU/内存摘要、运维历史、运行就绪自检、OPS 告警钻取、首用诊断、Tushare 数据源状态和准入自检、雷达总览、生命周期分布、市场情绪摘要、个股回推证据、信号列表、单信号后端分析摘要和确定性 agent assessments、持仓、自选、报告摘要、确认后手动生成 deep 报告、日报/周报、单信号 v2 评分明细，维护 Telegram chat 绑定/白名单并打开 Web 面板；查看 Telegram 绑定时会同时显示严格绑定模式和汇总计数；GUI 可用 `OPS Lookback (hours)` 为运行状态、运维历史、就绪自检、告警钻取和首用诊断选择 1 到 168 小时统计窗口，默认 24
- Celery 5 分钟调度 MVP：`baizefindb.radar.collect_and_scan` 顺序执行 AKShare 最小采集、雷达扫描，并在 `TELEGRAM_PUSH_ENABLED=true` 时触发 Telegram 折叠推送；Tushare `anns_d` Beat 调度默认不加入，只有 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 时才额外启用
- 雷达连续扫描记忆：记录同一板块前后变化、连续 P1 次数和生命周期转移
- P2 7 天观察窗口：当前总览和默认信号列表隐藏超出观察期的 P2，历史排查可显式包含
- 雷达扫描会携带 Provider 数据质量摘要和涨停/跌停/炸板池情绪摘要，信号和证据也会保留对应质量标签
- 雷达扫描失败会记录 `failure`、`error_message` 和失败摘要，避免普通异常留下 `running` 批次
- 轻量审查层：拦截诱导交易语言、证据缺失、低置信度证据、失败/降级数据质量，并标记证据冲突、重复触发和来源过期；否定式风险提示不会误判为诱导交易
- 分享预览安全门：内部预检输出阻断原因；公开 payload 只输出脱源脱敏摘要和公开标签
- `golden_cases` 规则黄金样例，用于锁定基础 P0/P1/P2 判定、Tushare 公告 risk P0 / 普通公告无信号的完整扫描、诱导交易语言误报场景、审查结果和分享安全
- Pydantic 配置
- SQLAlchemy 2.0 异步数据库连接
- Alembic 迁移框架
- Celery Worker / Beat 调度入口
- Docker Compose 的 PostgreSQL / Redis 配置
- Linux 服务端部署骨架：API Dockerfile、server compose overlay、worker/beat、部署预检脚本、server compose runtime contract 预检、只读 M5 smoke check（含 `/ops/overview`、`/ops/history`、`/ops/trends`、`/ops/readiness`、Tushare 状态、`/radar/signals` 和有信号时的 `/radar/signals/{id}/analysis` 契约；其中 analysis smoke 会校验固定 agent assessment 角色和基础字段形状）、运行采样验证脚本、cron/systemd 友好的监控摘要脚本和 5 分钟 systemd timer 示例、PostgreSQL 备份/恢复脚本、默认 dry-run 的 PostgreSQL backup retention helper、每日 PostgreSQL backup systemd timer 示例、systemd 自启动示例和 nginx HTTPS 反代示例
- pytest 冒烟测试

## 当前进度

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| M1 工程骨架 | 已完成 | 后端可启动、可测试，PostgreSQL / Redis / Alembic / Docker Compose 基础就绪。 |
| M2 数据底座 | 已完成早期闭环 | AKShare 最小 Provider、采集入库、质量标签、查询 API、Celery 采集壳已完成；Tushare `stock_basic`、`anns_d` 和 `stock_company` 已支持手动抓取、日志和快照查询，`anns_d` 重大风险公告可被后续雷达扫描映射为 risk P0；`anns_d` Beat 调度有默认关闭的显式开关。 |
| M3 雷达核心 | 已完成早期闭环 | 可基于板块/概念快照生成候选信号、证据链、生命周期、连续 P1 标记、扫描失败状态和雷达总览。 |
| M4 审查层 | 已完成 | 已有轻量规则审查 API、审查记录表、数据质量审查、诱导交易语言正反例、否定式风险提示误报防护、审查/分享黄金样例、内部分享预检和公开分享 payload，先不接复杂 Agent/LLM。 |
| M5 | 验收项完成 | 已有静态 Web 终端工作台、Telegram Bot MVP、Windows 客户端 MVP、5 分钟采集后扫描调度、持仓/自选最小 API、quick/standard 报告、手动 deep 报告入口、日报/周报、1d/3d/5d/10d v2 综合评分、Telegram 折叠推送、P0 推送后 standard report、风险 P0、Review Agent 范围控制、模型降级审计和只读 M5 smoke check；后续进入生产化验证和真实数据增强。 |

## 本地启动

先准备 Python 3.12：

```powershell
uv python install 3.12
uv sync --dev
```

迁移到新机器、Linux 服务器续开发或开始较长开发前，先运行只读开发环境自检：

```powershell
uv run python infra/scripts/dev_environment_check.py
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
- `http://127.0.0.1:8000/ops/trends?lookback_hours=24&bucket_count=12`
- `http://127.0.0.1:8000/ops/readiness?lookback_hours=24`

如果 PostgreSQL / Redis 还没启动，`/health` 仍会正常，`/health/ready` 会显示依赖未就绪。

更完整的本地开发、数据库重置、AKShare 采集和雷达扫描流程见 [docs/runbooks/local-dev.md](docs/runbooks/local-dev.md)。

Linux 服务器端部署骨架文件见 [docs/runbooks/linux-server.md](docs/runbooks/linux-server.md) 和 [infra/linux/](infra/linux/)。该骨架用于后续部署 API、静态 Web、Telegram webhook、Celery worker 和 Celery beat；`infra/scripts/server_deploy_check.py` 可检查 `.env`、compose 配置、容器状态、API 健康状态、只读 M5 JSON 契约、`/ops/overview` 运行状态和服务端资源契约、`/ops/history` 运维历史契约、`/ops/trends` 趋势快照契约、`/ops/readiness` 就绪自检契约、Tushare 状态契约、`/radar/signals` 候选信号列表契约，以及有信号时的 `/radar/signals/{id}/analysis` 单信号分析摘要契约；空信号列表只作为 warning，不阻断新服务器部署预检；该脚本还可选运行 Tushare `anns_d` Beat enablement 离线/no-token checklist、模型 Provider readiness 只读配置预检和 `pg_dump` 可用性检查，可用 `--json-output <path>` 额外写出结构化部署预检报告，也可用 `--check-backup --backup-check-json-output <path>` 在同一部署预检中写出 PostgreSQL backup check-only evidence；`infra/scripts/server_runtime_check.py` 可对运行中的 API 连续采样健康、OPS 和就绪状态并生成 JSON 报告，也可用 `--include-ops-trends` 额外读取只读 `/ops/trends` 并输出 compact trend summary，还可用 `--ops-evidence-output <path>` 在 warning/blocked 排障时同步写出脱敏 OPS evidence；`infra/scripts/server_monitor_check.py` 复用 runtime check，默认单次零延迟采样并输出 cron/systemd 友好的 compact monitor summary JSON，`blocked` 返回非零，warning 默认零退出、可用 `--fail-on-warning` 升级为失败，也可用 `--alert-json-output <path>` 从同一份内存 summary 额外写 no-send 告警 payload；`infra/scripts/server_alert_payload.py` 可单独把已有 compact monitor summary 转成 no-send 告警 payload，输出 `severity`、`should_notify`、`dedupe_key` 和有界 items，供 `server_alert_telegram.py` 等交付适配器消费；`server_alert_telegram.py` 默认只预览并写 delivery evidence，只有显式 `--send` 才复用后端 `TelegramClient` 发送，收件人来自 `--chat-id` 或 `TELEGRAM_ALLOWED_CHAT_IDS`，token 来自 `TELEGRAM_BOT_TOKEN`，报告只保留 masked chat refs、不包含 token 或 raw URL；monitor/payload 两条路径当前都不发送通知、不读取 `.env`、不调用 API/Docker/数据库/Telegram/SMTP/webhook；`infra/linux/baizefindb-postgres-backup.service` 和 `.timer` 提供每日 PostgreSQL backup systemd 示例，先写 `evidence/postgres-backup-timer-check.json`，再把时间戳 `.sql` 写到 `backups/`，不执行恢复、不包含 secrets；`infra/scripts/postgres_backup_retention.py` 可默认 dry-run 扫描 `backups/` 下超过保留期的普通 `.sql` 文件并写出有界 JSON evidence，只有显式 `--delete` 才删除候选文件，symlink、目录和非 SQL 文件会跳过；`infra/scripts/postgres_restore.py --check-only --check-json-output <path>` 可在恢复前验证备份文件元数据和 server compose overlay 下的 `psql --version`，拒绝缺失、symlink、非普通文件、空文件或非 `.sql` 输入，且不会把备份流入数据库；`infra/scripts/server_delivery_acceptance.py` 可把部署预检、backup check-only evidence、backup retention dry-run evidence 和运行时采样串成一次交付验收，默认验收 `http://127.0.0.1:8000`，也可用 `--base-url <url>` 验证非默认端口、反向代理或域名地址，并在 `evidence/server-delivery-acceptance/` 下写出汇总 JSON，显式加 `--include-model-provider-readiness` 时会把模型 Provider readiness evidence 写入同一目录并纳入状态汇总，显式加 `--include-ops-evidence` 时会把脱敏 OPS evidence 写入同一目录并纳入状态汇总，也可用 `--skip-backup-retention` 跳过 retention evidence，或用 `--restore-check-input backups/<file>.sql` 把具体备份文件的非破坏性 restore preflight evidence 放入同一验收包；该脚本会把 helper evidence JSON 顶层 `warn` 状态保留为非阻塞 warning、把缺失或失败 evidence 标为 blocker，生产切换前可加 `--fail-on-warning` 让 warning-only 验收保留 `warn` 报告但返回非零退出码；evidence 默认不包含 `/ops/trends`，只有同一命令显式加 `--include-ops-trends --trend-bucket-count <n>` 时才写入脱敏 `snapshots.ops_trends`，其中 `n` 必须在 1 到 48 之间；`infra/scripts/export_ops_evidence.py` 可从同一组只读健康/OPS 端点单独导出脱敏 JSON evidence，用于区分历史 warning 与真正 blocker，`infra/scripts/postgres_backup.py --check-only --check-json-output <path>` 可通过 server compose overlay 只验证备份命令元数据和 `pg_dump --version` 并写出有界 JSON evidence，不导出数据库内容；`infra/scripts/postgres_backup.py` 可通过同一 overlay 生成 PostgreSQL `pg_dump` 备份，`infra/scripts/postgres_restore.py` 可在显式确认后从备份恢复。不代表完整生产部署已经完成。

`server_deploy_check.py --check-m5-smoke --require-radar-signal-analysis-sample` 会把空 `/radar/signals?limit=1` 从 warning 升级为失败，用于首用演示、生产化验收或已有真实/演示信号后的严格 analysis 契约覆盖。该检查只读 API，不自动运行 seed、采集、扫描、报告或推送；新库可先显式运行 `infra/scripts/seed_demo_data.py` 或真实扫描生成样本。

`server_deploy_check.py --check-systemd-units` 可选静态验证 `infra/linux/` 里的 systemd service/timer 模板是否仍符合当前 contract，包括 monitor/alert/backup timer 目标、周期、证据输出、env preflight、dedupe 和 no-secret 边界；该检查只读仓库文件，不调用 `systemctl` / `journalctl`，也不检查服务器已安装 unit。

`server_deploy_check.py --check-server-compose-contract` 可选解析 `docker compose -f docker-compose.yml -f docker-compose.server.yml config --format json` 的结果，验证 `api`、`worker`、`beat`、`postgres`、`redis` 服务存在，API/worker/beat 的 server 环境变量、healthy PostgreSQL/Redis 依赖、API 8000 端口和 `/health` healthcheck、Celery worker/beat 命令、beat schedule 文件和 `restart: unless-stopped` 不漂移。该检查不启动容器；compose JSON 命令失败时不输出 stdout，避免把展开后的 env 值写进日志。

`server_deploy_check.py --check-telegram-strict-binding` 可选读取 `/telegram/status`，确认公网/生产式 Telegram 白名单入口是否已经关闭本地开放兜底：`TELEGRAM_REQUIRE_BINDING=true` 为通过；未开启严格绑定但存在环境白名单或 active 数据库绑定也为通过；未开启严格绑定且无白名单/active 绑定时为非阻塞 warning。该检查只读 API 状态，只输出计数和模式，不读取 `.env` 明文、不调用 `/telegram/bindings`、不发送 Telegram、不输出 token、secret 或 raw chat id。

模型 Provider readiness 仍是本地配置预检，不代表已启用真实多 agent 编排：

```powershell
uv run python infra/scripts/model_provider_readiness.py --json-output evidence/model-provider-readiness.json
```

默认禁用模型分析时该检查为 OK；显式启用后会检查 provider、primary/fallback model、API base URL 和 key 是否具备，不会发起网络请求或模型调用。`MODEL_AUDIT_STORE_RAW_PROMPT=true` 会作为 warning 出现，默认保持 false。

同一检查也可以纳入部署预检和交付验收：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-model-provider-readiness --model-provider-readiness-json-output evidence/model-provider-readiness.json
uv run python infra/scripts/server_delivery_acceptance.py --include-model-provider-readiness
```

`server_delivery_acceptance.py --production-readiness` 默认包含模型 Provider readiness，并在 evidence 目录写入 `model-provider-readiness.json`。warning 会进入最终验收汇总；只有 readiness `fail`、缺失或损坏 evidence 会阻断默认验收。

需要把 server compose runtime contract 检查纳入同一交付验收包时，可用 `server_delivery_acceptance.py --include-server-compose-contract-check`；该参数只会让 deploy preflight 阶段追加 `--check-server-compose-contract`，不新增独立阶段、不启动容器、不把该检查传给 backup/runtime/Telegram 阶段。

需要把这项静态 systemd 模板检查纳入同一交付验收包时，可用 `server_delivery_acceptance.py --include-systemd-unit-check`；该参数只会让 deploy preflight 阶段追加 `--check-systemd-units`，不新增独立 systemd 阶段、不启动服务、不读取凭据。

需要把 Telegram 严格绑定 readiness 纳入同一交付验收包时，可用 `server_delivery_acceptance.py --include-telegram-strict-binding-check`；该参数只会让 deploy preflight 阶段追加 `--check-telegram-strict-binding`，warning 会进入 `server-deploy-check.json` 和最终验收汇总，生产切换前可再配合 `--fail-on-warning` 阻断 warning-only 交付。

需要把 Tushare `anns_d` Beat enablement 离线/no-token checklist 纳入同一交付验收包时，可用 `server_delivery_acceptance.py --include-tushare-anns-d-beat-enablement`；该参数只会让 deploy preflight 阶段追加 `--check-tushare-anns-d-beat-enablement` 和 `--tushare-anns-d-beat-enablement-json-output <evidence-dir>/tushare-anns-d-beat-enablement.json`，不新增独立 Tushare 阶段、不访问 Tushare、不写数据库、不触发抓取或扫描。

需要把数据库迁移和应用表计数纳入同一交付验收包时，可用 `server_delivery_acceptance.py --include-database-inventory`；该参数会新增一个只读 `database_inventory` stage，写入 `<evidence-dir>/database-inventory.json`，不输出连接串、密码或行内容，不执行迁移、seed、采集、扫描、报告、推送或模型调用。

生产化交付前可用 `server_delivery_acceptance.py --production-readiness` 一次启用当前非破坏性验收预设：server compose runtime contract、systemd 模板静态检查、Telegram 严格绑定 readiness、Tushare `anns_d` Beat enablement checklist、模型 Provider readiness、严格 radar analysis 样本门禁、数据库只读清单、脱敏 OPS evidence、no-send alert payload / Telegram preview 和 Telegram alert env preflight。最终 JSON 会写入 `profile: "production_readiness"`；该预设不会启用手动 alert service evidence verification、严格 env 权限、`--fail-on-warning`、`--fail-fast`、restore、Telegram 发送、backup deletion、`systemctl` 或 `journalctl`，需要更严格门禁时仍要显式叠加对应参数。

需要在真实运行前预览交付验收命令和 evidence 路径时，可加 `--plan-only`，例如 `server_delivery_acceptance.py --plan-only --production-readiness`。该模式只写计划报告，不调用部署预检、runtime、backup、Telegram、Docker、API、`systemctl` 或 `journalctl`；JSON 顶层会写入 `execution_mode: "plan"` 和 `status: "planned"`，每个非跳过阶段状态为 `planned`，跳过阶段仍为 `skipped`。正常执行报告会写入 `execution_mode: "run"`。

Telegram 告警交付如果用于 cron/systemd，推荐加 `--dedupe-state evidence/server-alert-telegram-dedupe-state.json`。该本地 JSON 状态按 alert payload 的 `dedupe_key` 做默认 3600 秒冷却，只在全部 Telegram 发送成功后更新，避免服务器持续 warning 时重复刷屏；preview、配置错误、失败发送和无效 state 不会写入成功状态。

Linux 骨架提供可选 `infra/linux/baizefindb-alert-telegram.service`，用于手动从 systemd 调用上述交付 adapter。它读取服务器本地 `/etc/baizefindb/telegram-alert.env`，发送前会先运行 env 预检并写 `evidence/server-alert-telegram-env-check.json`；timer 需要在手动发送、env check 和 dedupe evidence 通过后单独复制启用。

Telegram 告警凭据文件可用 `infra/scripts/server_alert_telegram_env_check.py --env-file /etc/baizefindb/telegram-alert.env --json-output evidence/server-alert-telegram-env-check.json` 做只读预检；该报告只记录权限状态、token 是否配置、chat id 数量和 masked chat refs，不输出 token、raw chat id 或 env 文件内容。

手动启动 `baizefindb-alert-telegram.service` 后，可用 `infra/scripts/server_alert_telegram_service_verify.py --json-output evidence/server-alert-telegram-service-verification.json` 验证 env check、send evidence 和 dedupe state 是否足以进入后续调度设计；`sent` / `deduped` 且 dedupe state 有效为 `ok`，`skipped` 为非阻塞 `warn`，preview、配置错误、发送失败、损坏或缺失 evidence 为 `fail`。

同一预检也可以纳入交付验收包：`infra/scripts/server_delivery_acceptance.py --include-alert-telegram-env-check` 会额外生成 `evidence/server-delivery-acceptance/server-alert-telegram-env-check.json`；生产交付时可加 `--telegram-alert-env-strict-permissions`，让凭据文件权限过宽直接阻断验收。

如果已经手动运行过 `baizefindb-alert-telegram.service`，交付验收还可加 `--include-alert-telegram-service-verify`，把 `server_alert_telegram_service_verify.py` 的只读报告写入同一 acceptance evidence 目录；该阶段只读取已有 env-check、send 和 dedupe-state JSON，不启动 systemd、不发送 Telegram。

通过手动 service verification 后，Linux 骨架提供可选 `infra/linux/baizefindb-alert-telegram.timer` 示例；它每 5 分钟触发一次 alert delivery service，启动时间比 monitor timer 晚 1 分钟，便于读取最新 `server-alert-payload.json`。该 timer 不默认启用，不包含 secrets 或发送命令，复制启用前先确认 monitor timer、手动发送和 dedupe evidence 都已通过。

## Windows 客户端 MVP

Windows 客户端位于 [clients/windows/](clients/windows/)，默认是源码运行版。仓库提供可选 PyInstaller onedir 打包脚手架，用于开发者在 Windows 目标机验证 exe 形态；它不是签名安装器或生产分发包。

首次 Windows 试运行推荐使用一条命令完成只读 smoke check 和 GUI 启动：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1
```

默认值是 `ServerUrl=http://127.0.0.1:8000`、`UserKey=default`、
`SmokeLookbackHours=24`。该脚本只委托 `run-client.ps1 -SmokeCheck`，不复制
smoke check 或 GUI 逻辑。

如果本机还没有启动后端，且确认要用 Docker Desktop 跑本地服务，可以显式加
`-StartDockerBackend`。该模式会使用 `docker-compose.yml` 和
`docker-compose.server.yml` 先重建当前源码的 `api` 镜像，确保 `/ops/trends` 等新端点
存在，再启动 `postgres` / `redis`，通过 `api` 容器执行 `alembic upgrade head`，
启动 `api` / `worker` / `beat`，等待 `<ServerUrl>/health` 可访问后才委托同一套
smoke check 和 GUI 启动。Docker build / 启动 / 迁移失败都会在 smoke 或 GUI 前退出，不会
对远端 URL 隐式发生，必须显式 opt-in；可用 `-BackendHealthTimeoutSeconds` 和
`-BackendHealthPollIntervalSeconds` 调整有界等待：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1 -StartDockerBackend
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1 -StartDockerBackend -SeedDemoDataJsonOutput evidence/demo-seed.json -DatabaseInventoryJsonOutput evidence/database-inventory.json -DeployCheckJsonOutput evidence/server-deploy-check.json -DeployCheckServerComposeContract -DeployCheckM5Smoke -DeployCheckRequireRadarAnalysisSample -DeployCheckBackupJsonOutput evidence/postgres-backup-check.json -SmokeCompactJsonOutput evidence/windows-client-smoke-compact.json
```

也可以单独跑只读 smoke check：

```powershell
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default
```

可选缩短 OPS readiness 统计窗口，用来区分最近健康状态和历史 Provider / 数据质量 warning；默认 24 小时，范围 1 到 168：

```powershell
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default --ops-readiness-lookback-hours 6
```

本地连接：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000
```

用 launcher 一次完成 preflight 和 GUI 启动：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default -SmokeCheck
```

如果 API 已经在运行，只想执行同一套首用 smoke check 并退出、不打开 GUI：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default -SmokeOnly
```

如果要先启动本机 Docker 后端、等待健康检查，然后只跑 smoke check 并退出：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1 -StartDockerBackend -SmokeOnly
```

严格门禁和首次试运行 evidence 推荐使用 compact JSON；详细 JSON 仍保留给深度排障：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1 -SmokeLookbackHours 6 -SmokeCompactJsonOutput evidence/windows-client-smoke-compact.json -SmokeStrict
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default -SmokeCheck -SmokeLookbackHours 6 -SmokeCompactJsonOutput evidence/windows-client-smoke-compact.json -SmokeStrict
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default --json-output evidence/windows-client-smoke.json
```

连接服务器：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl https://<your-domain>
```

可选 onedir 打包脚手架：

```powershell
uv sync --group package
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1
```

也可以先 dry run 预览命令；该模式不要求已安装 PyInstaller，也不会生成构建产物：

```powershell
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -DryRun
```

需要验证真实打包前置条件但不生成产物时，用 check-only：

```powershell
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -CheckOnly
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -CheckOnly -CheckJsonOutput clients/windows/package-check-evidence.local.json
```

脚本入口仍是 `clients.windows.baizefindb_client`，默认输出 `clients/windows/dist/BaizeFinDB-Windows-Client/`，中间文件在 `clients/windows/build/`；PyInstaller 通过可选 `package` 依赖组复现，不进入默认运行时或普通 dev 路径。`-DryRun` 会反映自定义 `-Name`、`-DistPath`、`-WorkPath` 和 `-Clean`，并跳过 Python/PyInstaller 检查和所有产物创建。`-CheckOnly` 会运行 Python 3.12、`tkinter` import、入口模块解析 preflight 和 PyInstaller 可用性检查，然后在创建目录、launcher 或调用 PyInstaller 构建前退出；它不能和 `-SkipPreflight` 同用。`-CheckJsonOutput` 只能和 `-CheckOnly` 同用，写出的有界 JSON 只包含打包前置条件、命令和路径元数据；`clients/windows/package-check-evidence*.json` 已忽略，不提交本地证据。非 dry-run 默认先做轻量 Python preflight，验证 Python 3.12、`tkinter` import 和入口模块解析，不创建 `tk.Tk()`、不打开 GUI、不调用 API；特殊本地排查可加 `-SkipPreflight`。生成物和 `*.spec` 已加入 `.gitignore`，不要提交 exe 或构建目录。该脚手架不做 onefile、MSI、代码签名、SmartScreen 信誉或自动更新。

smoke check 会验证 Tkinter 可导入、核心健康、readiness GET 和可选 OPS trends GET；首次试运行推荐 `--compact-json-output` / `-SmokeCompactJsonOutput` 保存 compact evidence，只包含总体状态、服务端 URL 元数据、脱敏 user key、检查数、每项检查的 name/status/message、warning/blocker 和 OPS readiness 非 OK 摘要，不包含端点 payload、原始后端响应、环境变量、token、secret、API key、authorization、原始 provider URL、个人持仓、二进制或构建输出；`--json-output` / `-SmokeJsonOutput` 仍可写出有界脱敏详细 JSON 用于深度排障。`first-trial.ps1 -StartDockerBackend -SeedDemoDataJsonOutput <path>` 可在 Docker 后端健康后、database inventory/deploy preflight/smoke/GUI 前写入可重复复用的 synthetic demo 数据并保存 evidence，失败时阻断后续启动；`first-trial.ps1 -StartDockerBackend -DatabaseInventoryJsonOutput <path>` 可在 Docker 后端健康后、deploy preflight/smoke/GUI 前保存脱敏数据库只读清单 JSON，失败时阻断后续启动；`first-trial.ps1 -StartDockerBackend -DeployCheckJsonOutput <path>` 可在 Docker 后端健康后、smoke/GUI 前保存服务端部署预检 JSON，失败时阻断后续启动；加 `-DeployCheckServerComposeContract` 会把 server compose runtime contract 纳入同一次 deploy preflight，只追加后端脚本参数，不在 PowerShell 中解析 compose；加 `-DeployCheckM5Smoke` 会把服务端只读 M5 JSON 契约也纳入该报告；加 `-DeployCheckRequireRadarAnalysisSample` 会把 M5 smoke 中缺少可抽样雷达信号从 warning 升级为失败，适合 demo seed 或真实扫描后确认 `/radar/signals/{id}/analysis` 契约确实被覆盖；加 `-DeployCheckBackupJsonOutput <path>` 会在同一次部署预检中额外保存 PostgreSQL backup check-only evidence。空雷达、空信号、空绑定和可选 `/ops/trends?lookback_hours=<selected>&bucket_count=12` 失败是 warning，不是 blocker。`first-trial.ps1` 是推荐的首次试运行入口，默认委托 `run-client.ps1 -SmokeCheck` 并传入 localhost、`default` 用户键和 24 小时 OPS readiness/trends 窗口；`run-client.ps1 -SmokeCheck` 会在启动 GUI 前执行同一套检查并传入相同 ServerUrl/UserKey；`-SmokeLookbackHours` 会把 1 到 168 小时的 OPS readiness 窗口和可选 trends 窗口传给 smoke check，默认 24；`-SmokeStrict` 会让 warning 阻断启动，默认 warning 仍不阻断。GUI 的 `OPS Lookback (hours)` 同样默认 24，范围 1 到 168，并传给 `/ops/overview`、`/ops/history`、`/ops/readiness` 和 `/ops/trends?lookback_hours=<selected>&bucket_count=12`；`告警钻取` 按钮用同一个窗口顺序读取 `/ops/readiness`、`/ops/overview` 和 `/ops/history`，优先显示后端 readiness 状态、非 OK 检查、overview alerts、failure_summary 和有界最近事件，不本地重算 OPS 状态、不写 evidence；`首用诊断` 按钮复用同一套 `run_smoke_check` 和 `format_summary`，传入当前 Server URL、User Key 和 OPS Lookback，只在窗口内显示摘要，默认不写 evidence 文件，也不打开第二个 GUI 窗口；非法输入会在 API 请求前阻断。客户端只消费后端 API，不重新计算 P0/P1/P2、生命周期、市场情绪、运行状态、OPS readiness、数据源状态、审查状态或评分；`生成 Deep Report` 会先确认，再调用 `/reports/deep/from-signal?user_key=<User Key>` 并发送 `confirm_deep_report=true`，报告正文、审查状态和建议标签仍由后端生成；Tushare 状态/自检按钮只读取 `/providers/tushare/status` 和 `/providers/tushare/readiness`，不触发真实抓取；持仓/自选/报告/日报/周报按 User Key 读取，只作为个人上下文；Telegram 绑定查看会读取 `/telegram/status` 和 `/telegram/bindings` 显示严格绑定模式与汇总计数，绑定和禁用仍只调用绑定 API；不保存 token、secret、Tushare token 原文、持仓截图、报告导出或个人数据；不提供买卖建议、不接自动交易、不承诺收益。详细说明见 [docs/runbooks/windows-client.md](docs/runbooks/windows-client.md)。

## Telegram Bot MVP

`.env` 可选配置：

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_REQUIRE_BINDING=false
TELEGRAM_PUSH_ENABLED=false
OPS_DISK_CHECK_PATH=.
OPS_DISK_FREE_PERCENT_ALERT_THRESHOLD=10
OPS_CPU_USAGE_PERCENT_ALERT_THRESHOLD=90
OPS_MEMORY_USED_PERCENT_ALERT_THRESHOLD=90
```

- `TELEGRAM_BOT_TOKEN` 留空时，`POST /telegram/webhook` 不会调用 Telegram Bot API，而是返回 `preview`，方便本地测试。
- `TELEGRAM_ALLOWED_CHAT_IDS` 可填逗号分隔的 chat id；配置后只有白名单 chat 会被处理。
- `TELEGRAM_WEBHOOK_SECRET` 配置后，Webhook 必须携带 `X-Telegram-Bot-Api-Secret-Token`。
- `TELEGRAM_REQUIRE_BINDING=true` 会关闭无白名单、无绑定时的本地开放模式；生产/公网部署建议开启，并先用 `/id` 获取 chat id 后写入 `/telegram/bindings`。
- 生产/公网部署前可运行 `uv run python infra/scripts/server_deploy_check.py --check-telegram-strict-binding`，只读检查 `/telegram/status`；如果严格绑定未开启且没有环境白名单或 active 数据库绑定，会记录 warning，但不输出 token、secret 或 raw chat id。
- `TELEGRAM_PUSH_ENABLED=true` 后，Celery 扫描任务会向白名单 chat 发送最新扫描的折叠推送；留空或 false 时只保留手动 API 调试。
- P0 信号完成折叠推送后，会为对应 `user_key=telegram-<chat_id>` 自动生成一份 `standard` report；重复推送同一扫描不会重复生成。
- `/telegram/bindings` 可把 chat id 绑定到指定 `user_key` 并控制是否允许；配置 `TELEGRAM_ALLOWED_CHAT_IDS` 时，环境白名单仍是硬过滤；未配置环境白名单且无绑定时默认仅本地开放，`TELEGRAM_REQUIRE_BINDING=true` 会要求必须有 active 绑定。
- `/health` 返回 API、数据库、Redis 和最近一次雷达扫描摘要。
- `/ops` 返回服务端运行时、磁盘/CPU/内存、最近运行状态、扫描失败率、Provider、数据质量、推送、模型调用和告警摘要。
- `/ops_history` 返回最近运维异常历史和异常汇总，不触发采集、扫描、推送或模型调用。
- `/ops_ready` 返回运行就绪自检，不触发采集、扫描、推送或模型调用。
- `/ops_warn` 返回 OPS 告警钻取，固定使用 Telegram 24 小时窗口和有界历史条数，只读复用后端 readiness、overview 和 history 结果，不在 Telegram 层重算 OPS 状态，也不触发采集、扫描、评分、报告、推送、模型调用、evidence 写入、后端修改或交易相关动作。
- `/tushare` 返回 Tushare token 配置、手动抓取启用状态和已实现端点数；不返回 token 原文，不触发真实抓取。
- `/tushare_ready` 返回 Tushare token、端点、最新抓取、数据质量准入状态和 `anns_d` Beat 开关策略；不返回 token 原文，不触发真实抓取或调度。
- `/analysis <id>` 读取 `/radar/signals/{signal_id}/analysis` 的后端单信号研究摘要，展示 key points、metric highlights、risk flags、evidence/review summary 和 next actions；Telegram 不本地生成分析、不展示 raw source、raw excerpt、精确信心值、个人持仓字段或交易指令。
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

查看当前数据库迁移、表和关键业务表计数，不输出连接串、密码或行内容：

```powershell
uv run python infra/scripts/database_inventory.py --json-output evidence/database-inventory.json
```

新库只完成迁移后仍是空业务库。需要让 Web、Windows 客户端、Telegram 和
M5 smoke check 立刻有样例可用时，可写入可重复执行的开发/演示数据：

```powershell
uv run python infra/scripts/seed_demo_data.py --json-output evidence/demo-seed.json
```

该命令只写合成 demo 用户、持仓/自选、雷达信号、证据、审查和报告；
不访问真实数据源、不写 token、不包含真实个人持仓、不提供交易建议。重复执行会复用
稳定 demo key，不重复膨胀业务表。

验证 AKShare 最小接口，不写数据库：

```powershell
uv run python infra/scripts/verify_akshare_minimal.py
```

验证 Tushare `stock_basic`，不写数据库：

```powershell
uv run python infra/scripts/verify_tushare_stock_basic.py --json-output evidence/tushare-stock-basic.json
uv run python infra/scripts/check_tushare_anns_d_beat_enablement.py --json-output evidence/tushare-anns-d-beat-enablement.json
uv run python infra/scripts/verify_tushare_anns_d_preflight.py
uv run python infra/scripts/verify_tushare_announcements.py --ann-date 20260503 --json-output evidence/tushare-anns-20260503.json
uv run python infra/scripts/verify_tushare_stock_company.py --exchange SZSE --json-output evidence/tushare-stock-company-SZSE.json
```

`check_tushare_anns_d_beat_enablement.py` 输出 JSON checklist，默认离线/no-token，不访问 Tushare、不写数据库、不触发抓取、扫描或推送；可用 `--json-output evidence/tushare-anns-d-beat-enablement.json` 保存同一份 checklist evidence。它会汇总本地 sample gate、`golden_cases/radar_m5_risk_announcements.json` 雷达风险公告 golden gate、`TUSHARE_TOKEN`、`TUSHARE_ANNS_D_BEAT_ENABLED`、`TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS`、仍需 live verify、readiness/live data 默认未检查等状态；只有显式加 `--check-readiness` 时才会做只读 readiness HTTP GET。

部署预检需要一起检查该 checklist 时使用：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-tushare-anns-d-beat-enablement --tushare-anns-d-beat-enablement-json-output evidence/tushare-anns-d-beat-enablement.json
```

该集成仍是离线/no-token 模式，终端和 `server-deploy-check.json` 输出精简摘要；`--tushare-anns-d-beat-enablement-json-output` 会额外保存原始 checklist evidence。`warn` 不阻断部署预检，只有 checklist `fail` 会返回失败退出码。

`verify_tushare_anns_d_preflight.py` 不需要 `TUSHARE_TOKEN`，只读取本地 golden case，检查 `anns_d` 归一化必需字段、重大风险公告应映射 risk P0，以及普通公告不应产生风险信号。`check_tushare_anns_d_beat_enablement.py` 默认还会读取 `golden_cases/radar_m5_risk_announcements.json`，确认 Tushare 公告 risk P0 / 普通公告无信号的完整规则样例没有漂移。该完整扫描 golden case 文件要求每个 case 声明 `case_type`，取值为 `true_positive_major_risk`、`true_positive_critical_risk`、`false_positive_guard`、`false_negative_guard` 或 `ordinary_no_signal`，并可选填写 `source` / `notes`；默认套件必须同时覆盖真阳性风险、无信号守卫和误报/漏报反馈守卫。后续真实误报/漏报样例优先追加到该文件。它们是启用 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 前的预调度门禁和调参基线，但不能替代真实 `TUSHARE_TOKEN` 权限、积分消耗、实时接口字段和 `/providers/tushare/readiness` 验证。

`verify_tushare_stock_basic.py`、`verify_tushare_announcements.py` 和 `verify_tushare_stock_company.py` 都支持 `--json-output <path>`，会在真实 token 可用时保存一份脱敏 live evidence JSON；报告只保留状态、端点、查询参数、行数、质量状态、必需字段、缺失字段和少量去 URL/source/token/secret-like 字段的归一化样例，样例值会递归脱敏并截断超长文本，失败时也会写入脱敏 failure report。启用 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 前，应先保留 offline checklist / preflight 结果，再保存 announcements live evidence；`stock_basic` 和 `stock_company` evidence 用于同步留存 token 权限、积分和字段稳定性。

`evidence/`、`runtime-check*.json` 和 `ops-evidence*.json` 是本地运行证据产物，默认已加入 `.gitignore`，不要提交真实 token 环境下生成的报告。

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

Beat 默认每 300 秒触发一次 `baizefindb.radar.collect_and_scan`，顺序执行最小 AKShare 采集和雷达扫描。可通过 `.env` 的 `RADAR_SCAN_INTERVAL_SECONDS` 调整本地/服务器调度间隔；`RADAR_CONTINUOUS_P1_TRIGGER_COUNT` 和 `RADAR_CONTINUITY_WINDOW_MINUTES` 控制连续 P1 快报候选阈值，默认 30 分钟内连续 3 次。Tushare `anns_d` 公告 Beat 调度默认关闭；只有设置 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 后才额外加入 `baizefindb.providers.collect_tushare_announcements`，间隔由 `TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS` 控制，默认 3600 秒。改成 `true` 前先执行 `check_tushare_anns_d_beat_enablement.py --json-output <path>` 和离线 `verify_tushare_anns_d_preflight.py`，再用 `verify_tushare_announcements.py --json-output <path>` 保存脱敏 live evidence，并确认真实 token 权限、积分消耗和 `/providers/tushare/readiness`。

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
uv run python infra/scripts/dev_environment_check.py
uv run pytest
uv run ruff check .
uv run alembic heads
uv run alembic upgrade head --sql
```

## 开发边界

当前已完成 M4 轻量审查层闭环：只基于已入库 AKShare 快照生成候选信号、总览、规则审查结果和脱源脱敏分享预览，连续 P1 只标记为快报候选；不接自动交易，不提供交易建议。M5 的真实 MVP 是 A 股 5 分钟资金主线雷达，Telegram、Web、报告、持仓自选、日报周报和评分只消费雷达结果或向后端发命令。

当前真实数据表与未来规划表的边界见 [docs/specs/current-data-model.md](docs/specs/current-data-model.md)。进入 M5 前先阅读 [docs/prd/m5-next-step.md](docs/prd/m5-next-step.md)，按雷达优先顺序推进，不再按 Telegram/报告/Web 三选一拆分下一阶段。
