# Windows 客户端 MVP Runbook

这份 runbook 用于在 Windows 上运行 BaizeFinDB 客户端 MVP。客户端默认使用 Python 标准库和 Tkinter 源码运行，不引入运行时依赖；仓库另提供可选 PyInstaller onedir 打包脚手架，但它不是签名安装器或生产分发包。

## 1. 功能边界

- 查看 API 就绪状态：`GET /health/ready`。
- 查看运行状态和服务端磁盘/CPU/内存摘要：`GET /ops/overview`。
- 查看只读运维历史：`GET /ops/history`。
- 查看运行就绪自检：`GET /ops/readiness`。
- GUI 的 `OPS Lookback (hours)` 输入框控制上述三个 OPS 视图的统计窗口，默认 24，范围 1 到 168 小时；非法输入会在请求前阻断。
- 查看 Tushare 数据源状态：`GET /providers/tushare/status`，只返回 token 是否配置和端点实现状态，不返回 token 原文。
- 查看 Tushare 数据源自检：`GET /providers/tushare/readiness`，只读取配置、最近抓取日志和数据质量记录，不触发真实抓取或调度。
- 查看雷达总览、优先级、生命周期分布、市场情绪摘要和个股回推证据：`GET /radar/overview`。
- 查看信号列表：`GET /radar/signals`。
- 查看持仓：`GET /portfolio/holdings`。
- 查看自选：`GET /portfolio/watchlist`。
- 查看报告摘要：`GET /reports`。
- 查看日报/周报汇总：`GET /reports/periodic`。
- 生成并查看单信号 v2 综合评分明细：`POST /scores/signals/{signal_id}`。
- 查看、绑定和禁用 Telegram chat：`GET/POST/PATCH /telegram/bindings`。
- 打开现有 Web 面板：`/`。
- P0/P1/P2、生命周期、市场情绪摘要、运行状态、OPS readiness、数据源状态、审查状态和计数都来自后端 API，客户端不重新计算。
- 日报/周报和评分结果也来自后端，客户端不做本地评分或规则推断。
- 不保存 token、secret、持仓截图或个人数据；Telegram Secret 输入框只用于本次 API header。
- Tushare 状态视图只读取 Provider 配置状态，不触发真实抓取。
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

推荐先运行首次试用 launcher。它默认连接 `http://127.0.0.1:8000`，使用
`user_key=default` 和最近 24 小时 OPS readiness 窗口，内部只委托
`run-client.ps1 -SmokeCheck`，不会复制 smoke check 或 GUI 逻辑：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1
```

也可以单独运行首次使用 smoke check。该命令只检查 Tkinter import 和只读 API GET，不打开 GUI，不触发采集、扫描、评分生成、报告生成或 Telegram 修改：

```powershell
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default
```

默认 OPS readiness 统计窗口是最近 24 小时。排查时如果要区分最近健康状态和更早的 Provider / 数据质量 warning，可以缩短窗口；允许范围与后端 `/ops/readiness` 一致，为 1 到 168 小时：

```powershell
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default --ops-readiness-lookback-hours 6
```

需要留存首次试运行证据时，优先写出 compact JSON。compact evidence 只包含总体状态、服务端地址元数据、脱敏 user key、检查数、每项检查的 name/status/message、warning/blocker 和 OPS readiness 非 OK 摘要，不包含端点 payload 或原始后端响应。详细 JSON 仍可用于深度排障：

```powershell
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default --compact-json-output evidence/windows-client-smoke-compact.json
python -m clients.windows.smoke_check --server-url http://127.0.0.1:8000 --user-key default --json-output evidence/windows-client-smoke.json
```

确认没有 blocker 后再启动客户端：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default
```

如果需要覆盖首次试用参数：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default -SmokeLookbackHours 6
```

底层 `run-client.ps1` 仍可在打开 GUI 前自动执行同一套 smoke check：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default -SmokeCheck
```

