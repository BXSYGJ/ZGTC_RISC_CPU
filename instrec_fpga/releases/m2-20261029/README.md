# InstRec-FPGA M2 位流归档（2026-10-29）

- 位流：`instrec_top.sbit`（PG2L100H-6IFBG676，顶层 `instrec_top`）
- 来源 run：`20261029-110719-01d91e40`（PDS 2022.2-SP6.4，六阶段 OK，编译到出位流 48m22s）
- SHA-256：`E793A792B72437BEADC77B15CADF7EC5253CFEE63BE2FC72A051486C0B8C23F2`
- 内容范围：
  - 音频链路（I2S + DDR3 + Mel 引擎）、NPU 全链（wdma / conv / pool / gap / fc / softmax）、
    概率条 UI（bars_disp + ui_renderer）
  - `conv_engine` 已合并为**单共享核**（conv1..conv4 时分复用同一个 16-lane MAC 阵列），
    四组行缓冲与计数器仍各自独立
  - `softmax_top` 已从 267 级组合链改为流水实现（约 5 级，340 拍，位级不变）
  - 临时关闭（仅为缓解拥塞）：`text_disp`、`spectrum_disp`、`feat_copy_engine`、
    `feat_page_buf`、`ui_coord_delay` —— 谱图与文字层未在本位流中生效
- 时序：**Some Constraints Violated**
  - `ddrphy_sysclk`（core_clk 125 MHz）WNS **-3.593 ns**（6265 failing endpoints，TNS -5251.8）
  - `pix_clk` WNS +0.260、`clk_nco` +1.474、`cfg_clk` +92.288、`rst_clk` +4.509
  - Hold 全部满足（最差 tddrphy 0.027 ns）
- 资源：LUT 35045/66600 (53%)、FF 49478/133200 (37%)、APM 90/240 (38%)、
  DRAM 1501/19900 (8%)、DRM 79.5/155 (51%)、BKCL 6/6
- 关键证据：
  - 这是**全 NPU 系统首次布线完全收敛**（`Unrouted nets 0` at iteration 278）；
    此前 conv 四核/双核版本分别在 Place-0114 失败与 iteration 59 残留 11368 条未布网络
  - 相较 267 级 softmax 版本，`ddrphy_sysclk` 从 -42.057 ns 收敛到 -3.593 ns
  - 最差路径：`u_conv/g0_bank1`(DRM) -> `x_eff` -> APM 乘法 -> 32-bit 累加树 -> `acc_a`；
    走线 6.199 ns 占 56%，属布局分散而非逻辑层数问题
- 不能作为最终交付：core 域 -3.593 ns 意味着 DDR3 用户逻辑实际只能跑 86.3 MHz，
  板级 DDR3 读写存在风险；谱图/文字层缺失
- 复现：`pwsh -File scripts/run_pds_full.ps1`；构建脚本只要产出位流就报成功，
  时序判断必须读 `manifest.json` 的 `Wns` 或 `timing.rtr` 的 `Design Summary`

校验：`sha256sum -c SHA256SUMS`。