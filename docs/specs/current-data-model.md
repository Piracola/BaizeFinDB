# 当前数据模型说明

本文档区分“当前已经实现的数据表”和“规划中的未来数据表”，避免后续开发时误把路线图当成现状。

## 1. 当前真实数据表

当前 Alembic head：`202605030010`。

| 表 | 阶段 | 作用 |
| --- | --- | --- |
| `schema_health_checks` | M1 | 数据库连通和 schema 健康检查预留表 |
| `market_snapshots` | M2 | 保存 Provider 标准化后的市场快照 |
| `provider_fetch_logs` | M2 | 记录每次 Provider 拉取状态、错误、质量摘要 |
| `data_quality_checks` | M2 | 记录数据质量检查结果 |
| `users` | M5 | 单用户/白名单阶段的身份键和个人数据隔离前置 |
| `portfolio_holdings` | M5 | 手动持仓，成本价和仓位比例可为空 |
| `watchlist_items` | M5 | 自选关注项，只影响个人提醒和展示上下文 |
| `reports` | M5 | quick/standard 模板报告，按用户隔离，生成前复用审查 |
| `push_logs` | M5 | Telegram 折叠推送记录，按用户和渠道隔离 |
| `score_records` | M5 | 1d/3d/5d/10d 综合评分记录 |
| `telegram_bindings` | M5 | Telegram chat 与 `user_key` 的绑定、白名单和禁用状态 |
| `model_call_logs` | M5 | 模型失败、降级和 fallback 审计，默认不保存完整 raw prompt |
| `radar_scan_batches` | M3 | 记录每次雷达扫描批次、状态、摘要、失败原因 |
| `radar_signals` | M3 | 保存候选信号、优先级、生命周期、审查状态 |
| `signal_evidences` | M3 | 保存信号证据链、置信度、新鲜度和分享策略 |
| `radar_signal_reviews` | M4 | 保存单个雷达信号的审查结果和理由 |

## 2. 当前关系

```text
market_snapshots
  <- provider_fetch_logs.raw_snapshot_id
  <- data_quality_checks.snapshot_id

provider_fetch_logs
  <- data_quality_checks.fetch_log_id

users
  <- portfolio_holdings.user_id
  <- watchlist_items.user_id
  <- reports.user_id
  <- push_logs.user_id
  <- telegram_bindings.user_id

radar_scan_batches
  <- radar_signals.batch_id

radar_signals
  <- signal_evidences.signal_id
  <- radar_signal_reviews.signal_id
  <- reports.signal_id
  <- score_records.signal_id

model_call_logs
  (standalone audit table)
```

## 3. 当前核心枚举

### Provider

| 枚举 | 值 |
| --- | --- |
| `ProviderStatus` | `success`、`failure` |
| `DataQualityStatus` | `ok`、`degraded`、`failed` |

### Radar

| 枚举 | 值 |
| --- | --- |
| `RadarPriority` | `P0`、`P1`、`P2` |
| `RadarScanStatus` | `running`、`success`、`no_data`、`failure` |
| `RadarReviewStatus` | `candidate`、`approved`、`blocked`、`needs_human_review` |
| `RadarSignalShareStatus` | `ready`、`blocked` |
| `RadarLifecycleStage` | `ignition`、`developing`、`divergence`、`returning`、`climax`、`fading`、`extinguished` |

## 4. 当前表职责边界

### Provider 数据表

Provider 表只回答：

- 哪个数据源被拉取。
- 哪个 endpoint 被拉取。
- 拉取成功还是失败。
- 数据新鲜度和置信度如何。
- 标准化后保留了什么摘要和行数据。
- `market_snapshots` 当前也可承载轻量风险事件快照，例如 `risk_events`、`announcement_events`、`regulatory_events`、`black_swan_events`；普通 `news_flash` 不会被雷达主线规则直接升为 P0。
- Tushare `stock_basic`、`anns_d` 和 `stock_company` 当前会复用 `market_snapshots`、`provider_fetch_logs` 和 `data_quality_checks` 写入证券主数据、公告快照、公司信息快照、抓取日志和质量记录。公告 `url` 只允许留在内部 Provider 快照中，不能进入公开分享 payload。

Provider 表不负责：

- 直接生成 P0/P1/P2。
- 决定是否推送。
- 生成报告。

### Radar 数据表

Radar 表只回答：

- 哪次扫描产生了哪些信号。
- 每个信号属于哪个板块/概念/标的。
- 信号优先级、生命周期、证据链是什么。
- 当前审查状态是什么。
- P2 是否仍在 7 天默认观察窗口内由后端查询规则判断；历史记录不删除。

Radar 表不负责：

- 保存用户持仓。
- 保存 Telegram 会话。
- 保存报告正文。
- 保存模型调用日志。

### Governance 审查表

审查表只回答：

- 某个信号是否通过轻量规则审查。
- 为什么通过、阻断或需要人工复核。
- 使用了哪个审查版本。

审查表不负责：

- 发送消息。
- 生成公开页面。
- 保存完整 LLM prompt。

### Model audit 模型审计表

Model audit 表只回答：

- 哪个调用点发生了模型失败、显式降级或 fallback。
- 主模型、fallback 模型、状态、错误类型和错误摘要是什么。
- prompt 的 hash、长度和审计版本是什么。
- 是否在 debug 配置下保存了完整 `raw_prompt`。

Model audit 表不负责：

- 保存用户完整上下文，除非显式开启 debug。
- 代替报告、推送或审查结果。
- 伪造 AI 结论；模型失败只能记录为 `degraded` 或 `fallback`。

### Portfolio 个人数据表

Portfolio 表只回答：

