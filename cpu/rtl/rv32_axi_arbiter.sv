// rv32_axi_arbiter.sv
// Dual-master AXI transaction arbiter for the ZGTC RISC CPU SoC (M1-A).
//
// Function
// --------
// Arbitrates the single AXI slave port of the Pango DDR3 controller IP
// (ddr3_test, 256-bit data, core_clk = 125 MHz domain) between:
//   * master A = rv32_burst_ddr3 AXI master port (CPU cache backend), and
//   * master B = NPU DMA engine (rv32_ai_accel / rv32_ai_dma).
//
// Arbitration policy: transaction-level round-robin with a CPU safety quota.
// After the NPU has been granted NPU_QUOTA consecutive transactions, if the
// CPU has a pending request the CPU is granted next, regardless of rotation.
// This bounds the CPU's wait time: the CPU bridge (rv32_burst_ddr3) aborts a
// transaction after 4096 core_clk cycles (its 13-bit AXI_TO_LIMIT), i.e.
// 32.8 us.  NPU_QUOTA=8 of 16-beat bursts complete in well under 2000 cycles,
// so the quota keeps the CPU far away from its timeout.  Raising NPU_QUOTA
// above ~16 risks CPU cache-fill bus errors.
//
// Non-standard IP behaviour (transparently passed through, NOT "fixed")
// ---------------------------------------------------------------------
// The ddr3_test IP has NO axi_rready input: once a read is accepted the IP
// pushes one 256-bit beat every cycle and the receiver MUST accept it.  This
// arbiter therefore:
//   * never degrades read data (no rready is generated anywhere),
//   * locks the read path to the owning master from the AR handshake until
//     rlast is received (an atomic transaction window), and
//   * routes rdata/rid/rlast/rvalid only to the read owner.
// Write completion is signalled by the axiw_wready handshake (the same
// non-standard semantics used by the official demo test_wr_ctrl_v1_0.v and by
// rv32_burst_ddr3).  This arbiter counts W beats (awlen+1 of them) per
// transaction and releases the write lock on the final W handshake.  The IP's
// wusero_last output is routed to the owner for debug but is not required.
//
// Concurrency
// -----------
// ALLOW_RW_CONCURRENT=0 (default, safe): read and write channels are also
// serialized against each other - no new AR or AW is forwarded while any
// transaction is in flight.  This mirrors the strictly sequential behaviour
// of both the IP demo and the CPU bridge, and is the M1 bring-up setting.
// ALLOW_RW_CONCURRENT=1: the AR/AW channels are independent (read owner and
// write owner may differ).  Only enable after hardware validation shows the
// IP tolerates concurrent read/write channels.
//
// Address format note: both masters must present word addresses
// (byte_address[29:5] with low 3 bits zero, 32-byte aligned) exactly like
// rv32_burst_ddr3 does - this module is a pure pass-through and performs no
// address conversion.
//
// Style: SystemVerilog-2005, no interfaces/queues, synthesizable with PDS.

