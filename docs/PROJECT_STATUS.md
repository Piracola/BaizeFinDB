# BaizeFinDB Project Status

更新日期：2026-04-30

## 当前阶段

当前已完成 **M4 轻量审查层闭环**。

项目已经具备后端骨架、AKShare 最小数据底座、雷达扫描批次、候选信号、证据链、P0/P1/P2 初判、生命周期初判、连续扫描记忆、雷达总览查询、Provider 数据质量透传、轻量规则审查、内部分享预检和公开分享 payload。

当前仍然是投研辅助系统，不是交易系统，不提供买卖建议。

## 已完成

| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| M1 工程骨架 | 已完成 | FastAPI、配置系统、健康检查、SQLAlchemy async、Alembic、Docker Compose、Celery 壳、pytest。 |
| M2 数据底座 | 已完成早期闭环 | AKShare 行情/行业/概念最小 Provider，采集日志、快照、质量检查、Provider 查询 API。 |
| M3 雷达核心 | 已完成早期闭环 | 基于已入库快照生成雷达候选信号，写入扫描批次、信号和证据，并提供最新总览视图；普通扫描异常会落 `failure` 状态。 |
| M4 审查层 | 已完成 | 轻量规则审查可对单个雷达信号给出 `approved`、`blocked`、`needs_human_review`，并记录审查历史；Provider 数据质量、证据冲突、重复触发、来源过期和分享安全门已进入审查判断。 |
| M5+ Telegram / 报告 / Web | 未开始 | 进入前必须复用 M4 审查和分享预检，不提前接自动交易或强买卖口径。 |

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

## 当前数据表

- `schema_health_checks`
- `market_snapshots`
- `provider_fetch_logs`
- `data_quality_checks`
- `radar_scan_batches`
- `radar_signals`
- `radar_signal_reviews`
- `signal_evidences`

## 当前规则能力

- 基于板块/概念涨幅、上涨家数、下跌家数、联动宽度生成 P0/P1/P2 候选信号。
- 基于涨幅和联动宽度初判生命周期：`ignition`、`developing`、`climax`。
- 根据同一板块/概念的历史信号记录连续性。
- 30 分钟内连续 3 次 P1 会标记为 `quick_report_candidate`。
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

建议进入 **M5 最小入口或报告小闭环**，但范围继续保持轻量：

- Telegram / 报告 / Web 三者选一个最小闭环先做，不并行铺大面。
- 所有发布类输出都先走审查和分享预检。
- 继续补交易诱导词正反例，按真实误报再调规则。
