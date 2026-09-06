# 首轮 CPU 实板自检记录

## 验证对象

- 时间：2026-09-06 03:51–03:52，Asia/Shanghai。
- 远程设备：实验箱5，网站报告器件 PG2L200H；工程目标 PG2L200H -6 FBB676。
- PDS：Windows 2022.2-SP6.4 ADS；顶层 pds_soc_top；实际时钟 27 MHz。
- 构建目录：`build/pds/20260906-034718-be0d2a42`。
- 位流 SHA-256：`4081930BE7AECB51AE6E49AE559106B1C7393BB74692DB5EE7EBC91A30229084`。
- 固件快照 SHA-256：`BA7FA75942E243E78F2B2DC42E31F051117BC7FEA3FD38DC8CE4D099B29B72D5`。
- UART profile：RemoteLab，RX AC26 / TX AB26，115200 8N1；外部中断来自 UART RX，未用 GPIO 按键触发。

## 原始现象

网站确认“固件下载完成且设备已唤醒”。串口打开后接收到 12 字节启动信息；随后以 HEX 模式发送单字节 A5，接收到 11 字节回应：

```text
[03:51:43.532] RX  ZGTC RV32I\r\n
[03:51:55.863] TX  A5
[03:51:56.094] RX  ZSOC PASS\r\n
RX hex: 5A534F4320504153530D0A
```

首个 Z 是预期应答字节 5A，不是多出的乱码。服务端 read 响应显示 `bytesRead=11`、`hasData=true`，其 UTC 时间为 2026-09-05T19:51:56.083Z，与上述本地时间一致。

保存的本地证据：`build/hardware/soc-remotelab-pass.png`、`soc-remotelab-uart.txt`、`soc-remotelab-serial-events.json`。这些是生成的证据文件，不纳入源码版本控制；本记录保留关键摘要和位流身份。

## 结论边界

该固件只有在 C 启动数据检查、软件中断、定时中断、UART 外部中断各一次检查、FENCE.I 维护完成，以及输入字节 A5 检查之后才输出成功字符串。其成功响应构成此次 CPU+缓存+外设真实运行证据，而非仅下载成功。对应固件也已经通过仿真。

尚未由这次硬件实验验证：全 RV32I 指令覆盖、Cache 所有替换路径、错误注入、GPIO 按键输入、LED 数值的独立测量、长期稳定性、CoreMark、ILA。GPIO 外部中断版本目前有仿真证据，不与 UART 外部中断硬件版本混淆。

该位流映射资源为 3,735 LUT、3,007 FF、324 distributed-RAM LUT（属于总 LUT）、16.5 DRM36K 等效块、0 DSP/APM。27 MHz 下慢角 setup WNS=24.405 ns，慢/快角 hold WHS=0.142/0.100 ns，内部约束通过。报告估算频率 79.1640 MHz 不是本次实际工作频率，不得作为已实测 fmax。

异步输入已豁免同步 I/O 时序，LED/UART TX 未作外部同步接口签核；SCBV 提示仍存在，未凭猜测设置。初次实验箱9申请时长耗尽导致下载后唤醒失败，随后在实验箱5完成上述闭环；该失败不应写成 CPU 功能失败或隐去。
