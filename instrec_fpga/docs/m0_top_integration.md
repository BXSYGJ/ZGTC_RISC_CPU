# InstRec-FPGA M0 顶层集成蓝图（T-M0-09 前半交付）

| 项 | 内容 |
| ---- | ---- |
| 日期 | 2026-10-26 |
| 作者 | RTL 工程师（冯工） |
| 范围 | instrec_top M0 版的端口契约、例化树、信号接线表、CDC 清单——供 T-M0-09 后半（顶层 RTL 本体）直接照图施工 |
| 配套 | `constraints/instrec_top.fdc`（完整版，同轮交付）；各模块端口均已逐一核对自 `src/**` 实际文件（2026-10-26 状态） |

---

## 一、顶层端口总表（instrec_top M0 版）

### 1. 板载（13 脚，约束在 instrec_top.fdc）

| 端口 | 方向 | LOC | 属性 | 来源核对 |
| ---- | ---- | ---- | ---- | ---- |
| `clk` | in | D18 | LVCMOS33 | pin_constraints.md；**端口名 clk（非 design.md §2.2.1 的 clk_27m）**：兼容零改动 ddr3_100h.fdc 的 `[get_clocks {clk}]` 引用，内部网名 clk_27m |
| `rst_n` | in | C22 | LVCMOS33 | 同上（KEY0） |
| `key1_n` | in | C23 | LVCMOS33 | 同上（KEY1，导出触发） |
| `led[7:0]` | out | A20/C18/C19/E18/A17/A18/C17/B17 | LVCMOS33 DRIVE8 SLOW | 骨架原样 |
| `uart_rx` | in | B24 | LVCMOS33 | pin_constraints.md（CP2102 TXD） |
| `uart_tx` | out | C24 | LVCMOS33 DRIVE8 SLOW | 同上（低速慢沿） |

### 2. I2S（3 脚，design.md §8.2 选型）

| 端口 | 方向 | LOC | 属性 | 备注 |
| ---- | ---- | ---- | ---- | ---- |
| `i2s_bck` | out | U20 | LVCMOS33 DRIVE8 SLOW | demo ad_clk 复用；DRIVE/SLEW 为 §8.2 决策（偏离 demo DRIVE4/FAST，慢沿利于 SI） |
| `i2s_lrck` | out | T20 | 同上 | demo da_clk 复用 |
| `i2s_sd` | in | V16 | LVCMOS33 | demo ad_data_in[7] 复用 |

### 3. HDMI（30 脚，逐针照抄 demo fdc，diff 校验 30/30 属性块一致）

| 端口 | 方向 | LOC | 属性 |
| ---- | ---- | ---- | ---- |
| `vout_data[23:0]` | out | P16 K25 K26 L24 L25 L22 L23 N21 N22 N23 N24 P23 P24 R25 P25 T25 T22 R22 N18 M21 M22 P20 P21 P19（bit23→bit0 序） | LVCMOS33 DRIVE4 FAST（demo 原样） |
| `vout_clk` | out | T24 | 同上 |
| `vout_de` | out | N19 | 同上 |
| `vout_hs` | out | R20 | 同上 |
| `vout_vs` | out | R21 | 同上 |
| `iic_tx_scl` | out | K22 | 同上 |
| `iic_tx_sda` | inout | K23 | 同上 |

不引入：demo `rstn_out`(G25)、`led_int`(A20)（T-M0-07 决策；状态走 led[7:0]+UART）。

### 4. DDR3（75 脚，约束在 ddr3_100h.fdc，零改动复制）

| 端口 | 方向 | 说明 |
| ---- | ---- | ---- |
| `ref_clk_p/ref_clk_n` | in | N3/N2 差分 125MHz（create_clock ref_clk 8ns） |
| `mem_*`（cs_n/rst_n/ck/ck_n/cke/ras_n/cas_n/we_n/odt/a/ba/dqs/dqs_n/dq/dm） | out/inout | 73 针表由 gen_ddr3_fdc.py 生成校验（507 IO attribute lines，本轮复跑 OK） |

**引脚冲突终检**：instrec_top.fdc 46 脚 ∩ ddr3_100h.fdc = 空；fdc 内部无重复 LOC（脚本校验）。

---

## 二、例化树（实例名契约——fdc generated-clock 路径硬依赖）

