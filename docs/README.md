# BaizeFinDB 开发文档导航

本目录放项目开发过程中需要反复查阅的执行文档。`项目开发总文档.md` 负责讲方向和边界，本目录负责讲怎么开发、怎么验证、下一步怎么拆。

## 先读哪几份

| 文档 | 用途 | 什么时候读 |
| --- | --- | --- |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | 当前阶段、已完成能力、可用 API 和下一步建议 | 接手项目前先读 |
| [runbooks/local-dev.md](runbooks/local-dev.md) | 本地开发、Docker、迁移、采集、扫描、故障处理 | 每次搭环境或调试服务时读 |
| [runbooks/linux-server.md](runbooks/linux-server.md) | Linux 服务端部署骨架、Docker 镜像、compose overlay、worker/beat、systemd、nginx | 准备 Ubuntu 服务器部署前读 |
| [runbooks/windows-client.md](runbooks/windows-client.md) | Windows 客户端 MVP 的启动、连接本地/服务器和故障处理 | 在 Windows 上查看 API 状态、雷达总览或信号时读 |
| [api/current-api.md](api/current-api.md) | 当前 API、调用顺序、curl 示例、响应示例 | 写脚本、接 Telegram/Web/报告前读 |
| [specs/current-data-model.md](specs/current-data-model.md) | 当前真实数据表和规划表边界 | 改数据库、写迁移、设计新模块前读 |
| [prd/m5-next-step.md](prd/m5-next-step.md) | M5 A 股 5 分钟资金主线雷达 MVP PRD | 开始雷达闭环、Telegram/Web/报告前读 |
| [research-terminal-reference.md](research-terminal-reference.md) | FinceptTerminal / OpenBB 参考评估和采用边界 | 做 Web/客户端终端化改造前读 |

## 当前开发原则

