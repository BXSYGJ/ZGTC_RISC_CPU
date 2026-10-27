// rv32_ai_accel.sv
// NPU top level for the ZGTC RISC CPU SoC (M1-A skeleton).
//
// Function
// --------
// Hosts the NPU control plane (MMIO register file at 0x10000600..0x1000061F,
// CPU clock domain) and the data plane (descriptor engine, convolution
// engine, SiLU engine and a shared AXI DMA, core_clk = 125 MHz domain).
// The two domains are bridged with the same proven CDC pattern as
// rv32_burst_ddr3.sv: 2-FF synchronizers plus 4-phase level handshakes.
//
// MMIO register map (offsets from 0x10000600)
// --------------------------------------------
//   0x00 CTRL        W: bit0=start, bit1=soft_reset
//                    R: bit0=busy (start/soft_reset read back as 0)
//   0x04 STATUS      R: bit0=busy, bit1=done, bit2=error, bit3=dma_error,
//                       bits[7:4]=err_code, bits[31:16]=desc_idx
//   0x08 DESC_HEAD   RW: descriptor chain head address (DDR3, 32B aligned)
//   0x0C DESC_COUNT  RW: descriptor count (chain-walk limit, 16 bits used)
//   0x10 OUT_HEAD    RW: output region base (informational for software)
//   0x14 OUT_COUNT   R:  32-bit words written back by the DMA (accumulated)
//   0x18 IRQ         RW: bit0=irq_enable (cpu domain), bit1=write-1-clear
//                        of the core done flag; R: {done_sync, enable}
//   0x1C PERF_CYCLE  R:  core_clk cycles between start and done
//
// Descriptor format (16 x 32-bit words, 64 B, chained via word14)
// ---------------------------------------------------------------
//   word0  [7:0]  layer type: 0 conv3x3_s1, 1 conv3x3_s2, 2 conv1x1,
//                          3 silu, 4 maxpool2x2_s2, 5 maxpool5x5_s1,
//                          6 concat(memcpy), 7 upsample2x,
//                          8 detect_prefilter, 15 nop
//          [31:8] reserved
//   word1  INPUT address (C8-interleaved activation base, conv/silu)
//   word2  WEIGHT address (stream [oc][k][ch], conv only)
//   word3  OUTPUT address (C8-interleaved, conv/silu)
//   word4  [15:0] CIN / [31:16] COUT            (conv)
//          (silu uses word9 for its region length - see word9 note)
//   word5  [15:0] IW  / [31:16] IH              (conv)
//   word6  [7:0]  stride / [15:8] ksize         (conv)
//   word7  BIAS address (16 x int32)            (conv)
//   word8  QUANT address (16 x {M,S}) / LUT address (silu)
//   word9  silu total region length in bytes (matches M0 OUT_BYTES for
//          elementwise silu where input and output regions are equal)
//   word10..13 reserved
//   word14 NEXT_DESC_ADDR (0 = end of chain)
//   word15 reserved
// NOTE: word4..word13 semantics are provisional until the M0 deliverable
// ai_pcb/descriptor_format.md lands - see the report risk list.  The M0
// exporter (ai_pcb/export_yolo_deploy.py DESC_FORMAT_MD) currently defines
// word4/5/6 as IN_H/IN_W/IN_CH/OUT_CH/OUT_H/OUT_W geometry, so a word-map
// realignment pass is required before M1-B bring-up (see report section E).
//
// Layer types 4..8 are dispatched but not implemented in M1: the engine
// records ERR_UNSUPPORTED in STATUS and SKIPS the layer (chain continues)
// so partial networks stay debuggable.  Type 15 (nop) passes through.
//
// Engine scheduling is strictly sequential (descriptor engine, then one
// compute engine at a time, all sharing one DMA instance) which matches
// the arbiter's safe serial mode.
//
// irq_npu is a CPU-domain level output (done_sticky && irq_enable); the
// SoC integrates it into irq_external (this module only provides it).
//
// Style: SystemVerilog-2005, synthesizable with PDS.

