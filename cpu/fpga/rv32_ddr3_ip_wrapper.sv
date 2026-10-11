// rv32_ddr3_ip_wrapper.sv
// Wraps the Pango DDR3 controller IP (ddr3_test) for the ZGTC RISC CPU SoC.
//
// - Converts the on-board 125 MHz differential reference clock to single-ended
//   with GTP_INBUFDS and feeds it to the IP.
// - Generates a core_clk-domain, synchronously-released reset for the DDR3
//   burst bridge (core_clk_rst_n).
// - Exposes the AXI-lite master port, DDR3 control/status pins and the
//   physical DDR3 pads for placement in the top-level constraint file.
//
// The IP instance must be named I_ips_ddr_top so that the generated-clock
// constraint paths (I_ips_ddr_top.u_ddrphy_top.*) resolve.
// APB configuration port is tied off (defaults), matching the reference demo.

`timescale 1 ns / 1 ps

module rv32_ddr3_ip_wrapper (
    // ---- reference clock / reset ----
    input  wire ref_clk_p,
    input  wire ref_clk_n,
    input  wire resetn,           // async, active-low board reset
    // ---- DDR controller side (core_clk = 125 MHz) ----
    output wire core_clk,
    output wire core_clk_rst_n,   // sync-released reset in core_clk domain
    output wire ddr_init_done,
    output wire pll_lock,
    // ---- AXI write channel ----
    output wire [27:0] axiw_awaddr,
    output wire        axiw_awuser_ap,
    output wire [3:0]  axiw_awuser_id,
    output wire [3:0]  axiw_awlen,
    output wire        axiw_awvalid,
    input  wire        axiw_awready,
    output wire [255:0] axiw_wdata,
    output wire [31:0]  axiw_wstrb,
    output wire        axiw_wvalid,
    input  wire        axiw_wready,
    input  wire [3:0]   axiw_wusero_id,
    input  wire         axiw_wusero_last,
    // ---- AXI read channel ----
    output wire [27:0] axir_araddr,
    output wire        axir_aruser_ap,
    output wire [3:0]  axir_aruser_id,
    output wire [3:0]  axir_arlen,
    output wire        axir_arvalid,
    input  wire        axir_arready,
    input  wire [255:0] axir_rdata,
    input  wire [3:0]   axir_rid,
    input  wire         axir_rlast,
    input  wire         axir_rvalid,
    // ---- DDR3 physical ----
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
    wire ref_clk;
    wire core_clk_rst_n_int;

    GTP_INBUFDS refclk_inbuf (
        .O  (ref_clk),
        .I  (ref_clk_p),
        .IB (ref_clk_n)
    );

    // Synchronously release the async board reset into the core_clk domain.
    ips2l_rst_sync_v1_3 u_core_clk_rst_sync (
        .clk        (core_clk),
        .rst_n      (resetn),
        .sig_async  (1'b1),
        .sig_synced (core_clk_rst_n_int)
    );
    assign core_clk_rst_n = core_clk_rst_n_int;

    // PHY reset sequencer: hold dbg_ddrphy_rst_n low after power-on until
    // pll_lock is asserted, then wait 1024 core_clk cycles before releasing.
    // The official demo drives this via UART control bus (ctrl_bus_0[12]);
    // we generate it automatically so no host command is needed.
    reg [10:0] phy_rst_cnt;
    reg dbg_ddrphy_rst_n_r;
    always @(posedge core_clk or negedge resetn) begin
        if (!resetn) begin
            phy_rst_cnt <= 11'd0;
            dbg_ddrphy_rst_n_r <= 1'b0;
        end else if (pll_lock) begin
            if (phy_rst_cnt < 11'd1024)
                phy_rst_cnt <= phy_rst_cnt + 1'b1;
            else
                dbg_ddrphy_rst_n_r <= 1'b1;
        end
    end

    ddr3_test I_ips_ddr_top (
        .ref_clk                (ref_clk),
        .resetn                 (resetn),
        .core_clk               (core_clk),
        .pll_lock               (pll_lock),
        .phy_pll_lock           (),
        .gpll_lock              (),
        .rst_gpll_lock          (),
        .ddrphy_cpd_lock        (),
        .ddr_init_done          (ddr_init_done),

        .axi_awaddr             (axiw_awaddr),
        .axi_awuser_ap          (axiw_awuser_ap),
        .axi_awuser_id          (axiw_awuser_id),
        .axi_awlen              (axiw_awlen),
        .axi_awready            (axiw_awready),
        .axi_awvalid            (axiw_awvalid),

        .axi_wdata              (axiw_wdata),
        .axi_wstrb              (axiw_wstrb),
        .axi_wready             (axiw_wready),
        .axi_wusero_id          (axiw_wusero_id),
        .axi_wusero_last        (axiw_wusero_last),

        .axi_araddr             (axir_araddr),
        .axi_aruser_ap          (axir_aruser_ap),
        .axi_aruser_id          (axir_aruser_id),
        .axi_arlen              (axir_arlen),
        .axi_arready            (axir_arready),
        .axi_arvalid            (axir_arvalid),

        .axi_rdata              (axir_rdata),
        .axi_rid                (axir_rid),
        .axi_rlast              (axir_rlast),
        .axi_rvalid             (axir_rvalid),

        .apb_clk                (1'b0),
        .apb_rst_n              (1'b0),
        .apb_sel                (1'b0),
        .apb_enable             (1'b0),
        .apb_addr               (8'd0),
        .apb_write              (1'b0),
        .apb_ready              (),
        .apb_wdata              (16'd0),
        .apb_rdata              (),


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

        // debug: keep PHY out of reset, defaults otherwise
        .dbg_gate_start         (1'b0),
        .dbg_cpd_start          (1'b0),
        .dbg_ddrphy_rst_n       (1'b1),  // official demo default: ctrl_bus_0[12]=1
        .dbg_gpll_scan_rst      (1'b0),

        .samp_position_dyn_adj  (1'b0),
        .init_samp_position_even(32'd0),
        .init_samp_position_odd (32'd0),

        .wrcal_position_dyn_adj (1'b0),
        .init_wrcal_position    (32'd0),

        .force_read_clk_ctrl    (1'b0),
        .init_slip_step         (16'd0),
        .init_read_clk_ctrl     (12'd0),

        .debug_calib_ctrl       (),
        .dbg_slice_status       (),
        .dbg_slice_state        (),
        .debug_data             (),
        .dbg_dll_upd_state      (),
        .debug_gpll_dps_phase   (),

        .dbg_rst_dps_state      (),
        .dbg_tran_err_rst_cnt   (),
        .dbg_ddrphy_init_fail   (),

        .debug_cpd_offset_adj   (1'b0),
        .debug_cpd_offset_dir   (1'b0),
        .debug_cpd_offset       (10'd0),
        .debug_dps_cnt_dir0     (),
        .debug_dps_cnt_dir1     (),

        .ck_dly_en              (1'b1),
        .init_ck_dly_step       (8'd0),
        .ck_dly_set_bin         (),

        .align_error            (),
        .debug_rst_state        (),
        .debug_cpd_state        ()
    );
endmodule