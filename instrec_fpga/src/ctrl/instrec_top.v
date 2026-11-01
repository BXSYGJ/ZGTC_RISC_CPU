// -----------------------------------------------------------------------------
// File    : instrec_top.v
// Module  : instrec_top
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : M0 top-level integration: I2S capture -> CDC -> DDR3 -> HDMI
//           waveform display with the debug / self-test chain
//           (design doc sections 1.1 / 2.2.1, REQ-VER-001 M0 scope).
//
// Clock domains (design doc section 1.2):
//   clk       27 MHz board crystal (D18), reference of both GPLLs
//   clk_nco   216 MHz audio NCO time base (audio_pll / pll_audio IP)
//   pix_clk   148.5 MHz pixel clock (hdmi_tx_if / demo GPLL_B IP)
//   core_clk  125 MHz DDR3 controller user clock (ddr3_wrapper IP output)
//
// Reset tree (design doc section 1.3):
//   rst_n     asynchronous board reset (KEY0, C22)
//   rst_sync_nco   clk_nco domain, lock-gated sync release (audio_pll)
//   rst_pix_n      pix_clk domain, sync release (hdmi_tx_if)
//   rst_sync_core  = rst_n directly; feeds ONLY ddr3_wrapper.resetn.
//                  Must not depend on core_clk (the IP GPLL produces it,
//                  so a core_clk-based release counter deadlocks).
//   core_clk_rst_n core_clk domain, sync release (ddr3_wrapper IP)
//
// CDC points (producers synchronize internally, the top level only wires):
//   * pcm path        clk_nco -> core_clk  : audio_cdc_fifo dual-clock FIFO
//   * sd_idle         clk_nco -> core_clk  : 2FF inside audio_sink/sys_ctrl
//   * vsync_pulse     pix_clk -> core_clk  : 2FF + edge detect in audio_sink
//   * wave_rd channel pix_clk -> pix_clk   : same domain, direct wiring
//   * overflow_cnt    clk_nco -> core_clk  : 2FF in sys_ctrl (quasi-static)
//
// Observation taps left unconnected at this milestone (consumed by the
// T-M2-07 UART stats exporter; synthesis prunes them): wait_cnt_0..3,
// addr_err, to_err, cmd_to_err, dbg_to_state, wlast_miss_cnt, win_tick,
// win_id, mute_flag, err_cnt, fifo_full, sys_run, rx_byte_cnt,
// dbg_line_wready.
//
// The DDR3 IP instance hierarchy is instrec_top.ddr3_wrapper.I_ips_ddr_top
// (constraint paths in ddr3_100h.fdc depend on it, REQ-MEM-001).
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module instrec_top #(
    // 1 = full system (Mel -> NPU -> UI). Weights are loaded over UART
    // before sys_ctrl reaches RUN; the NPU starts on mel's window pulse.
    parameter NPU_ENABLE = 1
) (
    // ---- board pins ----
    input  wire        clk,          // 27 MHz crystal (D18)
    input  wire        rst_n,        // KEY0, active low (C22)
    input  wire        key1_n,       // KEY1, export trigger (C23)
    output wire [7:0]  led,          // status LEDs (A20..B17)
    input  wire        uart_rx,      // CP2102 RX (B24)
    output wire        uart_tx,      // CP2102 TX (C24)
    // ---- I2S audio pins ----
    output wire        i2s_bck,      // bit clock 1.4112 MHz (U20)
    output wire        i2s_lrck,     // frame clock 44.1 kHz (T20)
    input  wire        i2s_sd,       // serial data (V16)
    // ---- HDMI transmitter pins (demo fdc pinout) ----
    output wire        iic_tx_scl,   // I2C clock (K22)
    inout  wire        iic_tx_sda,   // I2C data (K23)
    output wire        vout_clk,     // pixel clock (T24)
    output wire        vout_de,      // data enable (N19)
    output wire        vout_hs,      // horizontal sync (R20)
    output wire        vout_vs,      // vertical sync (R21)
    output wire [23:0] vout_data,    // parallel RGB (demo 24-pin map)
    // ---- DDR3 physical side (ddr3_wrapper pass-through, N3/N2 + 73 pins) ----
    input  wire        ref_clk_p,    // 125 MHz differential reference
    input  wire        ref_clk_n,
    output wire        mem_cs_n,
    output wire        mem_rst_n,
    output wire        mem_ck,
    output wire        mem_ck_n,
    output wire        mem_cke,
    output wire        mem_ras_n,
    output wire        mem_cas_n,
    output wire        mem_we_n,
    output wire        mem_odt,
    output wire [14:0] mem_a,
    output wire [2:0]  mem_ba,
    inout  wire [3:0]  mem_dqs,
    inout  wire [3:0]  mem_dqs_n,
    inout  wire [31:0] mem_dq,
    output wire [3:0]  mem_dm
);

    // ==================================================================
    // Clock and reset nets
    // ==================================================================
    wire clk_nco;            // 216 MHz NCO time base
    wire pll_audio_locked;   // audio GPLL lock
    wire rst_sync_nco;       // clk_nco domain reset (lock gated)
    wire pix_clk;            // 148.5 MHz pixel clock
    wire rst_pix_n;          // pix_clk domain reset
    wire core_clk;           // 125 MHz DDR3 user clock
    wire core_clk_rst_n;     // core_clk domain reset
    wire ddr_init_done;      // DDR3 initialization done
    wire ddr_pll_lock;       // DDR3 controller PLL lock
    wire ddrphy_cpd_lock;    // DDR3 PHY CPD lock
    wire hdmi_init_over;     // HDMI I2C configuration done
    wire hdmi_init_fail;     // HDMI I2C retries exhausted
    wire hdmi_pll_lock;      // HDMI GPLL_B lock

    // ==================================================================
    // DDR3 IP reset: drive resetn straight from the board reset.
    // The IP's GPLL produces core_clk, so a reset-release counter that
    // runs on core_clk would deadlock (no reset -> no GPLL clock ->
    // counter never advances -> reset never releases). The validated
    // 100H CPU top (pds_cpu_top_100h.v.in) also ties .resetn(rst_n);
    // the IP's internal ips2l_rst_sync_v1_3 releases core_clk_rst_n
    // synchronously, so all core_clk logic still gets a clean reset.
    // ==================================================================
    wire rst_sync_core = rst_n;   // DDR3 IP reset, active low

    // ==================================================================
    // Audio chain (clk_nco / core_clk domains)
    // ==================================================================
    wire [4:0]  bck_phase;
    wire        bck_tick;
    wire [15:0] pcm_l;
    wire [15:0] pcm_r;
    wire        pcm_valid;
    wire        sd_idle;
    wire        fifo_rd_en;
    wire [31:0] fifo_rd_data;
    wire        fifo_rd_valid;
    wire        fifo_empty;
    wire        fifo_full;       // observation tap (unused in M0)
    wire [15:0] overflow_cnt;
    wire        m0_cmd_valid;
    wire [36:0] m0_cmd;
    wire [255:0] m0_wdata;
    wire        m0_done;
    wire        m0_wready_beat;  // observation tap (audio single-beat cmds)
    wire        win_tick;        // observation tap (T0.2 board check)
    wire [15:0] win_id;         // observation tap
    wire        mute_flag;       // observation tap
    wire [15:0] audio_err_cnt;  // observation tap

    // ==================================================================
    // Video chain (pix_clk domain)
    // ==================================================================
    wire [10:0] pix_x;
    wire [10:0] pix_y;
    wire        pix_de;
    wire        pix_hs;
    wire        pix_vs;
    wire [23:0] ui_rgb;
    wire        ui_de;
    wire        ui_hs;
    wire        ui_vs;
    wire [10:0] wave_rd_addr;
    wire [15:0] wave_min;
    wire [15:0] wave_max;
    wire        wave_valid;
    wire        mute_flag_sync;
    wire        vsync_pulse;
    // NPU top-1 class index (core_clk domain, quasi-static per window).
    wire [3:0]  npu_top1_u;

    // ==================================================================
    // DDR3 controller user side (core_clk domain)
    // ==================================================================
    // master 0: audio_sink PCM writes; master 1: NPU wdma (M2, tied off);
    // master 2: mel_engine (M1, wired below); master 3: self_test.
    wire [3:0]   ddr_cmd_valid;
    wire [36:0]  m1_cmd;          // tied off (T-M2-02 wdma alignment point)
    wire [36:0]  m2_cmd;          // mel_engine
    wire [36:0]  m3_cmd;
    wire [255:0] m1_wdata;        // tied off (T-M2-02)
    wire [255:0] m2_wdata;        // mel_engine
    wire [255:0] m3_wdata;
    wire [3:0]   ddr_wready_beat;
    wire [3:0]   ddr_rd_valid;
    wire [255:0] rd_data_0;
    wire [255:0] rd_data_1;
    wire [255:0] rd_data_2;
    wire [255:0] rd_data_3;
    wire [3:0]   ddr_done;
    // 2026-10-31: m0_done was declared but never driven. PDS only emitted
    // "Verilog-2036: Net m0_done ... has no driver, tie it to 0" and silently
    // tied it low, so audio_sink held m0_cmd_valid high forever (its FSM waits
    // for m0_done before releasing). With fixed-priority arbitration, master 0
    // then starved master 3: self_test aborted its first write after 4096
    // cycles and reported DDR3 ERR @00300000 on board.
    assign m0_done = ddr_done[0];
    // mel_engine master-2 port nets (per-master signals, packed into the
    // shared ctrl_axi buses exactly like audio_sink does for master 0)
    wire         mel_m2_cmd_valid;
    wire [36:0]  mel_m2_cmd;
    wire [255:0] mel_m2_wdata;
    wire         mel_m2_rd_ready;
    // AXI nets between ddr3_ctrl_axi and ddr3_wrapper
    wire [27:0]  axi_awaddr;
    wire         axi_awuser_ap;
    wire [3:0]   axi_awuser_id;
    wire [3:0]   axi_awlen;
    wire         axi_awvalid;
    wire         axi_awready;
    wire [255:0] axi_wdata;
    wire [31:0]  axi_wstrb;
    wire         axi_wready;
    wire [3:0]   axi_wusero_id;
    wire         axi_wusero_last;
    wire [27:0]  axi_araddr;
    wire         axi_aruser_ap;
    wire [3:0]   axi_aruser_id;
    wire [3:0]   axi_arlen;
    wire         axi_arvalid;
    wire         axi_arready;
    wire [255:0] axi_rdata;
    wire [3:0]   axi_rid;
    wire         axi_rlast;
    wire         axi_rvalid;
    // observation taps (M0: unconsumed, T-M2-07 UART exporter)
    wire [31:0]  wait_cnt_0;
    wire [31:0]  wait_cnt_1;
    wire [31:0]  wait_cnt_2;
    wire [31:0]  wait_cnt_3;
    wire [3:0]   ddr_addr_err;
    wire         ddr_to_err;
    wire [3:0]   ddr_cmd_to_err;
    wire [2:0]   ddr_dbg_to_state;
    wire [7:0]   ddr_wlast_miss_cnt;

    // ==================================================================
    // Control / debug chain (core_clk domain)
    // ==================================================================
    wire        st_start;
    wire        st_cmd_valid;
    wire        st_done;
    wire        st_fail;
    wire [27:0] st_fail_addr;
    wire        st_wready_beat;
    wire        st_rd_ready;
    wire [2:0]  dbg_line_id;
    wire [31:0] dbg_line_arg;
    wire        dbg_line_fire;
    wire        dbg_busy;
    wire        sys_run;           // observation tap (pipeline gate)
    wire        safe_err;
    wire [1:0]  stage_code;
    wire        heartbeat;
    wire        overflow_warn;
    wire [7:0]  tx_byte_data;
    wire        tx_byte_valid;
    wire        tx_byte_ready;
    wire [7:0]  rx_byte_data;
    wire        rx_byte_valid;
    wire        dbg_line_wready;   // observation tap (no text writer in M0)
    wire [15:0] uart_rx_byte_cnt;  // observation tap

    // ==================================================================
    // Module instances
    // ==================================================================

    // ---- 216 MHz audio time base (clk_nco domain reset included) ----
    audio_pll u_audio_pll (
        .clk_27m     (clk),
        .rst_n       (rst_n),
        .clk_nco     (clk_nco),
        .pll_locked  (pll_audio_locked),
        .rst_sync_nco(rst_sync_nco)
    );

    // ---- I2S clock generator (clk_nco domain) ----
    i2s_clk_gen u_i2s_clk_gen (
        .clk_nco   (clk_nco),
        .rst_n     (rst_sync_nco),
        .bck_phase (bck_phase),
        .bck_tick  (bck_tick),
        .i2s_bck   (i2s_bck),
        .i2s_lrck  (i2s_lrck)
    );

    // ---- I2S receiver (clk_nco domain, SD 2FF synchronized inside) ----
    i2s_rx u_i2s_rx (
        .clk_nco   (clk_nco),
        .rst_n     (rst_sync_nco),
        .i2s_sd    (i2s_sd),
        .bck_tick  (bck_tick),
        .bck_phase (bck_phase),
        .i2s_lrck  (i2s_lrck),
        .pcm_l     (pcm_l),
        .pcm_r     (pcm_r),
        .pcm_valid (pcm_valid),
        .sd_idle   (sd_idle)
    );

    // ---- 216 MHz -> 125 MHz stereo sample CDC FIFO ----
    audio_cdc_fifo u_audio_cdc_fifo (
        .clk_nco     (clk_nco),
        .wr_rst_n    (rst_sync_nco),
        .pcm_valid   (pcm_valid),
        .pcm_l       (pcm_l),
        .pcm_r       (pcm_r),
        .i2s_lrck    (i2s_lrck),
        .clk_core    (core_clk),
        .rd_rst_n    (core_clk_rst_n),
        .rd_en       (fifo_rd_en),
        .rd_data     (fifo_rd_data),
        .rd_valid    (fifo_rd_valid),
        .empty       (fifo_empty),
        .full        (fifo_full),
        .overflow_cnt(overflow_cnt)
    );

    // ---- PCM ring-buffer writer / DDR3 master 0 / waveform columns ----
    audio_sink u_audio_sink (
        .clk           (core_clk),
        .rst_n         (core_clk_rst_n),
        .fifo_rd_en    (fifo_rd_en),
        .fifo_rd_data  (fifo_rd_data),
        .fifo_rd_valid (fifo_rd_valid),
        .fifo_empty    (fifo_empty),
        .sd_idle       (sd_idle),
        .m0_cmd_valid  (m0_cmd_valid),
        .m0_cmd        (m0_cmd),
        .m0_wdata      (m0_wdata),
        .m0_done       (m0_done),
        .win_tick      (win_tick),
        .win_id        (win_id),
        .mute_flag     (mute_flag),
        .err_cnt       (audio_err_cnt),
        .pix_clk       (pix_clk),
        .vsync_pulse   (vsync_pulse),
        .wave_rd_addr  (wave_rd_addr),
        .wave_min      (wave_min),
        .wave_max      (wave_max),
        .wave_valid    (wave_valid),
        .mute_flag_sync(mute_flag_sync)
    );

    // ---- Mel feature engine (M1): PCM window -> log2 mel -> int8 feat ----
    // Master 2 of ddr3_ctrl_axi; starts on audio_sink win_tick (window
    // complete in DDR3). Feature export (npu_start/feat_rd_*) is the
    // T-M2 NPU alignment point - observation taps until the NPU lands.
    // Hex tables: PDS resolves $readmemh paths against the -work_dir
    // root (probe-verified in T-M1-06), so the "src/mel/..." prefix
    // form is used here (matching the fft twiddle ROM hardcodes) and
    // build_full.tcl copies src/mel/*.hex into <work_dir>/src/mel/.
    wire        mel_npu_start;
    wire        mel_feat_page;
    wire [14:0] mel_feat_rd_addr;   // NPU read request (tied 0 until M2)
    wire [7:0]  mel_feat_rd_data;
    wire        mel_done;
    wire [31:0] mel_cycles;
    wire        mel_timeout;
    wire        mel_win_miss;
    wire        mel_busy;

    mel_engine #(
        .HAN_HEX_FILE ("src/mel/hann_q15.hex"),
        .COO_HEX_FILE ("src/mel/mel_coo.hex"),
        .LUT_HEX_FILE ("src/mel/log2_lut.hex")
    ) u_mel_engine (
        .clk           (core_clk),
        .rst_n         (core_clk_rst_n),
        .win_tick      (win_tick),
        .win_id        (win_id),
        .m2_cmd_valid  (mel_m2_cmd_valid),
        .m2_cmd        (mel_m2_cmd),
        .m2_wdata      (mel_m2_wdata),
        .m2_wready     (ddr_wready_beat[2]),
        .m2_rd_valid   (ddr_rd_valid[2]),
        .m2_rd_ready   (mel_m2_rd_ready),
        .m2_rd_data    (rd_data_2),
        .m2_done       (ddr_done[2]),
        .npu_start     (mel_npu_start),
        .feat_page     (mel_feat_page),
        .feat_rd_addr  (mel_feat_rd_addr),
        .feat_rd_data  (mel_feat_rd_data),
        .mel_done      (mel_done),
        .mel_cycles    (mel_cycles),
        .mel_timeout   (mel_timeout),
        .win_miss      (mel_win_miss),
        .busy          (mel_busy)
    );

    // The NPU drives mel_feat_rd_addr and consumes the synchronous read
    // data one cycle later.

    // ---- HDMI transmitter front end (GPLL_B + I2C config + pads) ----
    hdmi_tx_if u_hdmi_tx_if (
        .clk_27m        (clk),
        .rst_n          (rst_n),
        .pix_clk        (pix_clk),
        .rst_pix_n      (rst_pix_n),
        .pix_x          (pix_x),
        .pix_y          (pix_y),
        .pix_de         (pix_de),
        .pix_hs         (pix_hs),
        .pix_vs         (pix_vs),
        .rgb_in         (ui_rgb),
        .de_in          (ui_de),
        .hs_in          (ui_hs),
        .vs_in          (ui_vs),
        .vout_clk       (vout_clk),
        .vout_de        (vout_de),
        .vout_hs        (vout_hs),
        .vout_vs        (vout_vs),
        .vout_data      (vout_data),
        .iic_tx_scl     (iic_tx_scl),
        .iic_tx_sda     (iic_tx_sda),
        .hdmi_init_over (hdmi_init_over),
        .hdmi_init_fail (hdmi_init_fail),
        .pll_lock       (hdmi_pll_lock)
    );

    // ---- UI renderer (waveform region; instantiates waveform_disp) ----
    // ---- Probability bar overlay (M3) ----
    wire [10:0] bars_x, bars_y;
    wire        bars_de;
    wire [7:0]  b0, b1, b2, b3, b4, b5, b6, b7;
    wire [23:0] bars_rgb;
    wire        bars_on;

    ui_coord_delay u_bars_delay (
        .pix_clk   (pix_clk),
        .rst_pix_n (rst_pix_n),
        .x         (pix_x),
        .y         (pix_y),
        .de        (pix_de),
        .x_d       (bars_x),
        .y_d       (bars_y),
        .de_d      (bars_de)
    );

    bars_data u_bars_data (
        .core_clk    (core_clk),
        .core_rst_n  (core_clk_rst_n),
        .probs_valid (npu_probs_valid_u),
        .probs_pct   (npu_probs_pct_u),
        .probs_idx   (npu_probs_idx_u),
        .pix_clk     (pix_clk),
        .pix_rst_n   (rst_pix_n),
        .pct0(b0), .pct1(b1), .pct2(b2), .pct3(b3),
        .pct4(b4), .pct5(b5), .pct6(b6), .pct7(b7)
    );

    bars_disp u_bars_disp (
        .pix_clk   (pix_clk),
        .rst_pix_n (rst_pix_n),
        .x         (bars_x),
        .y         (bars_y),
        .de        (bars_de),
        .pct0(b0), .pct1(b1), .pct2(b2), .pct3(b3),
        .pct4(b4), .pct5(b5), .pct6(b6), .pct7(b7),
        .rgb       (bars_rgb),
        .bars_on   (bars_on)
    );

    // ---- Class label text overlay (M3): top-1 name + percentage ----
    // top1 is quasi-static (one result per 3 s window), so a plain 2FF
    // synchronizer into the pixel domain is adequate (same argument as
    // bars_data; the frame may briefly mix old/new values, invisible at
    // 0.33 Hz).
    reg [3:0] top1_s0;
    reg [3:0] top1_s1;

    always @(posedge pix_clk or negedge rst_pix_n) begin
        if (!rst_pix_n) begin
            top1_s0 <= 4'd0;
            top1_s1 <= 4'd0;
        end else begin
            top1_s0 <= npu_top1_u;
            top1_s1 <= top1_s0;
        end
    end

    // Percentage of the top-1 class, selected from the eight latched bar
    // values already synchronized into the pixel domain by bars_data.
    reg [7:0] text_pct;
    always @* begin
        case (top1_s1)
            4'd0:    text_pct = b0;
            4'd1:    text_pct = b1;
            4'd2:    text_pct = b2;
            4'd3:    text_pct = b3;
            4'd4:    text_pct = b4;
            4'd5:    text_pct = b5;
            4'd6:    text_pct = b6;
            default: text_pct = b7;
        endcase
    end

    // One-cycle coordinate delay: text_disp already costs 2 cycles, so the
    // text layer lands on the same pixel as the 3-cycle waveform base
    // (ui_renderer samples its layers with de_pipe[2] and adds stage 4).
    reg [10:0] text_x, text_y;
    reg        text_de;

    always @(posedge pix_clk or negedge rst_pix_n) begin
        if (!rst_pix_n) begin
            text_x  <= 11'd0;
            text_y  <= 11'd0;
            text_de <= 1'b0;
        end else begin
            text_x  <= pix_x;
            text_y  <= pix_y;
            text_de <= pix_de;
        end
    end

    wire [23:0] text_rgb;
    wire        text_on;

    // 2026-10-31: text layer re-enabled.  LUT headroom was recovered by moving
    // the wdma parameter tables into a synchronous block RAM (53.57% -> 51.1%),
    // so the LUT-only part of M3 goes back in first; the spectrogram chain
    // (which costs 6.5 DRAM) follows separately.
    text_disp u_text_disp (
        .pix_clk   (pix_clk),
        .rst_pix_n (rst_pix_n),
        .pix_x     (text_x),
        .pix_y     (text_y),
        .de        (text_de),
        .class_idx ({4'd0, top1_s1}),
        .pct       (text_pct),
        .rgb       (text_rgb),
        .text_on   (text_on)
    );

    wire [14:0] npu_feat_rd_addr;
    wire [10:0] spec_x, spec_y;
    wire        spec_de;

    // ---- Mel spectrogram chain (M3): copy the window into a double page,
    // then shade it in the pixel domain ----
    wire [14:0] copy_src_addr;
    wire        copy_src_en;
    wire [14:0] copy_dst_addr;
    wire [7:0]  copy_dst_data;
    wire        copy_dst_we;
    wire        copy_dst_page;
    wire        copy_done_u;

    feat_copy_engine u_feat_copy (
        .core_clk   (core_clk),
        .core_rst_n (core_clk_rst_n),
        .start      (mel_npu_start),
        .busy_in    (npu_feat_rd_en_u),
        .src_addr   (copy_src_addr),
        .src_en     (copy_src_en),
        .src_data   (mel_feat_rd_data),
        .dst_addr   (copy_dst_addr),
        .dst_data   (copy_dst_data),
        .dst_we     (copy_dst_we),
        .dst_page   (copy_dst_page),
        .done       (copy_done_u)
    );

    // The NPU has priority on the mel feature port; the copy engine runs
    // only while the NPU is idle.
    assign mel_feat_rd_addr = npu_feat_rd_en_u ? npu_feat_rd_addr : copy_src_addr;

    wire [14:0] spec_ram_addr;
    wire [7:0]  spec_ram_data;

    feat_page_buf u_feat_page (
        .core_clk   (core_clk),
        .core_rst_n (core_clk_rst_n),
        .wr_en      (copy_dst_we),
        .wr_addr    (copy_dst_addr),
        .wr_data    (copy_dst_data),
        .wr_page    (copy_dst_page),
        .pix_clk    (pix_clk),
        .pix_rst_n  (rst_pix_n),
        .rd_addr    (spec_ram_addr),
        .rd_data    (spec_ram_data)
    );

    wire [23:0] spec_rgb;
    wire        spec_on;

    spectrum_disp u_spectrum (
        .pix_clk    (pix_clk),
        .rst_pix_n  (rst_pix_n),
        .x          (spec_x),
        .y          (spec_y),
        .de         (spec_de),
        .ram_addr   (spec_ram_addr),
        .ram_data   (spec_ram_data),
        .page_ready (1'b1),
        .rgb        (spec_rgb),
        .spec_on    (spec_on)
    );


    ui_coord_delay u_spec_delay (
        .pix_clk   (pix_clk),
        .rst_pix_n (rst_pix_n),
        .x         (pix_x),
        .y         (pix_y),
        .de        (pix_de),
        .x_d       (spec_x),
        .y_d       (spec_y),
        .de_d      (spec_de)
    );

    ui_renderer u_ui_renderer (
        .pix_clk       (pix_clk),
        .rst_pix_n     (rst_pix_n),
        .pix_x         (pix_x),
        .pix_y         (pix_y),
        .pix_de        (pix_de),
        .pix_hs        (pix_hs),
        .pix_vs        (pix_vs),
        .wave_rd_addr  (wave_rd_addr),
        .wave_min      (wave_min),
        .wave_max      (wave_max),
        .wave_valid    (wave_valid),
        .mute_flag_sync(mute_flag_sync),
        .spec_rgb      (spec_rgb),
        .spec_on       (spec_on),
        .text_rgb      (text_rgb),
        .text_on       (text_on),
        .bars_rgb      (bars_rgb),
        .bars_on       (bars_on),
        .vsync_pulse   (vsync_pulse),
        .rgb           (ui_rgb),
        .de_out        (ui_de),
        .hs_out        (ui_hs),
        .vs_out        (ui_vs)
    );

    // ---- DDR3 arbitration + IP contract adaptation ----
    wire        wl_tx_valid, wl_tx_ready;
    wire [7:0]  wl_tx_data;
    wire        wl_cmd_valid, wl_done, wl_wready;
    wire [36:0] wl_cmd;
    wire [255:0] wl_wdata;
    wire        wl_rd_ready;
    wire        weight_ok, weight_err;
    wire [27:0] wl_err_unused;
    wire [15:0] wl_cnt_unused;
    wire [31:0] wl_digest_unused;
    wire        npu_rd_cmd_valid_u;
    wire [36:0] npu_rd_cmd_u;
    wire        npu_rd_ready_u;

    // Master 1 arbitration: weight_loader owns m1 while busy, otherwise the
    // NPU weight DMA may use it. Both share the same read data bus.
    wire wl_busy;
    assign ddr_cmd_valid = {st_cmd_valid, mel_m2_cmd_valid,
                            (wl_busy ? wl_cmd_valid : npu_rd_cmd_valid_u), m0_cmd_valid};
    assign m1_cmd   = wl_busy ? wl_cmd : npu_rd_cmd_u;
    assign m1_wdata = wl_wdata;
    assign m2_cmd        = mel_m2_cmd;
    assign m2_wdata      = mel_m2_wdata;

    ddr3_ctrl_axi u_ddr3_ctrl_axi (
        .clk            (core_clk),
        .rst_n          (core_clk_rst_n),
        .cmd_valid      (ddr_cmd_valid),
        .m0_cmd         (m0_cmd),
        .m1_cmd         (m1_cmd),
        .m2_cmd         (m2_cmd),
        .m3_cmd         (m3_cmd),
        .m0_wdata       (m0_wdata),
        .m1_wdata       (m1_wdata),
        .m2_wdata       (m2_wdata),
        .m3_wdata       (m3_wdata),
        .wready_beat    (ddr_wready_beat),
        .rd_ready       ({st_rd_ready, mel_m2_rd_ready, wl_rd_ready, 1'b0}),
        .rd_data_0      (rd_data_0),
        .rd_data_1      (rd_data_1),
        .rd_data_2      (rd_data_2),
        .rd_data_3      (rd_data_3),
        .rd_valid       (ddr_rd_valid),
        .done           (ddr_done),
        .wait_cnt_0     (wait_cnt_0),
        .wait_cnt_1     (wait_cnt_1),
        .wait_cnt_2     (wait_cnt_2),
        .wait_cnt_3     (wait_cnt_3),
        .addr_err       (ddr_addr_err),
        .to_err         (ddr_to_err),
        .cmd_to_err     (ddr_cmd_to_err),
        .dbg_to_state   (ddr_dbg_to_state),
        .wlast_miss_cnt (ddr_wlast_miss_cnt),
        .axi_awaddr     (axi_awaddr),
        .axi_awuser_ap  (axi_awuser_ap),
        .axi_awuser_id  (axi_awuser_id),
        .axi_awlen      (axi_awlen),
        .axi_awvalid    (axi_awvalid),
        .axi_awready    (axi_awready),
        .axi_wdata      (axi_wdata),
        .axi_wstrb      (axi_wstrb),
        .axi_wready     (axi_wready),
        .axi_wusero_id  (axi_wusero_id),
        .axi_wusero_last(axi_wusero_last),
        .axi_araddr     (axi_araddr),
        .axi_aruser_ap  (axi_aruser_ap),
        .axi_aruser_id  (axi_aruser_id),
        .axi_arlen      (axi_arlen),
        .axi_arvalid    (axi_arvalid),
        .axi_arready    (axi_arready),
        .axi_rdata      (axi_rdata),
        .axi_rid        (axi_rid),
        .axi_rlast      (axi_rlast),
        .axi_rvalid     (axi_rvalid)
    );

    // ---- DDR3 IP shell (instance hierarchy: ddr3_wrapper.I_ips_ddr_top) ----
    ddr3_wrapper ddr3_wrapper (
        .ref_clk_p      (ref_clk_p),
        .ref_clk_n      (ref_clk_n),
        .resetn         (rst_sync_core),
        .core_clk       (core_clk),
        .core_clk_rst_n (core_clk_rst_n),
        .ddr_init_done  (ddr_init_done),
        .pll_lock       (ddr_pll_lock),
        .ddrphy_cpd_lock(ddrphy_cpd_lock),
        .axi_awaddr     (axi_awaddr),
        .axi_awuser_ap  (axi_awuser_ap),
        .axi_awuser_id  (axi_awuser_id),
        .axi_awlen      (axi_awlen),
        .axi_awvalid    (axi_awvalid),
        .axi_awready    (axi_awready),
        .axi_wdata      (axi_wdata),
        .axi_wstrb      (axi_wstrb),
        .axi_wready     (axi_wready),
        .axi_wusero_id  (axi_wusero_id),
        .axi_wusero_last(axi_wusero_last),
        .axi_araddr     (axi_araddr),
        .axi_aruser_ap  (axi_aruser_ap),
        .axi_aruser_id  (axi_aruser_id),
        .axi_arlen      (axi_arlen),
        .axi_arvalid    (axi_arvalid),
        .axi_arready    (axi_arready),
        .axi_rdata      (axi_rdata),
        .axi_rid        (axi_rid),
        .axi_rlast      (axi_rlast),
        .axi_rvalid     (axi_rvalid),
        .mem_cs_n       (mem_cs_n),
        .mem_rst_n      (mem_rst_n),
        .mem_ck         (mem_ck),
        .mem_ck_n       (mem_ck_n),
        .mem_cke        (mem_cke),
        .mem_ras_n      (mem_ras_n),
        .mem_cas_n      (mem_cas_n),
        .mem_we_n       (mem_we_n),
        .mem_odt        (mem_odt),
        .mem_a          (mem_a),
        .mem_ba         (mem_ba),
        .mem_dqs        (mem_dqs),
        .mem_dqs_n      (mem_dqs_n),
        .mem_dq         (mem_dq),
        .mem_dm         (mem_dm)
    );

    // ---- DDR3 write-read self test (master 3, self-test pattern area) ----
    // master-3 write-beat pulse (C-SELFTEST@1 F2/S1/S2).  Without this tap
    // PDS reports "Verilog-2036: Net st_wready_beat ... has no driver, tie
    // it to 0"; self_test then never sees a beat handshake and the first
    // write command aborts with st_fail at SELFTEST_BASE.
    assign st_wready_beat = ddr_wready_beat[3];

    self_test u_self_test (
        .clk          (core_clk),
        .rst_n        (core_clk_rst_n),
        .st_start     (st_start),
        .cmd_valid    (st_cmd_valid),
        .cmd          (m3_cmd),
        .wdata        (m3_wdata),
        .wready_beat  (st_wready_beat),
        .rd_ready     (st_rd_ready),
        .rd_data      (rd_data_3),
        .rd_valid     (ddr_rd_valid[3]),
        .done         (ddr_done[3]),
        .st_done      (st_done),
        .st_fail      (st_fail),
        .st_fail_addr (st_fail_addr)
    );

    // ---- System controller (boot self-test chain + LED encoding) ----

    wire weight_start_unused;

    sys_ctrl u_sys_ctrl (
        .weight_ok    (weight_ok),
        .weight_err   (weight_err),
        .weight_start (weight_start_unused),
        .clk             (core_clk),
        .rst_n           (core_clk_rst_n),
        .pll_locked      (pll_audio_locked),
        .ddrphy_cpd_lock (ddrphy_cpd_lock),
        .ddr_init_done   (ddr_init_done),
        .hdmi_init_over  (hdmi_init_over),
        .hdmi_init_fail  (hdmi_init_fail),
        .sd_idle         (sd_idle),
        .overflow_cnt    (overflow_cnt),
        .st_start        (st_start),
        .st_done         (st_done),
        .st_fail         (st_fail),
        .st_fail_addr    (st_fail_addr),
        // DDR3 AXI diagnostic taps: consumed by sys_ctrl for the
        // "DDR3 STS <hex8>" line (T21).  These nets were left dangling
        // (no consumer) until now.
        .ddr_dbg_to_state(ddr_dbg_to_state),
        .ddr_to_err      (ddr_to_err),
        .ddr_cmd_to_err  (ddr_cmd_to_err),
        .dbg_line_id     (dbg_line_id),
        .dbg_line_arg    (dbg_line_arg),
        .dbg_line_fire   (dbg_line_fire),
        .dbg_busy        (dbg_busy),
        .sys_run         (sys_run),
        .safe_err        (safe_err),
        .stage_code      (stage_code),
        .heartbeat       (heartbeat),
        .overflow_warn   (overflow_warn),
        .key1_n          (key1_n)
    );

    // ---- UART physical byte layer ----
    wire [7:0] dbg_tx_data;
    wire       dbg_tx_valid;
    wire       dbg_tx_ready;

    assign wl_tx_ready   = tx_byte_ready;
    assign dbg_tx_ready  = tx_byte_ready & ~wl_tx_valid;

    uart_tx u_uart_tx (
        .clk         (core_clk),
        .rst_n       (core_clk_rst_n),
        .byte_wdata  (wl_tx_valid ? wl_tx_data : dbg_tx_data),
        .byte_wvalid (wl_tx_valid | dbg_tx_valid),
        .byte_wready (tx_byte_ready),
        .uart_txd    (uart_tx)
    );

    uart_rx u_uart_rx (
        .clk         (core_clk),
        .rst_n       (core_clk_rst_n),
        .uart_rxd    (uart_rx),
        .byte_rdata  (rx_byte_data),
        .byte_rvalid (rx_byte_valid)
    );

    // ---- Weight loader (T-M2-01): UART frames -> DDR3 master 1 ----

    weight_loader u_weight_loader (
        .clk         (core_clk),
        .rst_n       (core_clk_rst_n),
        .rx_valid    (rx_byte_valid),
        .rx_data     (rx_byte_data),
        .tx_valid    (wl_tx_valid),
        .tx_data     (wl_tx_data),
        .tx_ready    (wl_tx_ready),
        .cmd_valid   (wl_cmd_valid),
        .cmd         (wl_cmd),
        .wdata       (wl_wdata),
        .wready_beat (ddr_wready_beat[1]),
        .done        (ddr_done[1]),
        .rd_ready    (wl_rd_ready),
        .rd_data     (rd_data_1),
        .rd_valid    (ddr_rd_valid[1]),
        .busy        (wl_busy),
        .weight_ok   (weight_ok),
        .weight_err  (weight_err),
        .err_addr    (wl_err_unused),
        .frame_cnt   (wl_cnt_unused),
        .digest      (wl_digest_unused)
    );

    // ---- NPU top (T-M2-06): instantiated but gated off until the mel
    // feat read port and m1 arbitration are finalized. Keeping the instance
    // here fixes the top-level topology and lets PDS elaborate the chain.
    wire        npu_busy_u, npu_done_u, npu_timeout_u;
    wire [31:0] npu_cycles_u;
    wire        npu_probs_valid_u;
    wire [7:0]  npu_probs_pct_u;
    wire [3:0]  npu_probs_idx_u;
    wire        npu_feat_rd_en_u;
    wire        npu_start = NPU_ENABLE ? mel_npu_start : 1'b0;

    npu_top u_npu (
        .clk          (core_clk),
        .rst_n        (core_clk_rst_n),
        .start        (npu_start),
        .busy         (npu_busy_u),
        .done         (npu_done_u),
        .npu_cycles   (npu_cycles_u),
        .timeout_flag (npu_timeout_u),
        .feat_rd_addr (npu_feat_rd_addr),
        .feat_rd_data (mel_feat_rd_data),
        .feat_rd_en   (npu_feat_rd_en_u),
        .rd_cmd_valid (npu_rd_cmd_valid_u),
        .rd_cmd       (npu_rd_cmd_u),
        .rd_ready     (wl_busy ? 1'b0 : npu_rd_ready_u),
        .rd_data      (rd_data_1),
        .rd_valid     (wl_busy ? 1'b0 : ddr_rd_valid[1]),
        .rd_done      (wl_busy ? 1'b0 : ddr_done[1]),
        .probs_valid  (npu_probs_valid_u),
        .probs_pct    (npu_probs_pct_u),
        .probs_idx    (npu_probs_idx_u),
        .top1         (npu_top1_u)
    );

    // ---- Debug line formatter (M0: status lines only, no text writer) ----
    uart_debug u_uart_debug (
        .clk            (core_clk),
        .rst_n          (core_clk_rst_n),
        .tx_byte_data   (dbg_tx_data),
        .tx_byte_valid  (dbg_tx_valid),
        .tx_byte_ready  (dbg_tx_ready),
        .rx_byte_data   (rx_byte_data),
        .rx_byte_valid  (rx_byte_valid),
        .dbg_line_wdata (8'd0),
        .dbg_line_wvalid(1'b0),
        .dbg_line_wready(dbg_line_wready),
        .dbg_line_id    (dbg_line_id),
        .dbg_line_arg   (dbg_line_arg),
        .dbg_line_fire  (dbg_line_fire),
        .dbg_busy       (dbg_busy),
        .rx_byte_cnt    (uart_rx_byte_cnt)
    );

    // ==================================================================
    // LED assembly (design doc section 2.2.9 / sys_ctrl contract):
    //   led[7:6] self-test stage code
    //   led[5]   CDC FIFO overflow warning (sticky)
    //   led[4]   SAFE_ERR latched state
    //   led[3:1] reserved for the M2 stats exporter
    //   led[0]   1 Hz heartbeat (active after RUN)
    // ==================================================================
    assign led = {stage_code, overflow_warn, safe_err, 3'b000, heartbeat};

endmodule
