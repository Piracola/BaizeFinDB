# BaizeFinDB Project Status

更新日期：2026-05-04

## 当前阶段

当前已完成 **M5 A 股 5 分钟资金主线雷达 MVP 验收项**，下一阶段进入生产化验证、真实数据源增强和运行稳定性建设。

项目已经具备后端骨架、AKShare 最小数据底座、Tushare `stock_basic`、`anns_d` 和 `stock_company` 手动抓取能力、Tushare 只读准入自检、Tushare 重大风险公告到 risk P0 的轻量映射、雷达扫描批次、候选信号、证据链、P0/P1/P2 初判、生命周期初判、连续扫描记忆、雷达总览查询、优先级和生命周期分布、Web/Telegram/Windows 市场情绪摘要、个股回推证据、涨停/跌停/炸板池情绪摘要、Provider 数据质量透传、只读运维状态、服务端磁盘/CPU/内存摘要、运维历史和运行就绪自检、轻量规则审查、内部分享预检、公开分享 payload、持仓/自选最小维护 API、quick/standard 报告 MVP 和 Telegram 折叠推送日志。

Telegram Bot MVP Webhook 模块已补充为当前命令入口，可查看健康状态、运行状态、运维历史、运行就绪自检、Tushare 数据源状态和准入自检、最近扫描状态、雷达总览、生命周期分布、市场情绪摘要、个股回推证据、信号折叠摘要、单条信号复盘、当前聊天绑定的持仓、自选、报告列表、日报/周报和单信号 v2 评分档位与组件明细；`telegram_bindings` 已接入 chat 与 `user_key` 绑定、白名单和禁用状态，环境变量 `TELEGRAM_ALLOWED_CHAT_IDS` 仍可作为硬过滤；Telegram 折叠推送 API 已能基于最新扫描按 P0/P1/P2 汇总、复用审查过滤 blocked、记录 push log，并在 P0 推送后为对应聊天用户自动生成 standard report。Telegram 仍只消费后端结果，不重新计算雷达等级、运行状态、数据源状态或评分。

M5 验收测试已覆盖 5 分钟 Celery beat 调度、P0/P1/P2 规则、新闻不能单独触发主线 P0、风险事件 P0、生命周期、Review Agent 审查范围、审查阻断、Telegram 折叠推送、P0 推送后 standard report、持仓隔离、报告审查、deep 报告预留约束、模型降级审计、Web 核心页面顺序和公开分享脱敏。

Windows 客户端 MVP 已补充为本地桌面入口，可连接本地或 Linux 服务器 API，查看健康状态、运行状态、运维历史、运行就绪自检、Tushare 数据源状态和准入自检、雷达总览、生命周期分布、市场情绪摘要、个股回推证据、信号列表、持仓、自选、报告摘要、日报/周报汇总、单信号 1d/3d/5d/10d v2 综合评分明细，维护 Telegram chat 绑定/白名单，并打开现有 Web 面板；它仍只消费后端结果，不重新计算雷达等级、运行状态、数据源状态或评分，也不是完整安装包。Tushare 状态/自检视图只读取 `/providers/tushare/status` 和 `/providers/tushare/readiness`，不触发真实抓取。

Web 雷达终端工作台、Windows 客户端和 Telegram `/tushare` 已展示 Tushare token 状态、手动抓取启用状态和已实现端点数；`/providers/tushare/readiness`、Web 数据源状态卡片、Windows“数据源自检”按钮和 Telegram `/tushare_ready` 已展示 token、端点、最近抓取和数据质量准入状态。所有这些入口都只读，不触发真实抓取或调度。