- 先做可运行小闭环，再扩大功能面。
- 下一阶段优先做 A 股 5 分钟资金主线雷达；Telegram、Web、报告、持仓自选、日报周报和评分都围绕雷达结果展开。
- 雷达等级由规则引擎判定，AI 只能解释、补证据、指出风险。
- 板块/主题/概念权重大于单票异动；个股异动主要用于反推主线或风险。
- 发布类输出必须复用 M4 审查和分享预检。
- Linux 服务器部署目前只有骨架，包含 API 容器、Celery worker/beat、compose overlay、server compose runtime contract 预检、systemd、nginx 示例、部署预检、运行采样、监控摘要脚本、no-send 告警 payload 生成脚本、默认预览的 Telegram 告警交付适配器、会写 alert payload evidence 的 5 分钟 monitor timer 示例、每日 PostgreSQL backup timer 示例、默认 dry-run 的 backup retention helper 和 restore check-only evidence；不要把它当作完整生产部署。
- Linux 部署骨架还包含可选 `baizefindb-alert-telegram.service` oneshot 示例；timer 需要在手动 evidence 验证通过后单独复制启用，使用前必须先在服务器本地创建服务账号可读的 `/etc/baizefindb/telegram-alert.env`，service 会在发送前先写 env check evidence，并确认 dedupe state 生效。
- Telegram 告警凭据文件可先用 `server_alert_telegram_env_check.py --env-file /etc/baizefindb/telegram-alert.env` 做只读预检；它验证文件存在、权限、`TELEGRAM_BOT_TOKEN` 配置和 `TELEGRAM_ALLOWED_CHAT_IDS` 格式，只输出 token 是否配置、chat id 数量和 masked chat refs。
- 手动运行 `baizefindb-alert-telegram.service` 后，用 `server_alert_telegram_service_verify.py --json-output evidence/server-alert-telegram-service-verification.json` 检查 env check、send evidence 和 dedupe state；`sent` / `deduped` 是通过路径，`skipped` 只说明本次无通知需求，preview、配置错误、发送失败或损坏 evidence 不能作为调度前依据。
- 可选 `baizefindb-alert-telegram.timer` 示例只在完成上述手动验证后启用；它每 5 分钟触发 alert service，不包含 token/chat id 或发送命令本身，仍由 service 负责 strict env preflight、`--send` 和 dedupe state。
- 新机器迁移、Linux 服务器续开发或开始较长开发前，先运行 `uv run python infra/scripts/dev_environment_check.py` 做只读开发环境自检；它检查 Python/uv、Linux `.venv`、Docker Compose、base/server compose config、Tkinter、PowerShell 可选项和 Git 工作区，不安装软件、不启动容器、不输出 secrets。
- 新库执行 `uv run alembic upgrade head` 之后仍然没有业务数据；需要首用演示或让 M5 smoke check 抽到分析样本时，运行 `uv run python infra/scripts/seed_demo_data.py --json-output evidence/demo-seed.json`。该脚本只写合成开发/demo 数据，包含 `default` 用户、持仓/自选、雷达信号、证据、审查和 quick 报告，不访问真实 Provider、不写 token、不保存真实个人持仓，重复执行按稳定 demo key 复用记录。
- `/ops/overview`、`/ops/history`、`/ops/trends` 和 `/ops/readiness` 是当前只读运行状态、服务端磁盘/CPU/内存摘要、运维历史、趋势快照、运行就绪自检和告警摘要入口，可用于本地排障、Web/Windows GUI/Telegram OPS 入口、服务器 smoke check、`server_runtime_check.py` 运行采样、`server_monitor_check.py` cron/systemd 友好监控摘要、`server_monitor_check.py --alert-json-output` 同步 no-send 告警 payload 生成、`server_alert_payload.py` 单独 no-send 告警 payload 生成，以及 `server_alert_telegram.py` 默认 preview / 显式 `--send` 的 Telegram 告警交付。`/ops/trends` 只按固定时间桶聚合已有运行表并附带当前资源上下文，不持久化资源采样，也不是完整监控系统。Web 状态面板会读取 `/ops/trends?lookback_hours=24&bucket_count=12`，`trend` / `trends` 命令只刷新并展示后端返回的趋势桶计数和趋势图，不在浏览器重算 OPS readiness 或状态。Windows 客户端 `OPS 趋势` 按钮会使用当前 `OPS Lookback (hours)` 并固定请求 `bucket_count=12`，只展示后端趋势桶的扫描、失败和 unhealthy 计数。Telegram `/ops_trends` 固定读取 24 小时 / 12 桶后端趋势计数，只展示扫描、失败和 Provider、数据质量、Telegram 推送、模型调用 unhealthy 桶摘要，不重算 OPS readiness 或状态。Web 和 Telegram 告警钻取固定沿用 24 小时窗口，可用 Web 命令栏 `warn` / `warning` 或 Telegram `/ops_warn` 打开，只展示后端 readiness、非 OK 检查、alerts、failure_summary 和有界 recent events，不在浏览器或 Telegram 层重算 OPS 状态。
- `server_alert_telegram.py --dedupe-state <path>` 是定时发送前的本地冷却保护：默认按 `dedupe_key` 在 3600 秒内抑制重复发送，同一告警成功发送后才更新本地 JSON state；preview、`should_notify=false`、配置错误、失败发送和无效 state 都不会写入成功状态。
- `server_deploy_check.py --check-m5-smoke` 会只读验证健康、OPS、Provider、Radar、Telegram、`/radar/signals` 和有信号时的 `/radar/signals/{id}/analysis` JSON 契约；analysis smoke 不只检查顶层字段存在，还会校验 5 个固定 `agent_assessments` 角色、状态取值和 findings/next_actions 数组形状；空信号列表只记录 warning，避免阻断新服务器首次部署。`server_delivery_acceptance.py` 默认验收 localhost，也可用 `--base-url <url>` 验证非默认端口、反向代理或域名地址；它会串联部署预检、backup check-only、backup retention dry-run 和 runtime check，并保留 helper evidence JSON 的 warning 状态，汇总报告可见但仍零退出，缺失、损坏或失败 evidence 会标为 fail；生产切换前可加 `--fail-on-warning`，让 warning-only 验收仍写 `warn` 报告但返回非零退出码；生产化交付前可加 `--production-readiness` 一次启用当前非破坏性生产验收预设，覆盖 server compose contract、systemd 模板、Telegram 严格绑定、Tushare Beat checklist、OPS evidence、no-send alert preview 和 Telegram alert env preflight，并在 JSON 报告中写入 `profile: "production_readiness"`；首次执行前可加 `--plan-only` 只写命令/evidence 计划报告，报告为 `execution_mode: "plan"` 和 `status: "planned"`，不调用 helper、Docker、API、Telegram、systemd 或 journalctl；该预设不启用手动 alert service verification、严格 env 权限、`--fail-on-warning`、`--fail-fast`、restore、Telegram send、backup deletion 或 systemd/journalctl 调用。需要单独控制时仍可使用 `--include-server-compose-contract-check`、`--include-systemd-unit-check`、`--include-tushare-anns-d-beat-enablement`、`--include-ops-evidence`、`--include-alert-telegram-preview`、`--include-alert-telegram-env-check`、`--include-alert-telegram-service-verify`、`--skip-backup-retention` 和 `--restore-check-input backups/<file>.sql` 等开关。
- `server_deploy_check.py --check-server-compose-contract` 会解析 server overlay 的 `docker compose config --format json` 输出，锁定 `api`、`worker`、`beat`、`postgres`、`redis` 服务存在，API/worker/beat 的 server 环境变量、healthy 依赖、API 8000 + `/health`、Celery worker/beat 命令、beat schedule 和 `restart: unless-stopped` 不漂移；失败时不输出 compose stdout，避免泄露展开后的 env 值。
- `server_deploy_check.py --check-telegram-strict-binding` 会只读读取 `/telegram/status`，检查生产/公网部署前是否已开启 `TELEGRAM_REQUIRE_BINDING=true`，或至少存在环境白名单/active 数据库绑定；如果三者都没有，会记录 warning，不读取 `.env` 明文、不调用 `/telegram/bindings`、不发送 Telegram、不输出 raw chat id。需要把这项 readiness 放进同一交付验收包时，加 `server_delivery_acceptance.py --include-telegram-strict-binding-check`；生产切换前可再配合 `--fail-on-warning` 让 warning-only 验收返回非零。
- `server_deploy_check.py --check-systemd-units` 只读验证仓库内 `infra/linux/` systemd 模板，不检查已安装 unit；它用于在复制到服务器前发现 service/timer 目标、周期、证据输出、dedupe、strict env preflight 或 no-secret 边界漂移。
- Tushare 当前已支持 `stock_basic`、`anns_d` 和 `stock_company` 手动抓取、失败记录、日志、快照查询和 `/providers/tushare/readiness` 只读准入自检；`anns_d` 重大风险公告可被雷达扫描映射为 risk P0，`golden_cases/radar_m5_risk_announcements.json` 已覆盖重大风险公告、退市风险公告、普通公告无信号和误报反馈守卫的完整扫描样例，并已纳入 `check_tushare_anns_d_beat_enablement.py --json-output <path>` 默认离线 gate。该文件的每个 case 必须声明 `case_type`，支持 `true_positive_major_risk`、`true_positive_critical_risk`、`false_positive_guard`、`false_negative_guard` 和 `ordinary_no_signal`，后续真实误报/漏报样例优先追加到这里。`anns_d` Beat 调度默认关闭，启用前必须再做真实 token 验证、字段漂移、积分消耗和误差样例。
- Web、Windows 客户端、Telegram `/tushare` 和 `/tushare_ready` 只读展示 Tushare 配置状态和准入自检，不触发真实抓取，不泄露 token 原文。
- Web 信号详情已展示 `/radar/signals/{signal_id}/analysis` 返回的确定性 `agent_assessments` scaffold，只显示后端 label/status/summary/findings/next_actions，不在浏览器本地生成多 agent 分析或重算雷达/审查状态。
- Telegram `/analysis <id>` 只读消费 `/radar/signals/{signal_id}/analysis`，展示后端单信号研究摘要和确定性 `agent_assessments` scaffold，不本地生成分析、不重算 agent 状态、不展示 raw source、raw excerpt、精确信心值、个人持仓字段或交易指令。
- Windows 客户端 `查看分析` 按钮只读消费 `/radar/signals/{signal_id}/analysis`，展示后端单信号研究摘要和确定性 `agent_assessments` scaffold，不本地生成分析、不重算 agent 状态、不展示 raw source、raw excerpt、精确信心值、个人持仓字段或交易指令。
- Windows 客户端 `生成 Deep Report` 按钮先确认，再调用 `/reports/deep/from-signal?user_key=<User Key>` 并发送 `confirm_deep_report=true`；取消确认不调用 API，客户端只展示后端返回报告摘要，不生成报告正文、审查状态或建议标签。
- Windows 客户端默认仍是 MVP 源码运行版；首次试运行推荐 `clients/windows/first-trial.ps1`，默认连接 `http://127.0.0.1:8000`、使用 `user_key=default` 和 24 小时 OPS readiness/OPS trends 窗口，并只委托 `run-client.ps1 -SmokeCheck`，通过后才打开 GUI。需要本机 Docker 后端时必须显式加 `-StartDockerBackend`；该 opt-in 路径使用 `docker-compose.yml` + `docker-compose.server.yml` 先重建当前源码的 `api` 镜像，确保 `/ops/trends` 等新端点存在，再启动 `postgres` / `redis`、通过 `api` 容器执行 `alembic upgrade head`、启动 `api` / `worker` / `beat`，并等待 `<ServerUrl>/health` 后才进入 smoke/GUI 委托，Docker build、启动、迁移失败或超时会在 GUI 前阻断；加 `-SmokeOnly` 时仍先完成同一 Docker bootstrap/health wait，然后只跑 smoke check 并退出；加 `-DeployCheckJsonOutput <path>` 可在 Docker health 后、smoke/GUI 前保存部署预检 JSON，`-DeployCheckServerComposeContract`、`-DeployCheckM5Smoke` 和 `-DeployCheckBackupJsonOutput <path>` 可分别把 server compose runtime contract、只读 M5 契约和 PostgreSQL backup check-only evidence 纳入同一次部署预检；Windows launcher 只追加后端脚本参数，不在 PowerShell 中解析 compose。`clients/windows/package-client.ps1` 仅提供可选 PyInstaller onedir 打包脚手架，不是签名安装器或生产分发包。打包工具通过 `uv sync --group package` 和 `uv run --group package powershell ... clients/windows/package-client.ps1 ...` 使用，PyInstaller 不进入默认运行时或普通 dev 路径。`-DryRun` 可在不生成构建产物的情况下预览命令，`-CheckOnly` 可运行 Python/Tkinter/入口模块 preflight 和 PyInstaller 可用性检查后退出且不生成产物，必要时加 `-CheckJsonOutput` 保存只含打包前置条件、命令和路径元数据的有界 JSON 证据。非 dry-run 默认先验证 Python 3.12、`tkinter` import 和入口模块解析；只有本地排查特殊问题时才加 `-SkipPreflight`，且不能和 `-CheckOnly` 同用。客户端只消费后端 API，不重新计算雷达等级、市场情绪、运行状态、数据源状态或评分。首次使用也可直接用 `run-client.ps1 -SmokeCheck` 在打开 GUI 前执行只读 preflight，或用 `run-client.ps1 -SmokeOnly` 对已运行 API 只执行 preflight 并退出、不打开 GUI；必要时加 `-SmokeLookbackHours` 调整 `/ops/readiness` 和可选 `/ops/trends?lookback_hours=<selected>&bucket_count=12` 的 1 到 168 小时统计窗口、加 `-SmokeCompactJsonOutput` 保存不含 endpoint payload/raw response 的 compact evidence、加 `-SmokeJsonOutput` 保存详细脱敏 JSON，或加 `-SmokeStrict` 让 warning 阻断启动。已打开 GUI 后，可用 `OPS 趋势` 按钮只读读取 `/ops/trends?lookback_hours=<selected>&bucket_count=12`，可用 `告警钻取` 按钮只读聚合 OPS readiness/overview/history 中的后端告警字段，也可用 `首用诊断` 按钮复用同一套 smoke check，传入当前 Server URL、User Key 和 OPS Lookback，默认不写 evidence 文件、不打开第二个窗口。
- 不接自动交易，不输出强买卖指令，不保存券商交易密码。
- 新表必须有 Alembic 迁移，新规则必须有测试或 golden case。
- 后续 AI 协作默认策略：模块设计或开发阶段完成后，AI 自动做 git commit，不再每次向用户确认；不自动 push。
- 即使是小的模块化更新，只要形成明确阶段边界，也要同步更新相关开发文档并提交 git commit。
- 提交前必须跑对应质量检查、查看 `git status`，并检查 staged 文件，确认没有误提交 `.env`、密钥、个人数据、原始付费数据、持仓截图、报告导出等敏感文件。
- commit 仍按模块边界拆分，不把多个无关模块混成一个大提交；commit message 要能看懂模块和动作，例如 `docs(prd): refine radar mvp`、`feat(radar): add scan scheduler`、`test(radar): cover p1 continuity`、`docs(dev): add git workflow`。
- 文档、迁移、测试和代码要随模块一起提交；如果只完成设计文档，也要提交文档版本。大模块拆成设计文档、数据模型/迁移、业务实现、测试/文档等阶段 commit。
- 如发现未识别的脏文件或疑似用户手工改动，不能自动纳入提交，要隔离并说明。

## 常用入口

```powershell
docker compose up -d postgres redis
uv run python infra/scripts/dev_environment_check.py
uv run alembic upgrade head
uv run python infra/scripts/seed_demo_data.py --json-output evidence/demo-seed.json
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
```

开发 API 默认地址：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/ready`
- `http://127.0.0.1:8000/docs`
