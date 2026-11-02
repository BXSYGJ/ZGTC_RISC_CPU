// -----------------------------------------------------------------------------
// File    : hdmi_tx_if.v
// Module  : hdmi_tx_if
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : HDMI transmit path integration layer (T-M0-07).
//
//           Integrates the vendor ADDA-HDMI demo assets unchanged (R-05):
//             * pll        (ipcore/pll, GPLL_B): 27 MHz -> pix_clk 148.5 MHz
//                          + cfg_clk 10 MHz, copied verbatim from the demo
//                          ipcore directory (see reports/asset_trace.md).
//             * ms72xx_ctl (src/hdmi/ms72xx_ctl.v): I2C register sequence for
//                          the HDMI transmitter chip, pins K22/K23, running
//                          on cfg_clk exactly as in demo hdmi_test.v.
//             * sync_vg    (src/hdmi/sync_vg.v): 1080p@60 video timing
//                          generator (H_TOTAL=2200 / V_TOTAL=1125 /
//                          H_ACT=1920 / V_ACT=1080), running on pix_clk.
//
//           This module is the NEW integration layer only. The five demo
//           files are kept bit-identical (module names and ports unchanged);
//           all glue logic (reset tree, watchdog, pin registers) lives here.
//
// References:
//   * design.md section 7.1  (video path reuse, REQ-UI-001)
//   * design.md section 1.2  (clock tree: GPLL_B 27->148.5/10 MHz)
//   * design.md section 1.3  (reset tree: rst_sync_pix / rst_sync_cfg)
//   * design.md section 2.2.8 (ui_renderer / hdmi_tx_if contract)
//   * spec.md   section 5.5.3 scenario 1 (init_over timeout retry)
//
// Clocking / reset summary (all resets: asynchronous assert, synchronous
// release per REQ-SYS-002):
//   cfg_clk domain (10 MHz):
//     rst_n (KEY0) -> 2-flop sync -> rstn_1ms counter (demo logic, 10000
//     cycles = 1 ms, gated by pll_lock) -> cfg_rstn -> ms72xx_ctl.
//   pix_clk domain (148.5 MHz):
//     cfg_rstn -> 2-flop sync -> rstn_pix -> sync_vg + pin output registers.
//     rst_pix_n is exported so ui_renderer shares the same pixel reset.
//
// init_over watchdog (spec 5.5.3 scenario 1):
//   ms72xx_ctl needs ~330 ms nominally (1 ms rstn_1ms + ~5 ms I2C sequence +
//   320 ms internal WAIT delay at 10 MHz + ~3 ms setting phase). If init_over
//   is not asserted within INIT_TIMEOUT_CYCLES (500 ms, ~50% margin over the
//   nominal demo sequence), ms72xx_ctl is reset for RETRY_HOLD_CYCLES (2 ms)
//   and the sequence is restarted. After INIT_RETRY_MAX retries the latched
//   hdmi_init_fail flag is raised for sys_ctrl (LED/UART error path); the
//   audio->inference pipeline keeps running (spec 5.5.3 scenario 1.b).
//   Worst case completion time = 4 x 500 ms + 3 x 2 ms ~= 2.006 s, which the
//   sys_ctrl HDMI_I2C_CFG stage watchdog budget must exceed.
//
// CDC notes: rgb_in / de_in / hs_in / vs_in are pix_clk-domain signals
// produced by ui_renderer (it runs directly on pix_clk, design.md section
// 1.4 - no clock crossing for pixel data). hdmi_init_over / hdmi_init_fail
// / pll_lock are quasi-static status outputs; the consumer (sys_ctrl,
// 125 MHz core domain) synchronizes them with its own 2-flop synchronizer.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module hdmi_tx_if #(
    // 1080p@60 timing, values copied from demo hdmi_test.v / ad_da_hdmi_top.v
    // (CEA-861 style: sync at line/frame start, then back porch, then active).
    parameter [11:0] V_TOTAL = 12'd1125,
    parameter [11:0] V_FP    = 12'd4,
    parameter [11:0] V_BP    = 12'd36,
    parameter [11:0] V_SYNC  = 12'd5,
    parameter [11:0] V_ACT   = 12'd1080,
    parameter [11:0] H_TOTAL = 12'd2200,
    parameter [11:0] H_FP    = 12'd88,
    parameter [11:0] H_BP    = 12'd148,
    parameter [11:0] H_SYNC  = 12'd44,
    parameter [11:0] H_ACT   = 12'd1920,
    // Release delay of the demo reset counter: 16'h2710 = 10000 cfg_clk
    // cycles at 10 MHz = 1 ms (demo hdmi_test.v "rstn_1ms" logic, kept as-is).
    parameter [15:0] RSTN_DELAY_CYCLES   = 16'd10_000,
    // I2C init watchdog (cfg_clk cycles at 10 MHz, spec 5.5.3 scenario 1):
    // nominal demo sequence is ~330 ms, timeout budget 500 ms.
    parameter [22:0] INIT_TIMEOUT_CYCLES = 23'd5_000_000,
    // Hold time of the ms72xx_ctl retry reset pulse (2 ms at 10 MHz).
    parameter [15:0] RETRY_HOLD_CYCLES   = 16'd20_000,
    // Maximum number of retry attempts before latching hdmi_init_fail
    // (total attempts = 1 initial + INIT_RETRY_MAX retries).
    parameter [2:0]  INIT_RETRY_MAX      = 3'd3
) (
    // Board 27 MHz crystal (pin D18), reference input of GPLL_B.
    input  wire        clk_27m,
    // Asynchronous board reset (KEY0, pin C22, active low).
    input  wire        rst_n,

    // -----------------------------------------------------------------
    // Pixel clock domain (148.5 MHz) - timing outputs for ui_renderer.
    // -----------------------------------------------------------------
    output wire        pix_clk,      // GPLL_B clkout0
    output wire        rst_pix_n,    // pixel-domain reset, synchronous release
    output wire [10:0] pix_x,        // active pixel column (0..1919)
    output wire [10:0] pix_y,        // active pixel row (0..1079)
    output wire        pix_de,       // active data enable
    output wire        pix_hs,       // horizontal sync
    output wire        pix_vs,       // vertical sync (frame start)

    // -----------------------------------------------------------------
    // Rendered video from ui_renderer (pix_clk domain). ui_renderer
    // already compensates its internal 3-stage pixel pipeline, so
    // rgb_in / de_in / hs_in / vs_in are mutually aligned (design.md
    // section 7.7). This layer only adds one IO output register stage.
    // -----------------------------------------------------------------
    input  wire [23:0] rgb_in,
    input  wire        de_in,
    input  wire        hs_in,
    input  wire        vs_in,

    // -----------------------------------------------------------------
    // HDMI connector pins (demo fdc pinout, LVCMOS33).
    // -----------------------------------------------------------------
    output wire        hdmi_rst_n,   // pin G25, board MS7210/MS7200 reset
    output wire        vout_clk,     // pin T24 (directly driven by pix_clk)
    output wire        vout_de,      // pin N19
    output wire        vout_hs,      // pin R20
    output wire        vout_vs,      // pin R21
    output wire [23:0] vout_data,    // 24-bit parallel RGB (demo fdc pins)
    output wire        iic_tx_scl,   // pin K22, HDMI transmitter I2C clock
    inout  wire        iic_tx_sda,   // pin K23, HDMI transmitter I2C data

    // -----------------------------------------------------------------
    // Status outputs (quasi-static, consumer-side synchronizer required).
    // -----------------------------------------------------------------
    output wire        hdmi_init_over, // I2C config done (cfg_clk domain)
    output wire        hdmi_init_fail, // watchdog retries exhausted (latched)
    output wire        pll_lock        // GPLL_B lock status
);

    // -----------------------------------------------------------------
    // GPLL_B instantiation - copied verbatim from demo hdmi_test.v.
    // The wrapper module "pll" is the demo IP generation output
    // (ipcore/pll/pll.v, GTP_GPLL primitive, CLKIN_FREQ=27.0,
    // clkout0 = 148.5 MHz, clkout1 = 10 MHz).
    // -----------------------------------------------------------------
    wire pix_clk_w;
    wire cfg_clk;
    wire pll_lock_w;

    pll u_pll (
        .clkin1  ( clk_27m   ),  // input, 27 MHz board clock
        .clkout0 ( pix_clk_w ),  // output, 148.5 MHz pixel clock
        .clkout1 ( cfg_clk   ),  // output, 10 MHz config clock
        .lock    ( pll_lock_w)   // output, GPLL locked
    );

    assign pix_clk  = pix_clk_w;
    assign pll_lock = pll_lock_w;

    // =================================================================
    // cfg_clk domain (10 MHz): reset tree + I2C controller
    // =================================================================

    // -----------------------------------------------------------------
    // Two-flop synchronizer of the external asynchronous reset into the
    // cfg_clk domain (asynchronous assert, synchronous release).
    // -----------------------------------------------------------------
    reg rst_n_meta;
    reg rst_n_cfg;

    always @(posedge cfg_clk or negedge rst_n) begin
        if (!rst_n) begin
            rst_n_meta <= 1'b0;
            rst_n_cfg  <= 1'b0;
        end else begin
            rst_n_meta <= 1'b1;
            rst_n_cfg  <= rst_n_meta;
        end
    end

    // -----------------------------------------------------------------
    // Two-flop synchronizer of the GPLL lock flag (quasi-static signal,
    // sampled in the cfg_clk domain; demo sampled it directly, the extra
    // flop pair removes any residual metastability risk).
    // -----------------------------------------------------------------
    reg pll_lock_meta;
    reg pll_lock_cfg;

    always @(posedge cfg_clk) begin
        pll_lock_meta <= pll_lock_w;
        pll_lock_cfg  <= pll_lock_meta;
    end

    // -----------------------------------------------------------------
    // Release delay counter - demo "rstn_1ms" logic kept bit-compatible:
    // count 10000 cfg_clk cycles (1 ms at 10 MHz) after the PLL is locked
    // and the board reset is released, then hold. This guarantees the GPLL
    // output clocks are stable before the I2C sequence starts.
    // -----------------------------------------------------------------
    reg [15:0] rstn_1ms;

    always @(posedge cfg_clk) begin
        if (!pll_lock_cfg || !rst_n_cfg)
            rstn_1ms <= 16'd0;
        else if (rstn_1ms == RSTN_DELAY_CYCLES)
            rstn_1ms <= rstn_1ms;             // hold (demo behaviour)
        else
            rstn_1ms <= rstn_1ms + 16'd1;
    end

    wire cfg_rstn = (rstn_1ms == RSTN_DELAY_CYCLES);
    // Restore the physical transmitter reset driven by the vendor demo.
    assign hdmi_rst_n = cfg_rstn;

    // -----------------------------------------------------------------
    // I2C init watchdog (spec section 5.5.3 scenario 1).
    //
    //   watch phase  (retry_rstn = 1): init_wdt_cnt counts while the I2C
    //                               sequence is running. Reaching the 500 ms
    //                               budget either starts a retry (reset the
    //                               controller) or, when the retry budget is
    //                               spent, latches init_fail.
    //   retry phase  (retry_rstn = 0): ms72xx_ctl is held in reset for 2 ms,
    //                               then the watch phase restarts cleanly.
    //
    // init_over is a registered output of ms72xx_ctl and drops during the
    // retry reset, so the watchdog always restarts from a clean slate.
    // -----------------------------------------------------------------
    reg [22:0] init_wdt_cnt;
    reg [15:0] retry_hold_cnt;
    reg [2:0]  init_retry_cnt;
    reg        retry_rstn;
    reg        init_fail;
    wire       init_over;

    always @(posedge cfg_clk or negedge cfg_rstn) begin
        if (!cfg_rstn) begin
            init_wdt_cnt   <= 23'd0;
            retry_hold_cnt <= 16'd0;
            init_retry_cnt <= 3'd0;
            retry_rstn     <= 1'b1;
            init_fail      <= 1'b0;
        end else if (!retry_rstn) begin
            // Retry phase: ms72xx_ctl held in reset.
            if (retry_hold_cnt == RETRY_HOLD_CYCLES - 16'd1) begin
                retry_rstn     <= 1'b1;
                retry_hold_cnt <= 16'd0;
                init_wdt_cnt   <= 23'd0;
            end else begin
                retry_hold_cnt <= retry_hold_cnt + 16'd1;
            end
        end else if (init_over || init_fail) begin
            // Success, or permanent failure already latched: stop watching.
            init_wdt_cnt <= 23'd0;
        end else begin
            // Watch phase: count while the config sequence is still running.
            if (init_wdt_cnt == INIT_TIMEOUT_CYCLES - 23'd1) begin
                init_wdt_cnt <= 23'd0;
                if (init_retry_cnt == INIT_RETRY_MAX) begin
                    init_fail <= 1'b1;          // give up, sys_ctrl reports it
                end else begin
                    init_retry_cnt <= init_retry_cnt + 3'd1;
                    retry_rstn     <= 1'b0;     // start retry reset pulse
                end
            end else begin
                init_wdt_cnt <= init_wdt_cnt + 23'd1;
            end
        end
    end

    // -----------------------------------------------------------------
    // ms72xx_ctl instantiation - demo hdmi_test.v wiring kept verbatim
    // (clk = cfg_clk, I2C pins straight through). The only delta is the
    // reset source: cfg_rstn ANDed with the watchdog retry pulse so the
    // I2C sequence can be restarted without disturbing the video timing.
    // -----------------------------------------------------------------
    wire ms_rstn = cfg_rstn & retry_rstn;
    wire init_over_rx_unused;   // constant '1' in the demo, left unobserved

    ms72xx_ctl u_ms72xx_ctl (
        .clk         ( cfg_clk   ),  // input, 10 MHz config clock
        .rst_n       ( ms_rstn   ),  // input, cfg_rstn & ~retry_hold
        .init_over_rx ( init_over_rx_unused ), // output, unused in demo too
        .init_over   ( init_over ),  // output, I2C sequence done
        .iic_scl     ( iic_tx_scl),  // output, pin K22
        .iic_sda     ( iic_tx_sda)   // inout,  pin K23
    );

    assign hdmi_init_over = init_over;
    assign hdmi_init_fail = init_fail;

    // =================================================================
    // pix_clk domain (148.5 MHz): video timing + pin output registers
    // =================================================================

    // -----------------------------------------------------------------
    // Pixel-domain reset: two-flop synchronizer of cfg_rstn. cfg_rstn is
    // already a synchronous, quasi-static signal in the cfg_clk domain
    // (asserted within 3 cfg cycles after KEY0 or lock loss), so this
    // completes the "asynchronous assert, synchronous release" chain of
    // design.md section 1.3 for the pixel domain. demo hdmi_test.v fed
    // the cfg-domain rstn_out straight into sync_vg; the synchronizer is
    // a safety-only delta (sync_vg itself stays untouched).
    // -----------------------------------------------------------------
    reg rstn_pix_meta;
    reg rstn_pix;

    always @(posedge pix_clk_w) begin
        rstn_pix_meta <= cfg_rstn;
        rstn_pix      <= rstn_pix_meta;
    end

    assign rst_pix_n = rstn_pix;

    // -----------------------------------------------------------------
    // sync_vg instantiation - 1080p@60 parameters from demo hdmi_test.v.
    // x_act / y_act are 12-bit demo coordinates; the exported pix_x /
    // pix_y are truncated to 11 bits (1920 and 1080 both fit in 11 bits).
    // -----------------------------------------------------------------
    wire [11:0] act_x;
    wire [11:0] act_y;
    wire        vg_hs;
    wire        vg_vs;
    wire        vg_de;

    sync_vg #(
        .X_BITS  ( 12      ),
        .Y_BITS  ( 12      ),
        .V_TOTAL ( V_TOTAL ),
        .V_FP    ( V_FP    ),
        .V_BP    ( V_BP    ),
        .V_SYNC  ( V_SYNC  ),
        .V_ACT   ( V_ACT   ),
        .H_TOTAL ( H_TOTAL ),
        .H_FP    ( H_FP    ),
        .H_BP    ( H_BP    ),
        .H_SYNC  ( H_SYNC  ),
        .H_ACT   ( H_ACT   )
    ) u_sync_vg (
        .clk    ( pix_clk_w ),  // input, 148.5 MHz
        .rstn   ( rstn_pix  ),  // input, pixel-domain reset
        .vs_out ( vg_vs     ),  // output reg, vertical sync
        .hs_out ( vg_hs     ),  // output reg, horizontal sync
        .de_out ( vg_de     ),  // output reg, active data enable
        .x_act  ( act_x     ),  // output reg [11:0], active column
        .y_act  ( act_y     )   // output reg [11:0], active row
    );

    assign pix_x  = act_x[10:0];
    assign pix_y  = act_y[10:0];
    assign pix_de = vg_de;
    assign pix_hs = vg_hs;
    assign pix_vs = vg_vs;

    // -----------------------------------------------------------------
    // HDMI pin output registers: one pipeline stage for the (mutually
    // aligned) ui_renderer outputs, so the IO registers see fully
    // registered data/enable/sync signals, exactly like the demo whose
    // vout_* pins were also driven by module-internal registers. During
    // reset the outputs force a black, blanked video stream.
    // -----------------------------------------------------------------
    reg [23:0] vout_data_r;
    reg        vout_hs_r;
    reg        vout_vs_r;
    reg        vout_de_r;

    always @(posedge pix_clk_w) begin
        if (!rstn_pix) begin
            vout_data_r <= 24'h00_00_00;
            vout_hs_r   <= 1'b0;
            vout_vs_r   <= 1'b0;
            vout_de_r   <= 1'b0;
        end else begin
            vout_data_r <= rgb_in;
            vout_hs_r   <= hs_in;
            vout_vs_r   <= vs_in;
            vout_de_r   <= de_in;
        end
    end

    assign vout_data = vout_data_r;
    assign vout_hs   = vout_hs_r;
    assign vout_vs   = vout_vs_r;
    assign vout_de   = vout_de_r;
    assign vout_clk  = pix_clk_w;   // demo wiring: pixel clock straight out

endmodule