// -----------------------------------------------------------------------------
// File    : tb_ddr3_byteaddr.sv
// Project : InstRec-FPGA / T38 byte-address semantics proof
// Purpose : Verify, at RTL level (real ddr3_ctrl_axi + behavioural IP model),
//           that the >>2 address fix restores byte semantics so sparse
//           single-beat writes and contiguous multi-beat reads align byte for
//           byte.  This is the RTL counterpart of the Python behavioural model
//           (tests/test_ddr3_contract_consistency.py) and covers the three
//           production paths named in the acceptance plan:
//
//             P0 audio -> mel   : 16 x len=0 page writes @0x000000, then
//                                 1 x len=15 read  (single-beat -> burst)
//             P1 weight -> wdma : 2 x len=7 frame writes @0x100000, then
//                                 1 x len=15 read  (8-beat -> burst)
//             P2 feat -> diag   : 8 x len=0 page writes @0x200000, then
//                                 1 x len=7 read   (single-beat -> burst)
//
//   Every 256-bit beat carries a pattern whose 32 bytes encode the ABSOLUTE
//   byte address (base + beat*32 + byte), so any address-scaling error (x4 or
//   otherwise) shifts the pattern and fails the byte compare.  Unwritten
//   locations return the model fill (0xA5), which never matches.
//
//   A single master (m0) drives all three phases; the >>2 conversion and the
//   arbiter region check are address-only, not per-master, so one master is a
//   faithful exercise of the fixed boundary logic.
//
// Run (from instrec_fpga/):
//   python sim/run_sim.py ddr3_byteaddr
//
// Simulation-only file: not part of src/**, not built by PDS.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module tb_ddr3_byteaddr;

    // ------------------------------------------------------------------
    // Clock / reset
    // ------------------------------------------------------------------
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
    // DUT ports (master 0 only; masters 1..3 tied off)
    // ------------------------------------------------------------------
    reg        m0_cv;
    reg [36:0] m0_cmd;
    reg [255:0] m0_wdata;
    reg        m0_rd_ready;

    wire [3:0]  done;
    wire [3:0]  wready_beat;
    wire [3:0]  rd_valid;
    wire [255:0] rd_data_0;

    wire [27:0] axi_awaddr;
    wire        axi_awuser_ap;
    wire [3:0]  axi_awuser_id;
    wire [3:0]  axi_awlen;
    wire        axi_awvalid;
    wire        axi_awready;
    wire [255:0] axi_wdata;
    wire [31:0] axi_wstrb;
    wire        axi_wready;
    wire [3:0]  axi_wusero_id;
    wire        axi_wusero_last;
    wire [27:0] axi_araddr;
    wire        axi_aruser_ap;
    wire [3:0]  axi_aruser_id;
    wire [3:0]  axi_arlen;
    wire        axi_arvalid;
    wire        axi_arready;
    wire [255:0] axi_rdata;
    wire [3:0]  axi_rid;
    wire        axi_rlast;
    wire        axi_rvalid;

    ddr3_ctrl_axi #(
        .AXI_USER_AP      (1'b1),
        .DUMMY_WSTRB_ALL1 (1'b0),
        .AXI_TO_LIMIT     (65536),
        .P3_QUOTA_TIMEOUT (125000)
    ) u_dut (
        .clk           (clk),
        .rst_n         (rst_n),
        .cmd_valid     ({1'b0, 1'b0, 1'b0, m0_cv}),
        .m0_cmd        (m0_cmd),
        .m1_cmd        (37'd0),
        .m2_cmd        (37'd0),
        .m3_cmd        (37'd0),
        .m0_wdata      (m0_wdata),
        .m1_wdata      (256'd0),
        .m2_wdata      (256'd0),
        .m3_wdata      (256'd0),
        .wready_beat   (wready_beat),
        .rd_ready      ({1'b0, 1'b0, 1'b0, m0_rd_ready}),
        .rd_data_0     (rd_data_0),
        .rd_data_1     (),
        .rd_data_2     (),
        .rd_data_3     (),
        .rd_valid      (rd_valid),
        .done          (done),
        .wait_cnt_0    (),
        .wait_cnt_1    (),
        .wait_cnt_2    (),
        .wait_cnt_3    (),
        .addr_err      (),
        .to_err        (),
        .cmd_to_err    (),
        .dbg_to_state  (),
        .wlast_miss_cnt(),
        .axi_awaddr    (axi_awaddr),
        .axi_awuser_ap (axi_awuser_ap),
        .axi_awuser_id (axi_awuser_id),
        .axi_awlen     (axi_awlen),
        .axi_awvalid   (axi_awvalid),
        .axi_awready   (axi_awready),
        .axi_wdata     (axi_wdata),
        .axi_wstrb     (axi_wstrb),
        .axi_wready    (axi_wready),
        .axi_wusero_id (axi_wusero_id),
        .axi_wusero_last (axi_wusero_last),
        .axi_araddr    (axi_araddr),
        .axi_aruser_ap (axi_aruser_ap),
        .axi_aruser_id (axi_aruser_id),
        .axi_arlen     (axi_arlen),
        .axi_arvalid   (axi_arvalid),
        .axi_arready   (axi_arready),
        .axi_rdata     (axi_rdata),
        .axi_rid       (axi_rid),
        .axi_rlast     (axi_rlast),
        .axi_rvalid    (axi_rvalid)
    );

    // ------------------------------------------------------------------
    // Behavioural DDR3 IP model (word-address interpretation)
    // ------------------------------------------------------------------
    ddr3_axi_model #(
        .AW_READY_AW_COUNT   (-1),
        .W_READY_BURST_COUNT (-1),
        .AW_DELAY            (2),
        .MEM_BEATS           (65536),
        .WSTRB_IGNORE        (0)
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
    // 256-bit beat pattern: byte b = (base + beat*32 + b) & 0xFF
    // ------------------------------------------------------------------
    function [255:0] beat_pat;
        input [27:0] base;
        input [7:0]  beat;
        integer b;
        begin
            beat_pat = 256'd0;
            for (b = 0; b < 32; b = b + 1)
                beat_pat[8*b +: 8] = (base + (beat * 32) + b) & 32'hFF;
        end
    endfunction

    // ------------------------------------------------------------------
    // Per-phase configuration (combinational, derived from `phase`)
    // ------------------------------------------------------------------
    reg  [1:0]  phase;          // 0,1,2
    wire [27:0] ph_base    = (phase == 2'd0) ? 28'h000000 :
                             (phase == 2'd1) ? 28'h100000 : 28'h200000;
    wire [7:0]  ph_wr_cmds = (phase == 2'd0) ? 8'd16 :
                             (phase == 2'd1) ? 8'd2   : 8'd8;
    wire [7:0]  ph_wr_len  = (phase == 2'd0) ? 8'd0  :
                             (phase == 2'd1) ? 8'd7  : 8'd0;
    wire [7:0]  ph_rd_len  = (phase == 2'd0) ? 8'd15 :
                             (phase == 2'd1) ? 8'd15 : 8'd7;
    wire [27:0] ph_stride  = (ph_wr_len + 8'd1) * 28'd32;  // bytes per write cmd
    wire [7:0]  ph_rd_beats = ph_rd_len + 8'd1;

    reg  [2:0]  st;             // FSM state
    localparam [2:0] S_IDLE = 3'd0;
    localparam [2:0] S_WR   = 3'd1;
    localparam [2:0] S_RDW  = 3'd2;
    localparam [2:0] S_RDD  = 3'd3;
    localparam [2:0] S_NEXT = 3'd4;

    reg  [7:0]  wr_cmd;         // write command index
    reg  [7:0]  wr_beat;        // beat index within the current write burst
    reg  [7:0]  rd_beat;        // beat index drained during the read
    reg  [27:0] waddr;          // current write command byte address
    reg  [31:0] errcnt;         // byte mismatch count
    reg  [31:0] rbeatcnt;       // read beats drained
    reg         finished;
    reg         pass_r;

    // Number of byte mismatches between a captured and an expected beat.
    function [5:0] beat_mismatch;
        input [255:0] got;
        input [255:0] exp;
        integer i;
        begin
            beat_mismatch = 6'd0;
            for (i = 0; i < 32; i = i + 1) begin
                if (got[8*i +: 8] != exp[8*i +: 8])
                    beat_mismatch = beat_mismatch + 6'd1;
            end
        end
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            phase       <= 2'd0;
            st          <= S_IDLE;
            m0_cv       <= 1'b0;
            m0_rd_ready <= 1'b0;
            wr_cmd      <= 8'd0;
            wr_beat     <= 8'd0;
            rd_beat     <= 8'd0;
            waddr       <= 28'd0;
            rbeatcnt    <= 32'd0;
            errcnt      <= 32'd0;
            finished    <= 1'b0;
        end else begin
            case (st)
                // ---- enter a phase: present the first write command ----
                S_IDLE: begin
                    wr_cmd    <= 8'd0;
                    wr_beat   <= 8'd0;
                    waddr     <= ph_base;
                    m0_cmd    <= {1'b1, ph_base, ph_wr_len};
                    m0_wdata  <= beat_pat(ph_base, 8'd0);
                    m0_cv     <= 1'b1;
                    st        <= S_WR;
                end

                // ---- write phase: advance beat data on each wready ----
                S_WR: begin
                    if (m0_cv && wready_beat[0]) begin
                        wr_beat  <= wr_beat + 8'd1;
                        m0_wdata <= beat_pat(waddr, wr_beat + 8'd1);
                    end
                    if (m0_cv && done[0]) begin
                        // this write command finished
                        if (wr_cmd + 8'd1 >= ph_wr_cmds) begin
                            // all writes done -> issue the read (cv stays high)
                            m0_cmd      <= {1'b0, ph_base, ph_rd_len};
                            m0_rd_ready <= 1'b0;
                            rd_beat     <= 8'd0;
                            st          <= S_RDW;
                        end else begin
                            // next write command, cmd_valid still held
                            wr_cmd   <= wr_cmd + 8'd1;
                            wr_beat  <= 8'd0;
                            waddr    <= waddr + ph_stride;
                            m0_cmd   <= {1'b1, waddr + ph_stride, ph_wr_len};
                            m0_wdata <= beat_pat(waddr + ph_stride, 8'd0);
                        end
                    end
                end

                // ---- read issued; wait for read done (all beats in fifo) ----
                S_RDW: begin
                    if (done[0]) begin
                        m0_cv       <= 1'b0;
                        m0_rd_ready <= 1'b1;
                        rd_beat     <= 8'd0;
                        st          <= S_RDD;
                    end
                end

                // ---- drain beats, byte-compare each ----
                S_RDD: begin
                    if (rd_valid[0]) begin
                        errcnt   <= errcnt + {26'd0, beat_mismatch(rd_data_0, beat_pat(ph_base, rd_beat))};
                        rd_beat  <= rd_beat + 8'd1;
                        rbeatcnt <= rbeatcnt + 32'd1;
                        if (rd_beat + 8'd1 >= ph_rd_beats) begin
                            m0_rd_ready <= 1'b0;
                            st          <= S_NEXT;
                        end
                    end
                end

                // ---- phase complete: next phase or finish ----
                S_NEXT: begin
                    if (phase == 2'd2) begin
                        finished <= 1'b1;
                        st       <= S_NEXT;   // stay; verdict reads errcnt
                    end else begin
                        phase <= phase + 2'd1;
                        st    <= S_IDLE;
                    end
                end
            endcase
        end
    end

    // ------------------------------------------------------------------
    // Watchdog: fail if nothing finishes in time
    // ------------------------------------------------------------------
    reg [31:0] wdog;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) wdog <= 32'd0;
        else if (!finished) wdog <= wdog + 32'd1;
    end

    // ------------------------------------------------------------------
    // Verdict
    // ------------------------------------------------------------------
    always @* begin
        if (!finished && (wdog < 32'd200000))
            pass_r = 1'b0;
        else
            pass_r = (errcnt == 32'd0) && (rbeatcnt == 32'd40);
    end

    integer wait_cyc;
    initial begin
        wait_cyc = 0; wait(rst_n === 1'b1);
        while ((!finished) && (wait_cyc < 200000)) begin
            @(posedge clk);
            wait_cyc = wait_cyc + 1;
        end
        repeat (4) @(posedge clk);

        $display("");
        $display("==============================================================");
        $display(" T38 BYTE-ADDRESS SEMANTICS - read/write byte-for-byte proof");
        $display("==============================================================");
        $display("  phases run        : %0d (3 expected)", phase + (finished ? 1 : 0));
        $display("  read beats drained: %0d (40 expected: 16 + 16 + 8)", rbeatcnt);
        $display("  byte mismatches   : %0d", errcnt);
        $display("  watchdog cycles   : %0d", wdog);
        $display("==============================================================");
        if (pass_r) $display("RESULT: PASS");
        else        $display("RESULT: FAIL");
        $finish;
    end

endmodule
