# BaizeFinDB Project Status

更新日期：2026-05-03

## 当前阶段

当前已完成 **M4 轻量审查层闭环**。

项目已经具备后端骨架、AKShare 最小数据底座、雷达扫描批次、候选信号、证据链、P0/P1/P2 初判、生命周期初判、连续扫描记忆、雷达总览查询、Provider 数据质量透传、轻量规则审查、内部分享预检、公开分享 payload、持仓/自选最小维护 API、quick/standard 报告 MVP 和 Telegram 折叠推送日志。

Telegram Bot MVP Webhook 模块已补充为当前命令入口，可查看健康状态、雷达总览、信号折叠摘要、单条信号复盘、当前聊天绑定的持仓、自选、报告列表、日报/周报和单信号评分；`telegram_bindings` 已接入 chat 与 `user_key` 绑定、白名单和禁用状态，环境变量 `TELEGRAM_ALLOWED_CHAT_IDS` 仍可作为硬过滤；Telegram 折叠推送 API 已能基于最新扫描按 P0/P1/P2 汇总、复用审查过滤 blocked、记录 push log，并在 P0 推送后为对应聊天用户自动生成 standard report。Telegram 仍只消费后端结果，不重新计算雷达等级。

Windows 客户端 MVP 已补充为本地桌面入口，可连接本地或 Linux 服务器 API，查看健康状态、雷达总览、信号列表、持仓、自选、报告摘要、日报/周报汇总、单信号 1d/3d/5d/10d 综合评分，维护 Telegram chat 绑定/白名单，并打开现有 Web 面板；它仍只消费后端结果，不重新计算雷达等级或评分，也不是完整安装包。

Linux 服务端部署骨架已完成：包含 API Dockerfile、server compose overlay、部署预检脚本、Ubuntu runbook、systemd 示例和 nginx HTTPS 反代示例。该状态只代表部署骨架完成，不代表完整生产部署完成。

5 分钟调度 MVP 已接入 Celery beat：默认每 300 秒执行 `baizefindb.radar.collect_and_scan`，顺序完成 AKShare 最小采集和雷达扫描；当 `TELEGRAM_PUSH_ENABLED=true` 时会追加 Telegram 折叠推送；服务器 compose overlay 已补充 worker / beat 服务。

持仓/自选最小 API 已接入：支持按 `user_key` 手工维护持仓和自选，成本价与仓位比例可为空；静态 Web 终端工作台已能维护和展示这些个人数据。这些个人数据只影响后续个人提醒、展示排序和报告上下文，不改变市场级 P0/P1/P2。

报告 MVP 已接入：`/reports/from-signal` 可从雷达信号生成 quick/standard 模板报告；生成前复用轻量规则审查，blocked 信号不会生成报告，needs_human_review 报告会显式标记。`/reports/periodic` 可按日/周生成当前 `user_key` 的雷达汇总报告。`/scores/signals/{signal_id}` 可生成 1d/3d/5d/10d 综合评分记录。静态 Web 已改为雷达终端工作台外壳，可从信号详情生成报告、查看报告列表、生成日报/周报并查看单信号评分。

当前仍然是投研辅助系统，不是交易系统，不提供买卖建议。

下一阶段开发基线已修正为 **A 股 5 分钟资金主线雷达 MVP**。Telegram、Web、报告、持仓自选、日报周报和评分都围绕雷达结果展开，不再按 Telegram / 报告 / Web 三选一推进。

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
| M2 数据底座 | 已完成早期闭环 | AKShare 行情/行业/概念最小 Provider，采集日志、快照、质量检查、Provider 查询 API。 |
| M3 雷达核心 | 已完成早期闭环 | 基于已入库快照生成雷达候选信号，写入扫描批次、信号和证据，并提供最新总览视图；普通扫描异常会落 `failure` 状态。 |
| M4 审查层 | 已完成 | 轻量规则审查可对单个雷达信号给出 `approved`、`blocked`、`needs_human_review`，并记录审查历史；Provider 数据质量、证据冲突、重复触发、来源过期和分享安全门已进入审查判断。 |
| M5 A 股 5 分钟资金主线雷达 MVP | 进行中 | 已有静态 Web 终端工作台（含报告、日报/周报、评分展示）、Telegram Bot MVP、Windows 客户端 MVP（含报告、日报/周报、评分展示和 Telegram 绑定管理）、Celery 5 分钟采集后扫描调度入口、持仓/自选最小 API 和 Web 维护视图、quick/standard 报告 MVP、日报/周报汇总 API、1d/3d/5d/10d 综合评分、Telegram 折叠推送日志和 P0 推送后 standard report 自动生成；后续继续补评分校准和生产化部署。 |
| Linux 服务端部署骨架 | 已完成 | 已有 API Dockerfile、`docker-compose.server.yml`、worker/beat、`infra/scripts/server_deploy_check.py` 部署预检、`infra/linux/` runbook、systemd 示例和 nginx HTTPS 反代示例；尚不是完整生产部署。 |