Linux 服务端部署骨架已完成：包含 API Dockerfile、server compose overlay、部署预检脚本、运行采样脚本、PostgreSQL 备份/恢复脚本、Ubuntu runbook、systemd 示例和 nginx HTTPS 反代示例；部署预检可选验证 `pg_dump` 可用性，并可执行只读 M5 smoke check 验证健康、Ops、Ops history、Ops readiness、AKShare Provider、Tushare Provider、Radar 和 Telegram 状态接口 JSON 契约；运行采样脚本可连续读取健康、Ops、运维历史和就绪状态，生成 JSON 验收记录并在接口失败或 readiness `blocked` 时返回失败退出码。Ops 已能生成扫描停滞、失败率、服务端磁盘/CPU/内存资源压力和 unhealthy 计数告警摘要，Ops history 已能只读列出最近扫描和运行异常历史，Ops readiness 已能给出运行就绪自检结果。该状态只代表部署骨架完成，不代表完整生产部署完成。

5 分钟调度 MVP 已接入 Celery beat：默认每 300 秒执行 `baizefindb.radar.collect_and_scan`，顺序完成 AKShare 最小采集和雷达扫描；当 `TELEGRAM_PUSH_ENABLED=true` 时会追加 Telegram 折叠推送；服务器 compose overlay 已补充 worker / beat 服务。

持仓/自选最小 API 已接入：支持按 `user_key` 手工维护持仓和自选，成本价与仓位比例可为空；静态 Web 终端工作台已能查看运行状态、维护和展示这些个人数据。跨 API 测试已锁定这些个人数据只影响后续个人提醒、展示排序和报告上下文，不改变市场级 P0/P1/P2、生命周期分布或当前主题。

报告 MVP 已接入：`/reports/from-signal` 可从雷达信号生成 quick/standard 模板报告；生成前复用轻量规则审查，blocked 信号不会生成报告，needs_human_review 报告会显式标记；报告发布前审查不受信号候选范围限制，确保发布前安全门始终执行；`deep` 已作为报告类型预留，但不会被 `/reports/from-signal` 自动或普通手动创建。`/reports/periodic` 可按日/周生成当前 `user_key` 的雷达汇总报告。`/scores/signals/{signal_id}` 可生成 1d/3d/5d/10d v2 综合评分记录，已纳入 Provider 数据质量、信号时效性、评分档位和权重说明。静态 Web 已改为雷达终端工作台外壳，可从信号详情生成报告、查看报告列表、生成日报/周报、查看单信号评分档位和组件明细，并维护 Telegram chat 绑定/白名单。

模型审计底座已接入：`model_call_logs` 可记录模型失败后的 `degraded` 或 `fallback` 状态、调用点、模型名、错误摘要、prompt hash 和 prompt 长度；默认不保存完整 `raw_prompt`，只有显式设置 `MODEL_AUDIT_STORE_RAW_PROMPT=true` 或调用方主动开启时才保存。

当前仍然是投研辅助系统，不是交易系统，不提供买卖建议。

下一阶段开发基线切换为 **M5 生产化验证和真实数据增强**。核心是让现有雷达闭环在 Docker / Linux 服务器上可持续运行、可观测、可恢复，并逐步接入更稳定的真实公告、监管、情绪和后续评分校准数据源。

当前长期开发规范：

- 后续 AI 协作默认在模块设计或开发阶段完成后自动做 git commit，不再每次向用户确认；不自动 push。
- 即使是小的模块化更新，只要形成明确阶段边界，也要同步更新相关开发文档并提交 git commit。
- 提交前先跑对应质量检查，再查看 `git status`，并检查 staged 文件，确认没有误提交 `.env`、密钥、个人数据、原始付费数据、持仓截图、报告导出等敏感文件。
- commit 仍按模块边界拆分，不把多个无关模块混成一个大提交。
- commit message 要能看懂模块和动作，例如 `docs(prd): refine radar mvp`、`feat(radar): add scan scheduler`、`test(radar): cover p1 continuity`、`docs(dev): add git workflow`。
- 文档、迁移、测试和代码随模块一起提交；只完成设计文档时，也要提交文档版本。
- 大模块拆成设计文档、数据模型/迁移、业务实现、测试/文档等多个 commit。
- 发现未识别的脏文件或疑似用户手工改动时，不能自动纳入提交，要隔离并说明。

## 开发文档入口

