// rv32_ai_dma.sv
// AXI DMA engine for the NPU (rv32_ai_accel), M1-A skeleton.
//
// Function
// --------
// Two independent channels sharing one AXI master port (to be wired to
// master B of rv32_axi_arbiter):
//   * read channel  - fetches descriptors / weights / activations from DDR3,
//   * write channel - stores computation results back to DDR3.
//
// Burst shape: up to 16 beats x 256 bit = 512 B per transaction (awlen/arlen
// = 15), matching the DDR3 IP's 4-bit length fields.
//
// IP non-standard behaviour handling
// -----------------------------------
// The ddr3_test IP has NO axi_rready: once a read address is accepted the IP
// pushes one 256-bit beat per cycle and the receiver must take it.  The read
// channel therefore contains a 16-beat skid FIFO (512 B, one full maximum-
// size burst) that absorbs the pushed data; the upstream consumer can drain
// it at any slower rate.  A new read command is only issued to the AXI side
// after the FIFO has fully drained (single-outstanding window), which keeps
// the FIFO from ever overflowing while still saturating the read port of the
// arbiter.  Multi-outstanding (2-4) is an M2 optimization: it requires rid
// tagging because rdata carries no backpressure.
//
// Write completion follows the IP's wready-handshake semantics (same as the
// official demo test_wr_ctrl_v1_0.v): the transaction is complete when the
// (awlen+1)-th W beat has been accepted by wready.  AW and W are presented
// together and complete their handshakes independently.
//
// Address conversion: upstream commands use 32-bit DDR3 byte addresses
// (32-byte aligned); the AXI side presents word addresses
// {addr[29:5], 3'b0} exactly like rv32_burst_ddr3 does.
//
// Defensive features: 4096-cycle AXI handshake timeouts (one counter per
// channel, mirroring the CPU bridge self-protection), FIFO overflow and
// rlast/count mismatch detection, all latched into dma_error and readable
// through the NPU MMIO STATUS word.
//
// Style: SystemVerilog-2005, synthesizable with PDS.

