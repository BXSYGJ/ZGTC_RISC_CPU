# PG200 共享存储集成验证记录

## 联合协议仿真

运行环境为 Windows Icarus Verilog 12.0；行为模型位于仿真目录，PDS 使用生成的 PG200 物理 DDR3 IP。

`python run_protocol_sim.py` 对完整 RV32IMC 固件、PaceRV 核、共享 DDR 桥、四主口控制器与现有 `self_test` 执行联合仿真。实际输出：

```text
PACERV_SHARED BEGIN seq=00000000 RV32IMC 125MHz physical-DDR3
ISA=RV32IMC MASK=SB_SH CRC=0359210D EXPECT=0359210D ERR=00000000
PACERV_SHARED PASS
REMOTE_PROTOCOL_SIM PASS overlap=1 masks=2 cpu_requests=1538
```

进程返回 0。检查包括 CPU 与竞争主口同时请求、两次部分写入、1,538 次 CPU DDR 请求、启动4 KiB自检、竞争主口4 KiB写读以及全部桥／仲裁／控制器错误信号为0。

固件输出中的 `physical-DDR3` 是该固件面向的硬件目标标识。上述结果属于协议级仿真；物理DDR和远程串口结果由实际上板采集生成。

## 正式音频控制固件

`python run_protocol_sim.py --audio --firmware <instrec_fpga/src/cpu/prog_pacerv.hex>` 运行主整机的 RV32IMC 新固件。DDR和共享端口为同一协议测试路径，NPU启动由模拟竞争主口回应。实际输出：

```text
PACERV RV32IMC SHARED SYSTEM
PACERV IMC OK 0
PACERV DDR OK 0 CRC=0xab60ce69
RV32 BOOT
RV32 MMIO OK
RV32 ISA OK
RV32 BENCH cycles=179874 inst=149878 acc=0xf2d8888b
DDR OK STS 0x00000070
NPU GO
NPU top1=0 last_class=0 last_p=100 c=600
REMOTE_AUDIO_PROTOCOL_SIM PASS masks=48 cpu_requests=331
```

进程返回 0。48 次字节／半字部分写入通过；331 次 CPU DDR 请求通过；正式固件取得模拟主口完成后的结果快照。这里的整数循环计数来源于该固件，CoreMark 不在本测试内。

## 采集脚本

`python -m unittest discover -s tests -p test_remote_capture.py -v` 返回0，11项测试通过，包括程序烧写、预约响应、读取和关闭异常后的释放；已有预约保持原状；跨包重组；完整BEGIN/CRC/ERR/PASS对应；序号连续性；超时保留原始证据。另外两项时钟约束检查通过。

`pwsh -File capture_remote.ps1 -Action inspect -AccountFile <既有账号文件>` 已实际返回0。平台目录18台均PG2L200H，7台online；账号无当前预约。脚本仅打印设备数据。

## 构建输入

`python verify_inputs.py` 输出 `INPUT_HASHES_OK files=96 target=PG2L200H-6FBB676`。75项IP源码和IDF来自官方PG200参考工程；构建输入覆盖17个设计源、IP、固件与三份管脚／时钟约束。各次PDS运行冻结自己的清单，后续修改另建目录。

首轮PDS由主任务启动，compile通过；后续约束检查提示10个低速IO缺少VCCIO。本目录已对照通过的最小PG200例程补齐方向、3.3 V、电气标准与输出驱动属性，失败构建证据保留在主任务的独立run目录。

## 复用约束的兼容性

联合测试发现旧 `self_test` 依赖最后写beat与done同拍。共享端口已恢复向客户传递下游原始done，同时保持所有权直至剩余读beat排空；现有自检和CPU桥使用各自的完成判据。上述仿真同时覆盖这两种客户。

## 启动与物理实现

`remote-20261113-190733-full` 在125MHz、0.150ns用户时钟不确定性下通过十张时序汇总表，setup WNS为+0.052ns，hold为+0.170ns。路由资源为11,164 LUT、7,501 FF、1,634 Distributed RAM、4 APM、0 DRM。两次远程烧写均完成，但90秒串口抓取为零字节，板卡ID分别为7和12，均已释放。独立原H3控制位流在板卡35取得1,007字节串口输出，验证了平台串口传输路径。

中间PG200适配增加D18/27MHz自动上电复位，并尝试在PLL锁定后等待1024个用户边沿再释放PHY。该中间版 `remote-20261113-200703-full` 通过全部时序（setup +0.002ns），但板卡15的90秒UART仍为零；记录保留。其clock stub当时令core clock无条件运行，覆盖不了真实IP启动过程对该时钟的依赖。

当前适配保留27MHz自动上电复位，恢复官方示例的 `dbg_ddrphy_rst_n=1`，由IP内部管理PLL/PHY启动，CK delay关闭。新的clock stub在启动阶段停止用户时钟，确认wrapper的PHY enable仍为1，时钟恢复后复位能同步释放。实际输出 `PG200_CLOCK_BOOT PASS independent_phy_enable=1 stopped_clock_start=1 key_reset=1 ck_delay=0`，返回0。

同板控制实验在板卡62上先收到原H3的1,031字节，再收到独立27MHz探针的78字节。探针暴露了远程顶层遗漏的注册ready适配，原始字节呈隔字符输出；当前顶层与探针均已补齐生产系统同款接受保持逻辑。现版协议仿真逐位解码UART引脚，专项固件全部147字节、音频控制固件全部247字节均按FIFO顺序一致，返回0。独立探针仿真输出完整26字节 `PG200_REF E=000003D1 R=1`；缩短后的1ms测量窗计数977，匹配125MHz输入。

启动修正版的路由和实板结果使用自己的冻结输入及采集目录；前述+0.052ns仅属于`190733`版本。
