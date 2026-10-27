# InstRec-FPGA M0 位流归档（2026-10-27）

- 位流：`instrec_top.sbit`（PG2L100H-6IFBG676，顶层 `instrec_top`）
- 来源 run：`20261027-000612-a71f1451`（PDS 2022.2-SP6.4，六阶段 OK）
- SHA-256：`C517736C7E61937521BC1776DDA4ACAC66F0373DF7E0FACDD86AEC017DD2EDAC`
- 时序：All Constraints Met，WNS +1.757 ns，WHS +0.249 ns
- 资源：LUT 6201/66600 (9%)、FF 6743/133200 (5%)、BKCL 6/6
- 范围：M0 链路（I2S → DDR3 → HDMI 波形），**尚未上板**；上板冒烟 T-M0-10 未执行。
  构建通过不等于板级/电气/长时稳定认证。
- 复现：`instrec_fpga/scripts/run_pds_full.ps1`；构建后必须核对 `Wns`，脚本不校验时序。

校验：`sha256sum -c SHA256SUMS`（在 Windows 可用 `Get-FileHash` 对照 `SHA256SUMS`）。