```
instrec_top
 +-- u_audio_pll        audio_pll      clk_27m/rst_n -> clk_nco, pll_locked, rst_sync_nco
 |                                            |  (fdc: instrec_top.u_audio_pll.u_pll_audio.u_gpll/CLKOUT0 -> clk_nco)
 +-- u_i2s_clk_gen      i2s_clk_gen    <- clk_nco, rst_sync_nco -> bck_phase/bck_tick/i2s_bck/i2s_lrck
 +-- u_i2s_rx           i2s_rx         <- bck_tick/bck_phase/i2s_lrck + i2s_sd(pin) -> pcm_l/pcm_r/pcm_valid/sd_idle
 +-- u_audio_cdc_fifo   audio_cdc_fifo 写侧<- u_i2s_rx（clk_nco, rst_sync_nco）
 |                                    读侧-> u_audio_sink（clk_core, rst_sync_core）
 +-- u_audio_sink       audio_sink     -> m0 主口 -> u_ddr3_ctrl_axi；win_tick/win_id 预留 M1；
 |                                    wave_min/max/wave_valid/mute_flag_sync <-> u_ui_renderer；pix_clk <- u_hdmi_tx_if
 +-- ddr3_wrapper       ddr3_wrapper   <- ref_clk_p/n, resetn(=rst_sync_core), axi_* <-> u_ddr3_ctrl_axi
 |                                    -> core_clk, core_clk_rst_n, ddr_init_done, pll_lock, ddrphy_cpd_lock, mem_*(pins)
 |                                    (fdc: ddr3_wrapper.I_ips_ddr_top 层级——实例名必须恰好为 ddr3_wrapper)
 +-- u_ddr3_ctrl_axi    ddr3_ctrl_axi  m0..m3 四主口 + axi_* <-> wrapper；wait_cnt_* / addr_err / to_err 遥测
 +-- u_self_test        self_test      主口 3 低优先级窗口（对接端口名见 §五.3 待核对项）
 +-- u_sys_ctrl         sys_ctrl       <- pll_locked/audio_pll, ddrphy_cpd_lock/ddr_init_done/wrapper,
 |                                    hdmi_init_over/hdmi_init_fail/hdmi_tx_if, sd_idle/i2s_rx, overflow_cnt/cdc_fifo
 |                                    -> st_start -> u_self_test; dbg_line_* -> u_uart_debug; led 编码
 +-- u_uart_debug       uart_debug     tx_byte_* -> u_uart_tx; rx_byte_* <- u_uart_rx; dbg_line_* <-> u_sys_ctrl
 +-- u_uart_tx          uart_tx        -> uart_tx(pin C24)
 +-- u_uart_rx          uart_rx        <- uart_rx(pin B24)
 +-- u_hdmi_tx_if       hdmi_tx_if     <- clk_27m(=clk)/rst_n -> pix_clk/rst_pix_n/pix_x/pix_y/pix_de/pix_hs/pix_vs,
 |                                    vout_*(pins)/iic_tx_*(pins)/hdmi_init_over/hdmi_init_fail/pll_lock
 |                                    (fdc: instrec_top.u_hdmi_tx_if.u_pll.u_gpll/CLKOUT0|1 -> pix_clk|cfg_clk)
 +-- u_ui_renderer      ui_renderer    <- pix_* + wave_*  <-> u_audio_sink；mute_flag_sync
      -> rgb/de_out/hs_out/vs_out -> u_hdmi_tx_if.rgb_in/de_in/hs_in/vs_in
```

**实例名硬约束**（改动须同步改 fdc 的 get_pins 路径）：
`u_hdmi_tx_if`、`u_audio_pll`（fdc 三条 generated-clock）、`ddr3_wrapper`（ddr3_100h.fdc 全部 73 针 + 5 条 PHY 时钟路径）。

---

## 三、关键信号接线表（逐对接，端口名以实际文件为准）

