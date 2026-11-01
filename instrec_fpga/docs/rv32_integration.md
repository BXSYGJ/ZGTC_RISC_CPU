# RV32 控制核与 AI 加速器集成

本轮以最小实际职责复用已交付的 `cpu/rtl/rv32_core.sv`，构建集 `rv_core` / 顶层 `top_rv_core`。
CPU 配置为 RV32I（M 扩展和预测关闭），不承担卷积、Mel 或 DDR 数据搬运；它运行 C 固件，通过 MMIO 请求推理、读取状态/结果、输出串口和控制 LED。原 `full`/`instrec_top` 不包含 CPU。

## 运行关系

- CPU 在 DDR 用户时钟 `core_clk` 域执行，8 KiB 固件 ROM、8 KiB RAM，不经过 DDR3 指令总线。
- 固件启动输出 `RV32 BOOT` / `RV32 MMIO OK` / `RV32 ISA OK`，执行固定整数工作负载并打印周期/指令计数。此计数不属于 CoreMark 或性能达标证明。
- 固件写 `CTRL[0]`，顶层挂起请求；只有 DDR 自检通过、权重有效、Mel 输出完整窗口、NPU 空闲且系统正常运行才发一个 start。
- 默认 `NPU_ENABLE=0`，无 CPU 请求不启动。首轮推理后固件观察概率事件、输出类别/百分比/结果周期并清除 sticky；当前固件只主动申请一次推理。需要连续推理时须明确增加后续请求。
- CPU UART 是 weight_loader、uart_debug 后的最低优先级源；满 FIFO 时 CPU store 背压，共享仲裁抑制 uart_tx 接收后残留的 ready。
- CPU 子系统锁存概率事件和对应周期数；软清除与新事件同拍时新事件优先。

## 内存与寄存器

| CPU 地址 | 含义 |
|---|---|
| `0x00000000..0x00001fff` | 固件 ROM，复位 PC=0 |
| `0x20000000..0x20001fff` | 数据/栈 RAM |
| `0x80000000` | ID=`0x52564331` |
| `0x80000004` | STATUS：busy bit0、done bit1、timeout bit2、probs bit3、DDR_OK bit5、DDR_ERR bit6 |
| `0x80000008` | 概率快照：idx[3:0]、pct[15:8] |
| `0x8000000c` | UART 写字节 |
| `0x80000010` | UART bit0可写、bits5:1占用 |
| `0x80000014` | LED 写/读 |
| `0x80000018/1c` | cycle/retired低32位 |
| `0x80000020` | 顶层 DDR 诊断字段 |
| `0x80000024` | CTRL bit0请求、bit1清除sticky |
| `0x80000028` | 对应概率事件的周期快照 |

## 构建与验证

从 `instrec_fpga/` 执行：

```powershell
python scripts/build_rv32_sw.py --no-m
python sim/run_sim.py rv_cpu --verbose
python sim/run_sim.py npu_completion --verbose
python scripts/check_rtl.py
python -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet rv_core
```

一次只允许一个独立 PDS run；launcher 与 worker 两个 pds_shell 进程可能属于同次调用。
构建输入一旦冻结不要改 RTL/FDC/hex；新脚本记录输入哈希并拒绝发布途中变更的产物。
`top_rv_core-latest.sbit/json` 只在完整成功后更新，部分阶段不会覆盖旧产物。
时序要读所有域 setup/hold，不能只看 manifest 旧式第一行 Wns。

新位流生成后：

```powershell
python scripts/board_check.py --sbit build/top_rv_core-latest.sbit --port COM5 --seconds 30 --expect "RV32 BOOT" "RV32 MMIO OK" "RV32 ISA OK" "DDROK" --json reports/board_rv_core.json
python scripts/weight_upload.py --port COM5
```

串口 `NPU GO` 只说明固件发出请求，不等于已经启动/完成推理；WOK 只说明权重上传验证。真正的 CPU+NPU 板级协作还需要完成请求后收到真实结果并与 golden 对拍。

## 交付边界

- 本顶层裁掉 UI/HDMI，I2S SD 接 0，不是外部真实音频全功能作品位流。
- `rv_cpu` 执行真实 CPU/固件，但 NPU 结果由测试台注入；真实 npu_top 完成仿真跳过前层，不能代替全链数值对拍。
- Python 与定向仿真结果见 `reports/rv32_sim_conclusion.md`；当前构建与板级结论以 `docs/STATUS.md` 为准。
- 旧 CPU 历史性能不适用于这里的 125 MHz 系统、配置或固件。不得据此声称 CoreMark、认证或全链板级通过。
