# Windows 客户端 MVP Runbook

这份 runbook 用于在 Windows 上运行 BaizeFinDB 客户端 MVP。客户端使用 Python 标准库和 Tkinter，不引入新依赖，不打包 exe，也不是完整安装包。

## 1. 功能边界

- 查看 API 就绪状态：`GET /health/ready`。
- 查看雷达总览：`GET /radar/overview`。
- 查看信号列表：`GET /radar/signals`。
- 查看持仓：`GET /portfolio/holdings`。
- 查看自选：`GET /portfolio/watchlist`。
- 查看报告摘要：`GET /reports`。
- 打开现有 Web 面板：`/`。
- P0/P1/P2、生命周期、审查状态和计数都来自后端 API，客户端不重新计算。
- 不保存 token、secret、持仓截图或个人数据。
- 不保存报告导出文件；报告正文继续在 Web/API 查看。
- 不提供买卖建议、不接自动交易、不承诺收益。
- 持仓/自选只作为个人提醒、展示排序和报告上下文，不改变市场雷达等级。

## 2. 前置要求

| 工具 | 要求 | 验证命令 |
| --- | --- | --- |
| Windows PowerShell | 可运行脚本 | `$PSVersionTable.PSVersion` |
| Python | 3.12，带 Tkinter | `python --version` |
| BaizeFinDB API | 本地或服务器已启动 | `Invoke-RestMethod <server-url>/health` |

如果本机 Python 缺少 Tkinter，请安装官方 Windows Python 3.12。

## 3. 连接本地 API

先启动本地依赖和 API：

```powershell
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

再启动客户端：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default
```

## 4. 连接 Linux 服务器 API

服务器应已经部署 API，并通过 HTTPS 域名暴露：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl https://<your-domain> -UserKey default
```

如果暂时使用环境变量：

```powershell
$env:BAIZEFINDB_SERVER_URL = "https://<your-domain>"
$env:BAIZEFINDB_USER_KEY = "default"
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1
```

## 5. 客户端按钮

| 按钮 | 行为 |
| --- | --- |
| 检查状态 | 调用 `/health/ready`，显示 API、PostgreSQL、Redis 状态。 |
| 刷新雷达 | 调用 `/radar/overview`，显示后端返回的优先级计数、最新扫描和当前主题。 |
| 查看信号 | 调用 `/radar/signals`，显示后端返回的信号摘要。 |
| 查看持仓 | 调用 `/portfolio/holdings`，按 User Key 显示个人持仓。 |
| 查看自选 | 调用 `/portfolio/watchlist`，按 User Key 显示个人自选。 |
| 查看报告 | 调用 `/reports`，按 User Key 显示 quick/standard 报告摘要。 |
| 打开 Web 面板 | 用系统浏览器打开服务器根路径。 |

## 6. 常见问题

### PowerShell 阻止脚本执行

使用本 runbook 中的启动方式：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000
```

### 无法连接 API

确认地址没有写错，并直接验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

如果连接服务器，确认域名、HTTPS 证书和 nginx 反代正常。

### `/health/ready` 未就绪

这通常表示 PostgreSQL 或 Redis 不可用。先检查：

```powershell
docker compose ps
uv run alembic heads
uv run alembic upgrade head
```

服务器部署排查见 [linux-server.md](linux-server.md)。

### 雷达总览或信号为空

从空数据库开始时，需要先采集 Provider 数据并运行雷达扫描：

```powershell
uv run python infra/scripts/collect_akshare_minimal.py
uv run python infra/scripts/run_radar_scan.py
```

也可以通过 Web 面板触发当前静态 MVP 已有的采集和扫描按钮。
