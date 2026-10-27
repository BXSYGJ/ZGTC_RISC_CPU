# InstRec-FPGA M1 位流归档（2026-10-27）

- 位流：`instrec_top.sbit`（PG2L100H-6IFBG676，顶层 `instrec_top`，含 M0 链路 + M1 Mel 引擎）
- 来源 run：`20261027-121101-5c24a968`（PDS 2022.2-SP6.4，六阶段 OK）
- SHA-256：`BD40D10A3DD82600DB8F0C0F709B0C45F0A2294B4177F36A822383C7769C3600`
- 时序：**All Constraints Met**，WNS +1.438 ns（clk_nco），WHS +0.224 ns；
  `ddrphy_sysclk`（core_clk 125 MHz）slack +0.837 ns
- 资源：LUT 15740/66600 (24%)、FF 11915/133200 (9%)、APM 29/240 (13%)、DRAM 43.5/155 (29%)、BKCL 6/6
- 时序报告：`timing.rtr`（同目录）
- 相对 M0 的变化：新增 Mel 引擎（stft/FFT/mel_filter/db_norm/standardize）；
  `db_norm` 改 4 拍流水、`standardize` 改 5 拍流水，算术顺序与位级结果不变
- 范围边界：**构建时序已收敛，但板级 Mel 对拍（T-M1-07）尚未执行**；
  上板通过不等于电气/CDC/长时稳定认证
- 复现：`instrec_fpga/scripts/run_pds_full.ps1`；构建后核对 `Wns`，脚本不替代时序判断

校验：`sha256sum -c SHA256SUMS`。