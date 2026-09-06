# CoreMark 首轮实板基线

2026-09-06（Asia/Shanghai）完成；这是已验证的起始基线，不是已优化极限性能，也不是 EEMBC 认证声明。配置与完整操作规则见 `COREMARK.md`。

| 项目 | 性能种子 | 验证种子 |
| --- | --- | --- |
| 器件/平台 | PG2L200H，实验箱5 | PG2L200H，实验箱2 |
| 实际时钟 | 27 MHz | 27 MHz |
| seed1/seed2/seed3（hex） | 0/0/66 | 3415/3415/66 |
| 迭代数 | 200 | 200 |
| 测量周期 | 550,019,013 | 585,496,940 |
| 测量时间 | 20.3710745556 s | 21.6850718519 s |
| seed/list/matrix/state CRC | e9f5/e714/1fd7/8e3a | 18f2/e3c1/0747/8d84 |
| 最终 CRC | 382f | eccd |
| 原程序验证 | Correct operation validated | Correct operation validated |

两次计分阶段均超过 10 秒。固定上游在本机 x86-64 上使用 POSIX port、200 次迭代另外运行，两组最终 CRC 同样为 382f/eccd；主机短时运行只用于结果比对，不用于 FPGA 性能计分。

## 性能计算

- 性能种子：**9.8178424243 CoreMark**，即 200 × 27,000,000 / 550,019,013。
- **0.3636237935 CoreMark/MHz**，分母为实际运行的 27 MHz，不是 PDS 估算主频。
- 两次实现均为 3,735 LUT、3,007 FF、16.5 DRM36K 等效块，0 DSP/APM；324 distributed-RAM LUT 已包含在总 LUT 中。
- **0.002628605736 CoreMark/LUT**。验证种子的 9.2229346237 iterations/s 仅作为验证运行指标，不替换性能种子正式分数。
- 本次逻辑的 PDS 时序报告估算 79.1640 MHz；实际仅在 27 MHz 运行，未验证该估算上限。慢角 setup WNS 24.405 ns，最差 hold WHS 0.100 ns。

## 位流身份

性能构建 `build/pds/20260906-040751-908a8c5b`：

```text
bitstream SHA256 87847EDA000A058132EA623042BA5E81BE122989876839F1C1A11367BAB20256
firmware  SHA256 CCF141D18D6076A2AF9386545B01ADA80B03B85458595D699269E4CDE8A3069D
```

验证构建 `build/pds/20260906-041159-7b2dff7c`：

```text
bitstream SHA256 E6A0B6FA97B14CE3361CC757EFA211112500463C85323EEFDFE2578C499EC602
firmware  SHA256 1F1CD4C98AE084A6D4BCC2F942EC9B0E5D9E29FC370AF756CF49D0EBFC1313C0
```

两者 RTL、Cache/预测配置和引脚配置相同，固件种子选项不同。因第一台租期届满，第二组在另一台同型号板卡执行；优化后的正式复测应在同一台板卡完成成对、多次采集，避免把当前单次结果写成重复性或长期稳定性结论。

## 原始证据与拒收记录

完整报告分别在 `build/hardware/coremark-v0-i200-p400000.uart` 和 `coremark-v1-i200-p400000.uart`，旁边有截图和解析结果 JSON；原始混合 UI 会话保存在 `coremark-session-full.txt`。解析使用 START/FINISHED 边界，保留边界外噪声但不把它拼入计分报告。第二次打开串口前有控制字符残留，完整会话如实保留；第二次 START 后报告完整并通过严格解析。

未限速的第一次报告在远程采集中丢失字节，已保存为 incomplete 文件，不计分、不补猜缺失字段。当前 ConsoleDelayCycles=400000 只限制计时区外 printf，每字符约 14.8 ms；完整报告读回后才接受 CRC 和周期数据。原程序整数时间输出 20/21 秒，主机分数按完整 64 位周期重新计算而非直接使用整数 iterations/sec。

运行已完成后关闭串口并主动释放实验箱2，网站确认未申请设备。无上传账号密码到工程、无提交或推送源码。