`timescale 1 ns / 1 ps

module rv32_ai_dma #(
    // AXI user id for this master (CPU bridge uses 4'd0).
    parameter [3:0] AXI_ID = 4'd1
) (
    input  wire core_clk,
    input  wire core_rst_n,
    // ---- upstream read command channel ----
    input  wire        rd_cmd_valid,
    output wire        rd_cmd_ready,
    input  wire [31:0] rd_cmd_addr,      // byte address, 32B aligned
    input  wire [3:0]  rd_cmd_beats,     // beats-1 (0 => single beat)
    // ---- upstream read data stream (drains the skid FIFO) ----
    output wire        rd_data_valid,
    input  wire        rd_data_ready,
    output wire [255:0] rd_data_word,
    output wire        rd_data_last,     // last beat of the current command
    // ---- upstream write command channel ----
    input  wire        wr_cmd_valid,
    output wire        wr_cmd_ready,
    input  wire [31:0] wr_cmd_addr,      // byte address, 32B aligned
    input  wire [3:0]  wr_cmd_beats,     // beats-1
    // ---- upstream write data stream ----
    input  wire        wr_data_valid,
    output wire        wr_data_ready,
    input  wire [255:0] wr_data_word,
    input  wire        wr_data_last,     // informational (beat count decides)
    // ---- completion / error ----
    output reg         wr_done,          // 1-cycle pulse per finished write
    output reg  [3:0]  dma_error,        // sticky error flags (cleared by reset)
    // ---- AXI master port (wire to rv32_axi_arbiter master B) ----
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
    input  wire [3:0]  axiw_wusero_id,
    input  wire        axiw_wusero_last,
    output wire [27:0] axir_araddr,
    output wire        axir_aruser_ap,
    output wire [3:0]  axir_aruser_id,
    output wire [3:0]  axir_arlen,
    output wire        axir_arvalid,
    input  wire        axir_arready,
    input  wire [255:0] axir_rdata,
    input  wire [3:0]  axir_rid,
    input  wire        axir_rlast,
    input  wire        axir_rvalid
);
    // ------------------------------------------------------------------
    // Error flag encoding (read back through NPU MMIO STATUS)
    // ------------------------------------------------------------------
    localparam [3:0] ERR_RFIFO_OVF   = 4'b0001; // rvalid with FIFO full
    localparam [3:0] ERR_RLAST_MISM  = 4'b0010; // rlast / beat count mismatch
    localparam [3:0] ERR_AXI_TO      = 4'b0100; // handshake timeout (4096 cyc)
    // bit 3 reserved (upstream write contract break detection, M2)

    // Timeout: 13-bit counter per channel - a 12-bit 12'd4096 literal
    // truncates to 0 (same pitfall as documented in rv32_burst_ddr3.sv).
    localparam [12:0] AXI_TO_LIMIT = 13'd4096;
    reg [12:0] rd_to_cnt;
    reg [12:0] wr_to_cnt;

    // ==================================================================
    // Read channel
    // ==================================================================
    localparam [1:0] RD_IDLE = 2'd0, RD_AR = 2'd1, RD_DRAIN = 2'd2, RD_ERR = 2'd3;
    reg [1:0]  rd_state;
    reg [31:0] rd_cur_addr;
    reg [3:0]  rd_cur_beats;   // beats-1 of the in-flight command
    reg [4:0]  rd_rcv_cnt;     // beats received from IP (0..16), no reset mid-txn
    reg        rd_last_seen;   // rlast observed for in-flight command

    // ---- 16-beat skid FIFO (512 B) ----
    // Single-outstanding window: the AR is only issued when the FIFO is
    // empty, and the next command waits until the FIFO has drained again,
    // so a full maximum burst always fits.
    reg [255:0] rfifo [0:15];
    reg [4:0]   rf_head, rf_tail;  // 5-bit wrap pointers, count = head - tail
    wire [4:0]  rf_count = rf_head - rf_tail;
    wire        rf_full  = (rf_count == 5'd16);
    wire        rf_empty = (rf_count == 5'd0);
    wire        rf_wr = axir_rvalid && (rd_state == RD_AR || rd_state == RD_DRAIN);
    wire        rf_pop = rd_data_valid && rd_data_ready;

    assign rd_cmd_ready = (rd_state == RD_IDLE) && rf_empty && (dma_error == 4'b0);
    assign rd_data_valid = !rf_empty;
    assign rd_data_word  = rfifo[rf_tail[3:0]];
    // Upstream beat counter of the command currently being drained.  Wraps
    // to zero on the last delivered beat, so it is always valid at the
    // command boundary (rd_data_last marks beat number beats+1).
    reg [4:0] rf_up_cnt;
    assign rd_data_last = (rf_up_cnt == {1'b0, rd_cur_beats});

    // AXI read address channel (word address conversion as in CPU bridge)
    assign axir_araddr    = {rd_cur_addr[29:5], 3'b0};
    assign axir_aruser_ap = 1'b0;               // official demo always 0
    assign axir_aruser_id = AXI_ID;
    assign axir_arlen     = rd_cur_beats;
    assign axir_arvalid   = (rd_state == RD_AR);

    // Completion check: on the rlast beat the pre-increment receive count
    // must equal rd_cur_beats (this beat is the (beats+1)-th).
    wire rlast_now = rf_wr && axir_rlast && !rd_last_seen;
    wire rcnt_mismatch = rlast_now && (rd_rcv_cnt != {1'b0, rd_cur_beats});

    // ------------------------------------------------------------------
    // Unified sticky error register (single driver; FSMs only produce
    // event wires so there is no multiple-driver conflict).
    //   bit0: read FIFO overflow, bit1: rlast/count mismatch,
    //   bit2: AXI handshake timeout (read or write channel).
    // ------------------------------------------------------------------
    wire err_ovf  = rf_wr && rf_full;
    wire err_mism = rcnt_mismatch;
    wire err_rdto = (rd_state == RD_AR) && !(axir_arvalid && axir_arready)
                    && (rd_to_cnt >= AXI_TO_LIMIT);
    wire err_wrto = (wr_state == WR_ACT) && !w_fire
                    && (wr_to_cnt >= AXI_TO_LIMIT);
    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            dma_error <= 4'b0;
        end else if (err_ovf || err_mism || err_rdto || err_wrto) begin
            dma_error <= dma_error | {1'b0, (err_rdto || err_wrto), err_mism, err_ovf};
        end
    end

    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            rd_state     <= RD_IDLE;
            rd_cur_addr  <= 32'b0;
            rd_cur_beats <= 4'b0;
            rd_rcv_cnt   <= 5'b0;
            rd_last_seen <= 1'b0;
            rf_head      <= 5'b0;
            rf_tail      <= 5'b0;
            rf_up_cnt    <= 5'b0;
            rd_to_cnt    <= 13'b0;
        end else begin
            // FIFO push (IP pushes unconditionally once AR is accepted).
            // Overflow cannot happen by construction; counted and latched
            // anyway so the failure is observable if it ever does.
            if (rf_wr) begin
                rd_rcv_cnt <= rd_rcv_cnt + 1'b1;
                if (!rf_full) begin
                    rfifo[rf_head[3:0]] <= axir_rdata;
                    rf_head <= rf_head + 1'b1;
                end
                // rf_full case: drop beat, keep counting; err_ovf latches
            end
            // FIFO pop (upstream consumption)
            if (rf_pop) begin
                rf_tail <= rf_tail + 1'b1;
                rf_up_cnt <= (rf_up_cnt == {1'b0, rd_cur_beats})
                             ? 5'd0 : rf_up_cnt + 1'b1;
            end
            case (rd_state)
                RD_IDLE: begin
                    rd_rcv_cnt  <= 5'b0;
                    rd_last_seen <= 1'b0;
                    rd_to_cnt   <= 13'b0;
                    if (rd_cmd_valid && rd_cmd_ready) begin
                        rd_cur_addr  <= rd_cmd_addr;
                        rd_cur_beats <= rd_cmd_beats;
                        rd_state     <= RD_AR;
                    end
                end
                RD_AR: begin
                    // Data may already flow while waiting for arready.
                    if (axir_arvalid && axir_arready) begin
                        rd_state <= RD_DRAIN;
                        rd_to_cnt <= 13'b0;
                    end else if (rd_to_cnt >= AXI_TO_LIMIT) begin
                        rd_state <= RD_ERR;    // err_rdto latches
                    end else begin
                        rd_to_cnt <= rd_to_cnt + 1'b1;
                    end
                    if (rlast_now) begin
                        rd_last_seen <= 1'b1;  // err_mism latches
                    end
                end
                RD_DRAIN: begin
                    if (rlast_now) begin
                        rd_last_seen <= 1'b1;  // err_mism latches
                        rd_state <= RD_IDLE;
                    end else if (rd_last_seen) begin
                        // rlast was seen in RD_AR (early data); done.
                        rd_state <= RD_IDLE;
                    end
                end
                RD_ERR: begin
                    // Latched error: hold until soft_reset (rst_n).
                    rd_state <= RD_ERR;
                end
                default: rd_state <= RD_IDLE;
            endcase
        end
    end

    // ==================================================================
    // Write channel
    // ==================================================================
    localparam [1:0] WR_IDLE = 2'd0, WR_ACT = 2'd1, WR_ERR = 2'd3;
    reg [1:0]  wr_state;
    reg [31:0] wr_cur_addr;
    reg [3:0]  wr_cur_beats;   // beats-1
    reg [3:0]  wr_beat_cnt;    // W beats accepted so far

    assign wr_cmd_ready = (wr_state == WR_IDLE) && (dma_error == 4'b0);
    assign wr_data_ready = (wr_state == WR_ACT);

    assign axiw_awaddr    = {wr_cur_addr[29:5], 3'b0};
    assign axiw_awuser_ap = 1'b0;               // official demo always 0
    assign axiw_awuser_id = AXI_ID;
    assign axiw_awlen     = wr_cur_beats;
    assign axiw_awvalid   = (wr_state == WR_ACT);
    assign axiw_wdata     = wr_data_word;
    assign axiw_wstrb     = {32{1'b1}};         // full beat writes only
    assign axiw_wvalid    = (wr_state == WR_ACT) && wr_data_valid;

    wire w_fire = axiw_wvalid && axiw_wready;

    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            wr_state     <= WR_IDLE;
            wr_cur_addr  <= 32'b0;
            wr_cur_beats <= 4'b0;
            wr_beat_cnt  <= 4'b0;
            wr_done      <= 1'b0;
            wr_to_cnt    <= 13'b0;
        end else begin
            wr_done <= 1'b0;
            case (wr_state)
                WR_IDLE: begin
                    wr_beat_cnt <= 4'b0;
                    wr_to_cnt   <= 13'b0;
                    if (wr_cmd_valid && wr_cmd_ready) begin
                        wr_cur_addr  <= wr_cmd_addr;
                        wr_cur_beats <= wr_cmd_beats;
                        wr_state     <= WR_ACT;
                    end
                end
                WR_ACT: begin
                    if (w_fire) begin
                        if (wr_beat_cnt == wr_cur_beats) begin
                            // final W beat accepted: complete (wready
                            // semantics, mirrors rv32_burst_ddr3 DDR_WR_W)
                            wr_done  <= 1'b1;
                            wr_state <= WR_IDLE;
                        end else begin
                            wr_beat_cnt <= wr_beat_cnt + 1'b1;
                        end
                    end else if (wr_to_cnt >= AXI_TO_LIMIT) begin
                        // No AW/W handshake progress for 4096 cycles.
                        wr_state <= WR_ERR;    // err_wrto latches
                    end else begin
                        wr_to_cnt <= wr_to_cnt + 1'b1;
                    end
                end
                WR_ERR:  wr_state <= WR_ERR;  // hold until reset
                default: wr_state <= WR_IDLE;
            endcase
        end
    end

    // ------------------------------------------------------------------
    // Unused IP outputs (kept in the port list for arbiter compatibility)
    // ------------------------------------------------------------------
    wire [3:0] unused_wusero_id   = axiw_wusero_id;
    wire       unused_wusero_last = axiw_wusero_last;
    wire [3:0] unused_rid         = axir_rid;
    wire       unused_wr_last     = wr_data_last;

endmodule