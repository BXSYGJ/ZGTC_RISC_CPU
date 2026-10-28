// -----------------------------------------------------------------------------
// sys_ctrl - system control, M0 simplified version (tasks.md T-M0-09,
//            design.md Sec. 2.2.9 / Sec. 1.3 reset tree, REQ-REL-001
//            skeleton, REQ-SYS-002/003/004, REQ-REL-002 subset)
// -----------------------------------------------------------------------------
// Self-test chain state machine (design.md Sec. 1.3):
//   BOOT -> PLL_WAIT -> DDR_TEST -> DDR_WAIT -> RUN
// Any stage timeout or failure enters SAFE_ERR (halt + LED error code +
// UART error line; downstream pipeline gates stay closed, REQ-REL-001
// skeleton). The M2/M3 stages WEIGHT_LOAD_SHA and window scheduling are
// intentionally NOT in this M0 version.
//
// Stage line prints via uart_debug predefined lines (Zheng's module,
// dbg_line_id: 0=BOOT 1=PLL LOCK ERR 2=DDR3 SELFTEST... 3=DDROK
// 4=DDR3 ERR @<hex32>):
//   BOOT      : id 0 "INSTREC BOOT\n"
//   PLL_WAIT  : (silent; timeout -> id 1 "PLL LOCK ERR\n" + SAFE_ERR)
//   DDR_TEST  : id 2 "DDR3 SELFTEST...\n"
//   DDR_WAIT  : pass -> id 3 "DDROK\n"; fail -> id 4 with
//               dbg_line_arg = st_fail_addr (zero-extended)
//   RUN       : sys_run=1 gates the downstream pipeline
//
// Watchdog budgets (2x worst-case margins, REQ-REL-002 subset):
//   PLL_WAIT  : audio_pll lock (<1 ms typ) + DDR3 PHY lock + init
//               (<500 ms per Pango IP spec) + HDMI I2C config with
//               internal 500 ms x 3 retries (worst 2.006 s, Feng's
//               hdmi_tx_if) -> budget 5 s > 2 x 2.01 s.
//   DDR_WAIT  : self_test 4 KB pattern run takes a few ms (16 x 512 B
//               bursts) -> budget 100 ms.
//   PLL/HDMI lock inputs are quasi-static status signals crossing into
//   core_clk: two-stage synchronizers (CDC points marked CDC below).
//
// LED encoding (M0 version, REQ-MNT-003 subset):
//   led[0] heartbeat 1 Hz after RUN (blinking 0.5 s on/off)
//   led[1] sys_run
//   led[2] ddr_ok (self-test passed)
//   led[3] hdmi_init_over
//   led[4] audio activity (~sd_idle, nco-domain input, 2FF synced CDC)
//   led[5] audio FIFO overflow warning (overflow_cnt != 0, latched)
//   led[7:6] self-test stage code: 00 BOOT, 01 PLL, 10 DDR, 11 RUN
//   (M3 extends to led[7:4] error code encoding, design.md Sec. 2.2.9)
//
// KEY semantics:
//   KEY0 (C22): asynchronous board reset (external, wired to the reset
//               tree at the top level, REQ-SYS-002).
//   KEY1 (C23): two-stage synchronizer + 20 ms debounce; in RUN state
//               it re-triggers the DDR self-test (useful for T0.2
//               first-error injection); in other states it is ignored.
//
// Reset tree consumption (design.md Sec. 1.3): this module runs in the
// core_clk domain and is reset by core_clk_rst_n (the DDR3 IP output
// sync-released reset). The asynchronous KEY0 net and the lock inputs
// enter only through synchronizers.
// -----------------------------------------------------------------------------
module sys_ctrl #(
    // Watchdog budgets in core_clk cycles (125 MHz).
    parameter integer PLL_TIMEOUT_CYCLES = 125000000 * 5,   // 5 s
    parameter integer DDR_TIMEOUT_CYCLES = 12500000,        // 100 ms
    // 0 = legacy M1 chain (no weight loader); set to 1 once the loader is
    // wired into instrec_top and npu_top consumes the weights.
    parameter REQUIRE_WEIGHT = 0
) (
    input  wire        clk,              // core_clk 125 MHz
    input  wire        rst_n,            // core_clk_rst_n (IP output)
    // status inputs (quasi-static, CDC: 2FF synchronizers inside)
    input  wire        pll_locked,       // audio_pll lock (nco domain)
    input  wire        ddrphy_cpd_lock,  // DDR3 PHY CPD lock (IP)
    input  wire        ddr_init_done,    // DDR3 init done (IP)
    input  wire        hdmi_init_over,   // HDMI I2C config done (cfg)
    input  wire        hdmi_init_fail,   // HDMI retries exhausted (cfg)
    input  wire        sd_idle,          // I2S idle flag (nco domain)
    input  wire [15:0] overflow_cnt,     // audio CDC FIFO overflow count
    // weight-loader self-test ring (REQ-REL-001 stage 4)
    input  wire        weight_ok,
    input  wire        weight_err,
    output reg         weight_start,
    // self_test control/status
    output reg         st_start,         // one-cycle start request
    input  wire        st_done,          // self-test pass
    input  wire        st_fail,          // self-test fail
    input  wire [27:0] st_fail_addr,     // first failing byte address
    // uart_debug predefined line channel
    output reg  [2:0]  dbg_line_id,
    output reg  [31:0] dbg_line_arg,
    output reg         dbg_line_fire,
    input  wire        dbg_busy,
    // system status outputs
    output reg         sys_run,          // pipeline gate (audio_sink/mel)
    output wire        safe_err,         // SAFE_ERR latched state
    output wire [1:0]  stage_code,       // self-test stage for LED[7:6]
    // heartbeat and LED raw bits (top level assembles led[7:0])
    output reg         heartbeat,        // 1 Hz blink, active after RUN
    output reg         overflow_warn,    // LED[5]: audio CDC FIFO had an
                                         // overflow since reset (sticky
                                         // until board reset)
    // KEY1 (C23), asynchronous active-low input
    input  wire        key1_n
);

    // ------------------------------------------------------------------
    // CDC: two-stage synchronizers for quasi-static status inputs.
    // ------------------------------------------------------------------
    reg pll_locked_m, pll_locked_s;
    reg ddrphy_lock_m, ddrphy_lock_s;
    reg ddr_init_m, ddr_init_s;
    reg hdmi_over_m, hdmi_over_s;
    reg hdmi_fail_m, hdmi_fail_s;
    reg sd_idle_m, sd_idle_s;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pll_locked_m <= 1'b0;
            pll_locked_s <= 1'b0;
            ddrphy_lock_m <= 1'b0;
            ddrphy_lock_s <= 1'b0;
            ddr_init_m    <= 1'b0;
            ddr_init_s    <= 1'b0;
            hdmi_over_m   <= 1'b0;
            hdmi_over_s   <= 1'b0;
            hdmi_fail_m   <= 1'b0;
            hdmi_fail_s   <= 1'b0;
            sd_idle_m     <= 1'b1;
            sd_idle_s     <= 1'b1;
        end else begin
            pll_locked_m <= pll_locked;
            pll_locked_s <= pll_locked_m;
            ddrphy_lock_m <= ddrphy_cpd_lock;
            ddrphy_lock_s <= ddrphy_lock_m;
            ddr_init_m    <= ddr_init_done;
            ddr_init_s    <= ddr_init_m;
            hdmi_over_m   <= hdmi_init_over;
            hdmi_over_s   <= hdmi_over_m;
            hdmi_fail_m   <= hdmi_init_fail;
            hdmi_fail_s   <= hdmi_fail_m;
            sd_idle_m     <= sd_idle;
            sd_idle_s     <= sd_idle_m;
        end
    end

    // ------------------------------------------------------------------
    // KEY1: two-stage sync + 20 ms debounce -> single-cycle press pulse.
    // ------------------------------------------------------------------
    reg key1_m, key1_s, key1_stable, key1_prev;
    reg [23:0] key1_cnt;

    wire key1_press = key1_prev & ~key1_stable;   // falling edge = press

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            key1_m      <= 1'b1;
            key1_s      <= 1'b1;
            key1_stable <= 1'b1;
            key1_prev   <= 1'b1;
            key1_cnt    <= 24'd0;
        end else begin
            key1_m <= key1_n;
            key1_s <= key1_m;
            key1_prev <= key1_stable;
            if (key1_s != key1_stable) begin
                if (key1_cnt == 24'd2500000) begin   // 20 ms at 125 MHz
                    key1_stable <= key1_s;
                    key1_cnt    <= 24'd0;
                end else begin
                    key1_cnt <= key1_cnt + 24'd1;
                end
            end else begin
                key1_cnt <= 24'd0;
            end
        end
    end

    // ------------------------------------------------------------------
    // Self-test chain FSM.
    // ------------------------------------------------------------------
    localparam [2:0] ST_BOOT    = 3'd0;
    localparam [2:0] ST_PLL     = 3'd1;
    localparam [2:0] ST_DDR     = 3'd2;
    localparam [2:0] ST_DDW     = 3'd3;
    localparam [2:0] ST_RUN     = 3'd4;
    localparam [2:0] ST_SAFEERR = 3'd5;
    localparam [2:0] ST_WEIGHT  = 3'd6;

    reg [2:0]  state;
    reg [31:0] timeout_cnt;
    reg        err_latch;      // SAFE_ERR latch
    reg        started;        // guards ST_DDW against a stale st_done
                              // from a previous self-test round: on a
                              // KEY1 re-trigger, self_test clears its
                              // flags one cycle after st_start, so the
                              // first ST_DDW cycle is skipped

    assign safe_err   = err_latch;
    assign stage_code = (state == ST_BOOT)              ? 2'd00 :
                        (state == ST_PLL)               ? 2'd01 :
                        (state == ST_DDR || state == ST_DDW ||
                         state == ST_WEIGHT)            ? 2'd10 :
                        (state == ST_RUN)               ? 2'd11 : 2'd11;

    // pll_all: all lock/init conditions for the PLL stage.
    wire pll_all = pll_locked_s & ddrphy_lock_s & ddr_init_s &
                   hdmi_over_s & ~hdmi_fail_s;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= ST_BOOT;
            timeout_cnt  <= 32'd0;
            err_latch    <= 1'b0;
            started      <= 1'b0;
            st_start     <= 1'b0;
            sys_run      <= 1'b0;
            dbg_line_id  <= 3'd0;
            dbg_line_arg <= 32'd0;
            dbg_line_fire <= 1'b0;
        end else begin
            // Default: single-cycle pulses.
            st_start      <= 1'b0;
            dbg_line_fire <= 1'b0;

            case (state)
                ST_BOOT: begin
                    // Print the boot line once the printer is free.
                    if (!dbg_busy) begin
                        dbg_line_id   <= 3'd0;    // "INSTREC BOOT\n"
                        dbg_line_fire <= 1'b1;
                        state         <= ST_PLL;
                        timeout_cnt   <= 32'd0;
                    end
                end

                ST_PLL: begin
                    // Wait for all locks. HDMI init fail is an
                    // immediate error (no point waiting the timeout).
                    if (hdmi_fail_s) begin
                        dbg_line_id   <= 3'd1;    // "PLL LOCK ERR\n"
                        dbg_line_fire <= 1'b1;
                        err_latch     <= 1'b1;
                        state         <= ST_SAFEERR;
                    end else if (pll_all) begin
                        timeout_cnt <= 32'd0;
                        state       <= ST_DDR;
                    end else if (timeout_cnt >= PLL_TIMEOUT_CYCLES) begin
                        dbg_line_id   <= 3'd1;    // "PLL LOCK ERR\n"
                        dbg_line_fire <= 1'b1;
                        err_latch     <= 1'b1;
                        state         <= ST_SAFEERR;
                    end else begin
                        timeout_cnt <= timeout_cnt + 32'd1;
                    end
                end

                ST_DDR: begin
                    // Kick the DDR self-test.
                    if (!dbg_busy) begin
                        dbg_line_id   <= 3'd2;    // "DDR3 SELFTEST...\n"
                        dbg_line_fire <= 1'b1;
                        st_start      <= 1'b1;
                        timeout_cnt   <= 32'd0;
                        started       <= 1'b0;
                        state         <= ST_DDW;
                    end
                end

                ST_DDW: begin
                    if (!started) begin
                        // Skip one cycle: self_test clears its stale
                        // st_done/st_fail on the st_start edge, visible
                        // to this block one cycle later.
                        started <= 1'b1;
                    end else if (st_done) begin
                        dbg_line_id   <= 3'd3;    // "DDROK\n"
                        dbg_line_fire <= 1'b1;
                        state         <= ST_RUN;
                        sys_run       <= 1'b1;
                    end else if (st_fail) begin
                        dbg_line_id   <= 3'd4;    // "DDR3 ERR @<hex>\n"
                        dbg_line_arg  <= {4'd0, st_fail_addr};
                        dbg_line_fire <= 1'b1;
                        err_latch     <= 1'b1;
                        state         <= ST_SAFEERR;
                    end else if (timeout_cnt >= DDR_TIMEOUT_CYCLES) begin
                        dbg_line_id   <= 3'd4;    // timeout reported as err
                        dbg_line_arg  <= 32'hFFFF_FFFF;
                        dbg_line_fire <= 1'b1;
                        err_latch     <= 1'b1;
                        state         <= ST_SAFEERR;
                    end else begin
                        timeout_cnt <= timeout_cnt + 32'd1;
                    end
                end

                ST_WEIGHT: begin
                    // Wait for weight_loader's final read-back digest check.
                    weight_start <= 1'b1;
                    if (weight_ok) begin
                        weight_start <= 1'b0;
                        state        <= ST_RUN;
                        sys_run      <= 1'b1;
                    end else if (weight_err) begin
                        weight_start <= 1'b0;
                        err_latch    <= 1'b1;
                        state        <= ST_SAFEERR;
                    end
                end

                ST_RUN: begin
                    // Normal operation. KEY1 re-triggers the DDR
                    // self-test (T0.2 first-error injection path).
                    if (key1_press) begin
                        sys_run <= 1'b0;
                        state   <= ST_DDR;
                    end
                end

                ST_SAFEERR: begin
                    // Halt forever (KEY0 board reset is the only exit,
                    // REQ-REL-001 skeleton; watchdog-retry logic is an
                    // M3 extension, REQ-REL-002 full version).
                    state <= ST_SAFEERR;
                end

                default: state <= ST_BOOT;
            endcase
        end
    end

    // ------------------------------------------------------------------
    // Audio CDC FIFO overflow warning: sticky once any overflow has
    // been counted (overflow_cnt is a core-domain counter in the FIFO
    // read domain, same core_clk -> no synchronizer needed).
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            overflow_warn <= 1'b0;
        end else if (overflow_cnt != 16'd0) begin
            overflow_warn <= 1'b1;
        end
    end

    // ------------------------------------------------------------------
    // Heartbeat: 1 Hz blink (0.5 s on / 0.5 s off), active after RUN.
    // 125e6 / 2 = 62.5e6 -> 26-bit counter (2^26 = 67.1e6 > 62.5e6).
    // ------------------------------------------------------------------
    reg [25:0] hb_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hb_cnt     <= 26'd0;
            heartbeat  <= 1'b0;
        end else begin
            if (hb_cnt == 26'd62499999) begin
                hb_cnt    <= 26'd0;
                heartbeat <= ~heartbeat;
            end else begin
                hb_cnt <= hb_cnt + 26'd1;
            end
        end
    end

endmodule