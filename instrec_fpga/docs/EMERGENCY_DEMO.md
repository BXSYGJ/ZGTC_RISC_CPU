# 紧急音频与显示演示版

独立构建集 `emergency_demo`，顶层 `top_emergency_demo`，保存在 XSY；正式 full 顶层不改。

- 保留 PCM1808 真实音频、波形、Mel 频谱、HDMI 中文八类界面。
- 无 NPU 实例、不执行推理、不需要模型权重。置信度及主类别为预设曲线回放，不代表识别结果。
- 上电置信度为零；KEY1 消抖后从头播放，10Hz 更新，播完停在末帧，再按重播。KEY1 不再触发 DDR 自检；KEY0 仍为复位。
- DDR/HDMI 自检通过后真实音频和频谱持续运行，不依赖 KEY1。
- 已导入用户 confidence_timeline.json：114窗、中心1.485至57.985秒，581个10Hz采样点。CE2E2205已生成并烧录，BOOT/DDR自检通过，用户确认显示与回放正常；最终时序setup仍有负余量，详见STATUS。

用户曲线冻结在 `data/demo/confidence_timeline.json`，顺序为钢琴、小提琴、单簧管、长笛、萨克斯、小号、原声吉他、电吉他。演示专用标签与ROM使用这个顺序，正式模型标签/ROM不改。右上角标注“曲线演示”。

KEY1时刻对应WAV起点。第一窗中心前保持首窗数值，随后按center_sec在10Hz网格线性插值，概率乘100四舍五入到整数百分比，58.0秒开始保持末帧。最大整数百分比决定大标题，平局选靠前项；这是回放约定，不是实时推理。外部播放器独立运行，板卡不能控制WAV起播；播放eight_class_montage.wav时应同时按KEY1，偏差可重新开始。

导入：`python scripts/set_demo_curve.py data/demo/confidence_timeline.json`；生成隔离顶层及显示模块：`python scripts/prepare_emergency_demo.py`；验证：`python sim/run_sim.py demo_player demo_timeline`。也支持旧time/pct关键帧列表，但该模式不重新生成类别标签。新源门控：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet emergency_demo -StopAfter dev_map`。

正式顶层不改；生成脚本保留原实例层级用于现有约束。曲线必须在门控前冻结，改ROM后不复用旧映射。资源允许后限时PNR、完整时序核验，再安全复用既有JS下载。既有1497FAF4正式位流及证据保留，演示产物独立命名。
