// -----------------------------------------------------------------------------
// File    : ddr3_ctrl_axi.v
// Module  : ddr3_ctrl_axi
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : DDR3 controller front end: four-master command arbitration
//           (ddr3_arbiter instance) plus the hard IP-contract adaptations
//           of the Pango DDR3 controller (ddr3_wrapper/ddr3_test, REQ-MEM-003,
//           design doc sections 2.2.5 / 5.3, fact F-07):
//
//   1. WRITE channel: the IP has NO axi_wvalid input and NO b channel.
//      Write completion is judged by the axi_wready handshake: the command
//      finishes on the cycle where axi_wready is high and beat_cnt equals
//      the programmed length. axi_wusero_last serves as a side evidence
//      observed in a 4-cycle epilogue window (mismatch counted, never
//      blocking).
//   2. READ channel: every read is preceded by a same-address dummy write
//      of one beat with all-zero byte strobes (masked, no data destroyed).
//      The IP has no axi_rready: while axi_rvalid streams, one beat is
//      captured every cycle into a 16-deep elastic fifo (depth equals the
//      maximum burst length, so a burst can never overflow it). Back-
//      pressure exists only inside this controller: a new read command is
//      accepted only when the fifo is empty, and upstream masters pace
//      their consumption through m{i}_rd_ready.
//   3. axi_awuser_ap / axi_aruser_ap are driven with AXI_USER_AP (design
//      doc section 2.2.5 fixes 1; note the verified pds_cpu_100h bridge
//      uses 0 - switch the parameter if board bring-up misbehaves) and
//      axi_*user_id carry the fixed master number 0..3.
//
// Address map (design doc section 5.1, REQ-RSC-006) is checked in the
// arbiter: 32-byte alignment plus the five legal windows. Violations latch
// sticky per-master flags (addr_err) reported through the self-test chain.
//
// Timeouts: every AXI handshake phase is guarded by a 65536-cycle watchdog
// (AXI_TO_LIMIT, 524 us at 125 MHz).  The verified pds_cpu_100h bridge used
// 4096 cycles (32.7 us), but that design did not issue a same-address dummy
// write before every read.  HYPOTHESIS (not yet measured): the extra
// write-to-read turnaround plus DDR3 refresh can stall a read past 32.7 us
// on board, which would abort diag long reads at random frames.  No latency
// measurement or captured timeout status exists yet, so treat the stall
// source as unconfirmed; widening the window only removes the abort, it does
// not explain the delay.  To dispel or confirm it, capture dbg_to_state and
// a timestamp at the moment a long read is aborted.  On timeout the
// command is aborted (done pulse still issued to avoid upstream deadlock),
// to_err latches sticky, cmd_to_err latches per master, and dbg_to_state
// records the FSM state where it happened (REQ-REL-002 command-level guard
// feeding the sys_ctrl watchdog chain).
//
// Upstream protocol (per master i):
//   * hold m{i}_cmd_valid + m{i}_cmd until m{i}_done pulses (the wait
//     counters freeze while the command is executing: the controller
//     masks the in-flight owner's valid at the arbiter boundary);
//   * writes: present m{i}_wdata, advance it on every m{i}_wready beat
//     pulse (the pulse marks "current beat captured");
//   * reads: consume m{i}_rd_data on every m{i}_rd_valid cycle by
//     asserting m{i}_rd_ready (elastic pacing, fifo never overflows).
//
// The 37-bit command bundle packs {wr(1), addr[27:0], len[7:0]} with
// len = beats-1 (all production traffic uses len=15, 512 B per command).
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module ddr3_ctrl_axi #(
    // awuser/aruser ap bit: design doc fixes 1; verified pds_cpu_100h
    // bridge uses 0 (official demo value). Board bring-up fallback knob.
    parameter AXI_USER_AP = 1'b1,
    // Dummy-write strobe policy: 0 = all strobes masked (design doc, no
    // memory data destroyed); 1 = full strobes with zero data (verified
    // pds_cpu_100h bridge form). Board bring-up fallback knob.
    parameter DUMMY_WSTRB_ALL1 = 1'b0,
    // Legacy masters remain full-width writers unless this is enabled.
    parameter M3_MASK_ENABLE = 1'b0,
    // AXI handshake watchdog limit in core_clk cycles (65536 = 524 us at
    // 125 MHz; the 4096-cycle CPU-bridge value is too tight for the
    // dummy-write-before-read turnaround on this design).
    parameter integer AXI_TO_LIMIT = 65536,
    // P3 starvation quota in core_clk cycles (125000 = 1 ms at 125 MHz).
    parameter integer P3_QUOTA_TIMEOUT = 125000
) (
    input  wire        clk,          // core_clk (125 MHz DDR3 user side)
    input  wire        rst_n,        // core_clk_rst_n (sync-released)
    // ---- four upstream master ports (design doc section 2.2.5) ----
    input  wire [3:0]  cmd_valid,
    input  wire [36:0] m0_cmd,       // {wr, addr[27:0], len[7:0]}
    input  wire [36:0] m1_cmd,
    input  wire [36:0] m2_cmd,
    input  wire [36:0] m3_cmd,
    input  wire [255:0] m0_wdata,    // write beat data (all masters wired)
    input  wire [255:0] m1_wdata,
    input  wire [255:0] m2_wdata,
    input  wire [255:0] m3_wdata,
    input  wire [31:0] m3_wstrb,
    output wire [3:0]  wready_beat,  // per-master write beat pulse
    input  wire [3:0]  rd_ready,     // per-master read pacing
    output wire [255:0] rd_data_0,   // routed read data (active read master)
    output wire [255:0] rd_data_1,
    output wire [255:0] rd_data_2,
    output wire [255:0] rd_data_3,
    output wire [3:0]  rd_valid,     // routed read data valid
    output wire [3:0]  done,         // per-master command completion pulse
    // ---- observation exports (REQ-MEM-004 / self-test chain) ----
    output wire [31:0] wait_cnt_0,
    output wire [31:0] wait_cnt_1,
    output wire [31:0] wait_cnt_2,
    output wire [31:0] wait_cnt_3,
    output wire [3:0]  addr_err,     // sticky region/align/len error per master
    output wire        to_err,       // sticky AXI timeout flag (any master)
    output wire [3:0]  cmd_to_err,   // sticky timeout flag per master
    output wire [2:0]  dbg_to_state, // FSM state at the last timeout
    output wire [7:0]  wlast_miss_cnt,// wusero_last side-evidence miss count
    // ---- IP side: ddr3_wrapper user ports (ddr3_test.v port list) ----
    output wire [27:0] axi_awaddr,
    output wire        axi_awuser_ap,
    output wire [3:0]  axi_awuser_id,
    output wire [3:0]  axi_awlen,
    output wire        axi_awvalid,
    input  wire        axi_awready,
    output wire [255:0] axi_wdata,
    output wire [31:0] axi_wstrb,
    input  wire        axi_wready,
    input  wire [3:0]  axi_wusero_id,
    input  wire        axi_wusero_last,
    output wire [27:0] axi_araddr,
    output wire        axi_aruser_ap,
    output wire [3:0]  axi_aruser_id,
    output wire [3:0]  axi_arlen,
    output wire        axi_arvalid,
    input  wire        axi_arready,
    input  wire [255:0] axi_rdata,
    input  wire [3:0]  axi_rid,
    input  wire        axi_rlast,
    input  wire        axi_rvalid
);

    // ------------------------------------------------------------------
    // FSM states
    // ------------------------------------------------------------------
    localparam [3:0] S_IDLE    = 4'd0;  // arbitrate next command
    localparam [3:0] S_AW      = 4'd1;  // real write: address handshake
    localparam [3:0] S_W       = 4'd2;  // real write: data beats
    localparam [3:0] S_WLAST   = 4'd3;  // real write: wusero_last epilogue
    localparam [3:0] S_DW_AW   = 4'd4;  // dummy write: address handshake
    localparam [3:0] S_DW_W    = 4'd5;  // dummy write: single masked beat
    localparam [3:0] S_AR      = 4'd6;  // read: address handshake
    localparam [3:0] S_R       = 4'd7;  // read: capture beats into fifo
    localparam [3:0] S_R_DRAIN = 4'd8;  // discard a timed-out read response

    // ------------------------------------------------------------------
    // Command registers (latched at grant) and read fifo control
    // ------------------------------------------------------------------
    reg [3:0]  state;
    reg        cur_wr;
    reg [27:0] cur_addr;
    reg [7:0]  cur_len;
    reg [1:0]  cur_master;      // command owner (write or read)
    reg [1:0]  cur_rd_master;   // fifo drain owner, updated on read grants
    reg [3:0]  beat_cnt;        // current burst beat position
    reg [3:0]  wlast_window;    // epilogue cycle counter
    reg        wlast_seen;      // side evidence seen in the window
    reg [16:0] axi_to_cnt;      // handshake watchdog (65536 needs 17 bits)
    reg        to_err_r;
    reg [3:0]  cmd_to_err_r;
    reg [2:0]  dbg_to_state_r;
    reg [7:0]  wlast_miss_cnt_r;

    // 16 x 256-bit elastic read fifo (depth = max burst length).
    localparam RD_FIFO_DEPTH = 16;
    reg [255:0] rd_fifo_mem [0:RD_FIFO_DEPTH-1];
    reg [3:0]   rd_fifo_wr_ptr;
    reg [3:0]   rd_fifo_rd_ptr;
    reg [4:0]   rd_fifo_count;

    // ------------------------------------------------------------------
    // Arbitration (ddr3_arbiter instance)
    // ------------------------------------------------------------------
    wire [3:0]  grant;
    wire        grant_wr;
    wire [27:0] grant_addr;
    wire [7:0]  grant_len;
    wire        fifo_empty = (rd_fifo_count == 5'd0);

    // Valid masking: upstream masters hold cmd_valid until done, so the
    // in-flight command's owner would look like a fresh pending request
    // while the FSM executes it. Hide that master from the arbiter while
    // its command is running, otherwise the wait counters would count the
    // execution time instead of pure queueing time (REQ-MEM-004 semantics).
    wire        cmd_busy = (state != S_IDLE);
    wire [3:0]  arb_valid = cmd_valid &
                            ~(cmd_busy ? (4'b0001 << cur_master) : 4'b0000);

    // The controller can accept a command in S_IDLE; a read grant further
    // requires an empty fifo (back-pressure lives inside this controller).
    wire arb_en = (state == S_IDLE) && (grant_wr || fifo_empty);

    ddr3_arbiter #(
        .P3_QUOTA_TIMEOUT (P3_QUOTA_TIMEOUT)
    ) u_arbiter (
        .clk         (clk),
        .rst_n       (rst_n),
        .arb_en      (arb_en),
        .cmd_valid   (arb_valid),
        .m0_cmd      (m0_cmd),
        .m1_cmd      (m1_cmd),
        .m2_cmd      (m2_cmd),
        .m3_cmd      (m3_cmd),
        .grant       (grant),
        .grant_wr    (grant_wr),
        .grant_addr  (grant_addr),
        .grant_len   (grant_len),
        .wait_cnt_0  (wait_cnt_0),
        .wait_cnt_1  (wait_cnt_1),
        .wait_cnt_2  (wait_cnt_2),
        .wait_cnt_3  (wait_cnt_3),
        .addr_err    (addr_err)
    );

    // ------------------------------------------------------------------
    // IP-side outputs
    // ------------------------------------------------------------------
    assign axi_awvalid   = (state == S_AW) || (state == S_DW_AW);
    // ADDRESS UNIT (2026-11-11, docs/DDR3_CONTRACT_20261111.md): the Pango
    // DDR3 IP consumes axi_*addr as a 32-bit word index, so the byte
    // addresses produced by every master (audio page<<5, mel cmd<<9, weight
    // seq<<8, diag frame<<8) must be shifted right by 2 at the IP boundary.
    // cur_addr stays a byte address end-to-end inside this controller (the
    // arbiter region/alignment check and the same-address dummy write both
    // operate on byte addresses); only the IP-facing AXI address is scaled.
    assign axi_awaddr    = {2'b00, cur_addr[27:2]};
    assign axi_awuser_ap = AXI_USER_AP;
    assign axi_awuser_id = {2'b00, cur_master};
    assign axi_awlen     = (state == S_DW_AW) ? 4'd0 : cur_len[3:0];

    assign axi_wdata     = (state == S_DW_W) ? 256'd0 :
                           (cur_master == 2'd0) ? m0_wdata :
                           (cur_master == 2'd1) ? m1_wdata :
                           (cur_master == 2'd2) ? m2_wdata : m3_wdata;
    assign axi_wstrb     = (state == S_DW_W)
                           ? (DUMMY_WSTRB_ALL1 ? 32'hFFFFFFFF : 32'h00000000)
                           : ((M3_MASK_ENABLE && cur_master==2'd3) ? m3_wstrb : 32'hFFFFFFFF);

    assign axi_arvalid   = (state == S_AR);
    assign axi_araddr    = {2'b00, cur_addr[27:2]};
    assign axi_aruser_ap = AXI_USER_AP;
    assign axi_aruser_id = {2'b00, cur_master};
    assign axi_arlen     = cur_len[3:0];

    // ------------------------------------------------------------------
    // Upstream-facing routed outputs
    // ------------------------------------------------------------------
    // Write beat pulse: routes to the current command owner on every
    // accepted data beat.
    assign wready_beat = (state == S_W && axi_wready) ? (4'b0001 << cur_master)
                                                       : 4'b0000;

    // Read fifo drain: data routes to the master that owns the fifo.
    wire rd_fifo_pop = (rd_fifo_count != 5'd0) && rd_ready[cur_rd_master];
    wire [255:0] rd_fifo_head = rd_fifo_mem[rd_fifo_rd_ptr];

    assign rd_valid = (rd_fifo_count != 5'd0) ? (4'b0001 << cur_rd_master)
                                              : 4'b0000;
    assign rd_data_0 = rd_fifo_head;
    assign rd_data_1 = rd_fifo_head;
    assign rd_data_2 = rd_fifo_head;
    assign rd_data_3 = rd_fifo_head;

    // Command completion: real write (last beat accepted), read (rlast),
    // or watchdog abort. Single-cycle pulse routed to the command owner.
    wire write_cmpl = (state == S_W) && axi_wready && (beat_cnt == cur_len[3:0]);
    wire read_cmpl  = (state == S_R) && axi_rvalid && axi_rlast;
    wire to_abort   = (axi_to_cnt >= AXI_TO_LIMIT[16:0]) &&
                      (state != S_IDLE) && (state != S_WLAST) &&
                      (state != S_R_DRAIN);
    wire done_pulse = write_cmpl || read_cmpl || to_abort;
    assign done = done_pulse ? (4'b0001 << cur_master) : 4'b0000;

    // Observation exports.
    assign to_err        = to_err_r;
    assign cmd_to_err    = cmd_to_err_r;
    assign dbg_to_state  = dbg_to_state_r;
    assign wlast_miss_cnt = wlast_miss_cnt_r;

    // ------------------------------------------------------------------
    // Main sequential logic
    // ------------------------------------------------------------------
    integer k;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= S_IDLE;
            cur_wr          <= 1'b0;
            cur_addr        <= 28'd0;
            cur_len         <= 8'd0;
            cur_master      <= 2'd0;
            cur_rd_master   <= 2'd0;
            beat_cnt        <= 4'd0;
            wlast_window    <= 4'd0;
            wlast_seen      <= 1'b0;
            axi_to_cnt      <= 17'd0;
            to_err_r        <= 1'b0;
            cmd_to_err_r    <= 4'b0000;
            dbg_to_state_r  <= 3'd0;
            wlast_miss_cnt_r<= 8'd0;
            rd_fifo_wr_ptr  <= 4'd0;
            rd_fifo_rd_ptr  <= 4'd0;
            rd_fifo_count   <= 5'd0;
        end else begin
            // ---- read fifo push/pop (independent of the FSM phases) ----
            // Push happens while S_R streams beats; pop happens whenever
            // the drain master asserts ready with data available.
            if ((state == S_R) && axi_rvalid) begin
                rd_fifo_mem[rd_fifo_wr_ptr] <= axi_rdata;
                rd_fifo_wr_ptr <= rd_fifo_wr_ptr + 4'd1;
            end
            if (rd_fifo_pop) begin
                rd_fifo_rd_ptr <= rd_fifo_rd_ptr + 4'd1;
            end
            case ({(state == S_R) && axi_rvalid, rd_fifo_pop})
                2'b10:   rd_fifo_count <= rd_fifo_count + 5'd1;
                2'b01:   rd_fifo_count <= rd_fifo_count - 5'd1;
                default: rd_fifo_count <= rd_fifo_count;
            endcase

            // ---- wusero_last side-evidence epilogue (real writes) ----
            if (state == S_WLAST) begin
                if (axi_wusero_last) begin
                    wlast_seen <= 1'b1;
                end
                if (wlast_window == 4'd3) begin
                    if (!wlast_seen && !axi_wusero_last) begin
                        wlast_miss_cnt_r <= wlast_miss_cnt_r + 8'd1;
                    end
                    state <= S_IDLE;
                end else begin
                    wlast_window <= wlast_window + 4'd1;
                end
            end

            // ---- watchdog accumulator ----
            if ((state == S_AW) || (state == S_W) || (state == S_DW_AW) ||
                (state == S_DW_W) || (state == S_AR) ||
                ((state == S_R) && !axi_rvalid)) begin
                axi_to_cnt <= axi_to_cnt + 17'd1;
            end else begin
                axi_to_cnt <= 17'd0;
            end

            // ---- main FSM ----
            case (state)
                S_IDLE: begin
                    if (grant != 4'b0000) begin
                        // Latch the granted command and dispatch.
                        cur_wr     <= grant_wr;
                        cur_addr   <= grant_addr;
                        cur_len    <= grant_len;
                        for (k = 0; k < 4; k = k + 1) begin
                            if (grant[k]) begin
                                cur_master <= k[1:0];
                            end
                        end
                        if (!grant_wr) begin
                            // Read command: remember the fifo drain owner
                            // (kept until the next read grant, so leftover
                            // fifo data keeps routing to its master).
                            if (grant[0]) cur_rd_master <= 2'd0;
                            if (grant[1]) cur_rd_master <= 2'd1;
                            if (grant[2]) cur_rd_master <= 2'd2;
                            if (grant[3]) cur_rd_master <= 2'd3;
                        end
                        beat_cnt   <= 4'd0;
                        axi_to_cnt <= 17'd0;
                        wlast_seen <= 1'b0;
                        wlast_window <= 4'd0;
                        if (grant_wr) begin
                            state <= S_AW;
                        end else begin
                            state <= S_DW_AW;
                        end
                    end
                end

                S_AW: begin
                    if (axi_awready) begin
                        axi_to_cnt <= 17'd0;
                        state <= S_W;
                    end else if (axi_to_cnt >= AXI_TO_LIMIT[16:0]) begin
                        to_err_r       <= 1'b1;
                        cmd_to_err_r[cur_master] <= 1'b1;
                        dbg_to_state_r <= S_AW;
                        state          <= S_IDLE;
                    end
                end

                S_W: begin
                    if (axi_wready) begin
                        axi_to_cnt <= 17'd0;
                        beat_cnt   <= beat_cnt + 4'd1;
                        if (beat_cnt == cur_len[3:0]) begin
                            // last beat accepted: command complete
                            wlast_window <= 4'd0;
                            wlast_seen   <= 1'b0;
                            state        <= S_WLAST;
                        end
                    end else if (axi_to_cnt >= AXI_TO_LIMIT[16:0]) begin
                        to_err_r       <= 1'b1;
                        cmd_to_err_r[cur_master] <= 1'b1;
                        dbg_to_state_r <= S_W;
                        state          <= S_IDLE;
                    end
                end

                S_DW_AW: begin
                    if (axi_awready) begin
                        axi_to_cnt <= 17'd0;
                        state <= S_DW_W;
                    end else if (axi_to_cnt >= AXI_TO_LIMIT[16:0]) begin
                        to_err_r       <= 1'b1;
                        cmd_to_err_r[cur_master] <= 1'b1;
                        dbg_to_state_r <= S_DW_AW;
                        state          <= S_IDLE;
                    end
                end

                S_DW_W: begin
                    if (axi_wready) begin
                        // masked dummy beat accepted, now issue the read
                        axi_to_cnt <= 17'd0;
                        state <= S_AR;
                    end else if (axi_to_cnt >= AXI_TO_LIMIT[16:0]) begin
                        to_err_r       <= 1'b1;
                        cmd_to_err_r[cur_master] <= 1'b1;
                        dbg_to_state_r <= S_DW_W;
                        state          <= S_IDLE;
                    end
                end

                S_AR: begin
                    if (axi_arready) begin
                        axi_to_cnt <= 17'd0;
                        state <= S_R;
                    end else if (axi_to_cnt >= AXI_TO_LIMIT[16:0]) begin
                        to_err_r       <= 1'b1;
                        cmd_to_err_r[cur_master] <= 1'b1;
                        dbg_to_state_r <= S_AR;
                        state          <= S_IDLE;
                    end
                end

                S_R: begin
                    if (axi_rvalid) begin
                        axi_to_cnt <= 17'd0;
                        if (axi_rlast) begin
                            // burst fully captured; drain continues from
                            // the fifo at the upstream master's pace
                            state <= S_IDLE;
                        end
                    end else if (axi_to_cnt >= AXI_TO_LIMIT[16:0]) begin
                        to_err_r       <= 1'b1;
                        cmd_to_err_r[cur_master] <= 1'b1;
                        dbg_to_state_r <= S_R;
                        // Keep the AXI port quarantined.  The slave may
                        // still return this timed-out burst; accepting a new
                        // read before RLAST would misattribute its data.
                        state          <= S_R_DRAIN;
                    end
                end

                S_R_DRAIN: begin
                    // Discard all late beats.  Only the terminating RLAST
                    // releases the quarantine; reset remains the recovery
                    // path when the slave never completes the burst.
                    if (axi_rvalid && axi_rlast) begin
                        state <= S_IDLE;
                    end
                end

                S_WLAST: begin
                    // Epilogue window handled in the dedicated block above;
                    // this branch only keeps the state stable until the
                    // window closes (the default branch must not fire).
                    if (wlast_window == 4'd3) begin
                        state <= S_IDLE;
                    end
                end

                default: begin
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule
