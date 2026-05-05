# Linux 服务端部署骨架 Runbook

这份文档用于说明当前仓库已经具备哪些 Linux 服务器部署骨架文件，以及后续上 Ubuntu 服务器时从哪里开始。它不是完整生产部署验收文档。

## 文件位置

| 文件 | 说明 |
| --- | --- |
| `Dockerfile` | 生产取向的 FastAPI API 镜像，启动 `uvicorn app.main:app --host 0.0.0.0 --port 8000`。 |
| `.dockerignore` | 排除 `.env`、虚拟环境、缓存和本地日志，避免把 secrets 或本地状态打进镜像。 |
| `docker-compose.server.yml` | 服务器 compose overlay，新增 `api`、`worker`、`beat` 服务，依赖 healthy 的 `postgres` / `redis`。 |
| `infra/scripts/dev_environment_check.py` | 开发环境只读自检脚本，验证 Python/uv、Linux `.venv`、Docker Compose、base/server compose config、Tkinter、PowerShell 可选项和 Git 工作区。 |
| `infra/scripts/server_deploy_check.py` | 服务器部署预检脚本，验证 `.env`、compose 配置、可选镜像构建、容器状态、API 健康检查、Ops 运行状态、Ops 趋势快照、AKShare/Tushare 状态、Tushare 准入自检和 M5 只读 smoke check。 |
| `infra/scripts/server_runtime_check.py` | 服务器运行采样脚本，连续读取健康检查、Ops 运行状态、运维历史和运行就绪自检，可选读取 Ops 趋势快照，用退出码区分阻塞状态。 |
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

先确认当前机器适合作为开发环境：

```powershell
uv run python infra/scripts/dev_environment_check.py
```

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

需要给脚本、CI 或 Windows 首次试运行流程保留结构化结果时，加
`--json-output <path>`。终端 `[OK]` / `[WARN]` / `[FAIL]` 输出保持不变，JSON
报告会写入 `generated_at`、总体 `status`、`summary` 和逐项 `checks`：

```powershell
uv run python infra/scripts/server_deploy_check.py --json-output evidence/server-deploy-check.json
```

服务已经启动后，要做一次面向交付/首次真实使用的整体验收，可以用一条命令串联
部署预检、备份工具链 check-only evidence 和运行时采样。默认 evidence 目录是
`evidence/server-delivery-acceptance/`，最终汇总报告是
`server-delivery-acceptance.json`：

```powershell
uv run python infra/scripts/server_delivery_acceptance.py
```

默认验收 `http://127.0.0.1:8000`。如果 API 运行在非默认端口、内网地址、
反向代理或域名后面，可以显式传入目标地址；该值只传给部署预检和运行采样，
不会传给 PostgreSQL backup check-only 阶段：

```powershell
uv run python infra/scripts/server_delivery_acceptance.py --base-url https://api.example.com
```

这条命令默认依次运行：

- `server_deploy_check.py --check-containers --check-api --check-m5-smoke`
- `server_deploy_check.py --check-backup --backup-check-json-output <path>`
- `server_runtime_check.py --samples 3 --interval-seconds 30 --include-ops-trends`

汇总报告会读取每个 helper 生成的 evidence JSON 顶层 `status`：任一 evidence
为 `warn` / `warning` 时，阶段和总报告标为 `warn` 但仍零退出；任一 evidence
为 `fail` / `error` / `blocked`，或预期 evidence 文件缺失、不可读、JSON 损坏时，
对应阶段标为 `fail` 并返回非零。这样新服务器空信号列表等 warning 会被保留在
交付记录里，但不会被误当成 blocker。

它只编排已有 helper，不直接导出数据库、不读取 `.env` 内容、不输出展开后的 compose
environment。需要调整证据目录、运行采样窗口，或在首个失败阶段停止：

```powershell
uv run python infra/scripts/server_delivery_acceptance.py --base-url https://api.example.com --evidence-dir evidence/server-acceptance-prod --runtime-samples 5 --runtime-interval-seconds 60 --fail-fast
```

预检脚本只用 `docker compose config --quiet` 验证配置，不输出展开后的 environment，避免真实 `.env` 中的 token 或 secret 出现在终端日志里。默认部署预检不运行 Tushare `anns_d` Beat checklist；需要把该离线/no-token checklist 纳入部署预检时，显式加：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-tushare-anns-d-beat-enablement
```

该可选检查复用 `check_tushare_anns_d_beat_enablement.py`，不访问 Tushare、不写数据库、不触发抓取、扫描、推送或模型调用；checklist `warn` 只作为预警输出，只有 `fail` 会让部署预检失败。

服务已经启动后，可以追加容器和 API 检查：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-containers --check-api
```

