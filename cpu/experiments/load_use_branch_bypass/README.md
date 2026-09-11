# 分支专用加载前递

隔离核心和对应cached CPU覆盖fixture，完整设计、源绑定、执行周期、135 MHz实现与尚未完成项目见 `../../docs/LOAD_USE_BRANCH_BYPASS.md`。
用 `scripts/test_load_use_branch_bypass.py` 检查数据路径和拒绝控制；集成覆盖测试需要已建立的隔离阶段及selftest固件。
只有条件分支可在加载完成拍直通；其余消费者仍受LOAD_USE_BUBBLE控制。不要直接替换生产核心或将十轮代理值作为正式成绩。