`timescale 1 ns / 1 ps

module rv32_axi_arbiter #(
    // Number of consecutive NPU transactions after which the CPU is granted
    // (when the CPU has a pending request).  Keep <= 16, see header comment.
    parameter integer NPU_QUOTA = 8,
    // 0 = serialize reads and writes (safe default), 1 = independent R/W.
    parameter integer ALLOW_RW_CONCURRENT = 0,
    // Quota counter width, sized from NPU_QUOTA so the counter saturates
    // correctly for any parameter value (3 bits covers <= 8, etc).
    // Declared here (SV-2005 localparam in the parameter port list) so the
    // dbg_npu_streak port can use it; not overridable by the instantiation.
    localparam integer QUOTA_W = (NPU_QUOTA <= 7) ? 3
                               : (NPU_QUOTA <= 15) ? 4 : 5
) (
    input  wire core_clk,
    input  wire core_rst_n,
    // ---- master A: CPU bridge (rv32_burst_ddr3) AXI master port ----
    input  wire [27:0] a_axiw_awaddr,
    input  wire        a_axiw_awuser_ap,
    input  wire [3:0]  a_axiw_awuser_id,
    input  wire [3:0]  a_axiw_awlen,
    input  wire        a_axiw_awvalid,
    output wire        a_axiw_awready,
    input  wire [255:0] a_axiw_wdata,
    input  wire [31:0]  a_axiw_wstrb,
    input  wire        a_axiw_wvalid,
    output wire        a_axiw_wready,
    output wire [3:0]  a_axiw_wusero_id,
    output wire        a_axiw_wusero_last,
    input  wire [27:0] a_axir_araddr,
    input  wire        a_axir_aruser_ap,
    input  wire [3:0]  a_axir_aruser_id,
    input  wire [3:0]  a_axir_arlen,
    input  wire        a_axir_arvalid,
    output wire        a_axir_arready,
    output wire [255:0] a_axir_rdata,
    output wire [3:0]   a_axir_rid,
    output wire        a_axir_rlast,
    output wire        a_axir_rvalid,
    // ---- master B: NPU DMA (rv32_ai_dma) AXI master port ----
    input  wire [27:0] b_axiw_awaddr,
    input  wire        b_axiw_awuser_ap,
    input  wire [3:0]  b_axiw_awuser_id,
    input  wire [3:0]  b_axiw_awlen,
    input  wire        b_axiw_awvalid,
    output wire        b_axiw_awready,
    input  wire [255:0] b_axiw_wdata,
    input  wire [31:0]  b_axiw_wstrb,
    input  wire        b_axiw_wvalid,
    output wire        b_axiw_wready,
    output wire [3:0]  b_axiw_wusero_id,
    output wire        b_axiw_wusero_last,
    input  wire [27:0] b_axir_araddr,
    input  wire        b_axir_aruser_ap,
    input  wire [3:0]  b_axir_aruser_id,
    input  wire [3:0]  b_axir_arlen,
    input  wire        b_axir_arvalid,
    output wire        b_axir_arready,
    output wire [255:0] b_axir_rdata,
    output wire [3:0]   b_axir_rid,
    output wire        b_axir_rlast,
    output wire        b_axir_rvalid,
    // ---- slave: ddr3_test IP AXI port ----
    output wire [27:0] s_axiw_awaddr,
    output wire        s_axiw_awuser_ap,
    output wire [3:0]  s_axiw_awuser_id,
    output wire [3:0]  s_axiw_awlen,
    output wire        s_axiw_awvalid,
    input  wire        s_axiw_awready,
    output wire [255:0] s_axiw_wdata,
    output wire [31:0]  s_axiw_wstrb,
    output wire        s_axiw_wvalid,
    input  wire        s_axiw_wready,
    input  wire [3:0]  s_axiw_wusero_id,
    input  wire        s_axiw_wusero_last,
    output wire [27:0] s_axir_araddr,
    output wire        s_axir_aruser_ap,
    output wire [3:0]  s_axir_aruser_id,
    output wire [3:0]  s_axir_arlen,
    output wire        s_axir_arvalid,
    input  wire        s_axir_arready,
    input  wire [255:0] s_axir_rdata,
    input  wire [3:0]  s_axir_rid,
    input  wire        s_axir_rlast,
    input  wire        s_axir_rvalid,
    // ---- debug (core_clk domain) ----
    output wire [2:0]  dbg_rd_state,   // {rd_busy, rd_owner, 0}
    output wire [2:0]  dbg_wr_state,   // {wr_busy, wr_owner, 0}
    // saturated NPU consecutive-grant count (QUOTA_W bits, 4 @ quota 8)
    output wire [QUOTA_W-1:0] dbg_npu_streak
);
    // ------------------------------------------------------------------

    // Transaction ownership registers
    // ------------------------------------------------------------------
    reg rd_busy;        // read transaction in flight (AR accepted .. rlast)
    reg wr_busy;        // write transaction in flight (AW accepted .. last W beat)
    reg rd_owner;       // 0 = master A (CPU), 1 = master B (NPU)
    reg wr_owner;
    reg last_grant_npu; // rotation state: last granted master was the NPU
    reg [QUOTA_W-1:0] npu_streak; // consecutive NPU transactions, saturated
    reg [3:0]  wr_beat_cnt;        // W beats completed in current write txn
    reg [3:0]  wr_beat_total;      // awlen of current write txn

    // ------------------------------------------------------------------
    // Grant logic (evaluated only when no transaction blocks the channel)
    // ------------------------------------------------------------------
    wire cpu_pending = a_axir_arvalid || a_axiw_awvalid;
    wire npu_pending = b_axir_arvalid || b_axiw_awvalid;
    wire npu_fair    = (npu_streak < QUOTA_LIMIT);
    wire prefer_cpu  = last_grant_npu;
    // Round-robin with CPU safety quota:
    //  - both pending + last=NPU          -> CPU (rotation)
    //  - both pending + last=CPU + fair   -> NPU (rotation)
    //  - both pending + last=CPU + !fair  -> CPU (quota exhausted, forced)
    //  - only one pending                 -> that master (quota only matters
    //                                        while the CPU is pending)
    wire grant_npu = npu_pending && (!cpu_pending || (!prefer_cpu && npu_fair));
    wire grant_cpu = cpu_pending && !grant_npu;
    wire grant_active = grant_npu || grant_cpu; // some master is requesting

    // Channel availability.  In serial mode any in-flight transaction blocks
    // both channels; in concurrent mode each channel is blocked only by its
    // own transaction.
    wire rd_chan_free = !rd_busy && (ALLOW_RW_CONCURRENT != 0 || !wr_busy);
    wire wr_chan_free = !wr_busy && (ALLOW_RW_CONCURRENT != 0 || !rd_busy);

    // Channel grant: which master drives each channel this cycle.  While a
    // transaction is in flight the channel is driven by its owner; otherwise
    // by the round-robin grant (same master on both channels in serial mode).
    wire rd_sel = rd_busy ? rd_owner : grant_npu; // 0=A, 1=B
    wire wr_sel = wr_busy ? wr_owner : grant_npu;

    // Forwarding is additionally gated by channel availability so that no
    // request is presented to the IP while the channel is occupied.
    wire rd_fwd = rd_busy ? 1'b1 : (grant_active && rd_chan_free);
    wire wr_fwd = wr_busy ? 1'b1 : (grant_active && wr_chan_free);

    // ------------------------------------------------------------------
    // Read channel pass-through (no rready anywhere - IP pushes data)
    // ------------------------------------------------------------------
    assign s_axir_araddr    = rd_fwd ? (rd_sel ? b_axir_araddr    : a_axir_araddr)    : 28'b0;
    assign s_axir_aruser_ap = rd_fwd ? (rd_sel ? b_axir_aruser_ap : a_axir_aruser_ap) : 1'b0;
    assign s_axir_aruser_id = rd_fwd ? (rd_sel ? b_axir_aruser_id : a_axir_aruser_id) : 4'b0;
    assign s_axir_arlen     = rd_fwd ? (rd_sel ? b_axir_arlen     : a_axir_arlen)     : 4'b0;
    assign s_axir_arvalid   = rd_fwd ? (rd_sel ? b_axir_arvalid   : a_axir_arvalid)   : 1'b0;
    // arready routes back to the master that is driving AR this cycle.
    assign a_axir_arready = s_axir_arready && rd_fwd && !rd_sel;
    assign b_axir_arready = s_axir_arready && rd_fwd &&  rd_sel;
    // Read data routes to the read owner only (owner is stable for the whole
    // burst because rd_busy locks the channel until rlast).
    assign a_axir_rdata  = s_axir_rdata;
    assign a_axir_rid    = s_axir_rid;
    assign a_axir_rlast  = s_axir_rlast;
    assign a_axir_rvalid = s_axir_rvalid && rd_busy && !rd_owner;
    assign b_axir_rdata  = s_axir_rdata;
    assign b_axir_rid    = s_axir_rid;
    assign b_axir_rlast  = s_axir_rlast;
    assign b_axir_rvalid = s_axir_rvalid && rd_busy &&  rd_owner;

    // ------------------------------------------------------------------
    // Write channel pass-through (completion = final W handshake)
    // ------------------------------------------------------------------
    assign s_axiw_awaddr    = wr_fwd ? (wr_sel ? b_axiw_awaddr    : a_axiw_awaddr)    : 28'b0;
    assign s_axiw_awuser_ap = wr_fwd ? (wr_sel ? b_axiw_awuser_ap : a_axiw_awuser_ap) : 1'b0;
    assign s_axiw_awuser_id = wr_fwd ? (wr_sel ? b_axiw_awuser_id : a_axiw_awuser_id) : 4'b0;
    assign s_axiw_awlen     = wr_fwd ? (wr_sel ? b_axiw_awlen     : a_axiw_awlen)     : 4'b0;
    assign s_axiw_awvalid   = wr_fwd ? (wr_sel ? b_axiw_awvalid   : a_axiw_awvalid)   : 1'b0;
    assign a_axiw_awready   = s_axiw_awready && wr_fwd && !wr_sel;
    assign b_axiw_awready   = s_axiw_awready && wr_fwd &&  wr_sel;
    // W beats follow the write owner; the owner's wvalid may lag the AW
    // handshake (the CPU bridge asserts W one cycle after AW).
    // PROTOCOL CONTRACT: a master that has an AW accepted MUST eventually
    // present awlen+1 W beats, otherwise the write lock never releases.
    assign s_axiw_wdata  = wr_sel ? b_axiw_wdata  : a_axiw_wdata;
    assign s_axiw_wstrb  = wr_sel ? b_axiw_wstrb  : a_axiw_wstrb;
    assign s_axiw_wvalid = wr_busy && (wr_sel ? b_axiw_wvalid : a_axiw_wvalid);
    assign a_axiw_wready = s_axiw_wready && wr_busy && !wr_owner;
    assign b_axiw_wready = s_axiw_wready && wr_busy &&  wr_owner;
    assign a_axiw_wusero_id   = s_axiw_wusero_id;
    assign a_axiw_wusero_last = s_axiw_wusero_last;
    assign b_axiw_wusero_id   = s_axiw_wusero_id;
    assign b_axiw_wusero_last = s_axiw_wusero_last;

    // ------------------------------------------------------------------
    // Quota saturation limit (QUOTA_W itself lives in the parameter list)
    // ------------------------------------------------------------------
    localparam [QUOTA_W-1:0] QUOTA_LIMIT = NPU_QUOTA;

    // ------------------------------------------------------------------
    // Transaction ownership registers
    // ------------------------------------------------------------------
    wire ar_fire = s_axir_arvalid && s_axir_arready;   // read address accepted
    wire aw_fire = s_axiw_awvalid && s_axiw_awready;   // write address accepted
    wire w_fire  = s_axiw_wvalid  && s_axiw_wready;    // one write data beat
    wire rd_done = s_axir_rvalid  && s_axir_rlast;     // burst fully received
    wire wr_done = w_fire && (wr_beat_cnt == wr_beat_total); // final W beat

    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            rd_busy        <= 1'b0;
            wr_busy        <= 1'b0;
            rd_owner       <= 1'b0;
            wr_owner       <= 1'b0;
            last_grant_npu <= 1'b0;
            npu_streak     <= {QUOTA_W{1'b0}};
            wr_beat_cnt    <= 4'b0;
            wr_beat_total  <= 4'b0;
        end else begin
            // ---- read transaction bookkeeping ----
            if (!rd_busy) begin
                if (ar_fire) begin
                    rd_busy        <= 1'b1;
                    rd_owner       <= rd_sel;
                    last_grant_npu <= rd_sel;
                end
            end else if (rd_done) begin
                rd_busy <= 1'b0;
                // quota bookkeeping on read completion
                if (rd_owner)
                    npu_streak <= (npu_streak < QUOTA_LIMIT)
                                  ? npu_streak + 1'b1 : npu_streak;
                else
                    npu_streak <= {QUOTA_W{1'b0}};
            end
            // ---- write transaction bookkeeping ----
            if (!wr_busy) begin
                if (aw_fire) begin
                    wr_busy        <= 1'b1;
                    wr_owner       <= wr_sel;
                    wr_beat_cnt    <= 4'b0;
                    wr_beat_total  <= s_axiw_awlen; // count awlen+1 beats total
                    last_grant_npu <= wr_sel;
                end
            end else begin
                if (w_fire) begin
                    if (wr_beat_cnt == wr_beat_total) begin
                        // final beat: transaction complete (wready semantics)
                        wr_busy <= 1'b0;
                        // quota bookkeeping on write completion
                        if (wr_owner)
                            npu_streak <= (npu_streak < QUOTA_LIMIT)
                                          ? npu_streak + 1'b1 : npu_streak;
                        else
                            npu_streak <= {QUOTA_W{1'b0}};
                    end else begin
                        wr_beat_cnt <= wr_beat_cnt + 1'b1;
                    end
                end
            end
        end
    end

    // ------------------------------------------------------------------
    // Debug outputs
    // ------------------------------------------------------------------
    assign dbg_rd_state   = {rd_busy, rd_owner, 1'b0};
    assign dbg_wr_state   = {wr_busy, wr_owner, 1'b0};
    assign dbg_npu_streak = npu_streak;

endmodule