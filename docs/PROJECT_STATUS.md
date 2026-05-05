# BaizeFinDB Project Status

更新日期：2026-05-05

## 当前阶段

当前已完成 **M5 A 股 5 分钟资金主线雷达 MVP 验收项**，下一阶段进入生产化验证、真实数据源增强和运行稳定性建设。

项目已经具备后端骨架、AKShare 最小数据底座、Tushare `stock_basic`、`anns_d` 和 `stock_company` 手动抓取能力、Tushare 只读准入自检、Tushare `anns_d` 离线预调度校验、Tushare 重大风险公告到 risk P0 的轻量映射、带 `case_type` 分类的 Tushare 公告完整雷达扫描 golden cases、雷达扫描批次、候选信号、证据链、P0/P1/P2 初判、生命周期初判、连续扫描记忆、雷达总览查询、优先级和生命周期分布、单信号只读研究摘要 API 和确定性 `agent_assessments` scaffold、Web/Telegram/Windows 市场情绪摘要、个股回推证据、涨停/跌停/炸板池情绪摘要、Provider 数据质量透传、只读运维状态、服务端磁盘/CPU/内存摘要、运维历史和运行就绪自检、轻量规则审查、内部分享预检、公开分享 payload、持仓/自选最小维护 API、quick/standard 报告 MVP、手动 deep 报告入口、Telegram 折叠推送日志，以及可重复执行的开发/演示数据种子脚本；部署 M5 smoke check 已校验单信号分析的固定 agent assessment 角色和基础字段形状。真正 LLM-backed 多 agent 编排仍是后续阶段，但已新增只读模型 Provider readiness preflight、默认关闭的 OpenAI-compatible 模型客户端审计骨架、模型分析草稿输出净化契约，以及第一个显式手动 `POST /radar/signals/{signal_id}/model-analysis-draft` 草稿 API，用于启用前检查 provider/model/key 姿态、模型调用 fallback/degraded 留痕，并保证模型文本进入产品面前先被结构化、脱源、限长和交易语言拦截。

Telegram Bot MVP Webhook 模块已补充为当前命令入口，可查看健康状态、运行状态、运维历史、OPS 趋势桶、运行就绪自检、OPS 告警钻取、Tushare 数据源状态和准入自检、最近扫描状态、雷达总览、生命周期分布、市场情绪摘要、个股回推证据、信号折叠摘要、单条信号复盘、单信号后端分析摘要、当前聊天绑定的持仓、自选、报告列表、日报/周报和单信号 v2 评分档位与组件明细；`/analysis <id>` 只读消费 `/radar/signals/{signal_id}/analysis`，展示后端 key points、metric highlights、risk flags、确定性 agent assessments、evidence/review summary 和 next actions，不本地生成分析、不展示 raw source、raw excerpt、精确信心值、个人持仓字段或交易指令；`/ops_trends` 固定使用 Telegram 24 小时 OPS 窗口和 `bucket_count=12`，只读复用后端趋势桶扫描、失败和 unhealthy 计数，不重算 OPS readiness 或运行状态；`/ops_warn` 固定使用 Telegram 24 小时 OPS 窗口和有界历史条数，只读复用后端 readiness、overview 和 history，优先展示 readiness 状态、非 OK 检查、alerts、failure_summary 和有界 recent events；`telegram_bindings` 已接入 chat 与 `user_key` 绑定、白名单和禁用状态，环境变量 `TELEGRAM_ALLOWED_CHAT_IDS` 仍可作为硬过滤，`TELEGRAM_REQUIRE_BINDING=true` 可关闭无白名单且无绑定时的本地开放兜底；Telegram 折叠推送 API 已能基于最新扫描按 P0/P1/P2 汇总、复用审查过滤 blocked、记录 push log，并在 P0 推送后为对应聊天用户自动生成 standard report。Telegram 仍只消费后端结果，不重新计算雷达等级、运行状态、OPS readiness、数据源状态、分析摘要、agent 状态或评分。

M5 验收测试已覆盖 5 分钟 Celery beat 调度、P0/P1/P2 规则、新闻不能单独触发主线 P0、风险事件 P0、生命周期、Review Agent 审查范围、审查阻断、Telegram 折叠推送、P0 推送后 standard report、持仓隔离、报告审查、deep 报告手动确认约束、模型降级审计、Web 核心页面顺序和公开分享脱敏。

Windows 客户端已增加只读 OPS 趋势摘要：GUI `OPS 趋势` 按钮使用当前 `OPS Lookback (hours)` 请求 `/ops/trends?lookback_hours=<selected>&bucket_count=12`，只展示后端趋势桶里的扫描、失败和 Provider、数据质量、Telegram 推送、模型调用 unhealthy 计数，不本地推导 OPS readiness 或状态，也不触发采集、扫描、评分、报告、Telegram mutation、模型调用、evidence 写入或交易相关动作。

Windows 客户端已增加单信号后端分析摘要入口：GUI `查看分析` 按钮读取当前 Signal ID，调用 `/radar/signals/{signal_id}/analysis`，展示后端 key points、metric highlights、risk flags、确定性 agent assessments、evidence/review summary 和 next actions。客户端不本地生成分析、不重算雷达定级、生命周期、审查状态、agent 状态或评分，也不展示原始来源定位、raw excerpt、精确信心值、个人持仓成本或交易指令。

Windows 客户端已增加手动 deep 报告入口：GUI `生成 Deep Report` 按钮读取当前 Signal ID，先弹出确认；确认后调用 `/reports/deep/from-signal?user_key=<User Key>` 并发送 `confirm_deep_report=true`，取消确认不会调用 API。报告正文、审查状态、建议标签和生成元数据仍由后端决定，Windows 客户端只展示返回报告摘要，不通过 quick/standard endpoint 或本地模板生成 deep 报告。

