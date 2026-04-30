# AGENTS.md

用户是业余开发者，使用 vibe coding 开发，不需要过多解释技术细节。

## 当前状态

- 项目当前推进到 M3.2 雷达核心早期。
- M1 工程骨架已完成。
- M2 AKShare 最小数据底座已完成早期闭环。
- M3 已能生成候选信号、证据链、生命周期和连续 P1 快报候选标记。
- 详细状态见 `docs/PROJECT_STATUS.md`。

## 开发边界

- 不提供交易建议，不写强买入/卖出语言。
- 不接自动交易。
- Agent、Telegram、Web、报告系统还未开始，除非用户明确要求，不要提前大规模实现。
- 优先小步闭环：可启动、可测试、可提交。

## 常用质量门禁

```powershell
uv run pytest
uv run ruff check .
uv run alembic heads
uv run alembic upgrade head --sql
```
