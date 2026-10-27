// rv32_ai_silu.sv
// SiLU (x * sigmoid(x)) elementwise engine for the NPU, M1-A skeleton.
//
// Function
// --------
// Applies silu to a region of int8 activations stored in DDR3 and streams
// the result to a separate output region.
//
// Computation per element (int8 in, int8 out):
//   sig = LUT[in]        unsigned 0..128 (sigmoid quantized, 128 == 1.0)
//   out = clamp8( (in * sig) >> 7 )
//
// LUT
// ---
// LUT_DEPTH entries (default 1024).  Index = the int8 input sign-extended
// to 10 bits (negative inputs map to [768,1023], positive to [0,255]).
// The table is loaded over the DMA from lut_addr (1024 bytes) when the
// descriptor provides a non-zero lut_addr; otherwise a piecewise-linear
// power-on approximation is used (bring-up only - the M0-exported table
// is mandatory for bit-exact verification).
//
// Pipeline (4 lanes, one 32-bit input sub-word per cycle):
//   T    in_r  <= in_beat[sub]            (consume)
//   T+1  lut_d <= lut_mem[idx(in_r)]      (table read)
//   T+2  prod_r <= in_r * lut_d           (multiply)
//   T+3  out_beat[sub_p] <= bytes         (shift+clamp, assemble)
// Input and output beats use separate registers, so a newly received DMA
// beat never collides with the assembly of the previous one (the pipeline
// is 3 cycles deep but beats are spaced 9 cycles: 8 sub-words + 1 receive
// bubble - OPT-TODO M2: skid register to remove the bubble).
//
// Geometry contract: total_len % 32 == 0 (M0 pads regions to beats).
//
// Style: SystemVerilog-2005, synthesizable with PDS.