Windows 客户端 MVP 已补充为本地桌面入口，可连接本地或 Linux 服务器 API，查看健康状态、运行状态、运维历史、运行就绪自检、OPS 告警钻取、首用诊断、Tushare 数据源状态和准入自检、雷达总览、生命周期分布、市场情绪摘要、个股回推证据、信号列表、持仓、自选、报告摘要、确认后手动生成 deep 报告、日报/周报汇总、单信号 1d/3d/5d/10d v2 综合评分明细，维护 Telegram chat 绑定/白名单，并打开现有 Web 面板；它仍只消费后端结果，不重新计算雷达等级、运行状态、OPS readiness、数据源状态或评分。Windows GUI 已提供 `OPS Lookback (hours)` 输入框，默认 24，范围 1 到 168，运行状态、运维历史、就绪自检、告警钻取和首用诊断都会使用该值，非法输入会在发起 API 请求前阻断。告警钻取只读调用 `/ops/readiness`、`/ops/overview` 和 `/ops/history`，优先展示后端 readiness 状态、非 OK 检查、overview alerts、failure_summary 和有界最近事件，不触发采集、扫描、评分、报告生成、Telegram mutation、模型调用、evidence 写入或交易相关动作。Windows 首次使用 smoke check 已接入，可在打开 GUI 前验证 Tkinter import、核心健康、OPS readiness、可选 `/ops/trends?lookback_hours=<selected>&bucket_count=12` 和非变更只读端点，空首用数据和可选 trends 读取失败只作为 warning；首次试运行推荐 compact evidence，只保存总体状态、服务端 URL 元数据、脱敏 user key、检查数、每项检查的 name/status/message、warning/blocker 和 OPS readiness 非 OK 摘要，不包含端点 payload、原始后端响应、环境变量、token、secret、API key、authorization、原始 provider URL、个人持仓、二进制或构建输出；详细脱敏有界 JSON 仍保留给深度排障。OPS readiness 和可选 trends 统计窗口默认 24 小时，可配置为 1 到 168 小时，便于区分最近健康状态和历史 Provider / 数据质量 warning；`clients/windows/first-trial.ps1` 已成为推荐首次试运行入口，默认连接 localhost、使用 `default` 用户键和 24 小时 OPS readiness/trends 窗口，并委托 `run-client.ps1 -SmokeCheck`，通过后才打开 GUI；需要本机 Docker 后端时必须显式加 `-StartDockerBackend`，脚本会使用 `docker-compose.yml` + `docker-compose.server.yml` 先重建当前源码的 `api` 镜像，确保 `/ops/trends` 等新端点存在，再启动 `postgres` / `redis`、通过 `api` 容器执行 `alembic upgrade head`、启动 `api` / `worker` / `beat` 并等待 `<ServerUrl>/health`，Docker build、启动、迁移失败或超时会在 GUI 前阻断；可选 `-DatabaseInventoryJsonOutput <path>` 只能和 `-StartDockerBackend` 同用，会在 Docker health 后、deploy preflight/smoke/GUI 前运行 `database_inventory.py --json-output <path>` 保存脱敏数据库只读清单 JSON，失败时阻断后续启动；可选 `-DeployCheckJsonOutput <path>` 只能和 `-StartDockerBackend` 同用，会在 Docker health 后、smoke/GUI 前运行 `server_deploy_check.py --check-containers --check-api --json-output <path>` 保存部署预检 JSON，失败时阻断后续启动；加 `-DeployCheckServerComposeContract` 会把 server compose runtime contract 纳入同一次部署预检，Windows launcher 只追加 `--check-server-compose-contract`，不在 PowerShell 中解析 compose；加 `-DeployCheckM5Smoke` 会额外把服务端只读 M5 JSON 契约纳入同一报告；加 `-DeployCheckBackupJsonOutput <path>` 会在同一次部署预检中额外写出 PostgreSQL backup check-only evidence；`-SmokeOnly` 可用于只执行同一套 smoke check 并退出、不打开 GUI，和 `-StartDockerBackend` 同用时仍先完成 Docker bootstrap/health wait；`run-client.ps1 -SmokeCheck` 仍可直接使用，复用 ServerUrl/UserKey，支持 `-SmokeLookbackHours`、`-SmokeCompactJsonOutput`、`-SmokeJsonOutput` 和 `-SmokeStrict` warning 阻断模式；GUI 的 `首用诊断` 按钮复用同一套 `run_smoke_check` 和 `format_summary`，传入当前 Server URL、User Key 和 OPS Lookback，只在当前窗口显示摘要，默认不写 evidence 文件且不打开第二个 GUI。`clients/windows/package-client.ps1` 已提供可选 PyInstaller onedir 打包脚手架，用于 Windows 目标机验证 exe 形态；PyInstaller 通过可选 `package` 依赖组、`uv sync --group package` 和 `uv run --group package powershell ... clients/windows/package-client.ps1 ...` 复现，不进入默认运行时或普通 dev 路径；`-DryRun` 可不生成构建产物地预览命令；`-CheckOnly` 可运行 Python/Tkinter/入口模块 preflight 和 PyInstaller 可用性检查后退出且不生成构建产物；`-CheckJsonOutput` 只能随 `-CheckOnly` 写出有界前置条件 JSON 证据，不包含环境变量、密钥、smoke 报告、后端响应、构建输出或二进制；非 dry-run 默认先验证 Python 3.12、`tkinter` import 和入口模块解析，特殊本地排查可用 `-SkipPreflight`，但不能与 `-CheckOnly` 同用；默认输出、中间产物和本地 evidence pattern 已忽略，不提交二进制，也不是签名安装器、onefile、MSI、自动更新或生产分发。Tushare 状态/自检视图只读取 `/providers/tushare/status` 和 `/providers/tushare/readiness`，不触发真实抓取。

Web 雷达终端工作台已在状态面板加入只读 OPS 趋势摘要、OPS 趋势图和 OPS 告警钻取，命令栏 `trend` / `trends` 会滚动并刷新 `/ops/trends?lookback_hours=24&bucket_count=12`，只展示后端趋势桶的扫描、失败和 unhealthy 计数，并用同一批后端桶渲染扫描/失败/异常柱状图，不在浏览器重算 OPS readiness 或状态；命令栏 `warn` / `warning` 会滚动并刷新钻取块，该块固定沿用 Web 24 小时 OPS 窗口，只读取 `/ops/readiness`、`/ops/overview` 和 `/ops/history`，优先展示后端 readiness 状态、非 OK 检查、overview alerts、history `failure_summary` 和有界 recent events，不在浏览器从 alerts/counts/events 重算 OPS 状态，也不触发采集、扫描、评分、报告、Telegram mutation、模型调用、evidence 写入或交易相关动作。Web 信号详情已读取 `/radar/signals/{signal_id}/analysis` 并展示后端生成的只读单信号研究摘要，包括 key points、metric highlights、risk flags、确定性 agent assessments、evidence/review summary 和 next actions；Web 只显示后端 `agent_assessments` 的 label/status/summary/findings/next_actions，不本地生成或重算多 agent 输出。Web 信号详情也新增手动 `生成模型草稿` 按钮，点击后才 POST `/radar/signals/{signal_id}/model-analysis-draft`，只展示后端返回的模型/草稿状态、脱敏 advisory 字段、blocked count 和 boundary。前端不重算雷达定级、生命周期、审查状态、评分、模型状态或交易建议。Web 雷达终端工作台、Windows 客户端和 Telegram `/tushare` 已展示 Tushare token 状态、手动抓取启用状态和已实现端点数；`/providers/tushare/readiness`、Web 数据源状态卡片、Windows“数据源自检”按钮和 Telegram `/tushare_ready` 已展示 token、端点、最近抓取、数据质量准入状态和 `anns_d` Beat 开关策略。所有这些入口都只读，不触发真实抓取或调度。

`infra/scripts/dev_environment_check.py` 已新增为开发环境只读自检入口，可在新机器迁移或继续开发前检查 Python/uv、Linux `.venv`、Docker Compose、base/server compose config、Tkinter、PowerShell 可选项和 Git 工作区，并可写出有界 JSON evidence；它不安装软件、不启动容器、不输出 `.env` 或 secrets。

`infra/scripts/model_provider_readiness.py` 已新增为未来 LLM-backed 多 agent 接入前的只读配置自检入口：默认 `MODEL_ANALYSIS_ENABLED=false` / `MODEL_PROVIDER=disabled` 为 OK；启用 `openai` 时检查 `MODEL_PRIMARY_MODEL` 和 `OPENAI_API_KEY`，启用 `custom` 时检查 `MODEL_PRIMARY_MODEL`、`MODEL_API_BASE_URL` 和 `MODEL_API_KEY`。该 helper 不调用模型、不验证 token、不读取数据库、不生成报告、不发送 Telegram、不输出 API key；`MODEL_AUDIT_STORE_RAW_PROMPT=true` 会作为 warning。