需要同时保存 compact evidence，或让 warning 也阻断 GUI 启动，推荐：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1 -SmokeLookbackHours 6 -SmokeCompactJsonOutput evidence/windows-client-smoke-compact.json -SmokeStrict
```

等价的底层 launcher 参数是：

```powershell
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl http://127.0.0.1:8000 -UserKey default -SmokeCheck -SmokeLookbackHours 6 -SmokeCompactJsonOutput evidence/windows-client-smoke-compact.json -SmokeStrict
```

## 4. 连接 Linux 服务器 API

服务器应已经部署 API，并通过 HTTPS 域名暴露：

```powershell
python -m clients.windows.smoke_check --server-url https://<your-domain> --user-key default
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl https://<your-domain> -UserKey default
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1 -ServerUrl https://<your-domain> -UserKey default -SmokeCheck
powershell -ExecutionPolicy Bypass -File clients/windows/first-trial.ps1 -ServerUrl https://<your-domain> -UserKey default
```

如果暂时使用环境变量：

```powershell
$env:BAIZEFINDB_SERVER_URL = "https://<your-domain>"
$env:BAIZEFINDB_USER_KEY = "default"
powershell -ExecutionPolicy Bypass -File clients/windows/run-client.ps1
```

## 5. 可选 PyInstaller onedir 打包

打包只用于开发者验证 Windows 桌面 exe 形态，源码运行仍是默认和推荐路径。先同步可选 packaging 依赖组；PyInstaller 只在这个打包组中声明，不是客户端运行依赖，也不进入普通 dev 路径：

```powershell
uv sync --group package
```

在仓库根目录执行：

```powershell
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1
```

可以先用 dry run 预览命令。该模式不会检查 PyInstaller 是否已安装，也不会生成 `build/`、`dist/`、`spec/`、临时 launcher 或 exe；自定义名称、输出目录和 `-Clean` 会反映在打印出的命令里：

```powershell
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -DryRun
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -DryRun -Name CustomClient -DistPath C:\tmp\baize-dist -WorkPath C:\tmp\baize-build -Clean
```

也可以用 check-only 验证真实打包前置条件。该模式会运行同一套 Python 3.12、`tkinter` import、入口模块解析 preflight，并检查 PyInstaller 是否已安装；检查通过后在创建 `build/`、`dist/`、`spec/`、临时 launcher 或调用 PyInstaller 构建前退出。`-CheckOnly` 必须运行 preflight，因此不能和 `-SkipPreflight` 同用：

```powershell
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -CheckOnly
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -CheckOnly -CheckJsonOutput clients/windows/package-check-evidence.local.json
```

`-CheckJsonOutput` 只能和 `-CheckOnly` 同用，用于保存有界 JSON 前置条件证据。证据只记录状态、Python 版本、`tkinter`/入口模块/PyInstaller 可用性、命令元数据和输出路径元数据；不会记录环境变量、token、secret、smoke 报告、后端响应、构建输出或生成二进制。`clients/windows/package-check-evidence*.json` 已加入 `.gitignore`，本地证据文件不要提交。

非 dry-run 打包会在调用 PyInstaller 前先运行轻量 Python preflight，确认 Python 3.12、`tkinter` 可导入、并且能从仓库路径解析 `clients.windows.baizefindb_client`。这个检查不会创建 `tk.Tk()`、打开 GUI、访问后端 API、运行 smoke check 或生成构建产物。只有本地排查特殊问题时才显式跳过：

```powershell
uv run --group package powershell -ExecutionPolicy Bypass -File clients/windows/package-client.ps1 -SkipPreflight
```

脚本随后会生成临时 launcher，入口模块仍是 `clients.windows.baizefindb_client`，并调用 PyInstaller `--onedir --windowed --name BaizeFinDB-Windows-Client`。默认输出：

- `clients/windows/dist/BaizeFinDB-Windows-Client/`
- `clients/windows/build/`

这些目录和生成的 `*.spec` 已加入 `.gitignore`。不要提交 exe、spec、中间构建目录、签名证书、token、smoke evidence 或个人数据。脚手架不做 onefile、MSI、代码签名、SmartScreen 信誉、自动更新或生产发布。

打包前建议先运行第 3 节的 smoke check。打包后的 GUI 与源码版边界一致：只消费后端 API，不自动采集、扫描、评分、生成报告、修改 Telegram，也不提供交易相关能力。

## 6. 客户端按钮

| 按钮 | 行为 |
| --- | --- |
| 检查状态 | 调用 `/health/ready`，显示 API、PostgreSQL、Redis 状态。 |
| 运行状态 | 调用 `/ops/overview`，带上 `OPS Lookback (hours)`，显示服务端运行时、磁盘可用空间、CPU、内存、最近扫描、失败率、Provider、数据质量、推送、模型调用和告警摘要。 |
| 运维历史 | 调用 `/ops/history`，带上 `OPS Lookback (hours)`，显示最近扫描和运行异常历史，以及异常汇总。 |
| 就绪自检 | 调用 `/ops/readiness`，带上 `OPS Lookback (hours)`，显示部署/运行自检总体状态和逐项检查。 |
| 数据源状态 | 调用 `/providers/tushare/status`，显示 Tushare token 配置、手动抓取启用状态和已实现端点数；不触发真实抓取。 |
| 数据源自检 | 调用 `/providers/tushare/readiness`，显示 Tushare token、端点、最近抓取和数据质量准入状态；不触发真实抓取或调度。 |
| 刷新雷达 | 调用 `/radar/overview`，显示后端返回的优先级计数、生命周期分布、市场情绪摘要、个股回推证据、最新扫描和当前主题。 |
| 查看信号 | 调用 `/radar/signals`，显示后端返回的信号摘要。 |
| 查看持仓 | 调用 `/portfolio/holdings`，按 User Key 显示个人持仓。 |
| 查看自选 | 调用 `/portfolio/watchlist`，按 User Key 显示个人自选。 |
| 查看报告 | 调用 `/reports`，按 User Key 显示 quick/standard 报告摘要。 |
| 查看日报 | 调用 `/reports/periodic?period=daily`，按 User Key 显示周期汇总。 |
| 查看周报 | 调用 `/reports/periodic?period=weekly`，按 User Key 显示周期汇总。 |
| 生成评分 | 读取窗口里的 Signal ID，调用 `/scores/signals/{signal_id}` 生成并显示 1d/3d/5d/10d 综合评分、评分档位和组件明细。 |
| 查看绑定 | 调用 `/telegram/bindings` 显示当前 Telegram chat 绑定和允许/禁用状态。 |
| 绑定 Chat | 读取 Telegram Chat ID 和 User Key，调用 `/telegram/bindings` 新增或启用绑定。 |
| 禁用 Chat | 读取 Telegram Chat ID，调用 `/telegram/bindings/{chat_id}` 禁用该 chat。 |
| 打开 Web 面板 | 用系统浏览器打开服务器根路径。 |

如果服务器配置了 `TELEGRAM_WEBHOOK_SECRET`，需要在 `Telegram Secret` 输入框填写同一个值；也可以用环境变量 `BAIZEFINDB_TELEGRAM_SECRET` 启动客户端。该值不会写入本地文件。`OPS Lookback (hours)` 默认 24；排查时可改成较短窗口区分最近健康状态和更早的 Provider / 数据质量 warning，客户端只把数值传给后端，不本地重算 OPS 状态。

首次使用 smoke check 默认跳过当前会在 GET 时创建用户行的持仓、自选、报告和周期报告端点，避免自检命令改变后端状态；这些个人首用数据为空会作为 warning 提醒。空雷达、空信号和空 Telegram 绑定也只是 warning，真正 blocker 包括 URL 非法、Tkinter 不可导入、API 连接失败、`/health/ready` 未 ready、`/ops/readiness` blocked 或核心 JSON 结构异常。推荐的 `first-trial.ps1` 默认传入 `ServerUrl=http://127.0.0.1:8000`、`UserKey=default`、`SmokeLookbackHours=24`，并委托 `run-client.ps1 -SmokeCheck`；它不调用采集、扫描、评分、报告生成、Telegram 修改或交易相关端点。`run-client.ps1 -SmokeCheck` 会把同一个 `-ServerUrl` 和 `-UserKey` 传给 smoke check；`-SmokeLookbackHours <n>` 会把 OPS readiness 统计窗口传给 smoke check，默认 24，范围 1 到 168；`-SmokeCompactJsonOutput <path>` 会写出首次试运行推荐 compact evidence，不含 endpoint payload/raw response；`-SmokeJsonOutput <path>` 会写出详细脱敏 JSON；`-SmokeStrict` 会把 warning 作为启动 blocker，默认 warning 不阻断启动。

## 7. 常见问题

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
