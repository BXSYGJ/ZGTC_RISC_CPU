// -----------------------------------------------------------------------------
// File    : ddr3_wrapper.v
// Module  : ddr3_wrapper
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Instantiation shell around the Pango DDR3 controller IP
//           (ipcore/ddr3_test/ddr3_test.idf, 100H-generated).
//
// Structure follows the verified cpu/fpga/rv32_ddr3_ip_wrapper.sv of the
// pds_cpu_100h project (see reports/asset_trace.md):
//   * GTP_INBUFDS converts the on-board 125 MHz differential reference
//     clock (N3/N2) to single-ended and feeds it to the IP.
//   * ips2l_rst_sync_v1_3 (part of the IP delivery) releases the core_clk
//     domain reset synchronously after power-up.
//   * The IP instance name is HARD-KEPT as I_ips_ddr_top: the generated
//     clock paths in constraints/ddr3_100h.fdc reference
//     ddr3_wrapper.I_ips_ddr_top.u_ddrphy_top.* (pds_cpu_100h lesson).
//   * APB configuration port is tied off with constants (defaults), the
//     debug/status outputs that nobody consumes are simply left
//     unconnected (omitted in the port map).
//
// AXI contract notes (design doc section 2.2.5, REQ-MEM-003):
//   * The IP slave port has NO axi_wvalid and NO axi_rready signals -
//     write completion is judged by the axi_wready handshake and reads are
//     accepted with arvalid/arready only. This wrapper mirrors the real
//     port list of ipcore/ddr3_test/ddr3_test.v one-to-one.
//   * The future master (src/ddr3/ddr3_ctrl_axi.v, T-M0-05) drives
//     axi_awuser_ap=1 and encodes its master id in axi_*user_id.
//
// dbg_ddrphy_rst_n is tied to 1'b1: the official 100Pro+ demo releases the
// PHY reset through the UART control bus (ctrl_bus_0[12]=1); the verified
// pds_cpu_100h build drives the same constant directly.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module ddr3_wrapper (
    // ---- reference clock / board reset ----
    input  wire        ref_clk_p,     // 125 MHz differential reference (N3)
    input  wire        ref_clk_n,     // 125 MHz differential reference (N2)
    input  wire        resetn,        // asynchronous board reset, active low
    // ---- controller side (core_clk = 125 MHz) ----
    output wire        core_clk,      // DDR3 controller core clock
    output wire        core_clk_rst_n,// sync-released reset in core_clk domain
    output wire        ddr_init_done, // DDR3 initialization done flag
    output wire        pll_lock,      // controller GPLL lock flag
    output wire        ddrphy_cpd_lock,// PHY CPD lock flag (self-test chain)
    // ---- AXI write channel (master side of the wrapper) ----
    input  wire [27:0] axi_awaddr,    // write address, 28 bit byte address
    input  wire        axi_awuser_ap, // fixed 1 per REQ-MEM-003
    input  wire [3:0]  axi_awuser_id, // master id encoded by ddr3_ctrl_axi
    input  wire [3:0]  axi_awlen,     // burst length - 1 (15 for len=16)
    input  wire        axi_awvalid,
    output wire        axi_awready,
    input  wire [255:0] axi_wdata,    // 256 bit write data (32 B per beat)
    input  wire [31:0]  axi_wstrb,    // byte strobes (all 0 on dummy writes)
    output wire        axi_wready,    // write beat handshake (no wvalid in IP)
    output wire [3:0]  axi_wusero_id, // write response master id
    output wire        axi_wusero_last,// write response last beat flag
    // ---- AXI read channel ----
    input  wire [27:0] axi_araddr,    // read address, 28 bit byte address
    input  wire        axi_aruser_ap, // fixed 1 per REQ-MEM-003
    input  wire [3:0]  axi_aruser_id, // master id encoded by ddr3_ctrl_axi
    input  wire [3:0]  axi_arlen,     // burst length - 1 (15 for len=16)
    input  wire        axi_arvalid,
    output wire        axi_arready,
    output wire [255:0] axi_rdata,    // 256 bit read data
    output wire [3:0]  axi_rid,       // read response master id
    output wire        axi_rlast,     // read response last beat flag
    output wire        axi_rvalid,
    // ---- DDR3 physical side (pass-through to the top-level pads) ----
    output wire        mem_cs_n,
    output wire        mem_rst_n,
    output wire        mem_ck,
    output wire        mem_ck_n,
    output wire        mem_cke,
    output wire        mem_ras_n,
    output wire        mem_cas_n,
    output wire        mem_we_n,
    output wire        mem_odt,
    output wire [14:0] mem_a,         // row/column address (MEM_ROW_WIDTH=15)
    output wire [2:0]  mem_ba,        // bank address (MEM_BANK_WIDTH=3)
    inout  wire [3:0]  mem_dqs,       // data strobes (MEM_DQS_WIDTH=4)
    inout  wire [3:0]  mem_dqs_n,
    inout  wire [31:0] mem_dq,        // data bus (MEM_DQ_WIDTH=32)
    output wire [3:0]  mem_dm         // data masks (MEM_DM_WIDTH=4)
);

    // Single-ended reference clock from the differential input pair.
    wire ref_clk;

    GTP_INBUFDS refclk_inbuf (
        .O  (ref_clk),
        .I  (ref_clk_p),
        .IB (ref_clk_n)
    );

    // Synchronously release the asynchronous board reset into the
    // core_clk domain (reset tree of design doc section 1.3).
    wire core_clk_rst_n_int;

    ips2l_rst_sync_v1_3 u_core_clk_rst_sync (
        .clk        (core_clk),
        .rst_n      (resetn),
        .sig_async  (1'b1),
        .sig_synced (core_clk_rst_n_int)
    );

    assign core_clk_rst_n = core_clk_rst_n_int;

    // DDR3 controller IP. Instance name I_ips_ddr_top is HARD-KEPT so the
    // generated-clock constraints (ddr3_wrapper.I_ips_ddr_top.u_ddrphy_top.*)
    // keep resolving - do not rename (REQ-MEM-001 / REQ-BLD-004).
    ddr3_test I_ips_ddr_top (
        .ref_clk                (ref_clk),
        .resetn                 (resetn),
        .core_clk               (core_clk),
        .pll_lock               (pll_lock),
        .ddrphy_cpd_lock        (ddrphy_cpd_lock),
        .ddr_init_done          (ddr_init_done),

        // ---- AXI write channel ----
        .axi_awaddr             (axi_awaddr),
        .axi_awuser_ap          (axi_awuser_ap),
        .axi_awuser_id          (axi_awuser_id),
        .axi_awlen              (axi_awlen),
        .axi_awready            (axi_awready),
        .axi_awvalid            (axi_awvalid),

        .axi_wdata              (axi_wdata),
        .axi_wstrb              (axi_wstrb),
        .axi_wready             (axi_wready),
        .axi_wusero_id          (axi_wusero_id),
        .axi_wusero_last        (axi_wusero_last),

        // ---- AXI read channel ----
        .axi_araddr             (axi_araddr),
        .axi_aruser_ap          (axi_aruser_ap),
        .axi_aruser_id          (axi_aruser_id),
        .axi_arlen              (axi_arlen),
        .axi_arready            (axi_arready),
        .axi_arvalid            (axi_arvalid),

        .axi_rdata              (axi_rdata),
        .axi_rid                (axi_rid),
        .axi_rlast              (axi_rlast),
        .axi_rvalid             (axi_rvalid),

        // ---- APB configuration port: tied off, defaults kept ----
        .apb_clk                (1'b0),
        .apb_rst_n              (1'b0),
        .apb_sel                (1'b0),
        .apb_enable             (1'b0),
        .apb_addr               (8'd0),
        .apb_write              (1'b0),
        .apb_wdata              (16'd0),

        // ---- DDR3 physical pads ----
        .mem_cs_n               (mem_cs_n),
        .mem_rst_n              (mem_rst_n),
        .mem_ck                 (mem_ck),
        .mem_ck_n               (mem_ck_n),
        .mem_cke                (mem_cke),
        .mem_ras_n              (mem_ras_n),
        .mem_cas_n              (mem_cas_n),
        .mem_we_n               (mem_we_n),
        .mem_odt                (mem_odt),
        .mem_a                  (mem_a),
        .mem_ba                 (mem_ba),
        .mem_dqs                (mem_dqs),
        .mem_dqs_n              (mem_dqs_n),
        .mem_dq                 (mem_dq),
        .mem_dm                 (mem_dm),

        // ---- debug / calibration control: demo defaults ----
        .dbg_gate_start         (1'b0),
        .dbg_cpd_start          (1'b0),
        .dbg_ddrphy_rst_n       (1'b1),  // demo default ctrl_bus_0[12]=1
        .dbg_gpll_scan_rst      (1'b0),

        .samp_position_dyn_adj  (1'b0),
        .init_samp_position_even(32'd0),
        .init_samp_position_odd (32'd0),

        .wrcal_position_dyn_adj (1'b0),
        .init_wrcal_position    (32'd0),

        .force_read_clk_ctrl    (1'b0),
        .init_slip_step         (16'd0),
        .init_read_clk_ctrl     (12'd0),

        .debug_cpd_offset_adj   (1'b0),
        .debug_cpd_offset_dir   (1'b0),
        .debug_cpd_offset       (10'd0),

        .ck_dly_en              (1'b1),
        .init_ck_dly_step       (8'd0)

        // Unused outputs are intentionally omitted from the port map
        // (phy_pll_lock, gpll_lock, rst_gpll_lock, apb_ready, apb_rdata,
        //  debug_calib_ctrl, dbg_slice_status, dbg_slice_state,
        //  debug_data, dbg_dll_upd_state, debug_gpll_dps_phase,
        //  dbg_rst_dps_state, dbg_tran_err_rst_cnt, dbg_ddrphy_init_fail,
        //  debug_dps_cnt_dir0/1, ck_dly_set_bin, align_error,
        //  debug_rst_state, debug_cpd_state): nobody consumes them.
    );

endmodule