`app.ai.model_client` 已新增为未来模型调用的第一层执行/audit scaffold：启用 `MODEL_ANALYSIS_ENABLED=true` 后，可构建 `openai` 或 `custom` 的 OpenAI-compatible `/chat/completions` 客户端，发送 `model`、`messages` 和可选 `response_format`，并解析 `choices[0].message.content`。执行包装器会在默认关闭时返回 `disabled` 且不写审计；主模型成功返回 `ok` 且不写 `model_call_logs`；主模型失败且 fallback 成功返回 `fallback` 并写一条 fallback 审计；主模型和 fallback 都失败返回 `degraded` 并写一条 degraded 审计。当前该模块没有接入 `/radar/signals/{signal_id}/analysis`、报告、Telegram、Provider 或调度，不会修改雷达优先级、生命周期、审查状态或其他业务表。

`app.ai.analysis_output` 已新增为模型分析草稿的输出净化契约：只解析 JSON 文本，允许 `advisory_summary`、`observations`、`risk_notes`、`follow_up_questions` 和固定 `suggested_attention_label`，忽略未知字段，缺失字段给默认空值；所有文本会脱源 URL/domain 并按字段限长/限条数。malformed JSON 或非对象 JSON 返回 `degraded`，直接交易语言如 `马上买入`、`满仓`、`保证收益`、`买入信号`、`卖出信号` 返回 `blocked`，安全否定风险提示如 `不建议马上买入` 不阻断。该模块不直接调用模型、不修改 radar/report/Telegram/Provider 状态，并已用于手动模型草稿 API。

`POST /radar/signals/{signal_id}/model-analysis-draft` 已新增为第一个显式手动模型草稿 API。默认 `MODEL_ANALYSIS_ENABLED=false` / `MODEL_PROVIDER=disabled` 时返回 disabled/not_available，不联网、不写审计；启用后只使用确定性 `/analysis` 的脱敏上下文调用模型客户端，再通过 `app.ai.analysis_output` 净化 JSON 草稿。主模型成功不写审计，fallback 成功写 fallback 审计，provider degraded、unsafe output 或 malformed output 写 degraded 审计，默认不保存完整 raw prompt。该接口不修改 P0/P1/P2、生命周期、审查状态、报告、Telegram、Provider 或确定性 `/analysis` 输出；Web 信号详情已有手动 `生成模型草稿` 按钮，Windows/Telegram 仍未接入。

`server_deploy_check.py --check-model-provider-readiness` 已可把上述模型 Provider readiness 纳入 Linux 部署预检；可选 `--model-provider-readiness-json-output <path>` 会写出独立脱敏 evidence，`warn` 保持非阻塞，`fail` 会让部署预检失败。`server_delivery_acceptance.py --include-model-provider-readiness` 会把该检查纳入同一交付验收包并追踪 `<evidence-dir>/model-provider-readiness.json`；`--production-readiness` 默认包含该 evidence，plan-only 会只展示命令和路径，不调用 helper。

`infra/scripts/database_inventory.py` 已新增为数据库只读清单入口：读取当前 `DATABASE_URL` 指向的数据库，输出脱敏 dialect/driver、Alembic repo head、已应用迁移、应用表存在情况和关键业务表计数，可用 `--json-output` 保存 evidence；该脚本不输出数据库连接串、密码、行内容、Provider 原始数据、报告正文、prompt 或 secrets，不执行迁移、seed、采集、扫描、报告、推送或模型调用。

Windows 首次试运行入口已可通过 `clients/windows/first-trial.ps1 -StartDockerBackend -DatabaseInventoryJsonOutput <path>` 在本机 Docker 后端健康后、deploy preflight/smoke/GUI 前保存同一份脱敏数据库只读清单 evidence；该参数只能和 `-StartDockerBackend` 同用，脚本只调用现有 `infra/scripts/database_inventory.py`，不在 PowerShell 中解析数据库内容，失败时阻断后续启动。

Windows 首次试运行入口已可通过 `clients/windows/first-trial.ps1 -StartDockerBackend -SeedDemoDataJsonOutput <path>` 在本机 Docker 后端健康后显式写入 synthetic demo 数据并保存 evidence；该参数只能和 `-StartDockerBackend` 同用，会在 database inventory、deploy preflight、smoke 和 GUI 前运行，失败时阻断后续启动。该路径只调用现有 `infra/scripts/seed_demo_data.py`，重复执行复用稳定 demo key，不访问真实 Provider、不写 token、不保存真实个人持仓、不发送 Telegram、不调用模型。

Windows 首次试运行入口已可通过 `-DeployCheckM5Smoke -DeployCheckRequireRadarAnalysisSample` 把现有 `server_deploy_check.py --require-radar-signal-analysis-sample` 严格样本门禁纳入同一次 deploy preflight；该参数只能随 `-DeployCheckM5Smoke` 使用，会把空 `/radar/signals?limit=1` 从 warning 升级为失败，适合 demo seed 或真实扫描后确认 `/radar/signals/{id}/analysis` 和固定 `agent_assessments` scaffold 确实被抽样覆盖。该路径只读 API，不自动 seed、采集、扫描、报告、推送或调用模型。

`infra/scripts/server_alert_telegram_service_verify.py` 已新增为手动 Telegram alert systemd service 的只读 evidence 验证入口：读取 `server-alert-telegram-env-check.json`、`server-alert-telegram-send.json` 和 `server-alert-telegram-dedupe-state.json`，确认 env check、显式 send 和 dedupe state 是否满足后续调度前提；`sent` / `deduped` 且 state 有效为 `ok`，`skipped` 为非阻塞 `warn`，preview、配置错误、发送失败、损坏或缺失 evidence 为 `fail`，报告不输出 token、raw chat id、raw URL、env 文件内容或 message preview。

`server_delivery_acceptance.py` 已可用 `--include-alert-telegram-service-verify` 把上述手动 alert service evidence 验证纳入同一交付验收包；该阶段只调用 verifier 读取已有 JSON evidence，不启动 systemd、不发送 Telegram、不读取凭据明文。

`infra/linux/baizefindb-alert-telegram.timer` 已新增为可选 Telegram 告警交付 timer 示例：完成 monitor payload、手动 alert service 和 service evidence verification 后，运维人员可手动复制启用；timer 每 5 分钟触发 alert service，开机首次运行比 monitor timer 晚 1 分钟，不包含 secrets 或发送命令本体。

`server_deploy_check.py --check-systemd-units` 已新增为只读 systemd 模板静态检查：验证 `infra/linux/` 中 compose、monitor、Telegram alert 和 PostgreSQL backup 的 service/timer 目标、周期、evidence 输出、env preflight、dedupe 和 no-secret contract；不调用 `systemctl` / `journalctl`，不检查服务器已安装 unit。

`server_delivery_acceptance.py --include-systemd-unit-check` 已可把上述 systemd 模板静态检查纳入同一交付验收 evidence bundle；该参数只让 deploy preflight 阶段追加 `--check-systemd-units`，默认验收不运行该检查，不启动 systemd、不读取凭据、不检查已安装 unit。

`server_delivery_acceptance.py --include-tushare-anns-d-beat-enablement` 已可把 Tushare `anns_d` Beat enablement 离线/no-token checklist 纳入同一交付验收包；该参数只让 deploy preflight 阶段追加 `--check-tushare-anns-d-beat-enablement` 和 `--tushare-anns-d-beat-enablement-json-output <evidence-dir>/tushare-anns-d-beat-enablement.json`，默认验收不运行该检查，不访问 Tushare、不写数据库、不触发抓取或扫描。

