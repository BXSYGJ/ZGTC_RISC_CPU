# PaceRV整机降频对音频识别的影响

当前候选将共享系统时钟从XSY2的125MHz降至109.375MHz。CPU替换为完整PaceRV H3 Base，NPU、Mel和DDR用户端使用同一较低时钟；PCM1808的48kHz采样、27MHz接收域及148.5MHz像素时钟独立运行。主要代价是计算结果稍晚到达，采集窗口长度仍为2.752秒。

| 项目 | XSY2 / 125MHz参考 | PaceRV候选 / 109.375MHz | 解释 |
| --- | ---: | ---: | --- |
| 系统时钟 | 125MHz | 109.375MHz | 降低12.5% |
| 同周期数任务耗时 | 1 | 1.142857 | 增加14.29% |
| 同一CPU固件整数循环 | 460,012周期；3.680096ms | 180,016周期；1.645861ms | 新核约快2.236倍；双方退休180,008条指令 |
| NPU按当前31,152,093周期折算 | 249.216744ms | 284.819136ms | 增加35.602392ms；为频率换算 |
| 外部采样率 | 48kHz | 48kHz | 时钟源不变 |
| 音频窗口 | 132,096帧；2.752s | 132,096帧；2.752s | 样本数和窗口时长不变 |
| 稳态第二窗I²S测试 | 132,096真实帧，0补零，0溢出 | 132,096真实帧，0补零，0溢出 | 所有样本顺序一致，写超时0 |

XSY2工作区`8f902aec29c38bc4a32a4e95ab47d18411684b52`的DDR IP为ACTUAL_RATE=1000Mbps、DFI_CLK_PERIOD=8000ps，用户时钟125MHz；其原CPU封装与prog.hex在换行规范化后匹配本轮冻结基线`852f067db4a4a710f5355e3ab311f035ced5b48d`。旧生产native报告`reports/cpu_native_pcm27_melsplit_20261103.json`记录31,141,255周期，125MHz下折算249.130040ms；新实现另有10,838周期流水开销，约0.035%。两项变化合计约35.689ms。

## 采集与计算的关系

I²S接收器按外部BCK/LRCK采样，经跨时钟FIFO送入audio_sink。audio_sink优先读取真实数据，每16帧汇集一页，并分别写入左右声道DDR区域；左声道采用两窗乒乓存储。其短暂停读由页写回控制，NPU推理不会直接冻结整窗采集。诊断锁窗是独立的软件功能。

降频时同步使用官方生成的875Mbps DDR IP、相应FDC、UART分频949、空FIFO补零间隔2279和匹配的超时计数。这样串口速率和音频时间节拍随实际系统时钟正确缩放。

现有I²S实验使用生产接收器、跨域FIFO和audio_sink，物理BCK=3.072MHz、LRCK=48kHz、接收域27MHz。每档各跑两个完整窗口，DDR命令使用固定512系统周期后完成的行为模型；所有立体声样本均逐个检查。启动首窗各出现1次补零，稳定第二窗均全部来自真实输入。原始结果保留在`build/pacerv_shared_system/audio_clock/20261114-022103/RESULT.json`。

NPU联合测试以实际RV32IMC固件通过共享DDR启动推理，四卷积、四池化、GAP、FC1、FC2、logits和概率均与独立整数golden精确一致。该项使用固定特征输入验证数值和控制；音频采集另由上述连续I²S测试验证。报告位于`build/sim/cpu_native_joint_pacerv_h3_imc_timing_rom_range_ff_fifos/PACERV_NATIVE_REPORT.json`。

## 综合判断

在当前2.752秒窗口、NPU负责主要卷积计算的应用中，降低系统时钟的主要影响是增加约36ms推理等待时间。相同CPU循环仍快约2.24倍，适合承担更多协议、状态管理和应用控制。采集与显示保留原时钟，现有仿真支持维持音频数据完整性及既有NPU数值结果。

109.375MHz目前为物理实现候选。021145完整六阶段结束并生成位流，最终系统slow setup为-1.633ns、slow hold为-0.127ns、fast hold为-0.136ns，像素slow setup为+0.611ns；该候选尚未取得时序资格。最终采用频率以100Pro+完整系统的全部时序检查为准；响应时间表中的毫秒数由RTL周期折算得到，约36ms增量对应NPU部分，完整端到端响应还包含Mel处理与共享DDR等待。本轮用户要求本地PDS验收，未新增实板采集。

复现命令（工作目录为instrec_fpga）：

```powershell
python sim/experiments/pacerv_integration/run_pacerv_checks.py
python sim/experiments/pacerv_integration/run_audio_clock_check.py
python sim/experiments/pacerv_integration/run_native_npu.py --firmware imc --backend wsl-verilator --distro Ubuntu-22.04 --verilator /home/bx/.local/src/verilator-5.040/bin/verilator --run-label audio_frequency_review
```
