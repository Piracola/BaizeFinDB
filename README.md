# BaizeFinDB

个人 AI 金融雷达与投研辅助系统。当前推进到 M3.2 雷达核心早期。

当前状态详见 [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)。

## 当前包含

- FastAPI 后端入口
- `/health` 存活检查
- `/health/ready` PostgreSQL / Redis 就绪检查
- AKShare 最小 Provider：A 股行情、行业板块、概念板块
- AKShare 情绪 Provider：涨停股池、跌停股池、炸板股池
- Provider 拉取日志、快照和数据质量表
- `/providers/akshare/endpoints` 查看已封装接口
- `/providers/akshare/fetch/minimal` 手动触发最小采集
- `/providers/akshare/status` 查看每个接口最近采集状态
- `/providers/akshare/fetch-logs` 查看最近采集日志
- `/providers/akshare/snapshots/latest` 查看最近快照摘要
- 雷达扫描批次、候选信号、证据链基础表
- `/radar/scans/run` 基于最近 Provider 快照生成雷达候选信号
- `/radar/scans/latest` 查看最近一次雷达扫描
- `/radar/signals` 查看候选信号列表
- `/radar/signals/{signal_id}` 查看候选信号和证据
- 雷达连续扫描记忆：记录同一板块前后变化、连续 P1 次数和生命周期转移
- `golden_cases` 规则黄金样例，用于锁定基础 P0/P1/P2 判定
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
| M3 雷达核心 | 进行中，已到 M3.2 | 可基于板块/概念快照生成候选信号、证据链、生命周期和连续 P1 标记。 |
| M4+ | 未开始 | Agent 审查、Telegram、报告、Web、日报周报后置。 |

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

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/ready`

如果 PostgreSQL / Redis 还没启动，`/health` 仍会正常，`/health/ready` 会显示依赖未就绪。

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
```

## 开发边界

当前推进到 M3.2 雷达核心早期：只基于已入库 AKShare 快照生成候选信号，连续 P1 只标记为快报候选，不接 Agent、Telegram 或 Web，不提供交易建议。