`server_delivery_acceptance.py --production-readiness` 已新增为只读生产化验收预设：在默认部署预检、backup check-only、backup retention dry-run 和 runtime check 基础上，追加 server compose runtime contract、systemd 模板静态检查、Telegram 严格绑定 readiness、Tushare `anns_d` Beat enablement checklist、严格 radar analysis 样本门禁、数据库只读清单、脱敏 OPS evidence、no-send alert preview 和 Telegram alert env preflight，并在最终 JSON 写入 `profile: "production_readiness"`；该预设不启用手动 alert service verification、严格 env 权限、`--fail-on-warning`、`--fail-fast`、restore、Telegram send、backup deletion、`systemctl` 或 `journalctl`。

`server_delivery_acceptance.py --plan-only` 已新增为交付验收计划预览模式：它复用同一套 stage 构造和 production readiness preset 展开逻辑，只写出 acceptance JSON 和终端摘要，不调用 helper subprocess、Docker、API、backup、Telegram、`systemctl` 或 `journalctl`；报告顶层为 `execution_mode: "plan"` 和 `status: "planned"`，非跳过 stage 为 `planned`，显式跳过 stage 仍为 `skipped`。正常执行报告为 `execution_mode: "run"`。

`server_deploy_check.py --check-telegram-strict-binding` 已新增为只读 Telegram 白名单/绑定 readiness 预检：读取 `/telegram/status` 的 `require_binding`、环境白名单数量和数据库绑定数量；`TELEGRAM_REQUIRE_BINDING=true` 为通过，未开启严格绑定但存在环境白名单或 active 数据库绑定也为通过，未开启严格绑定且无环境白名单/active 绑定时记录非阻塞 warning。`server_delivery_acceptance.py --include-telegram-strict-binding-check` 可把该检查纳入同一交付验收 deploy preflight 阶段；默认不运行，不读取 `.env` 明文、不调用 `/telegram/bindings`、不发送 Telegram、不输出 token、secret 或 raw chat id。

`server_deploy_check.py --check-server-compose-contract` 已新增为只读 server compose runtime contract 预检：解析 `docker compose -f docker-compose.yml -f docker-compose.server.yml config --format json` 后确认 `api`、`worker`、`beat`、`postgres`、`redis` 服务存在，API/worker/beat 的 server 环境变量、healthy PostgreSQL/Redis 依赖、API 8000 和 `/health` healthcheck、Celery worker/beat 命令、beat schedule 文件以及 `restart: unless-stopped` 未漂移；该检查不启动容器，compose JSON 命令失败时不输出 stdout，避免泄露展开后的 env 值。`server_delivery_acceptance.py --include-server-compose-contract-check` 可把它纳入同一交付验收 deploy preflight 阶段。

`server_deploy_check.py --check-m5-smoke --require-radar-signal-analysis-sample` 已新增为严格 analysis 样本门禁：默认空 `/radar/signals?limit=1` 仍是 warning，显式严格模式会把缺少可抽样信号升级为 fail；`server_delivery_acceptance.py --require-radar-signal-analysis-sample` 可透传该门禁，`--production-readiness` 默认启用它。该门禁只读 API，不自动运行 seed、采集、扫描、报告、推送或模型调用。

Linux 服务端部署骨架已完成：包含 API Dockerfile、server compose overlay、server compose runtime contract 预检、部署预检脚本、交付验收编排脚本、运行采样脚本、cron/systemd 友好的监控摘要脚本、no-send 告警 payload 生成脚本、默认预览的 Telegram 告警交付适配器和 5 分钟 systemd timer 示例、OPS evidence 导出脚本、PostgreSQL 备份/恢复脚本、默认 dry-run 的 backup retention helper、每日 PostgreSQL backup systemd timer 示例、Ubuntu runbook、systemd 示例和 nginx HTTPS 反代示例；部署预检可用 `--json-output <path>` 写出结构化 JSON 报告，包含生成时间、总体状态、summary 计数和逐项 checks，方便脚本、CI 或 Windows 首次试运行流程消费；`server_delivery_acceptance.py` 可把部署预检、backup check-only evidence、backup retention dry-run evidence 和运行时采样串成一次交付验收，默认验收 localhost，也可用 `--base-url <url>` 验证非默认端口、反向代理或域名地址，并在 `evidence/server-delivery-acceptance/` 下写出汇总 JSON；显式加 `--include-server-compose-contract-check` 时会把 compose runtime contract 检查纳入 deploy preflight 并保留在同一 `server-deploy-check.json`，显式加 `--include-ops-evidence` 时会把 runtime stage 生成的脱敏 OPS evidence 写入同一目录并纳入状态汇总，也可用 `--skip-backup-retention` 跳过 retention evidence，或用 `--restore-check-input backups/<file>.sql` 把具体备份文件的非破坏性 restore preflight evidence 放入同一验收包；汇总时会读取各 helper evidence JSON 顶层 `status`：warning 保留为非阻塞 `warn`，缺失、损坏或失败 evidence 标为 `fail`，生产切换前可用 `--fail-on-warning` 让 warning-only 验收保留 `warn` 报告但返回非零退出码；部署预检还可选验证 `pg_dump` 可用性，并可用 `--check-backup --backup-check-json-output <path>` 复用 backup check-only 合约写出有界 evidence，备份脚本也支持 `--check-only --check-json-output <path>` 只验证 repo root、输出路径元数据、server compose 命令形态和 `pg_dump --version`，两种 evidence 路径都不导出数据库内容；`infra/linux/baizefindb-postgres-backup.service` / `.timer` 示例默认每日 03:15 加 15 分钟随机延迟运行，先写 `evidence/postgres-backup-timer-check.json`，再把时间戳 `.sql` 写入 `backups/`，不执行恢复、不发送通知、不包含 secrets；`infra/scripts/postgres_backup_retention.py` 默认只报告超过保留期的普通 `.sql` 文件并可写有界 JSON evidence，只有显式 `--delete` 才删除候选文件，symlink、目录和非 SQL 文件会跳过，且不读取 `.env`、不调用 Docker、不触碰数据库；部署预检还可选执行 Tushare `anns_d` Beat enablement 离线/no-token checklist，并可执行只读 M5 smoke check 验证健康、Ops、Ops history、Ops trends、Ops readiness、AKShare Provider、Tushare Provider、Radar、Telegram、`/radar/signals` 和有信号时的 `/radar/signals/{id}/analysis` JSON 契约；analysis smoke 会进一步校验固定 `agent_assessments` 角色顺序、状态取值和 findings/next_actions 数组形状；空信号列表只作为 warning，不阻断新服务器首次预检；运行采样脚本可连续读取健康、Ops、运维历史和就绪状态，生成 JSON 验收记录并在接口失败或 readiness `blocked` 时返回失败退出码，可显式加 `--include-ops-trends` 读取 `/ops/trends` 并汇总最新趋势桶，也可通过 `--ops-evidence-output <path>` 在同一次只读采样中复用 `export_ops_evidence.py` 的脱敏逻辑写出 ready/warning/blocked OPS evidence，方便 warning 或 blocked 时留存可分享证据；`server_monitor_check.py` 复用同一 runtime sampler，默认单次零延迟采样，输出 `ok`、`warning` 或 `blocked` compact monitor summary JSON，适合 cron/systemd 或后续告警发送器消费；`server_monitor_check.py --alert-json-output <path>` 可在同一次巡检中从内存里的 monitor summary 额外写 no-send alert payload；`server_alert_payload.py` 也可单独读取已有 compact monitor summary JSON，生成带 `severity`、`should_notify`、`dedupe_key` 和有界 items 的 no-send alert payload；`server_alert_telegram.py` 消费该 payload，默认只预览并写 `server_alert_telegram_delivery` evidence，只有显式 `--send` 才复用后端 `TelegramClient` 发送，收件人来自 `--chat-id` 或 `TELEGRAM_ALLOWED_CHAT_IDS`，token 来自 `TELEGRAM_BOT_TOKEN`，报告只保留 masked chat refs、不包含 token 或 raw URL；monitor/payload 两条路径都不调用 API、Docker、Telegram、SMTP、webhook、数据库、采集、扫描、模型、报告、备份或清理；`infra/linux/baizefindb-monitor.timer` 示例默认每 5 分钟调用 monitor service 写入 compact monitor、full runtime 和 no-send alert payload JSON，不发送通知；OPS evidence 默认仍只读 `/health`、`/health/ready`、`/ops/overview`、`/ops/history` 和 `/ops/readiness`，只有显式加 `--include-ops-trends --trend-bucket-count <n>` 时才额外写入脱敏 `snapshots.ops_trends`，帮助区分历史 Provider / 数据质量 warning 和真正 blocker，普通 warning 不作为失败退出码。2026-05-04 已在本机 Docker Desktop 用 server overlay 完成一次 API/worker/beat 启动、容器迁移、M5 smoke check、runtime check 和手动扫描后 readiness `ready` 验证；同日重建最新 API 镜像后再次验证 Tushare `anns_d` Beat 默认关闭、显式 env 覆盖启用时只额外加入 `collect-tushare-announcements`，部署预检和 runtime ready 均通过；预检脚本已改为 quiet compose config，避免输出展开后的 `.env`。Ops 已能生成扫描停滞、失败率、服务端磁盘/CPU/内存资源压力和 unhealthy 计数告警摘要，Ops history 已能只读列出最近扫描和运行异常历史，Ops trends 已能按固定时间桶汇总既有运行表并附带当前资源上下文，Ops readiness 已能给出运行就绪自检结果。该状态只代表本机部署演练和部署骨架完成，不代表公网 HTTPS、域名、生产级 offsite 备份策略、生产安全加固或完整监控系统完成。