- [开发文档导航](README.md)
- [本地开发 Runbook](runbooks/local-dev.md)
- [Linux 服务端部署骨架 Runbook](runbooks/linux-server.md)
- [Windows 客户端 MVP Runbook](runbooks/windows-client.md)
- [当前 API 文档](api/current-api.md)
- [当前数据模型说明](specs/current-data-model.md)
- [M5 A 股 5 分钟资金主线雷达 MVP PRD](prd/m5-next-step.md)

## 已完成

| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| M1 工程骨架 | 已完成 | FastAPI、配置系统、健康检查、SQLAlchemy async、Alembic、Docker Compose、Celery 壳、pytest。 |
| M2 数据底座 | 已完成早期闭环 | AKShare 行情/行业/概念最小 Provider，采集日志、快照、质量检查、Provider 查询 API；Tushare `stock_basic`、`anns_d` 和 `stock_company` 已支持手动抓取、失败记录、日志、快照查询和只读准入自检，`anns_d` 重大风险公告可被后续雷达扫描映射为 risk P0，尚未纳入调度。 |
| M3 雷达核心 | 已完成早期闭环 | 基于已入库快照生成雷达候选信号，写入扫描批次、信号和证据，并提供最新总览视图；普通扫描异常会落 `failure` 状态。 |
| M4 审查层 | 已完成 | 轻量规则审查可对单个雷达信号给出 `approved`、`blocked`、`needs_human_review`，并记录审查历史；Provider 数据质量、证据冲突、重复触发、来源过期和分享安全门已进入审查判断。 |
| M5 A 股 5 分钟资金主线雷达 MVP | 验收项完成 | 静态 Web 终端工作台、Telegram Bot MVP、Windows 客户端 MVP、Celery 5 分钟采集后扫描调度、持仓/自选最小 API、quick/standard 报告、日报/周报、1d/3d/5d/10d v2 综合评分、Telegram 折叠推送、P0 推送后 standard report、风险 P0、Review Agent 范围控制、模型降级审计、运行状态汇总和只读 M5 smoke check 已接入。 |
| Linux 服务端部署骨架 | 已完成 | 已有 API Dockerfile、`docker-compose.server.yml`、worker/beat、`infra/scripts/server_deploy_check.py` 部署预检（含可选 `pg_dump` 可用性检查和只读 M5 smoke check，覆盖 `/ops/overview`、AKShare 状态和 Tushare 状态）、`infra/scripts/server_runtime_check.py` 运行采样脚本、`infra/scripts/postgres_backup.py` PostgreSQL 备份脚本、`infra/scripts/postgres_restore.py` PostgreSQL 恢复脚本、`infra/linux/` runbook、systemd 示例和 nginx HTTPS 反代示例；`/ops/overview` 和 `/ops/readiness` 已包含磁盘、CPU、内存资源摘要和压力告警；尚不是完整生产部署。 |

## 当前可用 API

健康检查：

- `GET /health`
- `GET /health/ready`

Ops：

- `GET /ops/overview`
- `GET /ops/history`
- `GET /ops/readiness`

Provider：

- `GET /providers/akshare/endpoints`
- `GET /providers/tushare/endpoints`
- `GET /providers/tushare/status`
- `GET /providers/tushare/readiness`
- `POST /providers/tushare/fetch/stock-basic`
- `POST /providers/tushare/fetch/announcements`
- `POST /providers/tushare/fetch/stock-company`
- `GET /providers/tushare/fetch-logs`
- `GET /providers/tushare/snapshots/latest`
- `POST /providers/akshare/fetch/minimal`
- `GET /providers/akshare/status`
- `GET /providers/akshare/fetch-logs`
- `GET /providers/akshare/snapshots/latest`

Portfolio：

- `GET /portfolio/holdings`
- `POST /portfolio/holdings`
- `PATCH /portfolio/holdings/{holding_id}`
- `DELETE /portfolio/holdings/{holding_id}`
- `GET /portfolio/watchlist`
- `POST /portfolio/watchlist`
- `PATCH /portfolio/watchlist/{item_id}`
- `DELETE /portfolio/watchlist/{item_id}`

Reports：

