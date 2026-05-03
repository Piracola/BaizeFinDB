# Linux 服务端部署骨架 Runbook

这份文档用于说明当前仓库已经具备哪些 Linux 服务器部署骨架文件，以及后续上 Ubuntu 服务器时从哪里开始。它不是完整生产部署验收文档。

## 文件位置

| 文件 | 说明 |
| --- | --- |
| `Dockerfile` | 生产取向的 FastAPI API 镜像，启动 `uvicorn app.main:app --host 0.0.0.0 --port 8000`。 |
| `.dockerignore` | 排除 `.env`、虚拟环境、缓存和本地日志，避免把 secrets 或本地状态打进镜像。 |
| `docker-compose.server.yml` | 服务器 compose overlay，新增 `api`、`worker`、`beat` 服务，依赖 healthy 的 `postgres` / `redis`。 |
| `infra/scripts/server_deploy_check.py` | 服务器部署预检脚本，验证 `.env`、compose 配置、可选镜像构建、容器状态、API 健康检查、Ops 运行状态和 M5 只读 smoke check。 |
| `infra/scripts/postgres_backup.py` | PostgreSQL 备份脚本，固定使用 server compose overlay 调用容器内 `pg_dump`。 |
| `infra/scripts/postgres_restore.py` | PostgreSQL 恢复脚本，固定使用 server compose overlay 调用容器内 `psql`，执行前必须显式确认。 |
| `infra/linux/README.md` | Ubuntu 部署步骤、迁移、健康检查、Telegram webhook、日志、备份、升级、回滚。 |
| `infra/linux/baizefindb-compose.service` | systemd 自动启动 compose project 示例。 |
| `infra/linux/nginx-baizefindb.conf` | nginx HTTPS/domain 反代到 `127.0.0.1:8000` 示例，包含 `/telegram/webhook`。 |

## 本地开发不变

本地 Windows 开发仍使用：

```powershell
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

`docker-compose.server.yml` 只在服务器或部署演练时显式叠加。只启动 API：

```powershell
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d api
```

启动 API、Celery worker 和 Celery beat：

```powershell
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat
```

## 部署演练命令

在仓库根目录验证 compose：

```powershell
docker compose config
docker compose -f docker-compose.yml -f docker-compose.server.yml config
```

构建 API 镜像：

```powershell
docker build -t baizefindb-api:dev .
```

运行服务器部署预检：

```powershell
uv run python infra/scripts/server_deploy_check.py
```

服务已经启动后，可以追加容器和 API 检查：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-containers --check-api
```

验证 M5 核心只读接口 JSON 契约，包含 `/ops/overview` 的运行状态汇总：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-m5-smoke
```

验证 Postgres 容器内 `pg_dump` 可用：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-backup
```

生成 PostgreSQL 备份：

```powershell
uv run python infra/scripts/postgres_backup.py
```

指定输出路径：

```powershell
uv run python infra/scripts/postgres_backup.py --output backups/pre-upgrade.sql
```

从备份恢复 PostgreSQL：

```powershell
uv run python infra/scripts/postgres_restore.py backups/pre-upgrade.sql --confirm-restore
```

恢复会覆盖目标数据库当前状态；执行前先确认当前 compose project、目标数据库和备份文件路径。

Linux 服务器上的完整步骤以 [infra/linux/README.md](../../infra/linux/README.md) 为准。Beat 默认每 300 秒触发 `baizefindb.radar.collect_and_scan`，即先采集最小 AKShare 数据，再运行雷达扫描；可用 `RADAR_SCAN_INTERVAL_SECONDS` 调整调度间隔，可用 `RADAR_CONTINUOUS_P1_TRIGGER_COUNT` 和 `RADAR_CONTINUITY_WINDOW_MINUTES` 调整连续 P1 快报候选阈值。`.env` 中 `TELEGRAM_PUSH_ENABLED=true` 后，该任务会继续触发 Telegram 折叠推送，并写入 `push_logs`。

## 运维状态接口

服务器启动后可用以下命令快速查看最近 24 小时运行状态：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/overview?lookback_hours=24"
```

该接口只读聚合已有数据库记录，不触发采集、扫描、推送或模型调用。重点看 `radar.recent_scan_failure_rate`、`radar.is_latest_scan_stale`、`provider_fetch.unhealthy_count`、`data_quality.unhealthy_count`、`telegram_push.unhealthy_count` 和 `model_calls.unhealthy_count`。

## Secrets 边界

- `.env` 不进入 git，也不会被 Dockerfile 复制进镜像。
- `backups/` 不进入 git；数据库备份文件只留在服务器安全备份流程里。
- 文档和示例只使用 `<telegram-bot-token>`、`<telegram-webhook-secret>`、`<db-password>` 这类占位符。
- Telegram webhook 需要公网 HTTPS 后再设置到 `https://<your-domain>/telegram/webhook`。
- Telegram 折叠推送只使用 `.env` 中的 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_ALLOWED_CHAT_IDS` 和 `TELEGRAM_PUSH_ENABLED`；不要把真实 chat id、token 或推送日志导出文件提交到 git。
- 当前只是部署骨架；PostgreSQL 默认凭据、TLS 证书签发、备份策略、监控告警和生产安全加固仍需要后续专门处理。