Telegram 告警 env 预检已新增：`infra/scripts/server_alert_telegram_env_check.py --env-file /etc/baizefindb/telegram-alert.env --json-output evidence/server-alert-telegram-env-check.json` 只读验证本机凭据文件存在、非 symlink、权限、`TELEGRAM_BOT_TOKEN` 配置和 `TELEGRAM_ALLOWED_CHAT_IDS` 格式；默认 group/world 权限只记 warning，`--strict-permissions` 可升级为失败，输出不包含 token、raw chat id、raw URL 或 env 文件内容。

`infra/linux/baizefindb-alert-telegram.service` 已在手动发送前接入同一 env 预检：service 先创建 evidence 目录，再运行 `server_alert_telegram_env_check.py --strict-permissions --json-output evidence/server-alert-telegram-env-check.json`，预检失败时不会进入 Telegram 发送；该 unit 本身不负责调度，调度由可选 `baizefindb-alert-telegram.timer` 在手动 evidence 验证后单独启用，不嵌入 token 或 raw chat id。

交付验收编排已支持可选 Telegram env 预检阶段：`server_delivery_acceptance.py --include-alert-telegram-env-check` 会在同一 evidence bundle 中调用上述只读 helper，默认输出 `server-alert-telegram-env-check.json` 并纳入 warning/fail 汇总；`--telegram-alert-env-file <path>` 可指定非默认凭据文件，`--telegram-alert-env-strict-permissions` 可把权限 warning 升级为阻断验收。

5 分钟调度 MVP 已接入 Celery beat：默认每 300 秒执行 `baizefindb.radar.collect_and_scan`，顺序完成 AKShare 最小采集和雷达扫描；当 `TELEGRAM_PUSH_ENABLED=true` 时会追加 Telegram 折叠推送；服务器 compose overlay 已补充 worker / beat 服务。Tushare `anns_d` 公告 Beat 调度已具备独立开关，但默认关闭，只有显式设置 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 才会额外加入调度；启用前应先运行 `uv run python infra/scripts/check_tushare_anns_d_beat_enablement.py --json-output evidence/tushare-anns-d-beat-enablement.json` 输出并保存 JSON checklist，再运行 `uv run python infra/scripts/verify_tushare_anns_d_preflight.py`，用本地样例验证字段漂移和风险 P0/普通公告映射边界；完整扫描层的 `golden_cases/radar_m5_risk_announcements.json` 已覆盖重大风险公告、退市风险公告、普通公告无信号和现实普通公告误报守卫样例，且每个 case 必须声明 `case_type`，用于后续持续追加真实误报/漏报反馈。随后再用 `uv run python infra/scripts/verify_tushare_announcements.py --ann-date YYYYMMDD --json-output evidence/tushare-anns-YYYYMMDD.json` 保存真实 token 下的脱敏 live evidence。`stock_basic`、`anns_d` 和 `stock_company` 三条 live verify 脚本均可输出同类脱敏 evidence；默认 checklist、离线门禁和 golden cases 不替代真实 `TUSHARE_TOKEN` 权限、积分消耗、实时接口字段和 readiness 验证。

持仓/自选最小 API 已接入：支持按 `user_key` 手工维护持仓和自选，成本价与仓位比例可为空；静态 Web 终端工作台已能查看运行状态、维护和展示这些个人数据。跨 API 测试已锁定这些个人数据只影响后续个人提醒、展示排序和报告上下文，不改变市场级 P0/P1/P2、生命周期分布或当前主题。

报告 MVP 已接入：`/reports/from-signal` 可从雷达信号生成 quick/standard 模板报告；生成前复用轻量规则审查，blocked 信号不会生成报告，needs_human_review 报告会显式标记；报告发布前审查不受信号候选范围限制，确保发布前安全门始终执行；诱导交易语言正反例已进入 golden cases，否定式风险提示如“不建议马上买入 / 不宜满仓 / 不应跟着买”不会误封，但带免责声明后的明确催单仍会 blocked；`/reports/deep/from-signal` 已提供手动 deep 模板报告入口，必须传 `confirm_deep_report=true`，继续复用发布前审查，不自动触发、不调用模型，`/reports/from-signal` 仍拒绝 deep。`/reports/periodic` 可按日/周生成当前 `user_key` 的雷达汇总报告。`/scores/signals/{signal_id}` 可生成 1d/3d/5d/10d v2 综合评分记录，已纳入 Provider 数据质量、信号时效性、评分档位和权重说明。静态 Web 已改为雷达终端工作台外壳，可从信号详情生成 quick/standard 报告、确认后手动生成 deep 报告、查看报告列表、生成日报/周报、查看单信号评分档位和组件明细，并维护 Telegram chat 绑定/白名单；Windows 客户端也已提供确认后手动生成 deep 报告入口，只展示后端返回摘要；Web 和 Windows 绑定视图会显示严格绑定模式与汇总计数，不暴露原始环境值、bot token 或 webhook secret。

模型审计底座已接入：`model_call_logs` 可记录模型失败后的 `degraded` 或 `fallback` 状态、调用点、模型名、错误摘要、prompt hash 和 prompt 长度；默认不保存完整 `raw_prompt`，只有显式设置 `MODEL_AUDIT_STORE_RAW_PROMPT=true` 或调用方主动开启时才保存。新增 `app.ai.model_client` 后，模型执行路径已有可测试客户端和 fallback/degraded 审计包装；新增 `app.ai.analysis_output` 后，模型文本已有进入产品面前的本地 JSON 净化契约；新增手动模型草稿 API 后，后端已有第一条显式 opt-in 模型执行路径，但仍未接入自动化真实多 agent 分析链。

当前仍然是投研辅助系统，不是交易系统，不提供买卖建议。

