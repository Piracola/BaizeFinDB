# Terminal Reference Evaluation

更新日期：2026-05-03

## 结论

本项目不直接 fork 或二改 FinceptTerminal；BaizeFinDB 继续保留现有 FastAPI 后端、静态 Web MVP、Telegram、Linux 和 Windows 客户端路线。FinceptTerminal 与 OpenBB 只作为产品和架构参考。

## FinceptTerminal 判断

- 已拉取参考仓库到 `F:\finance\reference-repos\FinceptTerminal`。
- 技术栈是 C++20、Qt6、CMake、嵌入式 Python，和当前项目的 Python/FastAPI/静态 Web/Tkinter 路线差异较大。
- 直接二改需要 Qt 6.8.3、MSVC/GCC、CMake、Ninja、Python 3.11 等完整原生桌面构建链，开发成本高于继续改造 BaizeFinDB。
- 许可证为 AGPL-3.0，并包含商业/内部使用和 trade dress 限制说明。为了降低合规风险，不复制代码、品牌、专有布局、命令体系或视觉识别。
- 可借鉴的抽象：终端式工作台、模块导航、命令栏、F-key 操作条、屏幕/服务分离、DataHub 风格的统一数据订阅思想。

## OpenBB 判断

- 已拉取参考仓库到 `F:\finance\reference-repos\OpenBB`。
- OpenBB 更适合作为数据平台架构参考：provider、extension、标准 schema、FastAPI 暴露和 Python API。
- 不把 OpenBB 整体并入当前项目；后续可参考其 provider/extension 思路重构 BaizeFinDB 的数据源插件层。

## 当前落地方式

- Web 侧先做 BaizeFinDB 自有的雷达终端工作台外壳。
- 终端壳只消费后端 API 和发命令，不计算 P0/P1/P2、生命周期、审查状态或发布状态。
- 保持项目定位：个人投研辅助，不接自动交易、不输出买卖指令、不承诺收益。