## 当前可用 API

健康检查：

- `GET /health`
- `GET /health/ready`

Provider：

- `GET /providers/akshare/endpoints`
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
- Telegram 命令：`/help`、`/health`、`/radar`、`/signals`、`/signal <id>`、`/holding`、`/watchlist`、`/reports`、`/daily`、`/weekly`、`/score <id>`

Windows 客户端：

- `clients/windows/run-client.ps1`
- `clients/windows/baizefindb_client.py`
- `clients/windows/client_api.py`

后台调度：

- `baizefindb.radar.collect_and_scan`：Celery beat 默认每 300 秒触发，先采集 AKShare 最小数据，再运行雷达扫描；`TELEGRAM_PUSH_ENABLED=true` 时追加 Telegram 折叠推送。
- `baizefindb.telegram.push_latest_radar`：手动触发最新扫描的 Telegram 折叠推送。
- `RADAR_SCAN_INTERVAL_SECONDS`：调度间隔环境变量，默认 `300`。

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
- `radar_scan_batches`
- `radar_signals`
- `radar_signal_reviews`
- `signal_evidences`

## 当前规则能力

- 基于板块/概念涨幅、上涨家数、下跌家数、联动宽度生成 P0/P1/P2 候选信号。
- M5 规则基线要求板块/主题/概念权重大于单票异动；单票异动优先用于反推板块/概念/风险。
- 主线 P0 不能只由新闻触发，必须有资金、板块联动或市场情绪确认；风险 P0 可由重大公告、监管或黑天鹅单独触发。
- 基于涨幅和联动宽度初判生命周期：`ignition`、`developing`、`climax`。
- 强度等级和生命周期必须分开处理，AI 只能解释、补证据和提示分歧，不能覆盖规则定级。
- 根据同一板块/概念的历史信号记录连续性。
- 当前实现为 30 分钟窗口内连续 3 次 P1 会标记为 `quick_report_candidate`；M5 设计基线里的 2-3 次触发口径还需要后续实现和测试确认。
- 前后扫描走弱会记录生命周期转移，例如 `climax_to_divergence`。
- 总览 API 基于最新扫描生成当前活跃信号、P0/P1/P2 聚合和按板块/概念去重视图。
- 雷达扫描 summary、信号 metrics 和 evidence details 会携带 Provider 数据质量摘要。
- 轻量审查层会拦截诱导交易语言、证据缺失、失败数据质量和低置信度证据；降级/未知数据质量、证据冲突、重复触发和来源过期会进入人工复核；P0 和连续 P1 快报候选会留下审查理由。
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
uv run python infra/scripts/run_radar_scan.py
```

启动 API：

```powershell
uv run uvicorn app.main:app --reload
```

## 下一步

建议进入 **M5 A 股 5 分钟资金主线雷达 MVP**，范围继续保持轻量：

- 继续巩固后端雷达计算、调度状态记录、P0/P1/P2 规则、生命周期和 P2 7 天观察。
- 将持仓/自选接入 Telegram/Web 展示和报告上下文；继续保持只影响个人优先级，不改变市场主线等级。
- Telegram 推送已能按 P0/P1/P2 折叠汇总、过滤 blocked、记录 `push_logs`，并在 P0 推送后为对应聊天用户生成 standard report。
- Web MVP 已改为雷达终端工作台外壳，具备左侧模块导航、顶部命令栏、F-key 操作条、雷达总览、信号详情、持仓/自选维护、报告列表、日报/周报和单信号评分。
- 报告分 quick/standard/deep；自动最多 quick/standard，deep 只手动触发；日报/周报汇总 API 已有最小生成能力。
- 1d/3d/5d/10d 基础综合评分已能按信号生成，并已接入 Telegram、Windows 与 Web 展示；后续继续校准评分权重。
- 所有发布类输出都先走审查和分享预检，公开分享默认脱敏脱源。
- 继续补交易诱导词正反例，按真实误报再调规则。

M5 可执行拆分见 [prd/m5-next-step.md](prd/m5-next-step.md)。当前建议按雷达优先顺序推进，不再把 Telegram、报告、Web 作为并列备选入口。