| 源（模块.端口） | 目的（模块.端口） | 说明 |
| ---- | ---- | ---- |
| u_audio_pll.clk_nco / rst_sync_nco | u_i2s_clk_gen、u_i2s_rx（clk_nco/rst_n）；u_audio_cdc_fifo（clk_nco/wr_rst_n） | 216M 域 |
| u_i2s_clk_gen.bck_tick/bck_phase/i2s_lrck | u_i2s_rx 同名 | 同域使能协议 |
| u_i2s_rx.pcm_valid/pcm_l/pcm_r + u_i2s_clk_gen.i2s_lrck | u_audio_cdc_fifo（pcm_valid/pcm_l/pcm_r/i2s_lrck） | **i2s_lrck 多接一根**（帧对齐写，T-M0-03 偏差 2） |
| u_audio_cdc_fifo.rd_data/rd_valid/empty | u_audio_sink（fifo_rd_data/fifo_rd_valid/fifo_empty） | audio_sink.fifo_rd_en -> cdc_fifo.rd_en |
| u_audio_sink.m0_cmd_valid/m0_cmd[36:0]/m0_wdata | u_ddr3_ctrl_axi（m0_cmd_valid/m0_cmd/m0_wdata） | 37bit 口径双方一致（已核） |
| u_ddr3_ctrl_axi.done（m0 完成 indication） | u_audio_sink.m0_done | 仲裁完成信号宽度/语义集成时核对（见 §五.3） |
| ddr3_wrapper.core_clk / core_clk_rst_n | 全部 core 域模块 clk/rst_n（sys_ctrl 直接用 core_clk_rst_n；audio_sink/self_test/uart_debug 同源） | core 域时钟+复位 |
| ddr3_wrapper.axi_* | u_ddr3_ctrl_axi.axi_* | 一一对应（孙工两文件端口已对齐） |
| u_hdmi_tx_if.pix_clk | u_audio_sink.pix_clk、u_ui_renderer.pix_clk | 148.5M 域时钟分发 |
| u_hdmi_tx_if.pix_x/pix_y/pix_de/pix_hs/pix_vs + rst_pix_n | u_ui_renderer 同名 | 时序/坐标/复位 |
| u_ui_renderer.rgb/de_out/hs_out/vs_out | u_hdmi_tx_if.rgb_in/de_in/hs_in/vs_in | 已对齐 3 拍流水 |
| u_ui_renderer.wave_rd_addr | u_audio_sink.wave_rd_addr | 组合地址直连 |
| u_audio_sink.wave_min/wave_max/wave_valid/mute_flag_sync | u_ui_renderer 同名 | 1 拍同步读契约 |
| u_ui_renderer.vsync_pulse | u_audio_sink.vsync_pulse | 消隐页切换锚点（audio_sink 内 2FF） |
| u_hdmi_tx_if.hdmi_init_over/hdmi_init_fail/pll_lock | u_sys_ctrl 同名 | sys_ctrl 内 2FF（郑工已注明） |
| u_i2s_rx.sd_idle | u_audio_sink.sd_idle（内 2FF）；u_sys_ctrl.sd_idle（内 2FF） | 两消费方各自同步 |
| u_audio_cdc_fifo.overflow_cnt | u_sys_ctrl.overflow_cnt（内 2FF） | 16bit 准静态遥测 |
| u_sys_ctrl.dbg_line_id/arg/fire | u_uart_debug 同名 | UART 行式输出 |
| u_uart_debug.tx_byte_data/valid | u_uart_tx.byte_wdata/wvalid | byte_wready -> tx_byte_ready |
| u_uart_rx.byte_rdata/rvalid | u_uart_debug.rx_byte_data/rvalid | |

## 四、CDC 清单（M0 全量，与 design.md §1.4 对照）

| # | 源域 → 目的域 | 信号 | 隔离（实现位置） |
| ---- | ---- | ---- | ---- |
| 1 | nco → core | PCM 样本流 | audio_cdc_fifo 双时钟 FIFO（模块内格雷指针） |
| 2 | nco → core | sd_idle | audio_sink 内 2FF；sys_ctrl 内 2FF（双消费各自同步） |
| 3 | nco → core | overflow_cnt[15:0] | sys_ctrl 内 2FF（准静态，多位同步毛刺可容忍——错误遥测语义） |
| 4 | cfg → core | hdmi_init_over / hdmi_init_fail | sys_ctrl 内 2FF |
| 5 | nco → core | pll_locked（audio_pll） | sys_ctrl 内 2FF |
| 6 | pix → core | vsync_pulse | audio_sink 内 2FF + 边沿检测 |
| 7 | core → pix | wave_valid / mute_flag_sync | audio_sink 内 2FF |
| 8 | core → pix | 列缓冲数据 + page_rd 位 | 双时钟 RAM（core 写/pix 读）；page_rd 仅在 vsync 锚点翻转（消隐期） |
| 9 | 异步 → nco | i2s_sd 引脚 | i2s_rx 内 2FF |
| 10 | 异步 → core | key1_n 引脚 | sys_ctrl 内两级同步+20ms 消抖（M0 预留） |
| 11 | core → nco | （design.md §1.4 行 2 的静音/使能） | **M0 无此路径**（无反向控制需求；M1+ 如需再补） |

