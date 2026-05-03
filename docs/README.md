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
- Linux 服务器部署目前只有骨架，包含 API 容器、Celery worker/beat、compose overlay、systemd 和 nginx 示例；不要把它当作完整生产部署。
- `/ops/overview` 是当前只读运行状态、服务端磁盘摘要和告警摘要入口，可用于本地排障、服务器 smoke check 和后续监控接入。
- Tushare 当前已支持 `stock_basic`、`anns_d` 和 `stock_company` 手动抓取、失败记录、日志和快照查询；`anns_d` 重大风险公告可被雷达扫描映射为 risk P0。接入调度前必须再做真实 token 验证、字段漂移和误差样例。
- Web、Windows 客户端和 Telegram `/tushare` 只读展示 Tushare 配置状态，不触发真实抓取，不泄露 token 原文。
- Windows 客户端目前只是 MVP 源码运行版，不是安装包；只消费后端 API，不重新计算雷达等级、市场情绪、运行状态、数据源状态或评分。
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
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
```

开发 API 默认地址：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/ready`
- `http://127.0.0.1:8000/docs`