- `POST /reports/from-signal`
- `GET /reports`
- `GET /reports/{report_id}`
- `GET /reports/periodic`

Scores：

- `POST /scores/signals/{signal_id}`
- `GET /scores/signals/{signal_id}`

Radar：

- `POST /radar/scans/run`
- `GET /radar/scans/latest`
- `GET /radar/scans/{scan_id}`
- `GET /radar/overview`
- `GET /radar/signals`
- `GET /radar/signals/{signal_id}`
- `POST /radar/signals/{signal_id}/review`
- `GET /radar/signals/{signal_id}/reviews`
- `GET /radar/signals/{signal_id}/share-preview`
- `GET /radar/signals/{signal_id}/share-payload`

Telegram：

- `GET /telegram/status`
- `POST /telegram/webhook`
- `GET /telegram/bindings`
- `POST /telegram/bindings`
- `PATCH /telegram/bindings/{chat_id}`
- `POST /telegram/push/latest`
- `GET /telegram/push/logs`
- Telegram 命令：`/help`、`/id`、`/health`、`/ops`、`/ops_history`、`/ops_ready`、`/tushare`、`/radar`、`/signals`、`/signal <id>`、`/holding`、`/watchlist`、`/reports`、`/daily`、`/weekly`、`/score <id>`；`/health` 展示最近扫描状态，`/ops` 展示运行状态摘要，`/ops_history` 展示只读运维异常历史，`/ops_ready` 展示运行就绪自检，`/tushare` 展示 Tushare 只读配置状态，`/score` 展示后端 v2 评分档位和组件明细

Windows 客户端：

- `clients/windows/run-client.ps1`
- `clients/windows/baizefindb_client.py`
- `clients/windows/client_api.py`

后台调度：

- `baizefindb.radar.collect_and_scan`：Celery beat 默认每 300 秒触发，先采集 AKShare 最小数据，再运行雷达扫描；`TELEGRAM_PUSH_ENABLED=true` 时追加 Telegram 折叠推送。
- `baizefindb.telegram.push_latest_radar`：手动触发最新扫描的 Telegram 折叠推送。
- `RADAR_SCAN_INTERVAL_SECONDS`：调度间隔环境变量，默认 `300`。
- `RADAR_CONTINUOUS_P1_TRIGGER_COUNT`：连续 P1 快报候选触发次数，默认 `3`。
- `RADAR_CONTINUITY_WINDOW_MINUTES`：连续 P1 计算窗口，默认 `30`。

## 当前数据表

以下为当前已经由 Alembic 迁移创建的真实数据表。路线图中的未来表请不要当成已实现能力，详情见 [specs/current-data-model.md](specs/current-data-model.md)。

- `schema_health_checks`
- `market_snapshots`
- `provider_fetch_logs`
- `data_quality_checks`
- `users`
- `portfolio_holdings`
- `watchlist_items`
- `reports`
- `push_logs`
- `score_records`
- `telegram_bindings`
- `model_call_logs`
- `radar_scan_batches`
- `radar_signals`
- `radar_signal_reviews`
- `signal_evidences`

## 当前规则能力