fdc 异步组：instrec_top.fdc 一条全量 set_clock_groups（clk/pix_clk/cfg_clk/clk_nco + ref_clk 家族各自成组，与 ddr3_100h.fdc line 26 幂等重叠，已注释）；core_clk 为 IP 传播时钟未具名——跨 core 域路径靠 RTL 隔离 + T-VF-02 审查兜底（风险 §六.2）。

## 五、T-M0-09 后半（顶层 RTL）施工待办

1. **rst_sync_core 生成**（顶层内联几行即可）：KEY0 rst_n 异步断言、core_clk 同步释放 + 10ms 计数（design.md §1.3）→ 驱动 ddr3_wrapper.resetn；core 域模块 rst_n 用 **ddr3_wrapper.core_clk_rst_n**（IP 输出，sys_ctrl 注释已按此口径）——两复位源不同（前者喂 IP，后者 IP 产出喂逻辑），**不得交叉**（resetn 若接 IP 自身输出会成环）。
2. **KEY1 处理**：两级同步+20ms 消抖（sys_ctrl 内是否已含？其端口无 key1 输入——M0 版 sys_ctrl 端口表未列 KEY1，集成时确认郑工 M0 简化版是否消费；若不需要则 key1_n 仅留 fdc 占位）。
3. **self_test ↔ ctrl_axi 对接核对**：self_test 端口为单主风格（cmd_valid/cmd/wdata/wready_beat/rd_ready/rd_data/rd_valid/done），与 ctrl_axi 的 m3 口/公共 done 的映射关系集成时逐信号核对（谁持有 done 的判据、rd_valid 是公共口还是 m3 专属口）。
4. **uart_debug ↔ uart_tx/rx 字节通道**：名字对接（tx_byte_* ↔ byte_*）见 §三表尾。
5. **mel 引擎占位**：M0 版 win_tick/win_id 仅引出（test point 或 LED 观测），mel_engine M1 轮接入。
6. **顶层骨架替换**：现 src/ctrl/instrec_top.v 为 T-GP-01 冒烟骨架（clk/rst_n/led 闪烁），按本蓝图全量重写；check_rtl.py 全绿后跑 run_pds_full.ps1 六阶段。
7. **构建挂载核对**：build_full.tcl 已含 `src/**/*.v` glob 与 ipcore（ddr3_test.idf + pll.idf；pll_audio.idf 待 IP 生成后补一行 add_design——见风险 1）。

## 六、风险清单

1. **pll_audio IP 生成物缺失**：src/ip/audio_pll.v 例化 `pll_audio u_pll_audio`（27→216MHz，M=8/D=1），ipcore/pll_audio/ 尚不存在——T-M0-09 后半前须用 PDS IP Compiler 生成（郑工 audio_pll.v 注释亦声明此预期）。fdc 的 clk_nco generated-clock 路径按 IP Compiler 惯例假设内部 GTP_GPLL 实例名 `u_gpll`（与 ipcore/pll/pll.v 同构）；**生成后核对实例名，不同则改 fdc 该行 pin 路径**。
2. **core_clk 未在 fdc 具名**（IP 传播时钟，pds_cpu 先例同口径）：pix↔core、nco↔core 跨域路径在时序报告中的呈现依赖工具传播行为——若出现 unexpected 路径告警，需在 fdc 补 core_clk 的 create_generated_clock（源 ref_clk_p 经 IP 内部 GPLL）或 max_delay 例外；T-VF-02 CDC 审查兜底。
3. **set_clock_groups 幂等重叠**：与 ddr3_100h.fdc line 26 有 6 对重复异步关系（SDC 语义无害，已注释声明）；若 PDS 对重复声明报警告，可裁剪本文件语句为仅新增时钟组（行为等价）。
4. **self_test/ctrl_axi 对接口径**（§五.3）：集成轮次唯一未预核对的模块对，预留半天核对窗口。

## 七、变更记录

| 日期 | 内容 |
| ---- | ---- |
| 2026-10-26 | 初版（T-M0-09 前半）：fdc 完整版 46 脚 + 本蓝图；HDMI 30 脚逐针 diff 30/30；gen_ddr3_fdc.py 复跑 OK |