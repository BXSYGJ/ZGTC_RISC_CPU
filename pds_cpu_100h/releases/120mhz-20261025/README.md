# PG2L100H RV32IM SoC 120 MHz 交付位流归档（2026-10-25）

- 位流：`pds_cpu_top_100h.sbit`（PG2L100H-6IFBG676，顶层 `pds_cpu_top_100h`）
- 来源 run：`20261025-112034-df03c4e4`
- SHA-256：`B4E623BF97B26734D3F3C723D0356A695FBD84E91B58F0D56395214BEACE4B98`
- 频率：120 MHz，全约束通过，WNS +0.014 ns
- 实板：CoreMark 383.0（3.19 CoreMark/MHz），CRC `0xd340`，timed_cycles 313,327,696（i1000）
- 加载方式：JTAG RAM 加载，**断电即失**；Flash 固化（.sfc）未做
- 频率边界：153 MHz 在本颗 100H 上不可复现（`cpu/docs/MIGRATION_100H_20261025.md`）
- 认证边界：电气/CDC/长时稳定性未做；上板通过不等于认证

校验：`sha256sum -c SHA256SUMS`。