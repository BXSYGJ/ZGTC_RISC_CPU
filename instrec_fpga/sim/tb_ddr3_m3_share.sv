// -----------------------------------------------------------------------------
// File    : tb_ddr3_m3_share.sv
// Project : InstRec-FPGA / diag bitstream DDR3 ERR @00300200 root-cause
// Purpose : Answer, by simulation only (no build, no board), whether the m3
//           SHARED-INTERFACE mux inside instrec_top corrupts the boot self_test
//           while diag_readback and feat_dump are also wired onto master 3.
//
//           The existing ddr3_subsys / ddr3_aw_timeout cases wire m3 DIRECTLY
//           to self_test ({st_cv, m_cv}) and therefore never exercise the mux
//           that instrec_top actually uses (lines 215..225 and the rd_ready
//           entry at the ddr3_ctrl_axi instantiation).  This TB replicates that
//           exact mux bit-for-bit, with diag_readback and feat_dump present but
//           idle (no UART input, no feature source) -- exactly the boot state.
//
// Hypothesis under test: instrec_top gates rd_ready[3] with
//     st_m3_sel = st_cmd_valid
//   (rd_ready[3] = st_m3_sel ? st_rd_ready : dg_m3_rd_ready).  self_test holds
//   cmd_valid only until `done`, but `done` fires on RLAST while the LAST read
//   beat still sits in the controller fifo one cycle later.  For that cycle
//   st_cmd_valid is already low, so rd_ready[3] falls to dg_m3_rd_ready = 0,
//   the fifo cannot pop, and the stale last beat of read i is presented to
//   self_test as the first beat of read i+1 => data compare fail at the second
//   read address 0x0030_0200.  The fix gates rd_ready by "!st_done" instead of
//   st_cmd_valid (self_test owns m3 until it finishes, not merely while its
//   command strobe is high).
//
// Two scenarios run side by side:
//   S0 (RD_GATE_BY_DONE=0) : the current instrec_top mux (st_cmd_valid gate).
//       EXPECT: st_fail=1, st_fail_addr=0x0030_0200, and NO AXI timeout
//       (to_err=0, cmd_to_err=0, dbg_to_state=0) => a pure DATA COMPARE fail.
//   S1 (RD_GATE_BY_DONE=1) : the proposed fix (!st_done gate).
//       EXPECT: st_done=1, st_fail=0, to_err=0 => self_test passes.
//
// Run (from instrec_fpga/):
//   python sim/run_sim.py ddr3_m3_share
//
// Simulation-only file: not part of src/**, not built by PDS, no product RTL
// is modified.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module tb_ddr3_m3_share;

    reg clk;
    reg rst_n;

    initial begin
        clk   = 1'b0;
        rst_n = 1'b0;
    end

    always #5 clk = ~clk;

    initial begin
        repeat (20) @(posedge clk);
        rst_n = 1'b1;
    end

    // ------------------------------------------------------------------
    // S0: current instrec_top mux (rd_ready gated by st_cmd_valid)
    // ------------------------------------------------------------------
    wire        s0_done, s0_fail, s0_to_err;
    wire [3:0]  s0_cte;
    wire [2:0]  s0_dbg;
    wire [27:0] s0_fail_addr;
    wire [7:0]  s0_sts;

    // ------------------------------------------------------------------
    // S1: proposed fix (rd_ready gated by !st_done)
    // ------------------------------------------------------------------
    wire        s1_done, s1_fail, s1_to_err;
    wire [3:0]  s1_cte;
    wire [2:0]  s1_dbg;
    wire [27:0] s1_fail_addr;
    wire [7:0]  s1_sts;

    m3_share_case #(.RD_GATE_BY_DONE(0)) u_s0 (
        .clk (clk), .rst_n (rst_n),
        .o_st_done (s0_done), .o_st_fail (s0_fail),
        .o_st_fail_addr (s0_fail_addr),
        .o_to_err (s0_to_err), .o_cmd_to_err (s0_cte), .o_dbg_to_state (s0_dbg),
        .o_sts_byte (s0_sts)
    );

    m3_share_case #(.RD_GATE_BY_DONE(1)) u_s1 (
        .clk (clk), .rst_n (rst_n),
        .o_st_done (s1_done), .o_st_fail (s1_fail),
        .o_st_fail_addr (s1_fail_addr),
        .o_to_err (s1_to_err), .o_cmd_to_err (s1_cte), .o_dbg_to_state (s1_dbg),
        .o_sts_byte (s1_sts)
    );

    // ------------------------------------------------------------------
    // Verdict
    // ------------------------------------------------------------------
    wire s0_ready = s0_done || s0_fail;
    wire s1_ready = s1_done || s1_fail;

    // S0 must reproduce the board symptom bit-exactly: a data compare failure
    // at the SECOND command address with no AXI timeout anywhere.
    // S1 must pass the whole self-test with no AXI timeout.
    integer wait_cyc;

    task verdict;
        input [8*44-1:0] label;
        input            ok;
        begin
            if (ok) $display("  %0s : PASS", label);
            else    $display("  %0s : FAIL", label);
        end
    endtask

    initial begin
        wait_cyc = 0;
        while ((!(s0_ready && s1_ready)) && (wait_cyc < 200000)) begin
            @(posedge clk);
            wait_cyc = wait_cyc + 1;
        end
        repeat (8) @(posedge clk);

        $display("");
        $display("==============================================================");
        $display(" T  M3 SHARED-INTERFACE SELF-TEST (diag bitstream topology)");
        $display("==============================================================");
        $display("  S0 (current mux, st_cmd_valid gate):");
        $display("     st_done=%0b st_fail=%0b fail_addr=0x%08X", s0_done, s0_fail, s0_fail_addr);
        $display("     to_err=%0b cmd_to_err=%b dbg_to_state=%0d  STS byte=0x%h",
                 s0_to_err, s0_cte, s0_dbg, s0_sts);
        $display("  S1 (fixed mux, !st_done gate):");
        $display("     st_done=%0b st_fail=%0b fail_addr=0x%08X", s1_done, s1_fail, s1_fail_addr);
        $display("     to_err=%0b cmd_to_err=%b dbg_to_state=%0d  STS byte=0x%h",
                 s1_to_err, s1_cte, s1_dbg, s1_sts);
        $display("");
        $display("--------------------------------------------------------------");
        $display(" ANSWER KEY");
        $display("--------------------------------------------------------------");
        $display("  board symptom  : DDR3 ERR @00300200  +  DDR3 STS 00000000");
        $display("  failure nature : if S0 shows st_fail=1, to_err=0, fail_addr=0x300200");
        $display("                   => DATA COMPARE fail on the 2nd READ command, not a");
        $display("                   write/read AXI timeout (which would set to_err=1 and");
        $display("                   a non-zero dbg_to_state).");
        $display("");

        $display("==============================================================");
        $display(" T VERDICT");
        $display("==============================================================");
        verdict("S0 reproduces board 0x300200 compare fail", 
                s0_fail && !s0_to_err && (s0_fail_addr == 28'h0030_0200));
        verdict("S1 self_test passes with !st_done gate   ",
                s1_done && !s1_fail && !s1_to_err);

        $display("  global wait cycles : %0d", wait_cyc);
        $display("==============================================================");
        if (s0_fail && !s0_to_err && (s0_fail_addr == 28'h0030_0200) &&
            s1_done && !s1_fail && !s1_to_err)
            $display("RESULT: PASS");
        else
            $display("RESULT: FAIL");
        $finish;
    end

endmodule


// =============================================================================
// Scenario harness: self_test + diag_readback + feat_dump all wired onto m3
// through the EXACT mux instrec_top uses, feeding ddr3_ctrl_axi + the
// behavioural DDR3 model.  m0/m1/m2 are tied off (boot state: no audio, no
// NPU weight upload, no mel window).
// =============================================================================
module m3_share_case #(
    // 0 = current instrec_top mux: rd_ready[3] = st_cmd_valid ? st_rd_ready : dg_rd_ready
    // 1 = proposed fix        : rd_ready[3] = (!st_done)    ? st_rd_ready : dg_rd_ready
    parameter integer RD_GATE_BY_DONE = 0,
    parameter integer FEAT_DUMP_ON_M3  = 1
) (
    input  wire        clk,
    input  wire        rst_n,
    output wire        o_st_done,
    output wire        o_st_fail,
    output wire [27:0] o_st_fail_addr,
    output wire        o_to_err,
    output wire [3:0]  o_cmd_to_err,
    output wire [2:0]  o_dbg_to_state,
    output wire [7:0]  o_sts_byte
);

    // ------------------------------------------------------------------
    // self_test (the real RTL, master 3)
    // ------------------------------------------------------------------
    reg         st_start;
    wire        st_cmd_valid;
    wire [36:0] st_cmd;
    wire [255:0] st_wdata;
    wire        st_rd_ready;
    wire        st_done_o, st_fail_o;
    wire [27:0] st_fail_addr_o;

    self_test u_self_test (
        .clk          (clk),
        .rst_n        (rst_n),
        .st_start     (st_start),
        .cmd_valid    (st_cmd_valid),
        .cmd          (st_cmd),
        .wdata        (st_wdata),
        .wready_beat  (wready_beat[3]),
        .rd_ready     (st_rd_ready),
        .rd_data      (rd_data_3),
        .rd_valid     (rd_valid[3]),
        .done         (done[3]),
        .st_done      (st_done_o),
        .st_fail      (st_fail_o),
        .st_fail_addr (st_fail_addr_o)
    );

    // ------------------------------------------------------------------
    // diag_readback (idle: no UART input during boot self-test)
    // ------------------------------------------------------------------
    wire        dg_m3_cmd_valid;
    wire [36:0] dg_m3_cmd;
    wire        dg_m3_rd_ready;
    wire        dg_diag_lock;

    diag_readback u_diag (
        .clk          (clk),
        .rst_n        (rst_n),
        .rx_valid     (1'b0),
        .rx_data      (8'd0),
        .tx_valid     (),
        .tx_data      (),
        .tx_ready     (1'b1),
        .m3_cmd_valid (dg_m3_cmd_valid),
        .m3_cmd       (dg_m3_cmd),
        .m3_rd_data   (rd_data_3),
        .m3_rd_valid  (rd_valid[3]),
        .m3_rd_ready  (dg_m3_rd_ready),
        .m3_done      (done[3]),
        .diag_lock    (dg_diag_lock),
        .win_id       (16'd0),
        .mel_done     (1'b0),
        .npu_done     (1'b0),
        .logits_valid (1'b0),
        .logits_in    (256'd0)
    );

    // ------------------------------------------------------------------
    // feat_dump (idle: no feature source during boot self-test)
    // ------------------------------------------------------------------
    wire        fd_m3_cmd_valid;
    wire [36:0] fd_m3_cmd;
    wire [255:0] fd_m3_wdata;

    feat_dump u_feat (
        .clk          (clk),
        .rst_n        (rst_n),
        .src_we       (1'b0),
        .src_addr     (15'd0),
        .src_data     (8'd0),
        .copy_done    (1'b0),
        .m3_cmd_valid (fd_m3_cmd_valid),
        .m3_cmd       (fd_m3_cmd),
        .m3_wdata     (fd_m3_wdata),
        .m3_done      (done[3]),
        .busy         (),
        .dump_done    ()
    );

    // ------------------------------------------------------------------
    // The EXACT m3 shared-interface mux from instrec_top (lines 215..225).
    // ------------------------------------------------------------------
    // diag_readback is read-only: it exposes no write-data port, so the mux's
    // dg_m3_wdata leg is a plain undriven net in instrec_top (line 180/224).
    // Tie it to 0 here to keep the mux faithful (never selected on a WRITE).
    wire [255:0] dg_m3_wdata = 256'd0;

    wire st_m3_sel    = st_cmd_valid;
    wire dg_m3_en     = st_done_o;
    wire dg_m3_sel    = !st_m3_sel && dg_m3_en && dg_m3_cmd_valid;
    wire fd_m3_sel    = !st_m3_sel && !dg_m3_sel && dg_m3_en && fd_m3_cmd_valid;
    wire fd_on        = (FEAT_DUMP_ON_M3 != 0);
    wire m3_req_valid = st_cmd_valid | dg_m3_sel | (fd_on && fd_m3_sel);

    wire [36:0]  m3_cmd   = st_m3_sel ? st_cmd   :
                             dg_m3_sel ? dg_m3_cmd : fd_m3_cmd;
    wire [255:0] m3_wdata = st_m3_sel ? st_wdata :
                             dg_m3_sel ? dg_m3_wdata :
                             (fd_on    ? fd_m3_wdata : 256'd0);

    // The variable under test: how rd_ready[3] is gated.
    wire m3_rd_ready = (RD_GATE_BY_DONE != 0)
                       ? ((!st_done_o) ? st_rd_ready : dg_m3_rd_ready)
                       : (st_m3_sel    ? st_rd_ready : dg_m3_rd_ready);

    // ------------------------------------------------------------------
    // Controller under test (m0/m1/m2 tied off: boot has no other traffic)
    // ------------------------------------------------------------------
    wire [3:0]   done, wready_beat, rd_valid;
    wire [255:0] rd_data_0, rd_data_1, rd_data_2, rd_data_3;
    wire [31:0]  wait_cnt_0, wait_cnt_1, wait_cnt_2, wait_cnt_3;
    wire         to_err;
    wire [3:0]   cmd_to_err;
    wire [2:0]   dbg_to_state;
    wire [7:0]   wlast_miss;
    wire [3:0]   addr_err;

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

    wire [3:0]  cmd_valid = {m3_req_valid, 1'b0, 1'b0, 1'b0};
    wire [3:0]  rd_ready  = {m3_rd_ready,  1'b0, 1'b0, 1'b0};

    ddr3_ctrl_axi #(
        .AXI_USER_AP      (1'b1),
        .DUMMY_WSTRB_ALL1 (1'b0),
        .AXI_TO_LIMIT     (4096),
        .P3_QUOTA_TIMEOUT (125000)
    ) u_dut (
        .clk         (clk),
        .rst_n       (rst_n),
        .cmd_valid   (cmd_valid),
        .m0_cmd      (37'd0),
        .m1_cmd      (37'd0),
        .m2_cmd      (37'd0),
        .m3_cmd      (m3_cmd),
        .m0_wdata    (256'd0),
        .m1_wdata    (256'd0),
        .m2_wdata    (256'd0),
        .m3_wdata    (m3_wdata),
        .wready_beat (wready_beat),
        .rd_ready    (rd_ready),
        .rd_data_0   (rd_data_0),
        .rd_data_1   (rd_data_1),
        .rd_data_2   (rd_data_2),
        .rd_data_3   (rd_data_3),
        .rd_valid    (rd_valid),
        .done        (done),
        .wait_cnt_0  (wait_cnt_0),
        .wait_cnt_1  (wait_cnt_1),
        .wait_cnt_2  (wait_cnt_2),
        .wait_cnt_3  (wait_cnt_3),
        .addr_err    (addr_err),
        .to_err      (to_err),
        .cmd_to_err  (cmd_to_err),
        .dbg_to_state(dbg_to_state),
        .wlast_miss_cnt (wlast_miss),
        .axi_awaddr      (axi_awaddr),
        .axi_awuser_ap   (axi_awuser_ap),
        .axi_awuser_id   (axi_awuser_id),
        .axi_awlen       (axi_awlen),
        .axi_awvalid     (axi_awvalid),
        .axi_awready     (axi_awready),
        .axi_wdata       (axi_wdata),
        .axi_wstrb       (axi_wstrb),
        .axi_wready      (axi_wready),
        .axi_wusero_id   (axi_wusero_id),
        .axi_wusero_last (axi_wusero_last),
        .axi_araddr      (axi_araddr),
        .axi_aruser_ap   (axi_aruser_ap),
        .axi_aruser_id   (axi_aruser_id),
        .axi_arlen       (axi_arlen),
        .axi_arvalid     (axi_arvalid),
        .axi_arready     (axi_arready),
        .axi_rdata       (axi_rdata),
        .axi_rid         (axi_rid),
        .axi_rlast       (axi_rlast),
        .axi_rvalid      (axi_rvalid)
    );

    // ------------------------------------------------------------------
    // Behavioural DDR3 IP model (healthy: ready always present, no fault)
    // ------------------------------------------------------------------
    ddr3_axi_model #(
        .AW_READY_AW_COUNT   (-1),
        .W_READY_BURST_COUNT (-1),
        .AW_DELAY            (2),
        .MEM_BEATS           (65536)
    ) u_model (
        .clk            (clk),
        .rst_n          (rst_n),
        .s_awaddr       (axi_awaddr),
        .s_awvalid      (axi_awvalid),
        .s_awlen        (axi_awlen),
        .s_awuser_id    (axi_awuser_id),
        .s_awready      (axi_awready),
        .s_wdata        (axi_wdata),
        .s_wstrb        (axi_wstrb),
        .s_wready       (axi_wready),
        .s_wusero_last  (axi_wusero_last),
        .s_araddr       (axi_araddr),
        .s_arvalid      (axi_arvalid),
        .s_arlen        (axi_arlen),
        .s_aruser_id    (axi_aruser_id),
        .s_arready      (axi_arready),
        .s_rdata        (axi_rdata),
        .s_rid          (axi_rid),
        .s_rlast        (axi_rlast),
        .s_rvalid       (axi_rvalid),
        .obs_aw_hs      (),
        .obs_ar_hs      (),
        .obs_wr_beats   (),
        .obs_rd_beats   (),
        .obs_len0_wr    (),
        .obs_len0_wstrb0(),
        .obs_len0_wstrb1(),
        .obs_last_marker()
    );

    assign axi_wusero_id = 4'd0;

    // ------------------------------------------------------------------
    // self_test kick (a few cycles after reset release)
    // ------------------------------------------------------------------
    reg started;
    reg [7:0] kick_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            started  <= 1'b0;
            st_start <= 1'b0;
            kick_cnt <= 8'd0;
        end else begin
            if (!started) begin
                if (kick_cnt == 8'd8) begin
                    st_start <= 1'b1;
                    started  <= 1'b1;
                end else begin
                    kick_cnt <= kick_cnt + 8'd1;
                end
            end else begin
                st_start <= 1'b0;
            end
        end
    end

    // ------------------------------------------------------------------
    // The exact byte sys_ctrl would (ideally) put on the STS line:
    // {1'b0, cmd_to_err[3], to_err, dbg_to_state, st_fail, st_done}
    // ------------------------------------------------------------------
    assign o_st_done      = st_done_o;
    assign o_st_fail      = st_fail_o;
    assign o_st_fail_addr = st_fail_addr_o;
    assign o_to_err       = to_err;
    assign o_cmd_to_err   = cmd_to_err;
    assign o_dbg_to_state = dbg_to_state;
    assign o_sts_byte     = {1'b0, cmd_to_err[3], to_err, dbg_to_state,
                             st_fail_o, st_done_o};

endmodule