2026-05-05 已把主开发环境迁移到 Linux 服务器
`/home/ling/projects/finance/BaizeFinDB`：`uv` 和 `python3-tk` 已安装，
Linux `.venv` 已重建，Windows 迁移虚拟环境已移入迁移备份目录，
迁移产生的 CRLF 假改动已清理。
当前服务器门禁已通过 `ruff check`、`pytest`、Alembic SQL 生成、base/server
compose config 和基础部署预检；当前全量 pytest 为 `640 passed, 45 skipped`，
Windows GUI helper 测试已可运行，剩余跳过项主要是 Linux 服务器缺少
PowerShell/Windows 打包脚本运行环境。

下一阶段开发基线切换为 **M5 生产化验证和真实数据增强**。核心是让现有雷达闭环在 Docker / Linux 服务器上可持续运行、可观测、可恢复，并逐步接入更稳定的真实公告、监管、情绪和后续评分校准数据源。

当前长期开发规范：

- 后续 AI 协作默认在模块设计或开发阶段完成后自动做 git commit，不再每次向用户确认；不自动 push。
- 即使是小的模块化更新，只要形成明确阶段边界，也要同步更新相关开发文档并提交 git commit。
- 提交前先跑对应质量检查，再查看 `git status`，并检查 staged 文件，确认没有误提交 `.env`、密钥、个人数据、原始付费数据、持仓截图、报告导出等敏感文件。
- commit 仍按模块边界拆分，不把多个无关模块混成一个大提交。
- commit message 要能看懂模块和动作，例如 `docs(prd): refine radar mvp`、`feat(radar): add scan scheduler`、`test(radar): cover p1 continuity`、`docs(dev): add git workflow`。
- 文档、迁移、测试和代码随模块一起提交；只完成设计文档时，也要提交文档版本。
- 大模块拆成设计文档、数据模型/迁移、业务实现、测试/文档等多个 commit。
- 发现未识别的脏文件或疑似用户手工改动时，不能自动纳入提交，要隔离并说明。

## 开发文档入口

- [开发文档导航](README.md)
- [本地开发 Runbook](runbooks/local-dev.md)
- [Linux 服务端部署骨架 Runbook](runbooks/linux-server.md)
- [Windows 客户端 MVP Runbook](runbooks/windows-client.md)
- [当前 API 文档](api/current-api.md)
- [当前数据模型说明](specs/current-data-model.md)
- [M5 A 股 5 分钟资金主线雷达 MVP PRD](prd/m5-next-step.md)

## 已完成

| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| M1 工程骨架 | 已完成 | FastAPI、配置系统、健康检查、SQLAlchemy async、Alembic、Docker Compose、Celery 壳、pytest。 |
| M2 数据底座 | 已完成早期闭环 | AKShare 行情/行业/概念最小 Provider，采集日志、快照、质量检查、Provider 查询 API；Tushare `stock_basic`、`anns_d` 和 `stock_company` 已支持手动抓取、失败记录、日志、快照查询和只读准入自检，`anns_d` 重大风险公告可被后续雷达扫描映射为 risk P0；`anns_d` Beat 调度有默认关闭的显式开关，并已有离线/no-token 预调度校验，尚未作为默认调度。 |
| M3 雷达核心 | 已完成早期闭环 | 基于已入库快照生成雷达候选信号，写入扫描批次、信号和证据，并提供最新总览视图；普通扫描异常会落 `failure` 状态。 |
| M4 审查层 | 已完成 | 轻量规则审查可对单个雷达信号给出 `approved`、`blocked`、`needs_human_review`，并记录审查历史；Provider 数据质量、证据冲突、重复触发、来源过期、诱导交易语言正反例、否定式风险提示误报防护和分享安全门已进入审查判断。 |
| M5 A 股 5 分钟资金主线雷达 MVP | 验收项完成 | 静态 Web 终端工作台、Telegram Bot MVP、Windows 客户端 MVP、Celery 5 分钟采集后扫描调度、持仓/自选最小 API、quick/standard 报告、日报/周报、1d/3d/5d/10d v2 综合评分、Telegram 折叠推送、P0 推送后 standard report、风险 P0、Review Agent 范围控制、模型降级审计、运行状态汇总和只读 M5 smoke check 已接入。 |
| Linux 服务端部署骨架 | 已完成 | 已有 API Dockerfile、`docker-compose.server.yml`、worker/beat、`infra/scripts/server_deploy_check.py` 部署预检（含 JSON 报告、可选 server compose runtime contract 检查、可选 systemd 模板静态检查、可选 Tushare `anns_d` Beat enablement checklist、可选 `pg_dump` 可用性检查、backup check-only evidence 和只读 M5 smoke check，覆盖 `/ops/overview`、`/ops/history`、`/ops/trends`、`/ops/readiness`、AKShare 状态和 Tushare 状态）、`infra/scripts/server_runtime_check.py` 运行采样脚本（支持 `--ops-evidence-output` 在 warning/blocked 排障时同步写脱敏 OPS evidence）、`infra/scripts/server_monitor_check.py` compact 监控摘要脚本（面向 cron/systemd 和后续告警发送器）、`infra/scripts/server_alert_payload.py` no-send 告警 payload 生成脚本、`infra/scripts/server_alert_telegram.py` 默认 preview / 显式 `--send` Telegram 告警交付适配器、`infra/scripts/server_alert_telegram_service_verify.py` 手动 alert service evidence 验证器、`server_delivery_acceptance.py --include-server-compose-contract-check` / `--include-systemd-unit-check` / `--include-tushare-anns-d-beat-enablement` / `--include-alert-telegram-service-verify` 验收集成、`infra/linux/baizefindb-monitor.service` / `.timer` 5 分钟 systemd 示例（默认写 compact monitor、full runtime 和 no-send alert payload JSON）、`infra/linux/baizefindb-alert-telegram.service` / `.timer` 可选 Telegram 告警交付示例、`infra/scripts/export_ops_evidence.py` 脱敏只读 OPS evidence 导出脚本、`infra/scripts/postgres_backup.py` PostgreSQL 备份脚本（支持 check-only 有界证据且不导出数据库内容）、`infra/scripts/postgres_backup_retention.py` 默认 dry-run 备份保留期 helper、`infra/linux/baizefindb-postgres-backup.service` / `.timer` 每日备份 systemd 示例、`infra/scripts/postgres_restore.py` PostgreSQL 恢复脚本（含不恢复数据的 check-only evidence）、`infra/linux/` runbook、systemd 示例和 nginx HTTPS 反代示例；本机 Docker Desktop server overlay 已完成 API/worker/beat 启动和 runtime ready 验证；`/ops/overview` 和 `/ops/readiness` 已包含磁盘、CPU、内存资源摘要和压力告警；尚不是完整公网生产部署。 |

## 当前可用 API

健康检查：

- `GET /health`
- `GET /health/ready`

Ops：

- `GET /ops/overview`
- `GET /ops/history`
- `GET /ops/trends`
- `GET /ops/readiness`

Provider：

- `GET /providers/akshare/endpoints`
- `GET /providers/tushare/endpoints`
- `GET /providers/tushare/status`
- `GET /providers/tushare/readiness`
- `POST /providers/tushare/fetch/stock-basic`
- `POST /providers/tushare/fetch/announcements`
- `POST /providers/tushare/fetch/stock-company`
- `GET /providers/tushare/fetch-logs`
- `GET /providers/tushare/snapshots/latest`
- `POST /providers/akshare/fetch/minimal`
- `GET /providers/akshare/status`
- `GET /providers/akshare/fetch-logs`
- `GET /providers/akshare/snapshots/latest`

