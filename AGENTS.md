# AGENTS.md

用户是业余开发者，使用 vibe coding 开发，不需要过多解释技术细节。

## 当前状态

- 项目当前已完成 M4 轻量审查层闭环。
- M1 工程骨架已完成。
- M2 AKShare 最小数据底座已完成早期闭环。
- M3 已能生成候选信号、证据链、生命周期、连续 P1 快报候选标记和雷达总览 API。
- M4 已有规则审查闭环，可审查单个雷达信号并记录结果；Provider 数据质量、证据冲突、重复触发、来源过期和分享预览安全门已进入审查判断。
- `/radar/signals/{signal_id}/share-preview` 是内部预检接口，可以返回阻断原因和审查状态。
- `/radar/signals/{signal_id}/share-payload` 是公开分享 payload，只输出脱源脱敏摘要和公开标签，不输出原始来源、内部证据详情、原始枚举、精确置信度或来源时间。
- 详细状态见 `docs/PROJECT_STATUS.md`。

## 开发边界

- 不提供交易建议，不写强买入/卖出语言。
- 不接自动交易。
- 复杂 Agent、Telegram、Web、报告系统还未开始，除非用户明确要求，不要提前大规模实现。
- 优先小步闭环：可启动、可测试、可提交。

## 常用质量门禁

```powershell
uv run pytest
uv run ruff check .
uv run alembic heads
uv run alembic upgrade head --sql
```
