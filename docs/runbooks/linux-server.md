# Linux 服务端部署骨架 Runbook

这份文档用于说明当前仓库已经具备哪些 Linux 服务器部署骨架文件，以及后续上 Ubuntu 服务器时从哪里开始。它不是完整生产部署验收文档。

## 文件位置

| 文件 | 说明 |
| --- | --- |
| `Dockerfile` | 生产取向的 FastAPI API 镜像，启动 `uvicorn app.main:app --host 0.0.0.0 --port 8000`。 |
| `.dockerignore` | 排除 `.env`、虚拟环境、缓存和本地日志，避免把 secrets 或本地状态打进镜像。 |
| `docker-compose.server.yml` | 服务器 compose overlay，新增 `api` 服务，依赖 healthy 的 `postgres` / `redis`。 |
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

`docker-compose.server.yml` 只在服务器或部署演练时显式叠加：

```powershell
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d api
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

Linux 服务器上的完整步骤以 [infra/linux/README.md](../../infra/linux/README.md) 为准。

## Secrets 边界

- `.env` 不进入 git，也不会被 Dockerfile 复制进镜像。
- 文档和示例只使用 `<telegram-bot-token>`、`<telegram-webhook-secret>`、`<db-password>` 这类占位符。
- Telegram webhook 需要公网 HTTPS 后再设置到 `https://<your-domain>/telegram/webhook`。
- 当前只是部署骨架；PostgreSQL 默认凭据、TLS 证书签发、备份策略、监控告警和生产安全加固仍需要后续专门处理。