验证 M5 核心只读接口 JSON 契约，包含 `/ops/overview` 的运行状态、服务端磁盘/CPU/内存摘要、`/ops/history` 运维历史、`/ops/trends` 趋势快照、`/ops/readiness` 运行就绪自检、AKShare 状态、Tushare 状态、Tushare 准入自检、`/radar/signals` 候选信号列表，以及有信号时的 `/radar/signals/{id}/analysis` 单信号分析摘要。新服务器还没有信号时，analysis 采样会记录 warning，不作为部署 blocker：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-m5-smoke
```

服务启动后做短窗口运行采样，默认连续读取 `/health`、`/health/ready`、`/ops/overview`、`/ops/history` 和 `/ops/readiness` 三次。`blocked` 或接口读取失败会返回失败退出码；普通 `warning` 只记录为告警，除非加 `--fail-on-warning`：

```powershell
uv run python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --json-output runtime-check.json
```

需要在同一份 JSON/text 报告里查看最近时间桶趋势时，显式加 `--include-ops-trends`。该选项只额外 GET `/ops/trends`，不触发采集、扫描、推送、模型、报告、evidence 写入或数据库变更：

```powershell
uv run python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --include-ops-trends --trend-bucket-count 12 --json-output runtime-check.json
```

当 readiness 因历史 Provider 或数据质量失败显示 `warning`，或运行采样已经判断为 `blocked`，但需要给开发者保留一份可分享的排障证据时，可以在 runtime check 同一条命令里加 `--ops-evidence-output <path>`。runtime check 会继续做原本的短窗口采样，并额外复用 `export_ops_evidence.py` 的脱敏报告逻辑写入只读 OPS evidence；evidence 导出默认只 GET `/health`、`/health/ready`、`/ops/overview`、`/ops/history` 和 `/ops/readiness`，不会触发采集、扫描、推送、模型、备份、清理或数据库写入。若同一条 runtime check 显式加了 `--include-ops-trends --trend-bucket-count <n>`，evidence 也会额外读取只读 `/ops/trends?lookback_hours=<n>&bucket_count=<n>` 并写入脱敏后的 `snapshots.ops_trends`；趋势桶数量 `n` 必须在 1 到 48 之间。若 evidence 导出本身读取失败或导出的 readiness 为 `blocked`，runtime check 会带清晰错误返回失败；普通 `warning` 仍为零退出码：

```powershell
uv run python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --ops-evidence-output evidence/ops-evidence.json
```

也可以单独运行只读脱敏 OPS evidence 导出脚本；默认 endpoint 列表不包含 `/ops/trends`，需要趋势上下文时显式加 `--include-ops-trends --trend-bucket-count <n>`，其中 `n` 必须在 1 到 48 之间。接口读取失败或 readiness `blocked` 返回非零，普通 `warning` 仍为零退出码：

```powershell
uv run python infra/scripts/export_ops_evidence.py --json-output evidence/ops-evidence.json
uv run python infra/scripts/export_ops_evidence.py --include-ops-trends --trend-bucket-count 12 --json-output evidence/ops-evidence-with-trends.json
```

报告会递归脱敏 token/secret/authorization/url/domain/source/webhook/credential/host-like 字段和字符串，并裁剪超长文本、列表和最近事件；重点查看 `summary.readiness_status`、`alerts`、`readiness_checks`、`failure_summary`、`recent_events_count` 和有限条 `recent_events`。若接口读取失败与 readiness `blocked` 同时出现，报告状态优先标为 `error` 以便定位读取失败。

如果 runtime check 只有 `radar_stale` warning，说明服务可读但最近雷达扫描过期。可手动跑一次只依赖既有快照的扫描，再复查 readiness：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/radar/scans/run
uv run python infra/scripts/server_runtime_check.py --samples 2 --interval-seconds 1
```

更严格的部署验收可以把 warning 也视为失败：

```powershell
uv run python infra/scripts/server_runtime_check.py --samples 5 --interval-seconds 60 --fail-on-warning
```

验证 Tushare `stock_basic` token 和字段稳定性，不写数据库。`anns_d` Beat 启用前先跑离线/no-token 预调度校验；它只读取本地 golden case，检查归一化必需字段、重大风险公告应映射 risk P0、普通公告不应生成风险信号。该离线门禁不能替代真实 `TUSHARE_TOKEN` 权限、积分消耗、实时接口字段和 `/providers/tushare/readiness` 验证：

