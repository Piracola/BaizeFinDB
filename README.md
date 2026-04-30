# BaizeFinDB

个人 AI 金融雷达与投研辅助系统。当前只完成 M1 后端工程骨架。

## 当前包含

- FastAPI 后端入口
- `/health` 存活检查
- `/health/ready` PostgreSQL / Redis 就绪检查
- AKShare 最小 Provider：A 股行情、行业板块、概念板块
- Provider 拉取日志、快照和数据质量表
- `/providers/akshare/endpoints` 查看已封装接口
- `/providers/akshare/fetch/minimal` 手动触发最小采集
- `/providers/akshare/status` 查看每个接口最近采集状态
- `/providers/akshare/fetch-logs` 查看最近采集日志
- `/providers/akshare/snapshots/latest` 查看最近快照摘要
- Pydantic 配置
- SQLAlchemy 2.0 异步数据库连接
- Alembic 迁移框架
- Celery Worker / Beat 配置壳
- Docker Compose 的 PostgreSQL / Redis 配置
- pytest 冒烟测试

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

当前推进到 M2 数据底座早期：只接 AKShare 最小 Provider，不做雷达规则，不接 Agent、Telegram 或 Web。
