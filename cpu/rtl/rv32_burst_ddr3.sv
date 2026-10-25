// rv32_burst_ddr3.sv
// DDR3 backend for the ZGTC RISC CPU burst memory bus.
//
// Converts the CPU-side burst-bus protocol (16 B cache lines, 4 x 32 b words)
// into 32 B single-beat AXI transactions on the Pango DDR3 controller
// interface (core_clk = 125 MHz domain).  The two clock domains (CPU clk and
// ddr core_clk) are connected with level handshakes through 2-FF synchronizers.
//
// Address map: CPU byte address [31:0], 16 B aligned.  DDR3 occupies the
// 128 MB space above 64 KB.  The bridge maps a 16 B line to the matching
// half (low/high) of a 32 B AXI word selected by bit 4 of the byte address;
// the other half is written with byte-strobe masked off (read returns the
// selected half only).
//
// The bridge is synthesizable with SystemVerilog-2005 syntax constraints
// (PDS platform): always @* / reg / wire, no implicit logic.

`timescale 1 ns / 1 ps

module rv32_burst_ddr3 (
    // ---- CPU clock domain (clk) ----
    input  wire clk,
    input  wire rst_n,
    // ---- burst bus backend slave interface ----
    input  wire        cmd_valid,
    output wire        cmd_ready,
    input  wire        cmd_write,
    input  wire [31:0] cmd_address,
    input  wire [7:0]  cmd_length,
    //
    input  wire        w_valid,
    output wire        w_ready,
    input  wire [31:0] w_data,
    input  wire        w_last,
    //
    output reg         b_valid,
    input  wire        b_ready,
    output reg         b_error,
    //
    output reg         r_valid,
    input  wire        r_ready,
    output reg  [31:0] r_data,
    output reg         r_last,
    output reg         r_error,
    // ---- DDR3 controller domain (ddr_clk) ----
    input  wire ddr_clk,
    input  wire ddr_rst_n,
    input  wire ddr_init_done,   // in ddr_clk domain
    // ---- AXI master (ddr_clk domain) ----
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
    // ---- debug bus (ddr_clk domain, sampled by CPU via GPIO) ----
    output wire [3:0]   dbg_ddr_state,
    output wire         dbg_arvalid,
    output wire         dbg_arready,
    output wire         dbg_rvalid,
    output reg          dbg_to_err,
    output reg  [2:0]   dbg_to_state
);
    // ------------------------------------------------------------------
    // CDC synchronizers
    // ------------------------------------------------------------------
    reg cpu_req_r, cpu_req_ff1, cpu_req_ff2;         // ddr side view of request
    reg ddr_ack_r, ddr_ack_ff1, ddr_ack_ff2;         // cpu side view of ack
    reg ddr_idle_ff1, ddr_idle_ff2;                  // cpu side view of ddr idle
    wire ddr_req_sync = cpu_req_ff2;
    wire ddr_ack_sync = ddr_ack_ff2;
    wire ddr_idle_sync = ddr_idle_ff2;

    always @(posedge ddr_clk or negedge ddr_rst_n) begin
        if (!ddr_rst_n) begin
            cpu_req_ff1 <= 1'b0; cpu_req_ff2 <= 1'b0;
        end else begin
            cpu_req_ff1 <= cpu_req_r;
            cpu_req_ff2 <= cpu_req_ff1;
        end
    end
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ddr_ack_ff1 <= 1'b0; ddr_ack_ff2 <= 1'b0;
            ddr_idle_ff1 <= 1'b0; ddr_idle_ff2 <= 1'b0;
        end else begin
            ddr_ack_ff1 <= ddr_ack_r;
            ddr_ack_ff2 <= ddr_ack_ff1;
            ddr_idle_ff1 <= ddr_idle;
            ddr_idle_ff2 <= ddr_idle_ff1;
        end
    end
    // ------------------------------------------------------------------
    // CPU domain: request path (lock address / data, raise req)
    // ------------------------------------------------------------------
    localparam CPU_IDLE = 0, CPU_COLLECT_W = 1, CPU_REQ = 2, CPU_READ_SEND = 3,
               CPU_WRITE_ACK = 4, CPU_CLEAR = 5;
    reg [2:0] cpu_state;
    reg [31:0] req_address;
    reg        req_write;
    reg [127:0] wbuf;
    reg [1:0]  wbeat, rbeat;
    reg [127:0] rd_hold;


    // cmd_ready: only when idle AND ddr backend is idle (ddr_idle_sync).
    assign cmd_ready = (cpu_state == CPU_IDLE) && ddr_idle_sync;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cpu_state <= CPU_IDLE;
            req_address <= 32'b0;
            req_write <= 1'b0;
            wbuf <= 128'b0;
            wbeat <= 2'b0;
            rbeat <= 2'b0;
            rd_hold <= 128'b0;
            cpu_req_r <= 1'b0;
            b_valid <= 1'b0; b_error <= 1'b0;
            r_valid <= 1'b0; r_last <= 1'b0; r_error <= 1'b0;
        end else begin
            b_valid <= 1'b0;
            r_valid <= 1'b0;
            case (cpu_state)
                CPU_IDLE: begin
                    if (cmd_valid && cmd_ready) begin
                        req_address <= cmd_address;
                        req_write <= cmd_write;
                        if (!cmd_write) begin
                            cpu_state <= CPU_REQ;
                        end else begin
                            cpu_state <= CPU_COLLECT_W;
                            wbeat <= 2'b0;
                        end
                    end
                end
                CPU_COLLECT_W: begin
                    if (w_valid && w_ready) begin
                        case (wbeat)
                            0: wbuf[ 31: 0] <= w_data;
                            1: wbuf[ 63:32] <= w_data;
                            2: wbuf[ 95:64] <= w_data;
                            default: wbuf[127:96] <= w_data;
                        endcase
                        if (wbeat == 2'd3) begin
                            cpu_state <= CPU_REQ;
                        end else begin
                            wbeat <= wbeat + 1'b1;
                        end
                    end
                end
                CPU_REQ: begin
                    cpu_req_r <= 1'b1;
                    if (ddr_ack_sync) begin
                        // data phase is stable after ack sync
                        if (req_write) begin
                            cpu_state <= CPU_WRITE_ACK;
                        end else begin
                            rd_hold <= rd_data_from_ddr;
                            rbeat <= 2'b0;
                            cpu_state <= CPU_READ_SEND;
                        end
                    end
                end
                CPU_READ_SEND: begin
                    // End only when the final beat (r_last=1) is handshake-acked,
                    // mirroring rv32_burst_ram.sv READ state. Previously r_last was
                    // cleared in the same cycle it would have become 1, so the
                    // arbiter/cache never saw r_last=1 and every DDR read hung.
                    if (r_valid && r_ready && r_last) begin
                        r_valid   <= 1'b0;
                        r_last    <= 1'b0;
                        cpu_state <= CPU_CLEAR;
                        cpu_req_r <= 1'b0;
                    end else if (!r_valid || r_ready) begin
                        r_valid <= 1'b1;
                        r_data  <= rd_hold[rbeat*32 +: 32];
                        r_last  <= (rbeat == 2'd3);
                        if (rbeat != 2'd3) rbeat <= rbeat + 1'b1;
                    end
                end
                CPU_WRITE_ACK: begin
                    b_valid <= 1'b1;
                    if (b_valid && b_ready) begin
                        b_valid <= 1'b0;
                        cpu_state <= CPU_CLEAR;
                        cpu_req_r <= 1'b0;
                    end
                end
                CPU_CLEAR: begin
                    if (!ddr_ack_sync) begin
                        cpu_state <= CPU_IDLE;
                    end
                end
            endcase
        end
    end

    // Write-addressary: 4-beat write data collection is driven by w_ready.
    assign w_ready = (cpu_state == CPU_COLLECT_W);

    // Read return: word select with rd_hold (combinational), clipped by r_valid
    // r_data shows the current beat; the cache only samples when r_valid&&r_ready
    wire [31:0] rd_selected = rd_hold;   // 128-bit half; sliced per beat in always block

    // ------------------------------------------------------------------
    // DDR domain: AXI master FSM
    // ------------------------------------------------------------------
    localparam DDR_IDLE = 0, DDR_WR_AW = 1, DDR_WR_W = 2, DDR_RD_AR = 3,
               DDR_RD_R = 4, DDR_ACK = 5;
    reg [2:0] ddr_state;
    reg [31:0] ddr_address;      // aligned to 16B, bit4 selects half
    reg [255:0] ddr_wdata;
    reg [31:0] ddr_wstrb;
    reg [127:0] ddr_rdata;
    reg        ddr_need_read;    // 1 = do dummy write then read

    wire ddr_busy = (ddr_state != DDR_IDLE);
    wire ddr_idle = !ddr_busy & ddr_init_done;   // in ddr domain

    // AXI output assignments — DDR3 IP uses word addresses (byte_address / 4),
    // aligned to 8 words (32 bytes) per beat.  Low 3 bits zero = 8-word align.
    assign axiw_awaddr    = {ddr_address[29:5], 3'b0};   // word addr, 32B aligned
    assign axiw_awuser_ap = 1'b0;  // official demo always 0
    assign axiw_awuser_id = 4'b0;
    assign axiw_awlen     = 4'b0;                        // single 32B beat
    assign axiw_awvalid   = (ddr_state == DDR_WR_AW);
    assign axiw_wdata     = ddr_wdata;
    assign axiw_wstrb     = ddr_wstrb;
    assign axiw_wvalid    = (ddr_state == DDR_WR_W);
    assign axir_araddr    = {ddr_address[29:5], 3'b0};   // word addr, 32B aligned
    assign axir_aruser_ap = 1'b0;  // official demo always 0
    assign axir_aruser_id = 4'b0;
    assign axir_arlen     = 4'b0;
    assign axir_arvalid   = (ddr_state == DDR_RD_AR);

    // AXI timeout: abort transaction after 4096 cycles and return error.
    // NOTE: the counter must be 13 bits - a 12-bit 12'd4096 literal truncates
    // to 0, which made the timeout fire on the first cycle of every state.
    reg [12:0] axi_to_cnt;
    localparam [12:0] AXI_TO_LIMIT = 13'd4096;

    always @(posedge ddr_clk or negedge ddr_rst_n) begin
        if (!ddr_rst_n) begin
            ddr_state <= DDR_IDLE;
            ddr_address <= 32'b0;
            ddr_wdata <= 256'b0;
            ddr_wstrb <= 32'b0;
            ddr_rdata <= 128'b0;
            ddr_ack_r <= 1'b0;
            axi_to_cnt <= 12'd0;
            dbg_to_err <= 1'b0;
            dbg_to_state <= 3'd0;
            ddr_need_read <= 1'b0;
        end else begin
            ddr_ack_r <= 1'b0;
            case (ddr_state)
                DDR_IDLE: begin
                    axi_to_cnt <= 12'd0;
                    if (ddr_req_sync && ddr_init_done) begin
                        ddr_address <= req_address;
                        ddr_need_read <= ~req_write;
                        if (req_write) begin
                            // Actual write: use collected data and strobe
                            ddr_wstrb <= req_address[4] ? 32'hFFFF0000 : 32'h0000FFFF;
                            ddr_wdata <= req_address[4] ? {wbuf, 128'b0} : {128'b0, wbuf};
                            ddr_state <= DDR_WR_AW;
                        end else begin
                            // Read: issue the AXI read directly.  (An earlier
                            // version did a dummy write of 32 zero bytes with
                            // full strobe to "prime" the IP first - that write
                            // landed on the very address being read, so every
                            // read came back as zero.  Removed.)
                            ddr_state <= DDR_RD_AR;
                        end
                    end
                end
                DDR_WR_AW: begin
                    if (axiw_awready) begin
                        ddr_state <= DDR_WR_W;
                        axi_to_cnt <= 12'd0;
                    end else if (axi_to_cnt >= AXI_TO_LIMIT) begin
                        dbg_to_err  <= 1'b1;
                        dbg_to_state <= DDR_WR_AW;
                        ddr_state   <= DDR_ACK;
                    end else begin
                        axi_to_cnt <= axi_to_cnt + 1'b1;
                    end
                end
                DDR_WR_W: begin
                    if (axiw_wready) begin
                        axi_to_cnt <= 12'd0;
                        ddr_state <= DDR_ACK;
                    end else if (axi_to_cnt >= AXI_TO_LIMIT) begin
                        dbg_to_err  <= 1'b1;
                        dbg_to_state <= DDR_WR_W;
                        ddr_state   <= DDR_ACK;
                    end else begin
                        axi_to_cnt <= axi_to_cnt + 1'b1;
                    end
                end
                DDR_RD_AR: begin
                    if (axir_arready) begin
                        ddr_state <= DDR_RD_R;
                        axi_to_cnt <= 12'd0;
                    end else if (axi_to_cnt >= AXI_TO_LIMIT) begin
                        dbg_to_err  <= 1'b1;
                        dbg_to_state <= DDR_RD_AR;
                        ddr_state   <= DDR_ACK;
                    end else begin
                        axi_to_cnt <= axi_to_cnt + 1'b1;
                    end
                end
                DDR_RD_R: begin
                    if (axir_rvalid) begin
                        ddr_rdata <= ddr_address[4] ? axir_rdata[255:128] : axir_rdata[127:0];
                        ddr_state <= DDR_ACK;
                        axi_to_cnt <= 12'd0;
                    end else if (axi_to_cnt >= AXI_TO_LIMIT) begin
                        dbg_to_err  <= 1'b1;
                        dbg_to_state <= DDR_RD_R;
                        ddr_state   <= DDR_ACK;
                    end else begin
                        axi_to_cnt <= axi_to_cnt + 1'b1;
                    end
                end
                DDR_ACK: begin
                    ddr_ack_r <= 1'b1;
                    if (!ddr_req_sync) begin
                        ddr_ack_r <= 1'b0;
                        ddr_state <= DDR_IDLE;
                    end
                end
            endcase
        end
    end
    // ------------------------------------------------------------------
    // Cross-domain read-data bus (valid while ddr_ack_r is high and held)
    // ------------------------------------------------------------------
    wire [127:0] rd_data_from_ddr = ddr_rdata;

    // Debug bus
    assign dbg_ddr_state = ddr_state[2:0];
    assign dbg_arvalid   = axir_arvalid;
    assign dbg_arready   = axir_arready;
    assign dbg_rvalid    = axir_rvalid;

endmodule