```powershell
uv run python infra/scripts/verify_tushare_stock_basic.py --json-output evidence/tushare-stock-basic.json
uv run python infra/scripts/check_tushare_anns_d_beat_enablement.py
uv run python infra/scripts/verify_tushare_anns_d_preflight.py
uv run python infra/scripts/verify_tushare_announcements.py --ann-date 20260503 --json-output evidence/tushare-anns-20260503.json
uv run python infra/scripts/verify_tushare_stock_company.py --exchange SZSE --json-output evidence/tushare-stock-company-SZSE.json
```

三条 live verify 脚本 `verify_tushare_stock_basic.py`、`verify_tushare_announcements.py` 和 `verify_tushare_stock_company.py` 的 `--json-output <path>` 保存的是脱敏 live evidence：包含状态、端点、查询参数、行数、质量状态、必需字段、缺失字段和少量去 URL/source/token/secret-like 字段的归一化样例，样例值会递归脱敏并截断超长文本；失败时也会写入脱敏 failure report。announcements evidence 步骤应放在 offline checklist 和 `verify_tushare_anns_d_preflight.py` 之后、设置 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 之前。

`evidence/`、`runtime-check*.json` 和 `ops-evidence*.json` 是本地/服务器运行证据产物，默认已加入 `.gitignore`。不要把真实 token 环境下生成的 evidence、runtime check 或 ops evidence 报告提交到 git。

手动写入 Tushare 股票基础信息或公告快照：

```powershell
uv run python infra/scripts/collect_tushare_stock_basic.py
uv run python infra/scripts/collect_tushare_announcements.py --ann-date 20260503
uv run python infra/scripts/collect_tushare_stock_company.py --exchange SZSE
```

验证 Postgres 容器内 `pg_dump` 可用：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-backup
```

需要把同一项备份工具链检查纳入部署预检证据时，可以让部署预检直接写
check-only evidence。该路径复用 `postgres_backup.py --check-only`，只验证
repo root、输出路径元数据、compose 命令形态和 `pg_dump --version`，不会导出
数据库内容：

```powershell
uv run python infra/scripts/server_deploy_check.py --check-backup --backup-check-json-output evidence/postgres-backup-check.json
```

通过备份脚本验证 repo root、输出路径元数据、compose 命令形态和
`pg_dump --version`，并保存不含数据库内容的有界证据：

```powershell
uv run python infra/scripts/postgres_backup.py --check-only --check-json-output evidence/postgres-backup-check.json
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

Linux 服务器上的完整步骤以 [infra/linux/README.md](../../infra/linux/README.md) 为准。Beat 默认每 300 秒触发 `baizefindb.radar.collect_and_scan`，即先采集最小 AKShare 数据，再运行雷达扫描；可用 `RADAR_SCAN_INTERVAL_SECONDS` 调整调度间隔，可用 `RADAR_CONTINUOUS_P1_TRIGGER_COUNT` 和 `RADAR_CONTINUITY_WINDOW_MINUTES` 调整连续 P1 快报候选阈值。`.env` 中 `TELEGRAM_PUSH_ENABLED=true` 后，该任务会继续触发 Telegram 折叠推送，并写入 `push_logs`。公网部署建议同时设置 `TELEGRAM_REQUIRE_BINDING=true`，避免无环境白名单且无数据库绑定时沿用本地开放模式；`/id` 仍可用于获取 chat id 后写入 active 绑定。

Tushare `anns_d` 公告采集有独立的可选 Beat 开关，默认关闭，不影响上述 5 分钟 AKShare+雷达闭环。只有在服务器 `.env` 中显式设置 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 时，Beat 才会额外加入 `baizefindb.providers.collect_tushare_announcements`；间隔由 `TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS` 控制，默认 `3600` 秒。启用前先运行 `uv run python infra/scripts/check_tushare_anns_d_beat_enablement.py` 汇总本地 sample gate、token、Beat 启停、interval、live verify 和 readiness/live data 状态；默认 checklist 不访问 Tushare、不写数据库、不触发抓取、扫描或推送。随后通过 `uv run python infra/scripts/verify_tushare_anns_d_preflight.py` 的本地字段漂移和风险映射样例校验，再用 `uv run python infra/scripts/verify_tushare_announcements.py --ann-date YYYYMMDD --json-output evidence/tushare-anns-YYYYMMDD.json` 保存脱敏 live evidence，最后确认 `TUSHARE_TOKEN` 权限、积分消耗、实时接口字段和 `/providers/tushare/readiness`；离线门禁不替代这些真实环境验证。

不改 `.env` 的情况下，可以用一次性容器验证 Beat schedule 形态：