Portfolio：

- `GET /portfolio/holdings`
- `POST /portfolio/holdings`
- `PATCH /portfolio/holdings/{holding_id}`
- `DELETE /portfolio/holdings/{holding_id}`
- `GET /portfolio/watchlist`
- `POST /portfolio/watchlist`
- `PATCH /portfolio/watchlist/{item_id}`
- `DELETE /portfolio/watchlist/{item_id}`

Reports：

- `POST /reports/from-signal`
- `GET /reports`
- `GET /reports/{report_id}`
- `GET /reports/periodic`

Scores：

- `POST /scores/signals/{signal_id}`
- `GET /scores/signals/{signal_id}`

Radar：

- `POST /radar/scans/run`
- `GET /radar/scans/latest`
- `GET /radar/scans/{scan_id}`
- `GET /radar/overview`
- `GET /radar/signals`
- `GET /radar/signals/{signal_id}`
- `GET /radar/signals/{signal_id}/analysis`
- `POST /radar/signals/{signal_id}/model-analysis-draft`
- `POST /radar/signals/{signal_id}/review`
- `GET /radar/signals/{signal_id}/reviews`
- `GET /radar/signals/{signal_id}/share-preview`
- `GET /radar/signals/{signal_id}/share-payload`

Telegram：

- `GET /telegram/status`
- `POST /telegram/webhook`
- `GET /telegram/bindings`
- `POST /telegram/bindings`
- `PATCH /telegram/bindings/{chat_id}`
- `POST /telegram/push/latest`
- `GET /telegram/push/logs`
- Telegram 命令：`/help`、`/id`、`/health`、`/ops`、`/ops_history`、`/ops_trends`、`/ops_ready`、`/ops_warn`、`/tushare`、`/radar`、`/signals`、`/signal <id>`、`/analysis <id>`、`/holding`、`/watchlist`、`/reports`、`/daily`、`/weekly`、`/score <id>`；`/health` 展示最近扫描状态，`/ops` 展示运行状态摘要，`/ops_history` 展示只读运维异常历史，`/ops_trends` 展示只读 OPS 趋势桶摘要，`/ops_ready` 展示运行就绪自检，`/ops_warn` 展示只读 OPS 告警钻取，`/tushare` 展示 Tushare 只读配置状态，`/analysis` 展示后端单信号研究摘要，`/score` 展示后端 v2 评分档位和组件明细

Windows 客户端：

- `clients/windows/first-trial.ps1`
- `clients/windows/run-client.ps1`
- `clients/windows/baizefindb_client.py`
- `clients/windows/client_api.py`
- `clients/windows/smoke_check.py`

后台调度：

- `baizefindb.radar.collect_and_scan`：Celery beat 默认每 300 秒触发，先采集 AKShare 最小数据，再运行雷达扫描；`TELEGRAM_PUSH_ENABLED=true` 时追加 Telegram 折叠推送。
- `baizefindb.providers.collect_tushare_announcements`：Tushare `anns_d` 公告采集任务；默认不进入 Beat，只有 `TUSHARE_ANNS_D_BEAT_ENABLED=true` 时按 `TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS` 调度。
- `baizefindb.telegram.push_latest_radar`：手动触发最新扫描的 Telegram 折叠推送。
- `RADAR_SCAN_INTERVAL_SECONDS`：调度间隔环境变量，默认 `300`。
- `RADAR_CONTINUOUS_P1_TRIGGER_COUNT`：连续 P1 快报候选触发次数，默认 `3`。
- `RADAR_CONTINUITY_WINDOW_MINUTES`：连续 P1 计算窗口，默认 `30`。
- `TUSHARE_ANNS_D_BEAT_ENABLED`：Tushare 公告 Beat 开关，默认 `false`。
- `TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS`：Tushare 公告 Beat 间隔，默认 `3600`。
- `infra/scripts/check_tushare_anns_d_beat_enablement.py --json-output <path>`：Tushare `anns_d` Beat 启用前 JSON checklist，默认离线/no-token，汇总 sample gate、雷达风险公告 golden gate、token、Beat 启停、interval、live verify 和 readiness/live data 检查状态；可保存和 stdout 相同的 evidence JSON。
- `infra/scripts/server_deploy_check.py --check-tushare-anns-d-beat-enablement --tushare-anns-d-beat-enablement-json-output <path>`：可选部署预检集成项，复用上述 checklist；`warn` 只告警不阻断，只有 checklist `fail` 会让部署预检失败；可把原始 checklist evidence 单独落盘。
- `infra/scripts/verify_tushare_anns_d_preflight.py`：离线/no-token `anns_d` 预调度校验，读取本地 golden case，验证必需字段、重大风险 P0 样例和普通公告无风险信号样例。
- `golden_cases/radar_m5_risk_announcements.json`：完整雷达扫描 golden cases，覆盖 Tushare 重大风险公告、退市风险公告映射 risk P0、普通公告不生成信号和误报反馈守卫；每个 case 必须声明 `case_type`，支持真阳性重大/严重风险、误报守卫、漏报守卫和普通无信号分类；默认已纳入 `check_tushare_anns_d_beat_enablement.py` 的离线启用前 gate。
- `infra/scripts/verify_tushare_stock_basic.py --json-output <path>`、`infra/scripts/verify_tushare_announcements.py --json-output <path>`、`infra/scripts/verify_tushare_stock_company.py --json-output <path>`：真实 token live verify 脱敏 evidence 输出；不写数据库，成功和失败都会保存状态、端点、查询参数、行数、质量状态、必需字段、缺失字段和去 URL/source/token/secret-like 字段的少量归一化样例或错误摘要，样例值会递归脱敏并截断超长文本。
- `evidence/`、`runtime-check*.json` 和 `ops-evidence*.json`：本地/服务器运行证据产物，已加入 `.gitignore`，真实 token 环境下生成后不要提交到 git。

## 当前数据表

以下为当前已经由 Alembic 迁移创建的真实数据表。路线图中的未来表请不要当成已实现能力，详情见 [specs/current-data-model.md](specs/current-data-model.md)。

- `schema_health_checks`
- `market_snapshots`
- `provider_fetch_logs`
- `data_quality_checks`
- `users`
- `portfolio_holdings`
- `watchlist_items`
- `reports`
- `push_logs`
- `score_records`
- `telegram_bindings`
- `model_call_logs`
- `radar_scan_batches`
- `radar_signals`
- `radar_signal_reviews`
- `signal_evidences`

## 当前规则能力