- 某个 `user_key` 手动维护了哪些持仓。
- 某个 `user_key` 手动维护了哪些自选关注项。
- 持仓成本价、仓位比例、备注和提醒开关是什么。

Portfolio 表不负责：

- 修改市场级 P0/P1/P2。
- 接券商、下单或保存交易密码。
- 进入公开分享 payload。

### Reports 报告表

Reports 表只回答：

- 哪个 `user_key` 生成了哪份 quick/standard 报告。
- 报告来源于哪个雷达信号。
- 报告生成前的审查状态、报告状态和建议标签是什么。
- 模板报告正文和生成元数据是什么。

Reports 表不负责：

- 覆盖雷达 P0/P1/P2。
- 自动生成 deep report。
- 发布公开分享或导出文件。
- 保存完整模型 prompt；当前 MVP 不调用模型。

### Push logs 推送表

Push logs 表只回答：

- 哪个 `user_key` 通过哪个渠道收到过哪次推送。
- 推送目标引用是什么，例如 Telegram chat id。
- 推送来源是什么，例如最新雷达扫描批次。
- 本次折叠推送包含、过滤或标记人工复核了哪些信号。
- 发送状态、预览文本和非敏感投递元数据是什么。

Push logs 表不负责：

- 决定 P0/P1/P2、生命周期或审查状态。
- 保存 Telegram bot token、webhook secret 或其他密钥。
- 保存原始证据摘录、原始 URL、来源域名或个人持仓成本。
- 阻止失败后的重试；服务层只对已成功或 preview 的同批次推送做幂等跳过。

### Score records 评分表

Score records 表只回答：

- 某个雷达信号在 1d/3d/5d/10d 窗口下的综合评分是多少。
- 评分窗口是否已经结束。
- 本次评分使用了哪些组件、权重版本和窗口信息。

Score records 表不负责：

- 输出买卖建议、仓位建议或收益承诺。
- 只按涨跌幅评分；M5 当前评分综合优先级、生命周期、审查、证据、连续性、数据质量和时效性。
- 改写雷达 P0/P1/P2 或生命周期。

### Telegram bindings 绑定表

Telegram bindings 表只回答：

- 哪个 Telegram `chat_id` 绑定到哪个内部 `user_key`。
- 该 chat 当前是否允许使用 bot 和接收推送。
- 绑定来源是手动 API 维护还是后续迁移/导入。

Telegram bindings 表不负责：

- 保存 Telegram bot token、webhook secret 或消息原文。
- 修改雷达 P0/P1/P2、生命周期、报告状态或评分。
- 替代 `TELEGRAM_ALLOWED_CHAT_IDS` 的硬安全门；如果环境白名单存在，环境白名单仍会先过滤。

## 5. 当前尚未实现但路线图中出现的表

这些表出现在总文档规划里，但当前代码和迁移里还没有实现。开发前必须先写 PRD、模型和迁移。

M5 的数据模型基线已经修正为 A 股 5 分钟资金主线雷达 MVP：

- 雷达主数据共享，不按用户复制。
- 持仓、自选、报告、Telegram 会话、导出和分享按用户隔离。
- 持仓成本价和仓位比例可选。
- 持仓/自选只影响个人优先级，不改变市场主线 P0/P1/P2。
- PostgreSQL + Redis 是 MVP 数据底座；vector DB、pgvector、Qdrant 后置。

| 规划表 | 所属未来阶段 | 预期用途 |
| --- | --- | --- |
| `instruments` | M5 | 标的主数据，用于个股异动回推和持仓/自选关联 |
| `sectors` | M5 | 行业/板块主数据，用于资金主线聚合 |
| `concepts` | M5 | 概念/主题主数据，用于资金主线聚合 |
| `signal_lifecycle_events` | M5 | 更细粒度生命周期事件，和 P0/P1/P2 强度等级分离 |
| `evidence_items` | M6+ | 更通用的证据对象 |
| `focus_items` | M5 | 临时关注、备注和 free-chat 低风险数据修改 |
| `report_exports` | M5+ | HTML/PDF/Markdown 导出记录，M5 可先只保留 Markdown/HTML |
| `report_reviews` | M5 | 所有报告发布前审查 |
| `agent_task_logs` | M5+ | Agent 任务日志、显式降级和 fallback 记录 |
| `tool_call_logs` | M5+ | Telegram/Web/Agent 工具调用日志 |
| `audit_events` | M5 | 用户操作、二次确认和系统审计 |
| `debug_cases` | M8+ | 调试案例库 |

## 6. 新增数据表规则

新增任何表之前，先回答：

1. 这个表服务哪个阶段的闭环？
2. 是否已有表能满足需求？
3. 是否涉及公开分享或个人数据？
4. 是否需要审计字段？
5. 是否需要唯一约束或索引？
6. 是否需要迁移旧数据？
7. 是否会错误影响市场主线等级？
8. 是否需要用户隔离或白名单限制？

必须同步完成：

- SQLAlchemy model。
- Alembic migration。
- 至少一个测试或迁移验证。
- 文档更新。

涉及持仓、自选、报告、推送、评分和分享的表，还必须检查：

- 个人字段不得进入公开分享 payload。
- 成本价、仓位比例必须可为空。
- 用户维度只能影响个人优先级，不能覆盖雷达主数据等级。
- 高风险操作需要二次确认和审计事件。

## 7. 修改现有表规则

修改现有表前先搜索引用：

```powershell
Select-String -Path backend\app\**\*.py,tests\**\*.py -Pattern "field_or_table_name"
```

重点检查：

- Pydantic schema 是否同步。
- API response 是否变化。
- golden case 是否需要更新。
- 分享脱敏是否受影响。
- Alembic 是否能从空库执行。
