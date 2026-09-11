# DC90363D 资源优化记录（2026-09-10 更正）

## 结论更正

此前将 device_map 的 8907 LUT / 4965 FF 误记为后布局资源；“减少 467 LUT / 4.98%”以及相应 CoreMark/LUT 提升结论撤回。后续比较只使用选中种子的 place_route 日志中 CLMA LUT + CLMS LUT，不使用映射表代替。

## 已重算物理结果

| 实验目录（build/ila 下） | 后布局 LUT | 后布局 FF | WNS/ns |
| --- | ---: | ---: | ---: |
| seed2-gplace-times2-20260910 | 9374 | 4984 | 0.078 |
| seed2-gplace-times3-20260910 | 9374 | 4984 | 0.078 |
| seed2-times2-logicopt-20260910 | 9374 | 4984 | 0.078 |
| seed2-times2-route-recovery-20260910 | 9374 | 4984 | 0.078 |
| seed2-place2-route2-20260910 | 9378 | 4984 | 0.078 |
| seed2-place2-route1-20260910 | 9378 | 4984 | 0.078 |

以上运行的 CPU 约束为 157.5 MHz，PDS 估算最高频率为 159.4642 MHz；估算值不是硬件频率测量。基线为 9374 LUT，故这些实验未产生资源收益。

## 固件与硬件证据边界

- 这些布局实验来源是 GPIO 诊断应用（source-candidate/原始 physical-qualification），不是 CoreMark 固件；同一 CPU RTL 不等于同一固件网表。
- 42 数据 / 33 触发 / 1024 深度的 cpu.fic 配置被保留；配置存在不等于实际 ILA 采集已验证。
- 历史浏览器操作报告了下载及唤醒成功；发送 G 返回 GPIO UNKNOWN 与 GPIO 诊断应用相符，不能据此断定是平台旧固件。
- 这些新位流没有独立的 CoreMark 成绩，禁止直接继承原成绩填入候选资源效率。
- 用户提供的基线成绩 501.0657302224314 CoreMark、3.181369715697977 CoreMark/MHz、9374 LUT 仍以 build/hardware/regfile-fanout-minimal-20260909-box5/hardware-coremark-qualification.json 为来源。

## 实验与测试边界

- full_icache_tagvalid 目录仍含未验收的 CPU/外设改动，不是已验收 DC90363D 原版，也没有证明满足 157.5 MHz。
- 之前运行 full_resource_opt_timer_keep/test_full_peripherals.py 只检查其自身候选，不能用于证明 full_icache_tagvalid/rtl 下的外设修改通过。
- 比较器回退曾引入 early_wb_mem_result 重复声明，本次修复；修复后的测试结果单独报告。
- gplace_times 是多个种子尝试，不能把相同映射资源当成迭代已经收敛的证据。

## 证据位置

重算资格：build/ila/seed2-gplace-times2-20260910/physical-qualification.json。
六组重算明细：build/ila/seed2-gplace-times2-20260910/post-route-reaudit.json。
原始日志保留，正式基线不覆盖，未执行 GitHub 推送。

## 本次补验

- 报告解析测试：10 项通过，新增映射表不能替代后布局资源的回归用例。
- 当前实验核心：删除重复声明后，BTB=8、EarlyDRequest 开启，预测器 0/1 各三组随机种子及独立退休轨迹检查通过。
- 当前实验外设：显式选中 full_icache_tagvalid/rtl/rv32_peripherals.sv，3811 项检查与 9088 周期定时器等价测试通过；未将旧属性形状测试或旧负面对照冒充本次覆盖。
- 精确源码哈希和测试范围：experiments/full_icache_tagvalid/build/reaudit-regression-20260910.json。这些仿真不证明 157.5 MHz 时序或 CoreMark 成绩。