`timescale 1 ns / 1 ps

module rv32_ai_silu #(
    parameter integer LUT_DEPTH = 1024
) (
    input  wire clk,
    input  wire rst_n,
    // ---- control ----
    input  wire        start,       // 1-cycle pulse
    input  wire [31:0] in_addr,     // source region (int8 activations)
    input  wire [31:0] out_addr,    // destination region
    input  wire [31:0] lut_addr,    // LUT base (0 = built-in approximation)
    input  wire [31:0] total_len,   // region length in bytes (32B aligned)
    output wire        busy,
    output reg         done,        // 1-cycle pulse
    output reg         error,
    // ---- DMA read channel ----
    output reg         rd_cmd_valid,
    input  wire        rd_cmd_ready,
    output reg  [31:0] rd_cmd_addr,
    output reg  [3:0]  rd_cmd_beats,
    input  wire        rd_data_valid,
    output wire        rd_data_ready,
    input  wire [255:0] rd_data_word,
    input  wire        rd_data_last,
    // ---- DMA write channel ----
    output reg         wr_cmd_valid,
    input  wire        wr_cmd_ready,
    output reg  [31:0] wr_cmd_addr,
    output reg  [3:0]  wr_cmd_beats,
    output reg         wr_data_valid,
    input  wire        wr_data_ready,
    output reg  [255:0] wr_data_word,
    output reg         wr_data_last,
    input  wire        wr_done
);
    // ------------------------------------------------------------------
    // LUT memory (BRAM inferred)
    // ------------------------------------------------------------------
    reg [7:0] lut_mem [0:LUT_DEPTH-1];
    integer li;
    initial begin : lut_init
        // Piecewise-linear sigmoid approximation, quantized 0..128.
        // Index low byte reinterpreted as int8 = the input value.
        for (li = 0; li < LUT_DEPTH; li = li + 1) begin
            if ($signed(li[7:0]) <= -8) lut_mem[li] = 8'd0;
            else if ($signed(li[7:0]) >= 8) lut_mem[li] = 8'd128;
            else lut_mem[li] = ($signed(li[7:0]) + 8) * 8;
        end
    end

    // ------------------------------------------------------------------
    // FSM
    // ------------------------------------------------------------------
    localparam [2:0] SL_IDLE = 3'd0,
                     SL_LUT  = 3'd1,   // optional table load
                     SL_RUN  = 3'd2,   // stream through the pipeline
                     SL_DONE = 3'd3,
                     SL_ERR  = 3'd4;
    reg [2:0]  state;
    assign busy = (state != SL_IDLE) && (state != SL_ERR);

    // ---- read transaction layer ----
    reg [31:0] rd_pos;               // bytes consumed by transactions
    reg        rd_txn_active;
    reg [3:0]  rd_txn_beats;
    reg [4:0]  rd_beat_cnt;
    // ---- beat / sub-word layer ----
    reg [255:0] in_beat;
    reg        have_beat;
    reg [2:0]  sub;                  // sub-word being consumed
    // ---- element pipeline ----
    reg [31:0] in_r;                 // stage A: four input bytes
    reg [31:0] in_p;                 // stage A delayed (pairs with lut_d)
    reg [7:0]  lut_d0, lut_d1, lut_d2, lut_d3;  // stage B: sigmoids
    reg [31:0] prod_r;               // stage C: four 16-bit products
    reg        v_a, v_b, v_c;        // stage valid flags
    reg [2:0]  sub_p;                // sub-word index pipelined to stage C
    // ---- output beat / write channel ----
    reg [255:0] out_beat;
    reg         out_beat_full;       // assembly complete, present next cycle
    reg         out_beat_send;
    reg [31:0] wr_pos;               // bytes committed by write transactions
    reg        wr_txn_active;
    reg [3:0]  wr_txn_beats;
    reg [4:0]  wr_beat_cnt;
    reg        out_txn_pending;      // write command not yet accepted
    reg        wr_last_txn;
    // ---- LUT load ----
    reg [10:0] lut_byte_cnt;         // LUT bytes loaded

    wire [31:0] rd_left = total_len - rd_pos;
    wire        rd_full = (rd_left >= 32'd512);
    wire [3:0]  rd_beats_new = rd_full ? 4'd15 : (rd_left[8:5] - 1'b1);
    wire [31:0] wr_left = total_len - wr_pos;
    wire        wr_full = (wr_left >= 32'd512);
    wire [3:0]  wr_beats_new = wr_full ? 4'd15 : (wr_left[8:5] - 1'b1);

    assign rd_data_ready = (state == SL_LUT) || (state == SL_RUN);

    // ------------------------------------------------------------------
    // Combinational datapath
    // ------------------------------------------------------------------
    wire [9:0] lut_idx0 = {{2{in_r[7]}},  in_r[7:0]};
    wire [9:0] lut_idx1 = {{2{in_r[15]}}, in_r[15:8]};
    wire [9:0] lut_idx2 = {{2{in_r[23]}}, in_r[23:16]};
    wire [9:0] lut_idx3 = {{2{in_r[31]}}, in_r[31:24]};
    // stage B products: signed in x unsigned sig (zero-extended, signed)
    // (uses in_p - the in_r value of the previous cycle - so that each
    //  product pairs the input bytes with THEIR OWN sigmoid values)
    wire signed [15:0] p0 = $signed({{8{in_p[7]}},  in_p[7:0]})
                             * $signed({8'b0, lut_d0});
    wire signed [15:0] p1 = $signed({{8{in_p[15]}}, in_p[15:8]})
                             * $signed({8'b0, lut_d1});
    wire signed [15:0] p2 = $signed({{8{in_p[23]}}, in_p[23:16]})
                             * $signed({8'b0, lut_d2});
    wire signed [15:0] p3 = $signed({{8{in_p[31]}}, in_p[31:24]})
                             * $signed({8'b0, lut_d3});
    // stage C: >> 7 and clamp to int8
    wire signed [15:0] s0 = p0 >>> 7;
    wire signed [15:0] s1 = p1 >>> 7;
    wire signed [15:0] s2 = p2 >>> 7;
    wire signed [15:0] s3 = p3 >>> 7;
    wire [7:0] b0 = (s0 < -16'sd128) ? 8'h80 : (s0 > 16'sd127) ? 8'h7F : s0[7:0];
    wire [7:0] b1 = (s1 < -16'sd128) ? 8'h80 : (s1 > 16'sd127) ? 8'h7F : s1[7:0];
    wire [7:0] b2 = (s2 < -16'sd128) ? 8'h80 : (s2 > 16'sd127) ? 8'h7F : s2[7:0];
    wire [7:0] b3 = (s3 < -16'sd128) ? 8'h80 : (s3 > 16'sd127) ? 8'h7F : s3[7:0];
    // LUT load write index: base + sub*4 + {0..3}
    wire [10:0] lut_wbase = {1'b0, lut_byte_cnt[9:0]} + {4'b0, sub, 2'b00};

    // ------------------------------------------------------------------
    // Main FSM
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= SL_IDLE;
            done <= 1'b0; error <= 1'b0;
            rd_pos <= 32'b0; wr_pos <= 32'b0;
            rd_txn_active <= 1'b0; rd_txn_beats <= 4'b0; rd_beat_cnt <= 5'b0;
            in_beat <= 256'b0; have_beat <= 1'b0; sub <= 3'b0;
            in_r <= 32'b0; in_p <= 32'b0; prod_r <= 32'b0;
            lut_d0 <= 8'b0; lut_d1 <= 8'b0; lut_d2 <= 8'b0; lut_d3 <= 8'b0;
            v_a <= 1'b0; v_b <= 1'b0; v_c <= 1'b0; sub_p <= 3'b0;
            out_beat <= 256'b0; out_beat_full <= 1'b0; out_beat_send <= 1'b0;
            wr_txn_active <= 1'b0; wr_txn_beats <= 4'b0; wr_beat_cnt <= 5'b0;
            out_txn_pending <= 1'b0; wr_last_txn <= 1'b0;
            lut_byte_cnt <= 11'd0;
            rd_cmd_valid <= 1'b0; rd_cmd_addr <= 32'b0; rd_cmd_beats <= 4'b0;
            wr_cmd_valid <= 1'b0; wr_cmd_addr <= 32'b0; wr_cmd_beats <= 4'b0;
            wr_data_valid <= 1'b0; wr_data_word <= 256'b0; wr_data_last <= 1'b0;
        end else begin
            done <= 1'b0;
            if (wr_data_valid && wr_data_ready) wr_data_valid <= 1'b0;
            out_beat_send <= 1'b0;

            // ---------------- element pipeline ----------------
            // T: in_r latched; T+1: lut_d; T+2: prod_r; T+3: bytes out
            v_a <= 1'b0;
            v_b <= v_a;
            v_c <= v_b;
            if (v_a) begin
                lut_d0 <= lut_mem[lut_idx0];
                lut_d1 <= lut_mem[lut_idx1];
                lut_d2 <= lut_mem[lut_idx2];
                lut_d3 <= lut_mem[lut_idx3];
                in_p   <= in_r;      // keep the operands of stage B paired
            end
            if (v_b) begin
                prod_r <= {p3, p2, p1, p0};
                sub_p  <= sub;
            end
            if (v_c) begin
                out_beat[{sub_p, 2'b00} * 8 +: 32] <= {b3, b2, b1, b0};
                if (sub_p == 3'd7) begin
                    out_beat_full <= 1'b1;
                end
            end

            case (state)
                SL_IDLE: begin
                    if (start) begin
                        error <= 1'b0;
                        rd_pos <= 32'b0; wr_pos <= 32'b0;
                        rd_txn_active <= 1'b0; rd_beat_cnt <= 5'b0;
                        wr_txn_active <= 1'b0; wr_beat_cnt <= 5'b0;
                        have_beat <= 1'b0; sub <= 3'b0;
                        out_txn_pending <= 1'b0; out_beat_full <= 1'b0;
                        v_a <= 1'b0; v_b <= 1'b0; v_c <= 1'b0;
                        lut_byte_cnt <= 11'd0;
                        if (total_len[4:0] != 5'b0 || total_len == 32'b0) begin
                            error <= 1'b1;   // region not beat-aligned
                            state <= SL_ERR;
                        end else if (lut_addr != 32'b0) begin
                            state <= SL_LUT;
                        end else begin
                            state <= SL_RUN;
                        end
                    end
                end
                // ------------------------------------------------------
                SL_LUT: begin
                    if (!rd_txn_active && !have_beat) begin
                        if (lut_byte_cnt >= LUT_DEPTH) begin
                            state <= SL_RUN;
                        end else begin
                            rd_cmd_valid <= 1'b1;
                            rd_cmd_addr  <= lut_addr + {21'b0, lut_byte_cnt};
                            rd_cmd_beats <= 4'd15;      // 512 B chunk
                            if (rd_cmd_ready) begin
                                rd_cmd_valid <= 1'b0;
                                rd_txn_active <= 1'b1;
                                rd_txn_beats  <= 4'd15;
                                rd_beat_cnt   <= 5'd0;
                            end
                        end
                    end
                    if (have_beat) begin
                        // four LUT entries per sub-word
                        lut_mem[lut_wbase[9:0] + 10'd0] <= in_beat[sub * 32 +: 8];
                        lut_mem[lut_wbase[9:0] + 10'd1] <= in_beat[sub * 32 + 8 +: 8];
                        lut_mem[lut_wbase[9:0] + 10'd2] <= in_beat[sub * 32 + 16 +: 8];
                        lut_mem[lut_wbase[9:0] + 10'd3] <= in_beat[sub * 32 + 24 +: 8];
                        if (sub == 3'd7) begin
                            have_beat <= 1'b0;
                            lut_byte_cnt <= lut_byte_cnt + 11'd32;
                        end
                        sub <= sub + 3'd1;
                    end else if (rd_data_valid) begin
                        in_beat <= rd_data_word;
                        have_beat <= 1'b1;
                        sub <= 3'b0;
                        rd_beat_cnt <= rd_beat_cnt + 5'd1;
                        if (rd_beat_cnt == {1'b0, rd_txn_beats}) begin
                            rd_txn_active <= 1'b0;
                        end
                    end
                end
                // ------------------------------------------------------
                SL_RUN: begin
                    // ---- read side: transaction layer ----
                    if (!rd_txn_active && !have_beat) begin
                        if (rd_pos >= total_len) begin
                            // source drained; pipeline flush continues
                        end else begin
                            rd_cmd_valid <= 1'b1;
                            rd_cmd_addr  <= in_addr + rd_pos;
                            rd_cmd_beats <= rd_beats_new;
                            if (rd_cmd_ready) begin
                                rd_cmd_valid <= 1'b0;
                                rd_txn_active <= 1'b1;
                                rd_txn_beats  <= rd_beats_new;
                                rd_beat_cnt   <= 5'd0;
                                rd_pos <= rd_pos + (rd_full ? 32'd512
                                            : (rd_left & ~32'h1F));
                            end
                        end
                    end
                    // ---- read side: beat consumption ----
                    if (have_beat) begin
                        in_r <= in_beat[sub * 32 +: 32];
                        v_a  <= 1'b1;
                        if (sub == 3'd7) begin
                            have_beat <= 1'b0;
                        end
                        sub <= sub + 3'd1;
                    end else if (rd_data_valid) begin
                        in_beat <= rd_data_word;
                        have_beat <= 1'b1;
                        sub <= 3'b0;
                        rd_beat_cnt <= rd_beat_cnt + 5'd1;
                        if (rd_beat_cnt == {1'b0, rd_txn_beats}) begin
                            rd_txn_active <= 1'b0;
                        end
                    end
                    // ---- write side: first / next transaction ----
                    if (!out_txn_pending && !wr_txn_active
                        && rd_pos != 32'b0 && wr_pos < total_len) begin
                        out_txn_pending <= 1'b1;
                    end
                    if (out_txn_pending) begin
                        wr_cmd_valid <= 1'b1;
                        wr_cmd_addr  <= out_addr + wr_pos;
                        wr_cmd_beats <= wr_beats_new;
                        if (wr_cmd_ready) begin
                            wr_cmd_valid   <= 1'b0;
                            out_txn_pending <= 1'b0;
                            wr_txn_active  <= 1'b1;
                            wr_txn_beats   <= wr_beats_new;
                            wr_beat_cnt    <= 5'd0;
                            wr_last_txn    <= (wr_pos
                                + (wr_full ? 32'd512 : (wr_left & ~32'h1F))
                                >= total_len);
                        end
                    end
                    // ---- write side: beat layer ----
                    if (out_beat_full) begin
                        out_beat_full <= 1'b0;
                        out_beat_send <= 1'b1;
                    end else if (out_beat_send && !wr_data_valid) begin
                        wr_data_valid <= 1'b1;
                        wr_data_word  <= out_beat;
                        wr_data_last  <= (wr_beat_cnt == {1'b0, wr_txn_beats});
                        wr_beat_cnt   <= wr_beat_cnt + 5'd1;
                    end
                    // ---- write side: transaction done ----
                    if (wr_done) begin
                        wr_txn_active <= 1'b0;
                        wr_pos <= wr_pos + (wr_full ? 32'd512
                                    : (wr_left & ~32'h1F));
                        if (wr_last_txn && rd_pos >= total_len
                            && !have_beat && !v_a && !v_b && !v_c
                            && !out_beat_full && !out_beat_send
                            && !wr_data_valid) begin
                            state <= SL_DONE;
                        end
                    end
                end
                // ------------------------------------------------------
                SL_DONE: begin
                    done <= 1'b1;
                    state <= SL_IDLE;
                end
                SL_ERR: begin
                    state <= SL_IDLE;
                end
                default: state <= SL_IDLE;
            endcase
        end
    end

endmodule