- 基于板块/概念涨幅、上涨家数、下跌家数、联动宽度生成 P0/P1/P2 候选信号；涨停、跌停和炸板池快照会进入扫描 summary，并透传到主线信号 metrics 作为情绪确认信息；普通新闻快讯不会进入主线 P0，`risk_events` 等重大风险事件快照和 Tushare `anns_d` 中明显重大风险公告可按重大公告、监管或黑天鹅口径单独生成 risk P0。
- M5 规则基线要求板块/主题/概念权重大于单票异动；单票异动优先用于反推板块/概念/风险。
- 主线 P0 不能只由新闻触发，必须有资金、板块联动或市场情绪确认；风险 P0 可由重大公告、监管或黑天鹅单独触发。
- 基于涨幅和联动宽度初判生命周期：`ignition`、`developing`、`climax`。
- 强度等级和生命周期必须分开处理，AI 只能解释、补证据和提示分歧，不能覆盖规则定级。
- 根据同一板块/概念的历史信号记录连续性。
- 当前实现为默认 30 分钟窗口内连续 3 次 P1 会标记为 `quick_report_candidate`；触发次数和窗口可通过环境变量调参。
- P2 默认保留 7 天观察：`/radar/overview` 和 `/radar/signals` 默认隐藏超出观察窗口的 P2；历史排查可在信号列表使用 `include_expired_p2=true`。
- 前后扫描走弱会记录生命周期转移，例如 `climax_to_divergence`。
- 总览 API 基于最新扫描生成当前活跃信号、P0/P1/P2 聚合、生命周期分布、市场情绪摘要、个股回推证据和按板块/概念去重视图；Web、Telegram 和 Windows 只展示该摘要，不在客户端重算。
- 雷达扫描 summary、信号 metrics 和 evidence details 会携带 Provider 数据质量摘要和市场情绪摘要。
- 轻量审查层会拦截诱导交易语言、证据缺失、失败数据质量和低置信度证据；降级/未知数据质量、证据冲突、重复触发和来源过期会进入人工复核；信号候选审查范围限制为 P0、连续 P1 快报、risk、holding/watchlist 相关候选，报告发布前审查始终执行。
- 诱导交易语言规则已覆盖基础禁词、常见热词、空格/标点拆分变体，并允许“不要马上买入”“禁止满仓”这类安全警示反例。
- `share-preview` 是内部预检接口，可以返回审查状态、阻断原因和脱敏记录。
- `share-payload` 是公开分享 payload，只在通过审查且分享策略安全时返回；它隐藏原始 URL、域名、原文摘录、内部证据详情、原始枚举、精确置信度和来源时间。

## 常用命令

```powershell
uv sync --dev
uv run pytest
uv run ruff check .
uv run alembic heads
uv run alembic upgrade head --sql
```

Docker / PostgreSQL 可用后：

```powershell
docker compose up -d postgres redis
uv run alembic upgrade head
uv run python infra/scripts/collect_akshare_minimal.py
uv run python infra/scripts/verify_tushare_stock_basic.py
uv run python infra/scripts/collect_tushare_stock_basic.py
uv run python infra/scripts/verify_tushare_announcements.py --ann-date 20260503
uv run python infra/scripts/collect_tushare_announcements.py --ann-date 20260503
uv run python infra/scripts/verify_tushare_stock_company.py --exchange SZSE
uv run python infra/scripts/collect_tushare_stock_company.py --exchange SZSE
uv run python infra/scripts/run_radar_scan.py
uv run python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --json-output runtime-check.json
uv run python infra/scripts/postgres_backup.py --output backups/pre-upgrade.sql
```

启动 API：

```powershell
uv run uvicorn app.main:app --reload
```

## 下一步

建议进入 **生产化验证和真实数据增强**，范围继续保持轻量：

- 用 Docker / Linux runbook 跑通 API、worker、beat、迁移、只读 M5 smoke check 和短窗口 runtime check。
- 接入更稳定的公告、监管、风险事件和情绪数据源，优先服务 risk P0 和主线确认。
- Tushare 当前已支持 `stock_basic`、`anns_d` 和 `stock_company` 手动抓取；`anns_d` 中明显重大风险公告已能被雷达扫描映射为 risk P0，后续再决定是否纳入调度。
- 增加运行可观测性：`/ops/overview` 已汇总服务端进程运行时长、磁盘/CPU/内存资源、扫描耗时、失败率、推送结果、模型降级、数据质量状态和只读告警摘要，`/ops/history` 已返回最近扫描、Provider 异常、数据质量异常、推送异常和模型降级/失败历史，`/ops/readiness` 已基于这些信息输出运行就绪自检；Web 状态面板、Windows 客户端和 Telegram `/ops`、`/ops_history`、`/ops_ready` 已展示这些摘要；后续再接趋势图和真实监控告警。
- 完善真实运行后的误报/漏报样例，把规则调参沉淀为 golden cases。
- Web / Telegram / Windows 继续只消费后端结果，不在入口层重算雷达等级。
