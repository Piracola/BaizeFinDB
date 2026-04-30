# BaizeFinDB Project Status

更新日期：2026-04-30

## 当前阶段

当前推进到 **M3.2 雷达核心早期**。

项目已经具备后端骨架、AKShare 最小数据底座、雷达扫描批次、候选信号、证据链、P0/P1/P2 初判、生命周期初判和连续扫描记忆。

当前仍然是投研辅助系统，不是交易系统，不提供买卖建议。

## 已完成

| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| M1 工程骨架 | 已完成 | FastAPI、配置系统、健康检查、SQLAlchemy async、Alembic、Docker Compose、Celery 壳、pytest。 |
| M2 数据底座 | 已完成早期闭环 | AKShare 行情/行业/概念最小 Provider，采集日志、快照、质量检查、Provider 查询 API。 |
| M3 雷达核心 | 进行中，已到 M3.2 | 基于已入库快照生成雷达候选信号，写入扫描批次、信号和证据。 |

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
- `GET /radar/signals`
- `GET /radar/signals/{signal_id}`

## 当前数据表

- `schema_health_checks`
- `market_snapshots`
- `provider_fetch_logs`
- `data_quality_checks`
- `radar_scan_batches`
- `radar_signals`
- `signal_evidences`

## 当前规则能力

- 基于板块/概念涨幅、上涨家数、下跌家数、联动宽度生成 P0/P1/P2 候选信号。
- 基于涨幅和联动宽度初判生命周期：`ignition`、`developing`、`climax`。
- 根据同一板块/概念的历史信号记录连续性。
- 30 分钟内连续 3 次 P1 会标记为 `quick_report_candidate`。
- 前后扫描走弱会记录生命周期转移，例如 `climax_to_divergence`。

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

建议继续做 **M3.3 雷达总览 API**：

- 当前活跃信号列表。
- 按 P0/P1/P2 聚合的总览。
- 按板块/概念去重的当前视图。
- 按批次查询扫描结果。
- 增加更多 `golden_cases`，锁定误报和退潮场景。

M3.3 稳定后，再进入 M4 轻量审查层。