`timescale 1 ns / 1 ps

module rv32_ai_accel #(
    // Passed down to the convolution engine (see rv32_ai_conv).
    parameter integer MAC_UNITS = 128,
    // SiLU LUT depth (see rv32_ai_silu).
    parameter integer SILU_LUT_DEPTH = 1024
) (
    // ---- CPU clock domain (MMIO slave, rv32_peripherals style) ----
    input  wire clk,               // cpu_clk (e.g. 27 MHz)
    input  wire rst_n,
    input  wire        req_valid,
    output wire        req_ready,
    input  wire [31:0] req_address,
    input  wire        req_write,
    input  wire [31:0] req_data,
    input  wire [3:0]  req_strobe,
    output reg         rsp_valid,
    input  wire        rsp_ready,
    output reg  [31:0] rsp_data,
    output reg         rsp_error,
    // ---- interrupt (cpu domain) ----
    output wire        irq_npu,
    // ---- core clock domain (125 MHz) ----
    input  wire core_clk,
    input  wire core_rst_n,
    // ---- AXI master port (to rv32_axi_arbiter master B) ----
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
    input  wire        axir_rvalid,
    // ---- debug (core domain) ----
    output wire [3:0]  dbg_de_state,
    output wire [3:0]  dbg_dma_error
);
    // ------------------------------------------------------------------
    // MMIO address decode (segment 0x10000600 assumed pre-demuxed by the
    // SoC; the module still verifies the segment to fail loudly).
    // 0x10000600 >> 5 = 0x0800030 (27-bit word-address of the segment).
    // ------------------------------------------------------------------
    wire seg_hit = (req_address[31:5] == 27'h0800_030);
    wire [4:0] mmio_off = req_address[4:0];
    wire [31:0] write_mask = {{8{req_strobe[3]}}, {8{req_strobe[2]}},
                              {8{req_strobe[1]}}, {8{req_strobe[0]}}};
    wire request_fire = req_valid && req_ready;

    // ==================================================================
    // CPU domain: transaction serialization + CDC channels
    // ==================================================================
    // One MMIO transaction in flight at a time: a write latches a payload
    // and waits for the 4-phase handshake; a read waits for the snapshot.
    reg        wr_req_r;          // level: write payload pending
    reg [37:0] wr_pay;            // {write=1, off[4:0], data[31:0]}
    reg        rd_req_r;          // level: read snapshot pending
    reg [4:0]  rd_off;
    reg [12:0] mmio_to_cnt;       // handshake watchdog (4096 cpu cycles)
    localparam [12:0] MMIO_TO_LIMIT = 13'd4096;

    assign req_ready = !rsp_valid && !wr_req_r && !rd_req_r;

    // ---- 2FF synchronizers (cpu side) ----
    reg wr_ack_ff1, wr_ack_ff2;
    reg snap_ack_ff1, snap_ack_ff2;
    reg [191:0] snap_hold_ff1, snap_hold_ff2;
    reg done_st_ff1, done_st_ff2;

    // ---- cpu-domain local registers ----
    reg irq_enable;
    wire done_sticky_cpu = done_st_ff2;
    assign irq_npu = irq_enable && done_sticky_cpu;

    // ---- write strobe helpers ----
    wire irq_wr = request_fire && req_write && seg_hit && (mmio_off == 5'h18);
    wire irq_en_next = irq_wr ? ((irq_enable & ~write_mask[0])
                                 | (req_data[0] & write_mask[0])) : irq_enable;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rsp_valid <= 1'b0; rsp_data <= 32'b0; rsp_error <= 1'b0;
            wr_req_r <= 1'b0; wr_pay <= 37'b0;
            rd_req_r <= 1'b0; rd_off <= 5'b0;
            mmio_to_cnt <= 13'b0;
            irq_enable <= 1'b0;
            wr_ack_ff1 <= 1'b0; wr_ack_ff2 <= 1'b0;
            snap_ack_ff1 <= 1'b0; snap_ack_ff2 <= 1'b0;
            snap_hold_ff1 <= 192'b0; snap_hold_ff2 <= 192'b0;
            done_st_ff1 <= 1'b0; done_st_ff2 <= 1'b0;
        end else begin
            // default: clear the response once accepted
            if (rsp_valid && rsp_ready) rsp_valid <= 1'b0;
            // 2FF clocking
            wr_ack_ff1 <= wr_ack_r;        // core domain signal
            wr_ack_ff2 <= wr_ack_ff1;
            snap_ack_ff1 <= snap_ack_r;    // core domain signal
            snap_ack_ff2 <= snap_ack_ff1;
            snap_hold_ff1 <= snap_hold;    // stable while ack in flight
            snap_hold_ff2 <= snap_hold_ff1;
            done_st_ff1 <= done_sticky;    // core domain signal
            done_st_ff2 <= done_st_ff1;
            // local irq enable register (byte-lane write semantics)
            irq_enable <= irq_en_next;
            // watchdog
            if (wr_req_r || rd_req_r) begin
                mmio_to_cnt <= mmio_to_cnt + 13'd1;
            end else begin
                mmio_to_cnt <= 13'b0;
            end
            // ---- write channel ----
            if (!wr_req_r && request_fire && req_write && seg_hit) begin
                wr_req_r <= 1'b1;
                wr_pay <= {1'b1, mmio_off, req_data & write_mask};
            end else if (wr_req_r && wr_ack_ff2) begin
                // write acknowledged by the core -> respond to the CPU
                wr_req_r <= 1'b0;
                rsp_valid <= 1'b1;
                rsp_error <= 1'b0;
                rsp_data <= 32'b0;
            end else if (wr_req_r && mmio_to_cnt >= MMIO_TO_LIMIT) begin
                wr_req_r <= 1'b0;
                rsp_valid <= 1'b1;
                rsp_error <= 1'b1;
                rsp_data <= 32'b0;
            end
            // ---- read channel ----
            if (!rd_req_r && !wr_req_r && request_fire && !req_write
                && seg_hit) begin
                rd_req_r <= 1'b1;
                rd_off <= mmio_off;
            end else if (rd_req_r && snap_ack_ff2) begin
                rd_req_r <= 1'b0;
                rsp_valid <= 1'b1;
                rsp_error <= 1'b0;
                // snapshot field mux
                case (rd_off)
                    5'h00: rsp_data <= {31'b0, snap_hold_ff2[0]};   // busy
                    5'h04: rsp_data <= snap_hold_ff2[31:0];
                    5'h08: rsp_data <= snap_hold_ff2[63:32];
                    5'h0C: rsp_data <= snap_hold_ff2[95:64];
                    5'h10: rsp_data <= snap_hold_ff2[127:96];
                    5'h14: rsp_data <= snap_hold_ff2[159:128];
                    5'h18: rsp_data <= {30'b0, done_sticky_cpu, irq_enable};
                    5'h1C: rsp_data <= snap_hold_ff2[191:160];
                    default: begin
                        rsp_error <= 1'b1;
                        rsp_data <= 32'b0;
                    end
                endcase
            end else if (rd_req_r && mmio_to_cnt >= MMIO_TO_LIMIT) begin
                rd_req_r <= 1'b0;
                rsp_valid <= 1'b1;
                rsp_error <= 1'b1;
                rsp_data <= 32'b0;
            end
            // ---- segment miss: immediate error response ----
            if (request_fire && !seg_hit) begin
                rsp_valid <= 1'b1;
                rsp_error <= 1'b1;
                rsp_data <= 32'b0;
            end
        end
    end

    // ==================================================================
    // Core domain: CDC receive + register file + descriptor engine
    // ==================================================================
    // ---- 2FF synchronizers (core side) ----
    reg wr_req_ff1, wr_req_ff2;
    reg snap_req_ff1, snap_req_ff2;
    wire wr_req_sync = wr_req_ff2;
    wire snap_req_sync = snap_req_ff2;

    // ---- handshake state (core side, NOT reset by soft reset) ----
    reg wr_ack_r, wr_seen;
    reg snap_ack_r, snap_seen;

    // ---- soft reset (clears run state, keeps configuration) ----
    reg [3:0] soft_rst_cnt;
    wire rst_run_n = core_rst_n && (soft_rst_cnt == 4'd0);

    // ---- configuration registers (kept across soft reset) ----
    reg [31:0] desc_head, out_head;
    reg [15:0] desc_count;

    // ---- run-state registers (cleared by soft reset) ----
    reg        run_busy, done_sticky, err_flag;
    reg [3:0]  err_code;
    reg [15:0] desc_idx;
    reg [31:0] out_word_cnt;
    reg [31:0] perf_cycle;
    reg        start_pending;

    // error code encoding
    localparam [3:0] EC_NONE = 4'd0, EC_UNSUP = 4'd1, EC_CONV = 4'd2,
                     EC_SILU = 4'd3, EC_DMA = 4'd4;

    // ---- descriptor buffer ----
    reg [31:0] desc_buf [0:15];

    // ---- descriptor engine FSM ----
    localparam [3:0] DE_IDLE = 4'd0, DE_FETCH = 4'd1, DE_DECODE = 4'd2,
                     DE_CONV = 4'd3, DE_SILU = 4'd4, DE_NEXT = 4'd5,
                     DE_DONE = 4'd6, DE_ERR = 4'd7;
    reg [3:0] de_state;
    reg [31:0] desc_addr;
    reg        de_rd_cmd_valid;

    reg [1:0]  de_beat_cnt;   // beats received (0..1)
    // engine select for the shared DMA
    localparam [1:0] SEL_FETCH = 2'd0, SEL_CONV = 2'd1, SEL_SILU = 2'd2;
    reg [1:0] engine_sel;
    // conv/silu control pulses
    reg conv_cfg_valid, silu_start;
    // dma write transaction bookkeeping for OUT_COUNT
    reg [3:0] dma_wr_beats_lat;
    wire dma_wr_fire;         // write command accepted
    wire dma_wr_done;         // write transaction finished

    // ---- descriptor field decode (conv) ----
    wire [7:0]  dw_type = desc_buf[0][7:0];
    wire [15:0] dw_stride = desc_buf[6][7:0];
    wire [15:0] dw_ksize = {8'b0, desc_buf[6][15:8]};

    // ---- engine interconnect wires ----
    wire conv_busy, conv_done, conv_error;
    wire conv_rd_cmd_valid, conv_rd_cmd_ready;
    wire [31:0] conv_rd_cmd_addr;
    wire [3:0]  conv_rd_cmd_beats;
    wire conv_rd_data_valid, conv_rd_data_ready;
    wire [255:0] conv_rd_data_word;
    wire conv_rd_data_last;
    wire conv_wr_cmd_valid, conv_wr_cmd_ready;
    wire [31:0] conv_wr_cmd_addr;
    wire [3:0]  conv_wr_cmd_beats;
    wire conv_wr_data_valid, conv_wr_data_ready;
    wire [255:0] conv_wr_data_word;
    wire conv_wr_data_last;

    wire silu_busy, silu_done, silu_error;
    wire silu_rd_cmd_valid, silu_rd_cmd_ready;
    wire [31:0] silu_rd_cmd_addr;
    wire [3:0]  silu_rd_cmd_beats;
    wire silu_rd_data_valid, silu_rd_data_ready;
    wire [255:0] silu_rd_data_word;
    wire silu_rd_data_last;
    wire silu_wr_cmd_valid, silu_wr_cmd_ready;
    wire [31:0] silu_wr_cmd_addr;
    wire [3:0]  silu_wr_cmd_beats;
    wire silu_wr_data_valid, silu_wr_data_ready;
    wire [255:0] silu_wr_data_word;

    wire silu_wr_data_last;

    // ---- DMA upstream (muxed; combinational, driven by assign below) ----
    wire dma_rd_cmd_valid;
    wire dma_rd_cmd_ready;
    wire [31:0] dma_rd_cmd_addr;
    wire [3:0]  dma_rd_cmd_beats;
    wire dma_rd_data_valid, dma_rd_data_ready;
    wire [255:0] dma_rd_data_word;
    wire dma_rd_data_last;
    wire dma_wr_cmd_valid;
    wire dma_wr_cmd_ready;
    wire [31:0] dma_wr_cmd_addr;
    wire [3:0]  dma_wr_cmd_beats;
    wire dma_wr_data_valid;
    wire dma_wr_data_ready;
    wire [255:0] dma_wr_data_word;
    wire dma_wr_data_last;
    wire [3:0] dma_error;

    // ---- snapshot bus (core side) ----
    // STATUS word layout (bits [31:0] of the snapshot):
    //   [0] busy, [1] done, [2] error, [3] dma_error (any), [7:4] err_code,
    //   [15:8] reserved, [31:16] desc_idx.
    wire [191:0] snap_bus = {
        perf_cycle,                                  // [191:160]
        out_word_cnt,                                // [159:128]
        out_head,                                    // [127:96]
        {16'b0, desc_count},                         // [95:64]
        desc_head,                                   // [63:32]
        {desc_idx, 8'b0, err_code[3:0], |dma_error,  // [31:0]
         err_flag, done_sticky, run_busy}
    };
    reg [191:0] snap_hold;

    // ------------------------------------------------------------------
    // Core domain: CDC write channel application + soft reset trigger
    // ------------------------------------------------------------------
    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            wr_req_ff1 <= 1'b0; wr_req_ff2 <= 1'b0;
            snap_req_ff1 <= 1'b0; snap_req_ff2 <= 1'b0;
            wr_ack_r <= 1'b0; wr_seen <= 1'b0;
            snap_ack_r <= 1'b0; snap_seen <= 1'b0;
            desc_head <= 32'b0; out_head <= 32'b0; desc_count <= 16'b0;
            soft_rst_cnt <= 4'd0;
        end else begin
            // 2FF clocking
            wr_req_ff1 <= wr_req_r;      // cpu domain signal
            wr_req_ff2 <= wr_req_ff1;
            snap_req_ff1 <= rd_req_r;    // cpu domain signal
            snap_req_ff2 <= snap_req_ff1;
            // soft reset counter (triggered by the write channel below)
            if (soft_rst_cnt != 4'd0) begin
                soft_rst_cnt <= soft_rst_cnt - 4'd1;
            end
            // ---- write handshake (4-phase) ----
            if (wr_req_sync && !wr_seen) begin
                wr_seen <= 1'b1;
                wr_ack_r <= 1'b1;
                // apply the register write (wr_pay = {write, off, data})
                case (wr_pay[36:32])
                    5'h00: begin
                        if (wr_pay[1]) soft_rst_cnt <= 4'd8; // soft_reset
                        // bit0=start handled in the run-state block
                    end
                    5'h08: desc_head <= wr_pay[31:0];
                    5'h0C: desc_count <= wr_pay[15:0];
                    5'h10: out_head  <= wr_pay[31:0];
                    default: ;   // 0x18 W1C handled in the run-state block
                endcase
                // start / W1C pulses are produced combinationally below
            end else if (!wr_req_sync) begin
                wr_seen <= 1'b0;
                wr_ack_r <= 1'b0;
            end
            // ---- snapshot handshake (4-phase) ----
            if (snap_req_sync && !snap_seen) begin
                snap_seen <= 1'b1;
                snap_ack_r <= 1'b1;
                snap_hold <= snap_bus;   // latched: stable during transfer
            end else if (!snap_req_sync) begin
                snap_seen <= 1'b0;
                snap_ack_r <= 1'b0;
            end
        end
    end

    // start pulse: CTRL.bit0 write applied via the CDC write channel
    // (wr_pay[31:0] is the MMIO write data, so bit0 = wr_pay[0])
    wire start_apply = wr_req_sync && !wr_seen && wr_pay[36:32] == 5'h00
                       && wr_pay[0];
    // done W1C pulse: IRQ.bit1 write (data bit1 = wr_pay[1])
    wire done_w1c = wr_req_sync && !wr_seen && wr_pay[36:32] == 5'h18
                    && wr_pay[1];

    // ------------------------------------------------------------------
    // Core domain: run state + descriptor engine
    // ------------------------------------------------------------------
    integer di;
    always @(posedge core_clk or negedge rst_run_n) begin
        if (!rst_run_n) begin
            run_busy <= 1'b0; done_sticky <= 1'b0;
            err_flag <= 1'b0; err_code <= EC_NONE;
            desc_idx <= 16'b0; out_word_cnt <= 32'b0; perf_cycle <= 32'b0;
            start_pending <= 1'b0;
            de_state <= DE_IDLE; desc_addr <= 32'b0;
            de_rd_cmd_valid <= 1'b0; de_beat_cnt <= 2'b0;
            engine_sel <= SEL_FETCH;
            conv_cfg_valid <= 1'b0; silu_start <= 1'b0;
            for (di = 0; di < 16; di = di + 1) desc_buf[di] <= 32'b0;
        end else begin
            conv_cfg_valid <= 1'b0;
            silu_start <= 1'b0;
            // start pulse from the CDC write channel
            if (start_apply) start_pending <= 1'b1;
            // done W1C
            if (done_w1c) done_sticky <= 1'b0;
            // performance counter
            if (run_busy) perf_cycle <= perf_cycle + 32'd1;
            // OUT_COUNT accounting: accumulate written 32-bit words
            if (dma_wr_done) begin
                out_word_cnt <= out_word_cnt
                    + ({28'b0, dma_wr_beats_lat} + 32'd1) * 32'd8;
            end

            case (de_state)
                DE_IDLE: begin
                    engine_sel <= SEL_FETCH;
                    if (start_pending) begin
                        start_pending <= 1'b0;
                        run_busy <= 1'b1;
                        err_flag <= 1'b0; err_code <= EC_NONE;
                        desc_idx <= 16'd0;
                        desc_addr <= desc_head;
                        perf_cycle <= 32'd0;
                        de_state <= DE_FETCH;
                    end
                end
                // ----------------------------------------------------
                // Fetch a 64-byte descriptor (2 beats) into desc_buf.
                // One 256-bit beat carries 8 sub-words; beat 0 fills
                // desc_buf[7:0], beat 1 fills desc_buf[15:8].  The fetch
                // read path is always ready (dma_rd_data_ready muxes to
                // 1 in SEL_FETCH), so every offered beat is consumed.
                // ----------------------------------------------------
                DE_FETCH: begin
                    engine_sel <= SEL_FETCH;
                    if (!de_rd_cmd_valid) begin
                        de_rd_cmd_valid <= 1'b1;
                    end else if (dma_rd_cmd_ready) begin
                        de_rd_cmd_valid <= 1'b0;
                    end
                    if (dma_rd_data_valid && dma_rd_data_ready) begin
                        for (di = 0; di < 8; di = di + 1) begin
                            desc_buf[de_beat_cnt * 8 + di]
                                <= dma_rd_data_word[di * 32 +: 32];
                        end
                        de_beat_cnt <= de_beat_cnt + 2'd1;
                        if (de_beat_cnt == 2'd1) begin
                            de_state <= DE_DECODE;   // both beats received
                        end
                    end
                end
                // ----------------------------------------------------
                DE_DECODE: begin
                    // beat counter restarts for the next descriptor fetch
                    de_beat_cnt <= 2'd0;
                    case (dw_type)
                        8'd0, 8'd1, 8'd2: begin
                            conv_cfg_valid <= 1'b1;
                            engine_sel <= SEL_CONV;
                            de_state <= DE_CONV;
                        end
                        8'd3: begin
                            silu_start <= 1'b1;
                            engine_sel <= SEL_SILU;
                            de_state <= DE_SILU;
                        end
                        8'd15: begin
                            de_state <= DE_NEXT;
                        end
                        default: begin
                            // types 4..8: unsupported in M1, skip layer
                            if (!err_flag) begin
                                err_flag <= 1'b1;
                                err_code <= EC_UNSUP;
                            end
                            de_state <= DE_NEXT;
                        end
                    endcase
                end
                // ----------------------------------------------------
                DE_CONV: begin
                    if (conv_done) begin
                        if (conv_error) begin
                            err_flag <= 1'b1;
                            err_code <= EC_CONV;
                            de_state <= DE_ERR;
                        end else begin
                            de_state <= DE_NEXT;
                        end
                    end
                end
                // ----------------------------------------------------
                DE_SILU: begin
                    if (silu_done) begin
                        if (silu_error) begin
                            err_flag <= 1'b1;
                            err_code <= EC_SILU;
                            de_state <= DE_ERR;
                        end else begin
                            de_state <= DE_NEXT;
                        end
                    end
                end
                // ----------------------------------------------------
                DE_NEXT: begin
                    if (desc_buf[14] == 32'b0
                        || desc_idx + 16'd1 >= desc_count) begin
                        de_state <= DE_DONE;
                    end else begin
                        desc_addr <= desc_buf[14];
                        desc_idx <= desc_idx + 16'd1;
                        de_state <= DE_FETCH;
                    end
                end
                // ----------------------------------------------------
                DE_DONE: begin
                    run_busy <= 1'b0;
                    done_sticky <= 1'b1;
                    de_state <= DE_IDLE;
                end
                DE_ERR: begin
                    run_busy <= 1'b0;
                    done_sticky <= 1'b1;
                    de_state <= DE_IDLE;
                end
                default: de_state <= DE_IDLE;
            endcase
        end
    end

    // ==================================================================
    // Shared DMA upstream multiplexer (fetch / conv / silu)
    // ==================================================================
    // Read command: the fetch engine's command is purely combinational
    // (address = desc_addr, beats = 1 for the 64-byte descriptor), the
    // compute engines drive their own command registers.
    assign dma_rd_cmd_valid = (engine_sel == SEL_CONV) ? conv_rd_cmd_valid
                            : (engine_sel == SEL_SILU) ? silu_rd_cmd_valid
                            : de_rd_cmd_valid;
    assign dma_rd_cmd_addr  = (engine_sel == SEL_CONV) ? conv_rd_cmd_addr
                            : (engine_sel == SEL_SILU) ? silu_rd_cmd_addr
                            : desc_addr;
    assign dma_rd_cmd_beats = (engine_sel == SEL_CONV) ? conv_rd_cmd_beats
                            : (engine_sel == SEL_SILU) ? silu_rd_cmd_beats
                            : 4'd1;   // fetch: 2 beats = 64 B descriptor
    assign conv_rd_cmd_ready = (engine_sel == SEL_CONV) && dma_rd_cmd_ready;
    assign silu_rd_cmd_ready = (engine_sel == SEL_SILU) && dma_rd_cmd_ready;
    wire de_rd_cmd_ready = (engine_sel == SEL_FETCH) && dma_rd_cmd_ready;

    // Read data (all consumers drain at their own pace)
    assign conv_rd_data_valid = (engine_sel == SEL_CONV) && dma_rd_data_valid;
    assign silu_rd_data_valid = (engine_sel == SEL_SILU) && dma_rd_data_valid;
    assign dma_rd_data_ready = (engine_sel == SEL_CONV) ? conv_rd_data_ready
                              : (engine_sel == SEL_SILU) ? silu_rd_data_ready
                              : 1'b1;   // fetch drains below
    assign conv_rd_data_word = dma_rd_data_word;
    assign silu_rd_data_word = dma_rd_data_word;
    assign conv_rd_data_last = dma_rd_data_last;
    assign silu_rd_data_last = dma_rd_data_last;

    // Write channel (fetch never writes)
    assign dma_wr_cmd_valid = (engine_sel == SEL_CONV) ? conv_wr_cmd_valid
                            : (engine_sel == SEL_SILU) ? silu_wr_cmd_valid
                            : 1'b0;
    assign dma_wr_cmd_addr  = (engine_sel == SEL_CONV) ? conv_wr_cmd_addr
                            : (engine_sel == SEL_SILU) ? silu_wr_cmd_addr
                            : 32'b0;
    assign dma_wr_cmd_beats = (engine_sel == SEL_CONV) ? conv_wr_cmd_beats
                            : (engine_sel == SEL_SILU) ? silu_wr_cmd_beats
                            : 4'b0;
    assign dma_wr_data_valid = (engine_sel == SEL_CONV) ? conv_wr_data_valid
                             : (engine_sel == SEL_SILU) ? silu_wr_data_valid
                             : 1'b0;
    assign dma_wr_data_word  = (engine_sel == SEL_CONV) ? conv_wr_data_word
                             : (engine_sel == SEL_SILU) ? silu_wr_data_word
                             : 256'b0;
    assign dma_wr_data_last  = (engine_sel == SEL_CONV) ? conv_wr_data_last
                             : (engine_sel == SEL_SILU) ? silu_wr_data_last
                             : 1'b0;
    assign conv_wr_cmd_ready = (engine_sel == SEL_CONV) && dma_wr_cmd_ready;
    assign silu_wr_cmd_ready = (engine_sel == SEL_SILU) && dma_wr_cmd_ready;
    assign conv_wr_data_ready = (engine_sel == SEL_CONV) && dma_wr_data_ready;
    assign silu_wr_data_ready = (engine_sel == SEL_SILU) && dma_wr_data_ready;
    assign dma_wr_fire = dma_wr_cmd_valid && dma_wr_cmd_ready;
    assign dma_wr_done = dma_wr_done_i;

    // OUT_COUNT beat latching
    always @(posedge core_clk or negedge rst_run_n) begin
        if (!rst_run_n) begin
            dma_wr_beats_lat <= 4'b0;
        end else if (dma_wr_fire) begin
            dma_wr_beats_lat <= dma_wr_cmd_beats;
        end
    end

    // ==================================================================
    // Component instances
    // ==================================================================
    wire dma_wr_done_i;

    rv32_ai_dma u_dma (
        .core_clk       (core_clk),
        .core_rst_n     (rst_run_n),
        .rd_cmd_valid   (dma_rd_cmd_valid),
        .rd_cmd_ready   (dma_rd_cmd_ready),
        .rd_cmd_addr    (dma_rd_cmd_addr),
        .rd_cmd_beats   (dma_rd_cmd_beats),
        .rd_data_valid  (dma_rd_data_valid),
        .rd_data_ready  (dma_rd_data_ready),
        .rd_data_word   (dma_rd_data_word),
        .rd_data_last   (dma_rd_data_last),
        .wr_cmd_valid   (dma_wr_cmd_valid),
        .wr_cmd_ready   (dma_wr_cmd_ready),
        .wr_cmd_addr    (dma_wr_cmd_addr),
        .wr_cmd_beats   (dma_wr_cmd_beats),
        .wr_data_valid  (dma_wr_data_valid),
        .wr_data_ready  (dma_wr_data_ready),
        .wr_data_word   (dma_wr_data_word),
        .wr_data_last   (dma_wr_data_last),
        .wr_done        (dma_wr_done_i),
        .dma_error      (dma_error),
        .axiw_awaddr    (axiw_awaddr),
        .axiw_awuser_ap (axiw_awuser_ap),
        .axiw_awuser_id (axiw_awuser_id),
        .axiw_awlen     (axiw_awlen),
        .axiw_awvalid   (axiw_awvalid),
        .axiw_awready   (axiw_awready),
        .axiw_wdata     (axiw_wdata),
        .axiw_wstrb     (axiw_wstrb),
        .axiw_wvalid    (axiw_wvalid),
        .axiw_wready    (axiw_wready),
        .axiw_wusero_id (axiw_wusero_id),
        .axiw_wusero_last(axiw_wusero_last),
        .axir_araddr    (axir_araddr),
        .axir_aruser_ap (axir_aruser_ap),
        .axir_aruser_id (axir_aruser_id),
        .axir_arlen     (axir_arlen),
        .axir_arvalid   (axir_arvalid),
        .axir_arready   (axir_arready),
        .axir_rdata     (axir_rdata),
        .axir_rid       (axir_rid),
        .axir_rlast     (axir_rlast),
        .axir_rvalid    (axir_rvalid)
    );

    rv32_ai_conv #(.MAC_UNITS(MAC_UNITS)) u_conv (
        .clk            (core_clk),
        .rst_n          (rst_run_n),
        .cfg_valid      (conv_cfg_valid),
        .cfg_in_addr    (desc_buf[1]),
        .cfg_w_addr     (desc_buf[2]),
        .cfg_out_addr   (desc_buf[3]),
        .cfg_bias_addr  (desc_buf[7]),
        .cfg_quant_addr (desc_buf[8]),
        .cfg_cin        (desc_buf[4][15:0]),
        .cfg_cout       (desc_buf[4][31:16]),
        .cfg_iw         (desc_buf[5][15:0]),
        .cfg_ih         (desc_buf[5][31:16]),
        .cfg_stride     (dw_stride[7:0]),
        .cfg_ksize      (dw_ksize[7:0]),
        .busy           (conv_busy),
        .done           (conv_done),
        .error          (conv_error),
        .err_code       (),
        .rd_cmd_valid   (conv_rd_cmd_valid),
        .rd_cmd_ready   (conv_rd_cmd_ready),
        .rd_cmd_addr    (conv_rd_cmd_addr),
        .rd_cmd_beats   (conv_rd_cmd_beats),
        .rd_data_valid  (conv_rd_data_valid),
        .rd_data_ready  (conv_rd_data_ready),
        .rd_data_word   (conv_rd_data_word),
        .rd_data_last   (conv_rd_data_last),
        .wr_cmd_valid   (conv_wr_cmd_valid),
        .wr_cmd_ready   (conv_wr_cmd_ready),
        .wr_cmd_addr    (conv_wr_cmd_addr),
        .wr_cmd_beats   (conv_wr_cmd_beats),
        .wr_data_valid  (conv_wr_data_valid),
        .wr_data_ready  (conv_wr_data_ready),
        .wr_data_word   (conv_wr_data_word),
        .wr_data_last   (conv_wr_data_last),
        .wr_done        (dma_wr_done_i)
    );

    rv32_ai_silu #(.LUT_DEPTH(SILU_LUT_DEPTH)) u_silu (
        .clk            (core_clk),
        .rst_n          (rst_run_n),
        .start          (silu_start),
        .in_addr        (desc_buf[1]),
        .out_addr       (desc_buf[3]),
        .lut_addr       (desc_buf[8]),
        .total_len      (desc_buf[9]),
        .busy           (silu_busy),
        .done           (silu_done),
        .error          (silu_error),
        .rd_cmd_valid   (silu_rd_cmd_valid),
        .rd_cmd_ready   (silu_rd_cmd_ready),
        .rd_cmd_addr    (silu_rd_cmd_addr),
        .rd_cmd_beats   (silu_rd_cmd_beats),
        .rd_data_valid  (silu_rd_data_valid),
        .rd_data_ready  (silu_rd_data_ready),
        .rd_data_word   (silu_rd_data_word),
        .rd_data_last   (silu_rd_data_last),
        .wr_cmd_valid   (silu_wr_cmd_valid),
        .wr_cmd_ready   (silu_wr_cmd_ready),
        .wr_cmd_addr    (silu_wr_cmd_addr),
        .wr_cmd_beats   (silu_wr_cmd_beats),
        .wr_data_valid  (silu_wr_data_valid),
        .wr_data_ready  (silu_wr_data_ready),
        .wr_data_word   (silu_wr_data_word),
        .wr_data_last   (silu_wr_data_last),
        .wr_done        (dma_wr_done_i)
    );

    // ==================================================================
    // Debug outputs
    // ==================================================================
    assign dbg_de_state  = de_state;
    assign dbg_dma_error = dma_error;

endmodule