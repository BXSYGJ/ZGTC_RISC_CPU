// -----------------------------------------------------------------------------
// File    : top_i2s_capture.v
// Module  : top_i2s_capture
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Board-level real-input I2S capture top (pre-resampler tap).
//
//           Captures raw 48 kHz Philips-I2S stereo input from the PCM1808
//           module (BCK 3.072 MHz, LRCK 48 kHz, 24 significant bits in
//           32-bit slots, MSB delayed one BCK after the LRCK edge) into
//           DDR3 at base 0x0000_0000, and exports it over UART for PC-side
//           golden comparison (board-input evidence for the collapse-point
//           investigation). The capture point sits BEFORE the FIR resampler,
//           pinning "I2S reception" and "FIR resampling" into separate
//           layers.
//
//           Sample format: one 32-bit word per stereo frame =
//           {R[15:0], L[15:0]} (top 16 bits of each 24-bit channel). In
//           little-endian byte order this is L_lo L_hi R_lo R_hi, i.e. the
//           exact stereo 16-bit WAV byte layout, so the exported dump can be
//           written straight into a .wav and consumed by
//           golden_pipeline.load_pcm_s16 (stereo auto-downmix, zero change).
//
// Structure (assembly copied from top_ddr3_diag, the minimal DDR3 top):
//   * ddr3_wrapper  : DDR3 hard IP shell (instance name is part of the
//                     generated clock constraint contract), 125 MHz
//                     core_clk + core_clk_rst_n + ddr_init_done outputs.
//   * ddr3_ctrl_axi : single controller, design configuration
//                     (AXI_USER_AP=1, DUMMY_WSTRB_ALL1=0), master 0 owned
//                     by the capture controller, masters 1..3 tied off.
//   * i2s_slave_rx  : PCM1808 slave receiver oversampled at 27 MHz (same
//                     wiring as top_pcm1808_probe), TIMEOUT_CYCLES=27000.
//   * CDC           : 16 x 32 bit Gray-coded dual-clock FIFO, write side
//                     27 MHz (board crystal domain), read side 125 MHz
//                     core domain. A dedicated FIFO is required because
//                     audio_cdc_fifo's frame-pair packing gate
//                     (pcm_valid & ~i2s_lrck) matches i2s_rx, NOT
//                     i2s_slave_rx, whose pcm_valid already pulses once per
//                     complete {L,R} pair with LRCK still at the right
//                     channel level.
//   * i2s_capture_ctrl : application layer (see its file header).
//   * uart_tx / uart_rx : 115200 8N1, BAUD_DIV=1085 at 125 MHz.
//
// CDC / alignment contract:
//   cap_gate (core domain, from i2s_capture_ctrl) is 2-FF synchronized into
//   the 27 MHz domain and gates the FIFO write. While the gate is low the
//   controller drains stale entries, so word 0 of every capture is exactly
//   the first complete stereo pair after the gate rises. sd_idle crosses
//   the other way (3-FF + rising edge) as the i2s error telemetry pulse.
//
// LED map: led[0] 27 MHz heartbeat (1.6 Hz), led[1] capturing,
//         led[2] capture done, led[3] i2s_err != 0, led[7:4] = 0.
//
// Constraint file: constraints/top_i2s_capture.fdc (local pins only).
// The DDR3 pads and generated clocks live in constraints/ddr3_100h.fdc,
// which must be loaded BEFORE this file's set_clock_groups semantics
// (identical ordering contract to the ddr3_diag build set).
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module top_i2s_capture #(
    // Captured stereo words; multiple of 64 (see i2s_capture_ctrl).
    parameter [31:0] CAP_WORDS = 32'd196608,
    // UART baud divider (125 MHz / 115200 = 1085).
    parameter integer BAUD_DIV = 1085,
    // PC 'K' reply timeout for one exported frame (100 ms).
    parameter [31:0] ACK_TIMEOUT_CYCLES = 32'd12500000,
    // DDR3 initialization timeout (3 s).
    parameter [31:0] DDR_TIMEOUT_CYCLES = 32'd375000000
) (
    // ---- board pins owned by this top level ----
    input  wire        clk,          // 27 MHz board crystal (D18)
    input  wire        rst_n,        // board reset, active low (C22)
    output wire [7:0]  led,          // status LEDs (A20..B17)
    input  wire        uart_rx,      // CP2102 RX (B24)
    output wire        uart_tx,      // CP2102 TX (C24), 115200 8N1
    // ---- PCM1808 I2S pins (master mode, module drives BCK/LRCK) ----
    input  wire        i2s_bck,      // 3.072 MHz (U20)
    input  wire        i2s_lrck,     // 48 kHz (T20)
    input  wire        i2s_sd,       // Philips, 24 bit in 32 slot (V16)
    // ---- DDR3 125 MHz differential reference ----
    input  wire        ref_clk_p,    // N3
    input  wire        ref_clk_n,    // N2
    // ---- DDR3 physical side, mirrored one-to-one from the wrapper ----
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
    output wire [3:0]  mem_dm,
    inout  wire [3:0]  mem_dqs,
    inout  wire [3:0]  mem_dqs_n,
    inout  wire [31:0] mem_dq
);

    // ------------------------------------------------------------------
    // 27 MHz domain reset synchronizer (top_pcm1808_probe style)
    // ------------------------------------------------------------------
    reg [1:0] reset_sync;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) reset_sync <= 2'b00;
        else        reset_sync <= {reset_sync[0], 1'b1};
    end
    wire reset_ok = reset_sync[1];

    // ------------------------------------------------------------------
    // Audio receive path (27 MHz domain)
    // ------------------------------------------------------------------
    wire [15:0] pcm_l, pcm_r;
    wire        pcm_valid;
    wire        sd_idle;

    i2s_slave_rx #(.TIMEOUT_CYCLES(27000)) u_i2s_rx (
        .clk_nco  (clk),
        .rst_n    (reset_ok),
        .i2s_bck  (i2s_bck),
        .i2s_lrck (i2s_lrck),
        .i2s_sd   (i2s_sd),
        .pcm_l    (pcm_l),
        .pcm_r    (pcm_r),
        .pcm_valid(pcm_valid),
        .sd_idle  (sd_idle)
    );

    // ------------------------------------------------------------------
    // DDR3 wrapper status and IP-side AXI buses (top_ddr3_diag copy)
    // ------------------------------------------------------------------
    wire         core_clk;
    wire         core_clk_rst_n;
    wire         ddr_init_done;
    wire         pll_lock;
    wire         ddrphy_cpd_lock;

    wire         axi_awready;
    wire         axi_wready;
    wire [3:0]   axi_wusero_id;
    wire         axi_wusero_last;
    wire         axi_arready;
    wire [255:0] axi_rdata;
    wire [3:0]   axi_rid;
    wire         axi_rlast;
    wire         axi_rvalid;

    wire ddr_ready = pll_lock & ddr_init_done & ddrphy_cpd_lock;

    // ------------------------------------------------------------------
    // Controller side AXI buses (single controller, master 0 = capture)
    // ------------------------------------------------------------------
    wire [27:0]  axi_awaddr_a;
    wire         axi_awuser_ap_a;
    wire [3:0]   axi_awuser_id_a;
    wire [3:0]   axi_awlen_a;
    wire         axi_awvalid_a;
    wire [255:0] axi_wdata_a;
    wire [31:0]  axi_wstrb_a;
    wire [27:0]  axi_araddr_a;
    wire         axi_aruser_ap_a;
    wire [3:0]   axi_aruser_id_a;
    wire [3:0]   axi_arlen_a;
    wire         axi_arvalid_a;

    wire [3:0]   wready_beat_a;
    wire [3:0]   rd_valid_a;
    wire [255:0] rd_data_0_a;
    wire [255:0] rd_data_1_unused;   // masters 1..3 tied off, tap kept
    wire [255:0] rd_data_2_unused;
    wire [255:0] rd_data_3_unused;
    wire [3:0]   done_a;
    wire [3:0]   addr_err_a;
    wire         to_err_a;
    wire [3:0]   cmd_to_err_a;
    wire [2:0]   dbg_to_state_a;
    wire [7:0]   wlast_miss_cnt_a;

    // Capture controller (master 0) nets
    wire        cap_m0_cmd_valid;
    wire [36:0] cap_m0_cmd;
    wire [255:0] cap_m0_wdata;
    wire        cap_m0_wready_beat;
    wire        cap_m0_rd_ready;
    wire        cap_m0_rd_valid;
    wire        cap_m0_done;

    wire [3:0]   ddr_cmd_valid = {3'b000, cap_m0_cmd_valid};

    // ------------------------------------------------------------------
    // Application layer nets
    // ------------------------------------------------------------------
    wire        cap_tx_valid;
    wire [7:0]  cap_tx_data;
    wire        cap_tx_ready;
    wire        rx_byte_valid;
    wire [7:0]  rx_byte_data;
    wire        smp_rd_en;
    wire        smp_valid;
    wire [31:0] smp_data;
    wire        i2s_err_pulse;
    wire        cap_gate;
    wire [1:0]  cap_state;
    wire [17:0] cap_word_cnt;
    wire [15:0] cap_i2s_err;

    // ------------------------------------------------------------------
    // CDC FIFO: 16 x 32 bit, Gray-coded, write 27 MHz / read 125 MHz
    // (structure follows audio_cdc_fifo, scaled down and with a plain
    // pcm_valid write strobe - see the header note for why the shared
    // module cannot be reused here)
    // ------------------------------------------------------------------
    function [4:0] bin2gray5;
        input [4:0] bin_val;
        begin
            bin2gray5 = bin_val ^ (bin_val >> 1);
        end
    endfunction

    // cap_gate crossing into the 27 MHz write domain
    reg  [1:0]   cap_gate_sync;
    always @(posedge clk or negedge reset_ok) begin
        if (!reset_ok) cap_gate_sync <= 2'b00;
        else           cap_gate_sync <= {cap_gate_sync[0], cap_gate};
    end
    wire cap_gate_27m = cap_gate_sync[1];

    // Write side (27 MHz)
    reg  [31:0]  cdc_mem [0:15];
    reg  [4:0]   cdc_wr_bin, cdc_wr_gray;
    reg          cdc_full_w;
    wire [4:0]   cdc_rd_gray_wsync;
    wire         cdc_wr_req  = pcm_valid & cap_gate_27m;
    wire         cdc_wr_fire = cdc_wr_req & ~cdc_full_w;
    wire [4:0]   cdc_wr_bin_next  = cdc_wr_bin + {4'd0, cdc_wr_fire};
    wire [4:0]   cdc_wr_gray_next = bin2gray5(cdc_wr_bin_next);
    wire         cdc_full_next = (cdc_wr_gray_next ==
        {~cdc_rd_gray_wsync[4:3], cdc_rd_gray_wsync[2:0]});

    always @(posedge clk or negedge reset_ok) begin
        if (!reset_ok) begin
            cdc_wr_bin  <= 5'd0;
            cdc_wr_gray <= 5'd0;
            cdc_full_w  <= 1'b0;
        end else begin
            cdc_wr_bin  <= cdc_wr_bin_next;
            cdc_wr_gray <= cdc_wr_gray_next;
            cdc_full_w  <= cdc_full_next;
        end
    end

    always @(posedge clk) begin
        if (cdc_wr_fire)
            cdc_mem[cdc_wr_bin[3:0]] <= {pcm_r, pcm_l};
    end

    // Read Gray pointer into the write domain (2-FF)
    reg [4:0] cdc_rd_gray_sync1;
    reg [4:0] cdc_rd_gray_sync2;
    always @(posedge clk or negedge reset_ok) begin
        if (!reset_ok) begin
            cdc_rd_gray_sync1 <= 5'd0;
            cdc_rd_gray_sync2 <= 5'd0;
        end else begin
            cdc_rd_gray_sync1 <= cdc_rd_gray;
            cdc_rd_gray_sync2 <= cdc_rd_gray_sync1;
        end
    end
    assign cdc_rd_gray_wsync = cdc_rd_gray_sync2;

    // Read side (125 MHz core domain)
    reg  [4:0]   cdc_rd_bin, cdc_rd_gray;
    wire [4:0]   cdc_wr_gray_rsync;
    wire         cdc_empty = (cdc_rd_gray == cdc_wr_gray_rsync);
    wire         cdc_rd_fire = smp_rd_en & ~cdc_empty;

    always @(posedge core_clk or negedge core_clk_rst_n) begin
        if (!core_clk_rst_n) begin
            cdc_rd_bin  <= 5'd0;
            cdc_rd_gray <= 5'd0;
        end else if (cdc_rd_fire) begin
            cdc_rd_bin  <= cdc_rd_bin + 5'd1;
            cdc_rd_gray <= bin2gray5(cdc_rd_bin + 5'd1);
        end
    end

    // Write Gray pointer into the read domain (2-FF)
    reg [4:0] cdc_wr_gray_sync1;
    reg [4:0] cdc_wr_gray_sync2;
    always @(posedge core_clk or negedge core_clk_rst_n) begin
        if (!core_clk_rst_n) begin
            cdc_wr_gray_sync1 <= 5'd0;
            cdc_wr_gray_sync2 <= 5'd0;
        end else begin
            cdc_wr_gray_sync1 <= cdc_wr_gray;
            cdc_wr_gray_sync2 <= cdc_wr_gray_sync1;
        end
    end
    assign cdc_wr_gray_rsync = cdc_wr_gray_sync2;

    // Registered read port: data + valid one core cycle after the read
    reg        smp_valid_r;
    reg [31:0] smp_data_r;
    always @(posedge core_clk or negedge core_clk_rst_n) begin
        if (!core_clk_rst_n) begin
            smp_valid_r <= 1'b0;
            smp_data_r  <= 32'd0;
        end else begin
            smp_valid_r <= cdc_rd_fire;
            if (cdc_rd_fire)
                smp_data_r <= cdc_mem[cdc_rd_bin[3:0]];
        end
    end
    assign smp_valid = smp_valid_r;
    assign smp_data  = smp_data_r;

    // ------------------------------------------------------------------
    // sd_idle crossing into the core domain (3-FF + rising edge detect).
    // The reset value is 3'b111, matching the i2s_slave_rx reset value of
    // sd_idle, so the synchronizer settling window after reset release
    // cannot fake a 0 -> 1 edge; a real watchdog timeout produces
    // sync 000 -> 001 -> 011 and the pulse fires in the 011 cycle as
    // sd_idle_sync[1] & ~sd_idle_sync[2].
    reg [2:0] sd_idle_sync;
    always @(posedge core_clk or negedge core_clk_rst_n) begin
        if (!core_clk_rst_n) sd_idle_sync <= 3'b111;
        else                 sd_idle_sync <= {sd_idle_sync[1:0], sd_idle};
    end
    assign i2s_err_pulse = sd_idle_sync[1] & ~sd_idle_sync[2];

    // ------------------------------------------------------------------
    // DDR3 wrapper (instance name is part of the constraint contract,
    // copied verbatim from top_ddr3_diag)
    // ------------------------------------------------------------------
    ddr3_wrapper ddr3_wrapper (
        .ref_clk_p      (ref_clk_p),
        .ref_clk_n      (ref_clk_n),
        .resetn         (rst_n),
        .core_clk       (core_clk),
        .core_clk_rst_n (core_clk_rst_n),
        .ddr_init_done  (ddr_init_done),
        .pll_lock       (pll_lock),
        .ddrphy_cpd_lock(ddrphy_cpd_lock),
        .axi_awaddr     (axi_awaddr_a),
        .axi_awuser_ap  (axi_awuser_ap_a),
        .axi_awuser_id  (axi_awuser_id_a),
        .axi_awlen      (axi_awlen_a),
        .axi_awvalid    (axi_awvalid_a),
        .axi_awready    (axi_awready),
        .axi_wdata      (axi_wdata_a),
        .axi_wstrb      (axi_wstrb_a),
        .axi_wready     (axi_wready),
        .axi_wusero_id  (axi_wusero_id),
        .axi_wusero_last(axi_wusero_last),
        .axi_araddr     (axi_araddr_a),
        .axi_aruser_ap  (axi_aruser_ap_a),
        .axi_aruser_id  (axi_aruser_id_a),
        .axi_arlen      (axi_arlen_a),
        .axi_arvalid    (axi_arvalid_a),
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

    // ------------------------------------------------------------------
    // DDR3 controller, design configuration, master 0 = capture
    // (copied from top_ddr3_diag u_ctrl_design with the unused masters
    // tied off)
    // ------------------------------------------------------------------
    ddr3_ctrl_axi #(
        .AXI_USER_AP     (1'b1),
        .DUMMY_WSTRB_ALL1(1'b0)
    ) u_ctrl_design (
        .clk            (core_clk),
        .rst_n          (core_clk_rst_n),
        .cmd_valid      (ddr_cmd_valid),
        .m0_cmd         (cap_m0_cmd),
        .m1_cmd         (37'd0),
        .m2_cmd         (37'd0),
        .m3_cmd         (37'd0),
        .m0_wdata       (cap_m0_wdata),
        .m1_wdata       (256'd0),
        .m2_wdata       (256'd0),
        .m3_wdata       (256'd0),
        .wready_beat    (wready_beat_a),
        .rd_ready       ({3'b111, cap_m0_rd_ready}),
        .rd_data_0      (rd_data_0_a),
        .rd_data_1      (rd_data_1_unused),
        .rd_data_2      (rd_data_2_unused),
        .rd_data_3      (rd_data_3_unused),
        .rd_valid       (rd_valid_a),
        .done           (done_a),
        .addr_err       (addr_err_a),
        .to_err         (to_err_a),
        .cmd_to_err     (cmd_to_err_a),
        .dbg_to_state   (dbg_to_state_a),
        .wlast_miss_cnt (wlast_miss_cnt_a),
        .axi_awaddr     (axi_awaddr_a),
        .axi_awuser_ap  (axi_awuser_ap_a),
        .axi_awuser_id  (axi_awuser_id_a),
        .axi_awlen      (axi_awlen_a),
        .axi_awvalid    (axi_awvalid_a),
        .axi_wdata      (axi_wdata_a),
        .axi_wstrb      (axi_wstrb_a),
        .axi_araddr     (axi_araddr_a),
        .axi_aruser_ap  (axi_aruser_ap_a),
        .axi_aruser_id  (axi_aruser_id_a),
        .axi_arlen      (axi_arlen_a),
        .axi_arvalid    (axi_arvalid_a),
        .axi_awready    (axi_awready),
        .axi_wready     (axi_wready),
        .axi_wusero_id  (axi_wusero_id),
        .axi_wusero_last(axi_wusero_last),
        .axi_arready    (axi_arready),
        .axi_rdata      (axi_rdata),
        .axi_rid        (axi_rid),
        .axi_rlast      (axi_rlast),
        .axi_rvalid     (axi_rvalid)
    );

    assign cap_m0_wready_beat = wready_beat_a[0];
    assign cap_m0_rd_valid    = rd_valid_a[0];
    assign cap_m0_done        = done_a[0];

    // ------------------------------------------------------------------
    // Application layer
    // ------------------------------------------------------------------
    i2s_capture_ctrl #(
        .CAP_WORDS         (CAP_WORDS),
        .BAUD_DIV          (BAUD_DIV),
        .ACK_TIMEOUT_CYCLES(ACK_TIMEOUT_CYCLES),
        .DDR_TIMEOUT_CYCLES(DDR_TIMEOUT_CYCLES)
    ) u_cap_ctrl (
        .clk           (core_clk),
        .rst_n         (core_clk_rst_n),
        .rx_valid      (rx_byte_valid),
        .rx_data       (rx_byte_data),
        .tx_valid      (cap_tx_valid),
        .tx_data       (cap_tx_data),
        .tx_ready      (cap_tx_ready),
        .smp_valid     (smp_valid),
        .smp_data      (smp_data),
        .smp_rd_en     (smp_rd_en),
        .i2s_err_pulse (i2s_err_pulse),
        .ddr_ready     (ddr_ready),
        .cap_gate      (cap_gate),
        .cap_state     (cap_state),
        .cap_word_cnt  (cap_word_cnt),
        .cap_i2s_err   (cap_i2s_err),
        .m0_cmd_valid  (cap_m0_cmd_valid),
        .m0_cmd        (cap_m0_cmd),
        .m0_wdata      (cap_m0_wdata),
        .m0_wready_beat(cap_m0_wready_beat),
        .m0_rd_data    (rd_data_0_a),
        .m0_rd_ready   (cap_m0_rd_ready),
        .m0_rd_valid   (cap_m0_rd_valid),
        .m0_done       (cap_m0_done)
    );

    // ------------------------------------------------------------------
    // UART physical byte layer (single TX source: the controller)
    // ------------------------------------------------------------------
    uart_tx #(.BAUD_DIV(BAUD_DIV)) u_uart_tx (
        .clk        (core_clk),
        .rst_n      (core_clk_rst_n),
        .byte_wdata (cap_tx_data),
        .byte_wvalid(cap_tx_valid),
        .byte_wready(cap_tx_ready),
        .uart_txd   (uart_tx)
    );

    uart_rx #(.BAUD_DIV(BAUD_DIV)) u_uart_rx (
        .clk        (core_clk),
        .rst_n      (core_clk_rst_n),
        .uart_rxd   (uart_rx),
        .byte_rdata (rx_byte_data),
        .byte_rvalid(rx_byte_valid)
    );

    // ------------------------------------------------------------------
    // 27 MHz heartbeat for led[0] (same as top_ddr3_diag: 1.6 Hz)
    // ------------------------------------------------------------------
    reg [23:0] hb_tick;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) hb_tick <= 24'd0;
        else        hb_tick <= hb_tick + 24'd1;
    end

    assign led[7:4] = 4'd0;
    assign led[3]   = (cap_i2s_err != 16'd0);
    assign led[2]   = (cap_state == 2'd2);
    assign led[1]   = (cap_state == 2'd1);
    assign led[0]   = hb_tick[23];

endmodule