- 基于板块/概念涨幅、上涨家数、下跌家数、联动宽度生成 P0/P1/P2 候选信号；涨停、跌停和炸板池快照会进入扫描 summary，并透传到主线信号 metrics 作为情绪确认信息；普通新闻快讯不会进入主线 P0，`risk_events` 等重大风险事件快照和 Tushare `anns_d` 中明显重大风险公告可按重大公告、监管或黑天鹅口径单独生成 risk P0。
- M5 规则基线要求板块/主题/概念权重大于单票异动；单票异动优先用于反推板块/概念/风险。
- 主线 P0 不能只由新闻触发，必须有资金、板块联动或市场情绪确认；风险 P0 可由重大公告、监管或黑天鹅单独触发。
- 基于涨幅和联动宽度初判生命周期：`ignition`、`developing`、`climax`。
- 强度等级和生命周期必须分开处理，AI 只能解释、补证据和提示分歧，不能覆盖规则定级。
- 根据同一板块/概念的历史信号记录连续性。
- 当前实现为默认 30 分钟窗口内连续 3 次 P1 会标记为 `quick_report_candidate`；触发次数和窗口可通过环境变量调参。
- P2 默认保留 7 天观察：`/radar/overview` 和 `/radar/signals` 默认隐藏超出观察窗口的 P2；历史排查可在信号列表使用 `include_expired_p2=true`。
- 前后扫描走弱会记录生命周期转移，例如 `climax_to_divergence`。
- 总览 API 基于最新扫描生成当前活跃信号、P0/P1/P2 聚合、生命周期分布、市场情绪摘要、个股回推证据和按板块/概念去重视图；Web、Telegram 和 Windows 只展示该摘要，不在客户端重算。
- 雷达扫描 summary、信号 metrics 和 evidence details 会携带 Provider 数据质量摘要和市场情绪摘要。
- 轻量审查层会拦截诱导交易语言、证据缺失、失败数据质量和低置信度证据；降级/未知数据质量、证据冲突、重复触发和来源过期会进入人工复核；信号候选审查范围限制为 P0、连续 P1 快报、risk、holding/watchlist 相关候选，报告发布前审查始终执行。
- 诱导交易语言规则已覆盖基础禁词、常见热词、空格/标点拆分变体，并允许“不要马上买入”“禁止满仓”这类安全警示反例。
- `share-preview` 是内部预检接口，可以返回审查状态、阻断原因和脱敏记录。
- `share-payload` 是公开分享 payload，只在通过审查且分享策略安全时返回；它隐藏原始 URL、域名、原文摘录、内部证据详情、原始枚举、精确置信度和来源时间。

## 常用命令

```powershell
uv sync --dev
uv run python infra/scripts/dev_environment_check.py
uv run pytest
uv run ruff check .
uv run alembic heads
uv run alembic upgrade head --sql
```

Docker / PostgreSQL 可用后：

```powershell
docker compose up -d postgres redis
uv run alembic upgrade head
uv run python infra/scripts/seed_demo_data.py --json-output evidence/demo-seed.json
uv run python infra/scripts/collect_akshare_minimal.py
uv run python infra/scripts/verify_tushare_stock_basic.py --json-output evidence/tushare-stock-basic.json
uv run python infra/scripts/collect_tushare_stock_basic.py
uv run python infra/scripts/check_tushare_anns_d_beat_enablement.py --json-output evidence/tushare-anns-d-beat-enablement.json
uv run python infra/scripts/verify_tushare_anns_d_preflight.py
uv run python infra/scripts/verify_tushare_announcements.py --ann-date 20260503 --json-output evidence/tushare-anns-20260503.json
uv run python infra/scripts/collect_tushare_announcements.py --ann-date 20260503
uv run python infra/scripts/verify_tushare_stock_company.py --exchange SZSE --json-output evidence/tushare-stock-company-SZSE.json
uv run python infra/scripts/collect_tushare_stock_company.py --exchange SZSE
uv run python infra/scripts/run_radar_scan.py
uv run python infra/scripts/server_deploy_check.py --json-output evidence/server-deploy-check.json
uv run python infra/scripts/server_deploy_check.py --check-telegram-strict-binding --json-output evidence/server-deploy-check-telegram.json
uv run python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --json-output runtime-check.json
uv run python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --ops-evidence-output evidence/ops-evidence.json
uv run python infra/scripts/server_delivery_acceptance.py --include-tushare-anns-d-beat-enablement
uv run python infra/scripts/server_delivery_acceptance.py --include-telegram-strict-binding-check
uv run python infra/scripts/server_delivery_acceptance.py --include-alert-telegram-preview
uv run python infra/scripts/server_delivery_acceptance.py --include-alert-telegram-preview --include-alert-telegram-env-check --telegram-alert-env-strict-permissions
uv run python infra/scripts/server_monitor_check.py --json-output evidence/server-monitor-summary.json --alert-json-output evidence/server-alert-payload.json
uv run python infra/scripts/server_alert_payload.py evidence/server-monitor-summary.json --json-output evidence/server-alert-payload.json
uv run python infra/scripts/server_alert_telegram.py evidence/server-alert-payload.json --json-output evidence/server-alert-telegram-preview.json
uv run python infra/scripts/server_alert_telegram_env_check.py --env-file /etc/baizefindb/telegram-alert.env --json-output evidence/server-alert-telegram-env-check.json
uv run python infra/scripts/server_alert_telegram.py evidence/server-alert-payload.json --send --dedupe-state evidence/server-alert-telegram-dedupe-state.json --json-output evidence/server-alert-telegram-send.json
sudo systemctl start baizefindb-alert-telegram.service
uv run python infra/scripts/server_deploy_check.py --check-backup --backup-check-json-output evidence/postgres-backup-check.json
uv run python infra/scripts/postgres_backup.py --check-only --check-json-output evidence/postgres-backup-check.json
uv run python infra/scripts/postgres_backup.py --output backups/pre-upgrade.sql
```

启动 API：

```powershell
uv run uvicorn app.main:app --reload
```

## 下一步

建议进入 **生产化验证和真实数据增强**，范围继续保持轻量：

- 用 Docker / Linux runbook 跑通 API、worker、beat、迁移、只读 M5 smoke check 和短窗口 runtime check。
- 新库迁移后如需首用演示或 analysis smoke 样本，先运行 `uv run python infra/scripts/seed_demo_data.py --json-output evidence/demo-seed.json` 写入可重复复用的合成 demo 用户、持仓/自选、雷达信号、证据、审查和 quick 报告；Windows 本机 Docker 首次试运行也可组合 `-SeedDemoDataJsonOutput <path> -DeployCheckM5Smoke -DeployCheckRequireRadarAnalysisSample`，在同一流程中先写 demo 数据，再严格验证单信号 analysis 样本；该路径不访问真实 Provider、不写 token、不保存真实个人持仓。
- 接入更稳定的公告、监管、风险事件和情绪数据源，优先服务 risk P0 和主线确认。
- Tushare 当前已支持 `stock_basic`、`anns_d` 和 `stock_company` 手动抓取；三条 live verify 脚本均支持脱敏 JSON evidence 输出；`anns_d` 中明显重大风险公告已能被雷达扫描映射为 risk P0；`anns_d` Beat 调度默认关闭，后续在 checklist、`verify_tushare_anns_d_preflight.py` 离线预调度校验、真实 token live evidence、字段和误报样例稳定后再显式启用。
- 增加运行可观测性：`/ops/overview` 已汇总服务端进程运行时长、磁盘/CPU/内存资源、扫描耗时、失败率、推送结果、模型降级、数据质量状态和只读告警摘要，`/ops/history` 已返回最近扫描、Provider 异常、数据质量异常、推送异常和模型降级/失败历史，`/ops/trends` 已按固定时间桶汇总扫描、失败和 unhealthy 计数，`/ops/readiness` 已基于这些信息输出运行就绪自检；Web 状态面板、Windows 客户端和 Telegram `/ops`、`/ops_history`、`/ops_trends`、`/ops_ready` 已展示这些摘要，Web 状态面板已补充只消费后端桶计数的 OPS 趋势图，Web、Windows 客户端和 Telegram `/ops_warn` 已有只读告警钻取视图聚合三组 OPS 响应；后续再接真实监控告警。
- 完善真实运行后的误报/漏报样例，把规则调参沉淀为 golden cases；Tushare 公告完整扫描层已先建立 `radar_m5_risk_announcements.json` 基线。
- Web / Telegram / Windows 继续只消费后端结果，不在入口层重算雷达等级。
