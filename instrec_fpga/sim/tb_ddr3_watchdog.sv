// ---------------------------------------------------------------------------
// tb_ddr3_watchdog.sv -- prove the controller handshake-watchdog fix.
//
// The board diag long-read failed at random frames because ddr3_ctrl_axi's
// handshake watchdog (AXI_TO_LIMIT cycles) aborted a read during a transient
// stall of the real Pango DDR3 IP.  This TB drives ONE m3 read through the
// real controller + behavioural model and injects a controlled read-data
// stall (R_STALL_CYCLES), then checks the outcome against the limit:
//
//   * stall <  AXI_TO_LIMIT -> read completes, to_err / cmd_to_err stay 0
//   * stall >= AXI_TO_LIMIT -> watchdog aborts, to_err / cmd_to_err[3] latch
//
// Registered cases pin the boundary:
//   ddr3_watchdog_old  : AXI_TO_LIMIT=4096,  stall=8000  -> expect timeout
//   ddr3_watchdog_new  : AXI_TO_LIMIT=65536, stall=8000  -> expect complete
//   ddr3_watchdog_over : AXI_TO_LIMIT=65536, stall=70000 -> expect timeout
// ---------------------------------------------------------------------------
`timescale 1ns/1ps

module tb_ddr3_watchdog #(
    parameter integer AXI_TO_LIMIT   = 65536,
    parameter integer R_STALL_CYCLES = 8000
);

    localparam integer CLK_HALF = 5;   // 100 MHz test clock (watchdog counts cycles)

    reg clk   = 1'b0;
    reg rst_n = 1'b0;
    always #(CLK_HALF) clk = ~clk;

    // ---- m3 read master: one read (len=15 -> 16 beats), hold until done ----
    reg        m3_cmd_valid = 1'b0;
    wire       m3_rd_ready  = 1'b1;    // always drain
    localparam [27:0] RD_ADDR = 28'h0000_0000;
    wire [36:0] m3_cmd_w = {1'b0, RD_ADDR, 8'd15};

    wire [3:0] cmd_valid = {m3_cmd_valid, 3'b000};
    wire [36:0] m0_cmd = 37'd0, m1_cmd = 37'd0, m2_cmd = 37'd0;
    wire [255:0] m0_wdata = 256'd0, m1_wdata = 256'd0, m2_wdata = 256'd0, m3_wdata = 256'd0;

    wire [3:0]   wready_beat, rd_valid_c, done_c;
    wire [255:0] rd_data_3;
    wire [31:0]  wait_cnt_0, wait_cnt_1, wait_cnt_2, wait_cnt_3;
    wire [3:0]   addr_err, cmd_to_err;
    wire         to_err;
    wire [2:0]   dbg_to_state;
    wire [7:0]   wlast_miss_cnt;

    wire [27:0] axi_awaddr; wire axi_awuser_ap; wire [3:0] axi_awuser_id, axi_awlen;
    wire axi_awvalid, axi_awready;
    wire [255:0] axi_wdata; wire [31:0] axi_wstrb; wire axi_wready;
    wire [3:0] axi_wusero_id; wire axi_wusero_last;
    wire [27:0] axi_araddr; wire axi_aruser_ap; wire [3:0] axi_aruser_id, axi_arlen;
    wire axi_arvalid, axi_arready;
    wire [255:0] axi_rdata; wire [3:0] axi_rid; wire axi_rlast, axi_rvalid;

    ddr3_ctrl_axi #(.AXI_TO_LIMIT(AXI_TO_LIMIT)) u_ctrl (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(cmd_valid),
        .m0_cmd(m0_cmd), .m1_cmd(m1_cmd), .m2_cmd(m2_cmd), .m3_cmd(m3_cmd_w),
        .m0_wdata(m0_wdata), .m1_wdata(m1_wdata), .m2_wdata(m2_wdata), .m3_wdata(m3_wdata),
        .wready_beat(wready_beat),
        .rd_ready({m3_rd_ready, 3'b000}),
        .rd_data_0(), .rd_data_1(), .rd_data_2(), .rd_data_3(rd_data_3),
        .rd_valid(rd_valid_c), .done(done_c),
        .wait_cnt_0(wait_cnt_0), .wait_cnt_1(wait_cnt_1),
        .wait_cnt_2(wait_cnt_2), .wait_cnt_3(wait_cnt_3),
        .addr_err(addr_err), .to_err(to_err), .cmd_to_err(cmd_to_err),
        .dbg_to_state(dbg_to_state), .wlast_miss_cnt(wlast_miss_cnt),
        .axi_awaddr(axi_awaddr), .axi_awuser_ap(axi_awuser_ap),
        .axi_awuser_id(axi_awuser_id), .axi_awlen(axi_awlen),
        .axi_awvalid(axi_awvalid), .axi_awready(axi_awready),
        .axi_wdata(axi_wdata), .axi_wstrb(axi_wstrb), .axi_wready(axi_wready),
        .axi_wusero_id(axi_wusero_id), .axi_wusero_last(axi_wusero_last),
        .axi_araddr(axi_araddr), .axi_aruser_ap(axi_aruser_ap),
        .axi_aruser_id(axi_aruser_id), .axi_arlen(axi_arlen),
        .axi_arvalid(axi_arvalid), .axi_arready(axi_arready),
        .axi_rdata(axi_rdata), .axi_rid(axi_rid),
        .axi_rlast(axi_rlast), .axi_rvalid(axi_rvalid)
    );

    assign axi_wusero_id = 4'd0;   // controller does not read it

    wire [31:0] obs_aw_hs, obs_ar_hs, obs_wr_beats, obs_rd_beats;
    wire [31:0] obs_len0_wr, obs_len0_wstrb0, obs_len0_wstrb1, obs_last_marker;

    ddr3_axi_model #(.R_STALL_CYCLES(R_STALL_CYCLES)) u_model (
        .clk(clk), .rst_n(rst_n),
        .s_awaddr(axi_awaddr), .s_awvalid(axi_awvalid), .s_awlen(axi_awlen),
        .s_awuser_id(axi_awuser_id), .s_awready(axi_awready),
        .s_wdata(axi_wdata), .s_wstrb(axi_wstrb), .s_wready(axi_wready),
        .s_wusero_last(axi_wusero_last),
        .s_araddr(axi_araddr), .s_arvalid(axi_arvalid), .s_arlen(axi_arlen),
        .s_aruser_id(axi_aruser_id), .s_arready(axi_arready),
        .s_rdata(axi_rdata), .s_rid(axi_rid), .s_rlast(axi_rlast), .s_rvalid(axi_rvalid),
        .obs_aw_hs(obs_aw_hs), .obs_ar_hs(obs_ar_hs),
        .obs_wr_beats(obs_wr_beats), .obs_rd_beats(obs_rd_beats),
        .obs_len0_wr(obs_len0_wr), .obs_len0_wstrb0(obs_len0_wstrb0),
        .obs_len0_wstrb1(obs_len0_wstrb1), .obs_last_marker(obs_last_marker)
    );

    // ---- outcome monitors ----
    integer rd_beats = 0;
    integer done_pulses = 0;

    always @(posedge clk) begin
        if (rd_valid_c[3] && m3_rd_ready) rd_beats = rd_beats + 1;
        if (done_c[3]) done_pulses = done_pulses + 1;
        if (rst_n && done_c[3]) m3_cmd_valid <= 1'b0;
    end

    localparam integer EXPECT_TIMEOUT = (R_STALL_CYCLES >= AXI_TO_LIMIT) ? 1 : 0;

    integer guard;

    initial begin
        repeat (20) @(posedge clk);
        rst_n = 1'b1;
        repeat (20) @(posedge clk);

        m3_cmd_valid <= 1'b1;   // issue one read
        guard = 0;
        while (done_pulses == 0 && guard < 2000000) begin
            @(posedge clk);
            guard = guard + 1;
        end
        repeat (200) @(posedge clk);   // let any late beats / drain settle

        $display("AXI_TO_LIMIT=%0d R_STALL_CYCLES=%0d EXPECT_TIMEOUT=%0d",
                 AXI_TO_LIMIT, R_STALL_CYCLES, EXPECT_TIMEOUT);
        $display("to_err=%b cmd_to_err=%b dbg_to_state=%0d done_pulses=%0d rd_beats=%0d",
                 to_err, cmd_to_err, dbg_to_state, done_pulses, rd_beats);

        if (EXPECT_TIMEOUT) begin
            if (to_err !== 1'b1 || cmd_to_err[3] !== 1'b1) begin
                $display("RESULT: FAIL (expected watchdog timeout; to_err=%b cmd_to_err[3]=%b)",
                         to_err, cmd_to_err[3]);
            end else begin
                $display("RESULT: PASS (timeout correctly reported)");
            end
        end else begin
            if (to_err !== 1'b0 || cmd_to_err[3] !== 1'b0) begin
                $display("RESULT: FAIL (unexpected timeout; to_err=%b cmd_to_err[3]=%b)",
                         to_err, cmd_to_err[3]);
            end else if (rd_beats != 16) begin
                $display("RESULT: FAIL (expected 16 read beats, got %0d)", rd_beats);
            end else begin
                $display("RESULT: PASS (read completed, 16 beats)");
            end
        end
        $finish;
    end

    // Absolute watchdog (must never trip for a well-formed test).
    initial begin
        repeat (5000000) @(posedge clk);
        $display("RESULT: FAIL (absolute watchdog; done_pulses=%0d rd_beats=%0d)",
                 done_pulses, rd_beats);
        $finish;
    end

endmodule
