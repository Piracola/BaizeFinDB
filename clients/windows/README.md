# BaizeFinDB Windows Client MVP

这是 Windows 客户端 MVP：用 Python 标准库和 Tkinter 连接 BaizeFinDB API，查看健康状态、运行状态、雷达总览、生命周期分布、市场情绪摘要、个股回推证据、信号列表、持仓、自选、报告摘要、日报/周报汇总、单信号 v2 综合评分明细，维护 Telegram chat 绑定/白名单，并打开现有 Web 面板。

它不是安装包，也不会打包成 exe。后续如果需要桌面分发，可以在这个目录基础上再做打包、签名和自动更新。

## 前置条件

- Windows PowerShell。
- Python 3.12。Windows 官方 Python 通常自带 Tkinter。
- BaizeFinDB API 已在本机或 Linux 服务器启动。

## 本地连接

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000
```

## 连接服务器

把地址换成你的 HTTPS 域名：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl https://<your-domain>
```

指定个人数据隔离键：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default
```

也可以先设置环境变量：

```powershell
$env:BAIZEFINDB_SERVER_URL = "https://<your-domain>"
$env:BAIZEFINDB_USER_KEY = "default"
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1
```

## 功能边界

- 客户端只消费后端 API：`/health/ready`、`/ops/overview`、`/radar/overview`、`/radar/signals`、`/portfolio/holdings`、`/portfolio/watchlist`、`/reports`、`/reports/periodic`、`/scores/signals/{signal_id}`。
- Telegram 绑定管理调用 `/telegram/bindings`；服务器配置 `TELEGRAM_WEBHOOK_SECRET` 时，需要在 `Telegram Secret` 输入框填写同一个 secret。
- P0/P1/P2、生命周期、生命周期分布、市场情绪摘要、运行状态、个股回推证据、审查状态和雷达计数均来自后端，客户端不重新计算。
- 日报/周报和综合评分也来自后端；客户端只负责触发、读取和展示评分窗口、档位和组件明细。
- 客户端不保存 token、secret、持仓截图或个人数据；Telegram Secret 只在当前进程内用于请求 header。
- 客户端不提供买卖建议、不接自动交易、不承诺收益。
- 持仓/自选只作为个人提醒、展示排序和报告上下文，不改变市场雷达等级。

## 常见问题

### 窗口无法启动

先确认 Python 可用：

```powershell
python --version
```

如果提示 Tkinter 不存在，安装带 Tkinter 的 Windows Python 3.12。

### 状态显示未就绪

`/health/ready` 会检查 PostgreSQL 和 Redis。先在 API 机器上确认依赖服务、迁移和 API 进程：

```powershell
uv run alembic heads
uv run uvicorn app.main:app --reload
```

本地依赖通常还需要：

```powershell
docker compose up -d postgres redis
```

### 可以打开 Web 面板但雷达为空

先采集 Provider 数据并运行雷达扫描。详见 `docs/runbooks/local-dev.md`。