```powershell
docker compose -f docker-compose.yml -f docker-compose.server.yml exec -T api python -c "from app.tasks.celery_app import celery_app; print(celery_app.conf.beat_schedule)"
docker compose -f docker-compose.yml -f docker-compose.server.yml run --rm --no-deps -e TUSHARE_ANNS_D_BEAT_ENABLED=true -e TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS=1800 api python -c "from app.tasks.celery_app import celery_app; print(celery_app.conf.beat_schedule)"
```

第一条默认只应看到 `baizefindb.radar.collect_and_scan`；第二条应保留主雷达任务，并只额外加入 `baizefindb.providers.collect_tushare_announcements`。

## 运维状态接口

服务器启动后可用以下命令快速查看最近 24 小时运行状态：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/overview?lookback_hours=24"
```

该接口只读聚合已有数据库记录和 API 进程运行信息，不触发采集、扫描、推送或模型调用。重点看 `alerts`、`server.disk_free_percent`、`server.is_disk_space_low`、`server.cpu_usage_percent`、`server.is_cpu_pressure_high`、`server.memory_used_percent`、`server.is_memory_pressure_high`、`radar.recent_scan_failure_rate`、`radar.is_latest_scan_stale`、`provider_fetch.unhealthy_count`、`data_quality.unhealthy_count`、`telegram_push.unhealthy_count` 和 `model_calls.unhealthy_count`。可用 `OPS_DISK_CHECK_PATH` 指定磁盘检查路径，用 `OPS_DISK_FREE_PERCENT_ALERT_THRESHOLD`、`OPS_CPU_USAGE_PERCENT_ALERT_THRESHOLD` 和 `OPS_MEMORY_USED_PERCENT_ALERT_THRESHOLD` 调整资源告警阈值。

查看最近运行异常历史：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/history?lookback_hours=24&limit=20"
```

重点看 `recent_events` 和 `failure_summary`。该接口同样只读，不触发采集、扫描、推送或模型调用。

查看 OPS 趋势桶：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/trends?lookback_hours=24&bucket_count=12"
```

Telegram `/ops_trends` 使用同一个 24 小时 / 12 桶只读契约，只展示后端返回的扫描、失败和 unhealthy 计数，不重算 OPS readiness 或运行状态，也不触发采集、扫描、评分、报告、Telegram mutation、模型调用、evidence 写入或后端修改。

查看运行就绪自检：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ops/readiness?lookback_hours=24"
```

重点看 `status` 和 `checks`。`ready` 表示核心运行条件满足，`warning` 表示可运行但有警告，`blocked` 表示至少一个关键检查失败。

需要把一段时间的运行状态保存为验收记录时，使用运行采样脚本：

```powershell
uv run python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --json-output runtime-check.json
```

该脚本只读，不触发采集、扫描、推送或模型调用；它基于 `/health/ready` 和 `/ops/readiness` 判断阻塞状态，并汇总 `/ops/overview` 的资源摘要、alerts 以及 `/ops/history` 的 failure summary。需要趋势上下文时加 `--include-ops-trends`，脚本会读取 `/ops/trends` 并汇总最新桶的 unhealthy 计数；这只是后续图表和监控的基础，不代表完整监控系统。需要在同一次运行里保存脱敏 evidence 时加 `--ops-evidence-output evidence/ops-evidence.json`，尤其适用于 `warning` 或 `blocked` 状态下把可分享证据随 runtime check 一起留存。

Windows 本机演练 server overlay 时，确认 `127.0.0.1:8000` 没有被本机 `uvicorn` 占用，否则浏览器和 `curl` 可能命中本地开发进程而不是 Docker API：

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  Select-Object LocalAddress,LocalPort,OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" |
  Select-Object ProcessId,CommandLine
```

如果确认是本项目的本地 `uvicorn`，先停止它，再验证 Docker API 的 `/health` 是否返回 `environment=server`。

## Secrets 边界

- `.env` 不进入 git，也不会被 Dockerfile 复制进镜像。
- `backups/` 不进入 git；数据库备份文件只留在服务器安全备份流程里。
- 文档和示例只使用 `<telegram-bot-token>`、`<telegram-webhook-secret>`、`<db-password>` 这类占位符。
- Telegram webhook 需要公网 HTTPS 后再设置到 `https://<your-domain>/telegram/webhook`。
- Telegram 折叠推送只使用 `.env` 中的 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_ALLOWED_CHAT_IDS`、`TELEGRAM_REQUIRE_BINDING` 和 `TELEGRAM_PUSH_ENABLED`；不要把真实 chat id、token 或推送日志导出文件提交到 git。
- 当前只是部署骨架；PostgreSQL 默认凭据、TLS 证书签发、备份策略、监控告警和生产安全加固仍需要后续专门处理。
