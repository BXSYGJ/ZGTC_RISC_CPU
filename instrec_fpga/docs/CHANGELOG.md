# InstRec-FPGA 变更日志

> 每次会话结束前追加一条：时间、做了什么、结论、证据路径。倒序，最新在上。
> 状态汇总见 `docs/STATUS.md`。

## 2026-10-27 11:15 — 工作区/文档/版本整理

- 恢复 4 个被误回退的已跟踪文件（`.gitignore`、`DEV_SNAPSHOT.md`、`cpu/fpga/rv32_ddr3_ip_wrapper.sv`、
  `cpu/rtl/rv32_burst_ddr3.sv`）。原 diff 留档：`reports/workspace-revert-20261027.diff`。
  其中 2 个 RTL 的改动会把已修复的 AXI 端口方向、13-bit 超时、读前 dummy-write 回退成旧 bug。
- `.gitignore` 增加 `!instrec_fpga/ipcore/`：DDR3 / GPLL IP 源文件是重建必需资产，此前被全局 `ipcore/` 忽略。
- SDD 三份文档复制到 `docs/sdd/`（`.codeartsdoer/` 被自身 `*` 规则整体忽略，交接会丢）。
- 新增 `docs/STATUS.md`（唯一实时状态源）与本文件。
- `instrec_fpga/` 首次纳入 git（此前 0 个文件被跟踪）：commit `1298395`，180 个文件。
- 搁置路线的 AI RTL 单独存档：commit `2abf5ed`。
- 证据从 `build/` 提取到可追踪位置：`reports/m0-manifest-20261027.json`、
  `reports/m1-timing-20261027-104218.txt`。
- 核对基线：pytest 63 passed；check_rtl 26 文件 0 violation。

## 2026-10-27 10:56 — M1 语法修复后的首次完整构建

- run `20261027-104218-acb7a788`：compile/synthesize/dev_map/pnr/report_timing 全过，
  gen_bit_stream 被会话结束中断，无 M1 位流。
- 新阻塞：`ddrphy_sysclk`（core_clk，125 MHz）WNS -4.401 ns / TNS -487.619 / 200 endpoints。
- 根因定位：最差路径在 `u_mel_engine/u_db_norm` 乘加组合链（17.539 ns，5 levels），非 DDR3 IP。
- 对照：`pds_cpu_100h` 同 IP `ddrphy_sysclk` = +2.110 ns。

## 2026-10-27 10:19 — 交接快照记录的语法错误全部修复

- `mel_engine.v`：参数基数字面量 `19'dPARAM` → `PARAM[18:0]`。
- `standardize.v`：`var_q16_u32` reg/wire 重复声明 → `var_q16_comb` 组合 + 快照。
- `fft2048_sdf.v`：去掉 generate 内嵌 generate，改裸 `if/else` + 条件 assign。
- `HANDOFF_SNAPSHOT_20261027.md` 第 4.1 节“fft 未修”的结论已过时。

## 2026-10-27 00:06 — M0 位流产出

- run `20261027-000612-a71f1451`，六阶段 OK，All Constraints Met，WNS +1.757。
- sbit sha256 `C517736C7E61937521BC1776DDA4ACAC66F0373DF7E0FACDD86AEC017DD2EDAC`。
- 资源 LUT 6201 (9%) / FF 6743 (5%) / BKCL 6/6。尚未上板。