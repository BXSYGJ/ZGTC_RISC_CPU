# 紧急音频与显示演示版

独立构建集 `emergency_demo`，顶层 `top_emergency_demo`，保存在 XSY；正式 full 顶层不改。

- 保留 PCM1808 真实音频、波形、Mel 频谱、HDMI 中文八类界面。
- 无 NPU 实例、不执行推理、不需要模型权重。置信度及主类别为预设曲线回放，不代表识别结果。
- 上电置信度为零；KEY1 消抖后从头播放，10Hz 更新，播完停在末帧，再按重播。KEY1 不再触发 DDR 自检；KEY0 仍为复位。
- DDR/HDMI 自检通过后真实音频和频谱持续运行，不依赖 KEY1。
- 目前曲线尚待用户提供，ROM 全零占位；尚无演示版位流或板测。

曲线 JSON 为关键帧列表，每项包含 time（秒，从0严格递增）与 pct（八项0..100）。顺序：单簧管、失真电吉他、女声、长笛、钢琴、次中音萨克斯、小号、小提琴。线性插值10Hz，最长409.5秒。最大值决定类别，相等时选靠前项，全零为等待。

生成：`python scripts/prepare_emergency_demo.py`；导入曲线：`python scripts/set_demo_curve.py docs/demo_curve.json`；验证：`python sim/run_sim.py demo_player`；新源门控：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet emergency_demo -StopAfter dev_map`。

正式顶层不改；生成脚本保留原实例层级用于现有约束。曲线必须在门控前冻结，改ROM后不复用旧映射。资源允许后限时PNR、完整时序核验，再安全复用既有JS下载。既有1497FAF4正式位流及证据保留，演示产物独立命名。
