# BaizeFinDB Windows Client MVP

这是 Windows 客户端 MVP：用 Python 标准库和 Tkinter 连接 BaizeFinDB API，查看健康状态、运行状态、服务端磁盘摘要、运维历史、运行就绪自检、告警摘要、Tushare 数据源状态和准入自检、雷达总览、生命周期分布、市场情绪摘要、个股回推证据、信号列表、持仓、自选、报告摘要、日报/周报汇总、单信号 v2 综合评分明细，维护 Telegram chat 绑定/白名单，并打开现有 Web 面板。GUI 内的 `OPS Lookback (hours)` 输入框默认 24，允许 1 到 168 小时，供运行状态、运维历史和就绪自检共用。

默认仍是源码运行版，不是安装包。当前目录提供可选 PyInstaller onedir 打包脚手架，方便后续在 Windows 目标机上验证 exe 形态；它不是签名安装器，也不包含自动更新或生产分发承诺。

## 前置条件

- Windows PowerShell。
- Python 3.12。Windows 官方 Python 通常自带 Tkinter。
- BaizeFinDB API 已在本机或 Linux 服务器启动。

## 本地连接

在仓库根目录执行：

```powershell
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default
```

默认使用最近 24 小时的 OPS readiness 窗口；需要隔离最近健康状态和历史 Provider / 数据质量 warning 时，可以缩短窗口，允许范围与后端一致，为 1 到 168 小时：

```powershell
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default --ops-readiness-lookback-hours 6
```

确认没有 blocker 后再打开 Tkinter 客户端：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000
```

也可以让 launcher 先执行同一套 smoke check，再在通过后打开 GUI：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default -SmokeCheck
```

需要留下脱敏 JSON evidence，或要求 warning 也阻断启动：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default -SmokeCheck -SmokeLookbackHours 6 -SmokeJsonOutput evidence/windows-client-smoke.json -SmokeStrict
```

## 连接服务器

把地址换成你的 HTTPS 域名：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl https://<your-domain>
```

指定个人数据隔离键：

```powershell
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default
```

也可以先设置环境变量：

```powershell
$env:BAIZEFINDB_SERVER_URL = "https://<your-domain>"
$env:BAIZEFINDB_USER_KEY = "default"
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1
```

## 可选打包脚手架

源码运行仍是默认路径。需要验证桌面 exe 形态时，先只为打包环境安装 PyInstaller：

```powershell
uv pip install pyinstaller
```

再在仓库根目录执行 onedir 打包：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1
```

如果只想检查即将执行的 PyInstaller 命令，不安装 PyInstaller 且不生成 `build/`、`dist/`、`spec/` 或 launcher，可以先 dry run：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -DryRun -Name CustomClient -DistPath C:\tmp\baize-dist -WorkPath C:\tmp\baize-build -Clean
```

如果只想验证打包前置条件而不生成任何产物，可以使用 check-only。该模式会运行同一套 Python 3.12、`tkinter`、入口模块解析 preflight，并检查 PyInstaller 是否可用，然后在创建 `build/`、`dist/`、`spec/`、launcher 或调用 PyInstaller 构建前退出。`-CheckOnly` 不能和 `-SkipPreflight` 同用：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -CheckOnly
powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -CheckOnly -CheckJsonOutput clients/windows/package-check-evidence.local.json
```

`-CheckJsonOutput` 只能和 `-CheckOnly` 同用；它写出的 JSON 只包含打包前置条件状态、Python 版本、`tkinter`/GUI 模块/PyInstaller 可用性、命令元数据和输出路径元数据，不包含环境变量、密钥、smoke 报告、后端响应、构建输出或二进制。`clients/windows/package-check-evidence*.json` 已加入 `.gitignore`，本地证据文件不要提交。

非 dry-run 打包会先运行轻量 Python preflight：确认当前 Python 是 3.12、`tkinter` 可导入、并且能从仓库路径解析 `clients.windows.baizefindb_client`。该 preflight 不会创建 `tk.Tk()`、打开 GUI、调用后端 API、运行 smoke check 或生成构建产物；只有本地排查特殊问题时才加 `-SkipPreflight` 明确跳过：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -SkipPreflight
```

脚本随后会为 `clients.windows.baizefindb_client` 生成临时 launcher，并调用 PyInstaller `--onedir --windowed --name BaizeFinDB-Windows-Client`。默认输出在 `clients/windows/dist/`，中间文件在 `clients/windows/build/`，这些生成物已加入 `.gitignore`，不要提交 exe、spec 或构建目录。

打包前仍建议先运行 smoke check；打包后的 GUI 只连接后端 API，不会自动采集、扫描、评分、生成报告、修改 Telegram 或执行任何交易相关动作。

## 功能边界

- 首次使用前可运行 `python -m clients.windows.smoke_check --server-url <api-url> --user-key <key>`，也可用 `run-client.ps1 -SmokeCheck` 在启动 GUI 前自动执行。该命令只做 Tkinter import 检查和 API GET 自检，不打开 GUI，不调用采集、扫描、评分生成、报告生成、Telegram 修改或任何交易相关动作。
- `--ops-readiness-lookback-hours <n>` 只调整 `/ops/readiness` 的统计窗口，默认 24，范围 1 到 168；`run-client.ps1 -SmokeLookbackHours <n>` 会把同一数值传给 smoke check。
- `--json-output <path>` 可写出有界脱敏 JSON 报告；报告会隐藏 `user_key`、token、secret 和 credential-like 字段。
- `run-client.ps1 -SmokeJsonOutput <path>` 会把该路径传给 smoke check；`-SmokeStrict` 会把 warning 当作启动 blocker。默认不加 `-SmokeStrict` 时，warning 不阻断 GUI 启动。
- 当 `/ops/readiness` 返回 warning 或 blocked 时，console summary 会列出非 OK 检查项名称和有界脱敏说明，例如 `provider_fetch`、`data_quality`，便于首用时区分历史数据源/数据质量 warning 和真正 blocker。
- GUI 的 `OPS Lookback (hours)` 会传给 `/ops/overview`、`/ops/history` 和 `/ops/readiness`，默认 24，范围 1 到 168；非法输入会在发起 API 请求前弹出校验错误。
- smoke check 默认跳过当前会在 GET 时创建用户行的持仓/自选/报告/周期报告端点，并以 warning 提醒；空雷达、空信号、空 Telegram 绑定属于首用 warning，不是 blocker。
- 客户端只消费后端 API：`/health/ready`、`/ops/overview`、`/ops/history`、`/ops/readiness`、`/providers/tushare/status`、`/providers/tushare/readiness`、`/radar/overview`、`/radar/signals`、`/portfolio/holdings`、`/portfolio/watchlist`、`/reports`、`/reports/periodic`、`/scores/signals/{signal_id}`。
- Telegram 绑定管理调用 `/telegram/bindings`；服务器配置 `TELEGRAM_WEBHOOK_SECRET` 时，需要在 `Telegram Secret` 输入框填写同一个 secret。
- P0/P1/P2、生命周期、生命周期分布、市场情绪摘要、运行状态、OPS readiness、Tushare 数据源状态、个股回推证据、审查状态和雷达计数均来自后端，客户端不重新计算。
- 日报/周报和综合评分也来自后端；客户端只负责触发、读取和展示评分窗口、档位和组件明细。
- 客户端不保存 token、secret、Tushare token 原文、持仓截图或个人数据；Telegram Secret 只在当前进程内用于请求 header。Tushare 状态和自检视图只读取配置、最近抓取日志和数据质量记录，不触发真实抓取或调度。
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
