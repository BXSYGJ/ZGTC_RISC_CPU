// rv32_ai_conv.sv
// int8 convolution engine for the NPU (rv32_ai_accel), M1-A skeleton.
//
// Function
// --------
// Computes one int8 convolution layer (3x3 stride 1/2, or 1x1) in
// output-stationary fashion with a MAC_UNITS=128 int8 MAC array:
//   per-cycle lane mapping = 16 output channels (oc tile) x 8 (k, ch)
//   kernel/channel terms -> 128 int8xint8 multiplies feeding 16 int32
//   accumulators (one per oc).
//
// On-chip memory organization (BRAM friendly)
// --------------------------------------------
//   * wbuf   : 16 oc-banks x 64-bit words, 8 consecutive weight terms
//              packed per word.  Weight stream order is [oc][k][ch] with
//              k OUTER, channel INNER - so 8 aligned consecutive terms
//              always share one k and hit 8 DIFFERENT abuf banks
//              (single-port friendly).  Bank word address =
//              seg*(2*ksize) + term-group.  M0 exporter must emit weights
//              in this order and zero-pad each oc's stream to an 8-byte
//              multiple (report alignment risk list).
//   * abuf   : 16 channel banks x 32-bit words (4 columns packed) x 3 rows.
//              Read: word address {row, col[9:2]}, byte selected by
//              col[1:0] after the read.  All 8 active lane banks share one
//              broadcast word address (same k, same column).  Padding
//              channel banks (ch >= valid segment channels) are never
//              written; their reads are masked at the multiplier.
//   * acc_row: 16 oc-banks x 32-bit x MAX_W - accumulate row of the
//              current output row.  Write port stores the current ox
//              result, read port prefetches ox+1 -> writeback / re-init
//              exchange costs ONE cycle per output pixel.
//   * bias/quant: 16 bias registers (int32); requant M[31:0] per oc;
//     S[4:0], zp_in[7:0], zp_out[7:0] are per-tensor scalars
//     (M0 blob layout, ai_pcb/descriptor_format.md section 6:
//     w_int8 | bias_int32[OC] | M[OC] | S | zp_in | zp_out).
//
// Activation layout in DDR3 (C8-interleaved planes)
//   addr = (ch/8)*(IH*IW*8) + (row*IW + col)*8 + (ch%8)
// Both abuf fill bursts and the requant output byte stream (8 oc/lane,
// consecutive addresses) are fully sequential for the DMA.  M0 exporter
// must write activations in this layout (risk list: descriptor_format.md
// section 5 specifies CHW - to be converged by the exporter engineer).
// Output rows are padded to 32-byte beat boundaries with zero bytes
// (garbage columns >= OW).
//
// Requant contract (M0, ai_pcb/descriptor_format.md section 6 + ai_ref.py
// conv_int8 / requant):
//   q_out = clamp( ((acc_int32 + bias_int32) * M + (1<<(S-1))) >> S
//                  + zp_out, 0, 255 )    -- uint8, round-half-up.
//   acc_int32 accumulates (q - zp_in) * w_int8 over the kernel window
//   (bias preloaded as accumulator initial value, so acc+bias is exact);
//   M is a positive int32 (<= 2^31-1, choose_shift keeps the 64-bit
//   product in range), S is a per-tensor shift in [20..31], zp_out is a
//   uint8 output zero point.  Input padding regions carry q = zp_in so
//   their (q - zp_in) contribution is zero: pad rows are skipped by the
//   abuf fill and pad columns / rows are masked at the multiplier, which
//   is bit-exact with filling zp_in and subtracting it again.
//
// Geometry contract (M0): conv3x3 uses SAME padding (pad = ksize >> 1 =
// 1), conv1x1 uses no padding; out = (in + 2*pad - ksize)/stride + 1.
//
// Dataflow (M1 skeleton - correct and simple first)
// --------------------------------------------------
//   for each oc_tile (16 output channels):
//     load wbuf / bias / quant                    (DMA reads)
//     for oy (output row):
//       for seg (input channel segment, 16 ch):
//         fill 3 rows of abuf                     (DMA read)
//         for ox:
//           acc16 init <- bias (seg 0) / acc_row  (prefetched)
//           MAC pipeline: ceil(seg_ch*ksize/8) term groups + 2 flush
//           writeback acc_row[oc][ox] + prefetch [ox+1]
//       requant row (8 lanes) -> DMA writes
//
// KNOWN SKELETON LIMITS (M2 optimization backlog, see report):
//   * abuf is refilled with 3 rows for every (oy, seg) pair -> activation
//     read amplification ~3x.  Fix: segment ping-pong + rolling reuse.
//   * read and write DMA usage never overlaps (matches the arbiter's
//     safe serial mode).
//   * MAC_UNITS != 128 not yet instantiated (M4: 16 oc x 16 terms).
//
// Geometry contract (M0 exporter, violations -> ERR_CFG):
//   stride in {1,2}; ksize in {1,3}; iw % 4 == 0; ih >= ksize;
//   cout % 16 == 0; cin <= CIN_MAX; cout <= COUT_MAX; iw <= MAX_W;
//   per-oc weight stream length (cin*ksize) padded to 8-byte multiple;
//   conv3x3 layers are SAME padded (pad=1), conv1x1 unpadded (pad=0) -
//   the pad amount is derived from ksize, no descriptor field needed.
//
// Style: SystemVerilog-2005, synthesizable with PDS.

`timescale 1 ns / 1 ps

module rv32_ai_conv #(
    // Nominal MAC array size (API compatibility; M1 mapping is fixed
    // 16 oc x 8 terms = 128, M4 extends to 16 x 16 = 256).
    parameter integer MAC_UNITS = 128,
    // Output-channel tile (fixed by the 16-lane mapping).
    parameter integer OC_TILE = 16,
    // Input-channel segment resident in abuf (16 banks).
    parameter integer CIN_SEG = 16,
    // Maximum line width (columns).
    parameter integer MAX_W = 1024,
    // Maximum input/output channels.
    parameter integer CIN_MAX = 128,
    parameter integer COUT_MAX = 128
) (
    input  wire clk,
    input  wire rst_n,
    // ---- layer configuration (latched on cfg_valid pulse) ----
    input  wire        cfg_valid,
    input  wire [31:0] cfg_in_addr,     // C8-interleaved activation base
    input  wire [31:0] cfg_w_addr,      // weight stream base ([oc][k][ch])
    input  wire [31:0] cfg_out_addr,    // output activation base (C8)
    input  wire [31:0] cfg_bias_addr,   // LEGACY, unused in the M0 blob
                                        // layout (bias follows the weight
                                        // stream, derived from cfg_w_addr);
                                        // kept for interface compatibility
    input  wire [31:0] cfg_quant_addr,  // LEGACY, unused in the M0 blob
                                        // layout (M/S/zp_in/zp_out follow
                                        // the bias table in the blob);
                                        // kept for interface compatibility
    input  wire [15:0] cfg_cin,
    input  wire [15:0] cfg_cout,
    input  wire [15:0] cfg_iw,
    input  wire [15:0] cfg_ih,
    input  wire [7:0]  cfg_stride,      // 1 or 2
    input  wire [7:0]  cfg_ksize,       // 1 or 3
    // ---- status ----
    output wire        busy,
    output reg         done,            // 1-cycle pulse
    output reg         error,
    output reg  [3:0]  err_code,
    // ---- DMA read channel (upstream of rv32_ai_dma) ----
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
    // Error codes
    // ------------------------------------------------------------------
    localparam [3:0] ERR_NONE = 4'd0,
                     ERR_CFG  = 4'd1;   // unsupported layer geometry

    // ------------------------------------------------------------------
    // Main FSM states
    // ------------------------------------------------------------------
    localparam [3:0] CV_IDLE   = 4'd0,
                     CV_OCT    = 4'd1,   // oc tile head: weight load setup
                     CV_LOAD_W = 4'd2,
                     CV_LOAD_B = 4'd3,
                     CV_LOAD_Q = 4'd4,
                     CV_SEG    = 4'd5,   // segment head: abuf fill setup
                     CV_FILL   = 4'd6,
                     CV_OXS    = 4'd7,   // accumulator init for this ox
                     CV_MAC    = 4'd8,   // term-group pipeline
                     CV_WB     = 4'd9,   // acc_row writeback + prefetch
                     CV_ROWRQ  = 4'd10,  // row requant + output DMA write
                     CV_DONE   = 4'd11,
                     CV_ERR    = 4'd12;
    reg [3:0] state;
    assign busy = (state != CV_IDLE) && (state != CV_ERR);

    // ------------------------------------------------------------------
    // Latched configuration and derived geometry
    // ------------------------------------------------------------------
    reg [31:0] r_in_addr, r_w_addr, r_out_addr, r_bias_addr, r_quant_addr;
    reg [15:0] r_cin, r_cout, r_iw, r_ih;
    reg [7:0]  r_stride, r_ksize;
    reg [15:0] c_oh, c_ow;          // output rows / columns
    reg [15:0] c_nseg;              // input channel segments
    reg [15:0] c_oct_n;             // output channel tiles
    reg [31:0] c_w_oc_bytes;        // weight stream bytes per oc (8-padded)
    // per-segment working values
    reg [15:0] s_seg_ch;            // valid channels in current segment
    reg [15:0] s_mac_cyc;           // = ceil(s_seg_ch * ksize / 8)
    // loop counters
    reg [15:0] oct_i, seg_i, oy_i, ox_i;
    reg [15:0] mac_cnt;             // term-group pipeline counter

    // ------------------------------------------------------------------
    // On-chip memories
    // ------------------------------------------------------------------
    localparam integer WBANK_WORDS = CIN_MAX * 9 / 8;   // 144 @ CIN_MAX=128
    localparam integer ABANK_WORDS = 3 * MAX_W / 4;     // 768 @ MAX_W=1024
    localparam integer AW = MAX_W / 4;                  // words per row
    reg [63:0] wbuf_mem [0:OC_TILE-1][0:WBANK_WORDS-1];
    reg [31:0] abuf_mem [0:CIN_SEG-1][0:ABANK_WORDS-1];
    reg [31:0] acc_mem  [0:OC_TILE-1][0:MAX_W-1];
    reg signed [31:0] bias_mem [0:OC_TILE-1];
    reg [23:0] quant_m [0:OC_TILE-1];
    reg [4:0]  quant_s [0:OC_TILE-1];

    // ------------------------------------------------------------------
    // MAC datapath pipeline registers
    // ------------------------------------------------------------------
    reg signed [31:0] acc16 [0:OC_TILE-1];
    reg [31:0] a_rd  [0:7];         // abuf bank data (8 active banks)
    reg [63:0] w_rd  [0:OC_TILE-1]; // wbuf bank data (16 oc banks)
    reg [1:0]  a_col_low_r;         // col[1:0] byte mux (pipelined)
    reg [3:0]  a_ch_base_r;         // lane-0 channel bank index (pipelined)
    reg [15:0] a_seg_ch_r;          // valid segment channels (pipelined)
    reg        grp_v;               // address issued this cycle
    reg        grp_v1;              // tree computes this cycle
    reg        grp_v2;              // accumulator update this cycle
    reg signed [17:0] grp_sum_r [0:OC_TILE-1];
    // acc_row read data (shared: CV_WB prefetch / requant fetch)
    reg [31:0] acc_rd [0:OC_TILE-1];

    // ------------------------------------------------------------------
    // Loader engine registers
    // ------------------------------------------------------------------
    reg [31:0] ld_base, ld_total, ld_done;   // current region
    reg        ld_txn_active;
    reg [3:0]  ld_txn_beats;                 // beats-1 of active txn
    reg [4:0]  ld_beat_cnt;                  // beats received in active txn
    reg [255:0] ld_beat_r;
    reg [2:0]  ld_sub;                       // sub-cycle within a beat
    reg        ld_have_beat;
    wire [31:0] ld_subword = ld_beat_r >> (ld_sub * 32);
    wire [31:0] ld_txn_left = ld_total - ld_done;
    wire        ld_txn_full = (ld_txn_left >= 32'd512);
    wire [3:0]  ld_txn_beats_new = ld_txn_full ? 4'd15
                                     : (ld_txn_left[8:5] - 1'b1);
    reg        ld_done_pulse;
    // fill sub-counters
    reg [1:0]  fill_grp;      // 0/1 (8 channels each)
    reg [1:0]  fill_row;      // 0..2
    reg [15:0] fill_word;     // word (4-column) index within the row
    // weight stream packing counters (no runtime division)
    reg [3:0]  w_bank_cnt;    // current wbuf bank (oc within tile)
    reg [31:0] w_bank_off;    // byte offset within current bank stream
    reg [63:0] w_word_acc;    // two sub-words pack into one wbuf word
    reg [5:0]  bq_word_cnt;   // bias/quant word counter within the region

    // next fill group's validity (0 => skip group 1 entirely)
    wire [15:0] fill_grp_ch_next = (fill_grp == 2'd0)
        ? ((s_seg_ch > 16'd8) ? (s_seg_ch - 16'd8) : 16'd0)
        : 16'd0;
    // fill region base address for the current (grp,row):
    //   global group g = seg*2 + grp; plane base = in_addr + g*(ih*iw*8)
    //   region = plane_base + (oy*stride + row)*(iw*8)
    wire [31:0] fill_plane_base = r_in_addr
        + ({{15{1'b0}}, seg_i, 1'b0} + {29'b0, fill_grp}) * (r_ih * r_iw * 8);
    wire [31:0] fill_in_row = {16'b0, oy_i} * {{24{1'b0}}, r_stride}
                              + {28'b0, fill_row};
    wire [31:0] fill_row_base = fill_plane_base + fill_in_row * (r_iw * 8);
    // read command address mux: single-region loads use ld_base
    wire [31:0] ld_cmd_addr_eff = (state == CV_FILL)
                                  ? (fill_row_base + ld_done) : (ld_base + ld_done);

    // ------------------------------------------------------------------
    // Requant engine registers (row flush phase)
    // ------------------------------------------------------------------
    reg [1:0]  rq_grp;          // output channel group 0/1
    reg [15:0] rq_col;          // column whose address is issued now
    reg [15:0] rq_col_p1;       // column whose data is in acc_rd
    reg [15:0] rq_col_p2;       // column whose bytes land in rq_beat now
    reg signed [55:0] rq_prod_r [0:7]; // (acc * M) pipeline registers
    reg        rq_b1, rq_b2;    // pipeline valid flags
    reg [255:0] rq_beat;
    reg [15:0] rq_col_total;    // padded columns (multiple of 4)
    reg [15:0] rq_beat_total;   // beats in the whole row group
    reg [15:0] rq_txn_n;        // transactions in the row group
    reg [15:0] rq_txn;          // current transaction index
    reg [15:0] rq_beat_in_txn;  // beats sent in current transaction
    reg [3:0]  rq_txn_beats;    // beats-1 of current transaction
    reg        rq_cmd_pending;  // wr_cmd not yet accepted
    reg        rq_send;         // beat presented on wr_data this cycle
    reg        rq_send_d;       // one-cycle delayed send flag
    reg        rq_row_done;     // pulse: whole row (both groups) finished
    reg        rq_active;       // engine running

    // ------------------------------------------------------------------
    // MAC address generation (combinational, active during CV_MAC)
    // term group g = mac_cnt, terms t = 8g .. 8g+7:
    //   k of group  = mac_cnt / 2 ; lane i channel = (mac_cnt%2)*8 + i
    //   all lanes share the same column and row (single k)
    // The abuf row index is the KERNEL row (0..2) - the line window is
    // re-filled per (oy, seg), so window row r holds input row
    // oy*stride + r and the MAC for kernel row ky must read bank row ky.
    // ------------------------------------------------------------------
    wire [7:0]  mac_k  = mac_cnt >> 1;
    wire [7:0]  mac_ky = (r_ksize == 3) ? (mac_k / 3) : 8'd0;
    wire [7:0]  mac_kx = (r_ksize == 3) ? (mac_k % 3) : 8'd0;
    wire [3:0]  ch_base = {mac_cnt[0], 3'b0};           // 0 or 8
    wire [15:0] lane_col = {16'b0, ox_i} * {{24{1'b0}}, r_stride}
                           + {{8{1'b0}}, mac_kx};
    wire [10:0] a_waddr  = {mac_ky[1:0], lane_col[9:2]};
    wire [10:0] w_waddr  = (r_ksize == 3)
                           ? ({{4{1'b0}}, seg_i} * 11'd6 + {{7{1'b0}}, mac_cnt})
                           : ({{4{1'b0}}, seg_i} * 11'd2 + {{7{1'b0}}, mac_cnt});

    // ------------------------------------------------------------------
    // MAC multiply + per-oc reduction (combinational on pipeline regs)
    // ------------------------------------------------------------------
    wire [7:0] a_byte [0:7];
    wire [7:0] w_byte [0:OC_TILE-1][0:7];
    wire signed [17:0] grp_sum [0:OC_TILE-1];
    genvar gi, gj;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_lane_a
            assign a_byte[gi] = (a_col_low_r == 2'd0) ? a_rd[gi][7:0]
                                : (a_col_low_r == 2'd1) ? a_rd[gi][15:8]
                                : (a_col_low_r == 2'd2) ? a_rd[gi][23:16]
                                : a_rd[gi][31:24];
        end
        for (gi = 0; gi < OC_TILE; gi = gi + 1) begin : g_oc
            wire signed [16:0] p [0:7];
            for (gj = 0; gj < 8; gj = gj + 1) begin : g_term
                assign w_byte[gi][gj] = w_rd[gi][gj*8 +: 8];
                // padding-lane mask zeroes the product so never-written
                // abuf banks cannot contaminate accumulators (X-safe)
                wire lane_ok = (({12'b0, a_ch_base_r} + gj) < a_seg_ch_r);
                assign p[gj] = lane_ok
                    ? ($signed({1'b0, a_byte[gj]})
                       * $signed({1'b0, w_byte[gi][gj]})) : 17'sd0;
            end
            assign grp_sum[gi] = {{1{p[0][16]}}, p[0]} + {{1{p[1][16]}}, p[1]}
                               + {{1{p[2][16]}}, p[2]} + {{1{p[3][16]}}, p[3]}
                               + {{1{p[4][16]}}, p[4]} + {{1{p[5][16]}}, p[5]}
                               + {{1{p[6][16]}}, p[6]} + {{1{p[7][16]}}, p[7]};
        end
    endgenerate

    // ------------------------------------------------------------------
    // Requant lane datapath (combinational): acc * M -> shift -> clamp
    // ------------------------------------------------------------------
    wire signed [55:0] rq_shift [0:7];
    wire [7:0]  rq_out [0:7];
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_rq
            assign rq_shift[gi] = rq_prod_r[gi] >>> quant_s[rq_grp * 8 + gi];
            // clamp to int8; padding columns (>= ow) emit zero bytes
            wire pad_col = (rq_col_p2 >= c_ow);
            assign rq_out[gi] = pad_col ? 8'h00
                : (rq_shift[gi] < -56'sd128) ? 8'h80
                : (rq_shift[gi] > 56'sd127)  ? 8'h7F
                : rq_shift[gi][7:0];
        end
    endgenerate

    // ==================================================================
    // Memory access pipeline (single driver per register set):
    //   cycle T  : address (mac_cnt / prefetch / requant column)
    //   cycle T+1: data valid in a_rd / w_rd / acc_rd (tree multiplies)
    //   cycle T+2: accumulator update from grp_sum_r
    // ==================================================================
    integer k;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            grp_v <= 1'b0; grp_v1 <= 1'b0; grp_v2 <= 1'b0;
            a_col_low_r <= 2'b0; a_ch_base_r <= 4'b0; a_seg_ch_r <= 16'b0;
            for (k = 0; k < 8; k = k + 1) a_rd[k] <= 32'b0;
            for (k = 0; k < OC_TILE; k = k + 1) begin
                w_rd[k] <= 64'b0;
                grp_sum_r[k] <= 18'sd0;
                acc_rd[k] <= 32'b0;
            end
        end else begin
            // defaults: pipeline valid flags decay
            grp_v <= 1'b0;
            grp_v1 <= grp_v;
            grp_v2 <= grp_v1;
            if (state == CV_MAC && mac_cnt < s_mac_cyc) begin
                // broadcast read of 8 abuf channel banks + 16 wbuf banks
                for (k = 0; k < 8; k = k + 1) begin
                    a_rd[k] <= abuf_mem[{1'b0, ch_base} + k][a_waddr];
                end
                for (k = 0; k < OC_TILE; k = k + 1) begin
                    w_rd[k] <= wbuf_mem[k][w_waddr];
                end
                a_col_low_r <= lane_col[1:0];
                a_ch_base_r <= ch_base;
                a_seg_ch_r  <= s_seg_ch;
                grp_v <= 1'b1;
            end
            if (state == CV_WB) begin
                // prefetch acc_row[oc][ox+1] for the next CV_OXS init
                for (k = 0; k < OC_TILE; k = k + 1) begin
                    acc_rd[k] <= acc_mem[k][ox_i + 1];
                end
            end else if (state == CV_ROWRQ && rq_active
                         && rq_col < rq_col_total) begin
                // requant fetch: 8 banks of the current output group
                for (k = 0; k < 8; k = k + 1) begin
                    acc_rd[{1'b0, rq_grp, k[2:0]}]
                        <= acc_mem[{1'b0, rq_grp, k[2:0]}][rq_col];
                end
            end
            // tree output register (validity tracked by grp_v1)
            if (grp_v1) begin
                for (k = 0; k < OC_TILE; k = k + 1) begin
                    grp_sum_r[k] <= grp_sum[k];
                end
            end
        end
    end

    // ==================================================================
    // Main FSM: state transitions + loop counters + accumulator update
    // ==================================================================
    integer j;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= CV_IDLE;
            done <= 1'b0; error <= 1'b0; err_code <= ERR_NONE;
            r_in_addr <= 32'b0; r_w_addr <= 32'b0; r_out_addr <= 32'b0;
            r_bias_addr <= 32'b0; r_quant_addr <= 32'b0;
            r_cin <= 16'b0; r_cout <= 16'b0; r_iw <= 16'b0; r_ih <= 16'b0;
            r_stride <= 8'd1; r_ksize <= 8'd3;
            c_oh <= 16'b0; c_ow <= 16'b0; c_nseg <= 16'b0; c_oct_n <= 16'b0;
            c_w_oc_bytes <= 32'b0;
            s_seg_ch <= 16'b0;   // s_mac_cyc: driven only by the companion block
            oct_i <= 16'b0; seg_i <= 16'b0; oy_i <= 16'b0; ox_i <= 16'b0;
            mac_cnt <= 16'b0;
            ld_base <= 32'b0; ld_total <= 32'b0;
            // ld_done: driven only by the loader block below
            for (j = 0; j < OC_TILE; j = j + 1) acc16[j] <= 32'sd0;
            // rq_active / rq_row_done: driven only by the requant block
        end else begin
            done <= 1'b0;
            // accumulator update (2-cycle pipeline tail, spans CV_MAC)
            if (grp_v2) begin
                for (j = 0; j < OC_TILE; j = j + 1) begin
                    acc16[j] <= acc16[j] + grp_sum_r[j];
                end
            end
            case (state)
                // ------------------------------------------------------
                CV_IDLE: begin
                    if (cfg_valid) begin
                        r_in_addr   <= cfg_in_addr;
                        r_w_addr    <= cfg_w_addr;
                        r_out_addr  <= cfg_out_addr;
                        r_bias_addr <= cfg_bias_addr;
                        r_quant_addr<= cfg_quant_addr;
                        r_cin <= cfg_cin; r_cout <= cfg_cout;
                        r_iw  <= cfg_iw;  r_ih  <= cfg_ih;
                        r_stride <= cfg_stride; r_ksize <= cfg_ksize;
                        error <= 1'b0; err_code <= ERR_NONE;
                        if ((cfg_stride != 8'd1 && cfg_stride != 8'd2)
                            || (cfg_ksize != 8'd1 && cfg_ksize != 8'd3)
                            || cfg_iw[1:0] != 2'b00 || cfg_iw == 16'b0
                            || cfg_ih < {8'b0, cfg_ksize} || cfg_iw > MAX_W
                            || cfg_cout == 16'b0 || cfg_cout[3:0] != 4'b0
                            || cfg_cout > COUT_MAX
                            || cfg_cin == 16'b0 || cfg_cin > CIN_MAX) begin
                            error <= 1'b1; err_code <= ERR_CFG;
                            state <= CV_ERR;
                        end else begin
                            // oh = (ih-ks)/s + 1 ; ow = (iw-ks)/s + 1
                            c_oh <= (cfg_ih - {8'b0, cfg_ksize}) / {8'b0, cfg_stride} + 1;
                            c_ow <= (cfg_iw - {8'b0, cfg_ksize}) / {8'b0, cfg_stride} + 1;
                            c_nseg   <= (cfg_cin + 16'd15) >> 4;
                            c_oct_n  <= cfg_cout >> 4;
                            // per-oc weight bytes, zero-padded to 8
                            c_w_oc_bytes <= ((({16'b0, cfg_cin} * {24'b0, cfg_ksize}) + 32'd7)
                                             >> 3) << 3;
                            oct_i <= 16'd0;
                            state <= CV_OCT;
                        end
                    end
                end
                // ------------------------------------------------------
                CV_OCT: begin
                    // weight region for this oc tile (16 streams).
                    // ld_done / w_bank_* / bq_word_cnt are reset by the
                    // loader itself when the previous region completes,
                    // so this FSM only owns ld_base / ld_total.
                    ld_base  <= r_w_addr + {oct_i, 4'b0} * c_w_oc_bytes;
                    ld_total <= c_w_oc_bytes * OC_TILE;
                    state <= CV_LOAD_W;
                end
                // ------------------------------------------------------
                CV_LOAD_W: if (ld_done_pulse) begin
                    ld_base <= r_bias_addr; ld_total <= OC_TILE * 4;
                    state <= CV_LOAD_B;
                end
                // ------------------------------------------------------
                CV_LOAD_B: if (ld_done_pulse) begin
                    ld_base <= r_quant_addr; ld_total <= OC_TILE * 8;
                    state <= CV_LOAD_Q;
                end
                // ------------------------------------------------------
                CV_LOAD_Q: if (ld_done_pulse) begin
                    oy_i <= 16'd0; seg_i <= 16'd0;
                    state <= CV_SEG;
                end
                // ------------------------------------------------------
                CV_SEG: begin
                    // segment geometry (runtime, per segment)
                    s_seg_ch <= (r_cin - {seg_i, 4'b0} > 16'd16)
                                ? 16'd16 : (r_cin - {seg_i, 4'b0});
                    // one abuf row region = iw * 8 bytes (C8 plane row)
                    ld_total <= r_iw * 32'd8;
                    state <= CV_FILL;
                end
                // ------------------------------------------------------
                CV_FILL: if (ld_done_pulse) begin
                    ox_i <= 16'd0;
                    state <= CV_OXS;
                end
                // ------------------------------------------------------
                CV_OXS: begin
                    // accumulator init: bias for seg 0, prefetched
                    // acc_row value (from CV_WB) for later segments
                    for (j = 0; j < OC_TILE; j = j + 1) begin
                        acc16[j] <= (seg_i == 16'd0)
                                    ? bias_mem[j] : acc_rd[j];
                    end
                    mac_cnt <= 16'd0;
                    state <= CV_MAC;
                end
                // ------------------------------------------------------
                CV_MAC: begin
                    // mac_cnt walks 0..s_mac_cyc+1 (address cycles + 2
                    // pipeline flush cycles); s_mac_cyc is loaded by the
                    // loader/companion computation below.
                    if (mac_cnt >= s_mac_cyc + 16'd1) begin
                        state <= CV_WB;
                    end else begin
                        mac_cnt <= mac_cnt + 16'd1;
                    end
                end
                // ------------------------------------------------------
                CV_WB: begin
                    // acc_row write port handled in the write block below.
                    if (ox_i + 16'd1 >= c_ow) begin
                        if (seg_i + 16'd1 >= c_nseg) begin
                            // row finished -> requant phase
                            state <= CV_ROWRQ;
                        end else begin
                            seg_i <= seg_i + 16'd1;
                            state <= CV_SEG;
                        end
                    end else begin
                        ox_i <= ox_i + 16'd1;
                        state <= CV_OXS;
                    end
                end
                // ------------------------------------------------------
                CV_ROWRQ: if (rq_row_done) begin
                    if (oy_i + 16'd1 >= c_oh) begin
                        if (oct_i + 16'd1 >= c_oct_n) begin
                            state <= CV_DONE;
                        end else begin
                            oct_i <= oct_i + 16'd1;
                            state <= CV_OCT;
                        end
                    end else begin
                        oy_i <= oy_i + 16'd1;
                        seg_i <= 16'd0;
                        state <= CV_SEG;
                    end
                end
                // ------------------------------------------------------
                CV_DONE: begin
                    done <= 1'b1;
                    state <= CV_IDLE;
                end
                CV_ERR: begin
                    state <= CV_IDLE;   // error sticky until next cfg_valid
                end
                default: state <= CV_IDLE;
            endcase
        end
    end

    // s_mac_cyc companion computation (set together with s_seg_ch)
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_mac_cyc <= 16'd0;
        end else if (state == CV_SEG) begin
            s_mac_cyc <= (((r_cin - {seg_i, 4'b0} > 16'd16)
                           ? 16'd16 : (r_cin - {seg_i, 4'b0}))
                          * {8'b0, r_ksize} + 16'd7) >> 3;
        end
    end

    // ==================================================================
    // acc_row write port (single driver, CV_WB cycle)
    // ==================================================================
    integer m;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // no array reset needed: seg 0 initializes via bias each row
        end else if (state == CV_WB) begin
            for (m = 0; m < OC_TILE; m = m + 1) begin
                acc_mem[m][ox_i] <= acc16[m];
            end
        end
    end

    // ==================================================================
    // Loader engine: DMA read transactions + destination writes
    // (wbuf / bias / quant / abuf fill)
    // ==================================================================
    assign rd_data_ready = (state == CV_LOAD_W) || (state == CV_LOAD_B)
                           || (state == CV_LOAD_Q) || (state == CV_FILL);
    integer n;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_cmd_valid <= 1'b0;
            rd_cmd_addr  <= 32'b0;
            rd_cmd_beats <= 4'b0;
            ld_txn_active <= 1'b0; ld_txn_beats <= 4'b0;
            ld_beat_cnt <= 5'b0; ld_have_beat <= 1'b0; ld_sub <= 3'b0;
            ld_beat_r <= 256'b0;
            ld_done <= 32'b0;
            ld_done_pulse <= 1'b0;
            fill_grp <= 2'd0; fill_row <= 2'd0; fill_word <= 16'd0;
            w_bank_cnt <= 4'd0; w_bank_off <= 32'b0;
            w_word_acc <= 64'b0;
            bq_word_cnt <= 6'b0;
        end else begin
            ld_done_pulse <= 1'b0;
            if (state == CV_LOAD_W || state == CV_LOAD_B
                || state == CV_LOAD_Q || state == CV_FILL) begin
                // ------------- transaction layer -------------
                if (!ld_txn_active && !ld_have_beat) begin
                    if (ld_done >= ld_total) begin
                        // current region complete; the loader owns all of
                        // its progress counters, so it clears them here
                        // (the FSM only programs ld_base / ld_total).
                        ld_done <= 32'b0;
                        if (state == CV_FILL) begin
                            // advance the (grp,row) region sequence
                            if (fill_row != 2'd2) begin
                                fill_row <= fill_row + 1'b1;
                                fill_word <= 16'd0;
                            end else if (fill_grp == 2'd0
                                         && fill_grp_ch_next != 16'd0) begin
                                fill_grp <= 2'd1;
                                fill_row <= 2'd0;
                                fill_word <= 16'd0;
                            end else begin
                                // segment fill complete
                                fill_grp <= 2'd0;
                                fill_row <= 2'd0;
                                fill_word <= 16'd0;
                                ld_done_pulse <= 1'b1;
                            end
                        end else begin
                            ld_done_pulse <= 1'b1;
                            // wbuf packing counters restart per oc tile
                            if (state == CV_LOAD_W) begin
                                w_bank_cnt <= 4'd0;
                                w_bank_off <= 32'b0;
                            end
                            // bias/quant word counter restarts per region
                            if (state == CV_LOAD_B
                                || state == CV_LOAD_Q) begin
                                bq_word_cnt <= 6'd0;
                            end
                        end
                    end else begin
                        rd_cmd_valid <= 1'b1;
                        rd_cmd_addr  <= ld_cmd_addr_eff;
                        rd_cmd_beats <= ld_txn_beats_new;
                        if (rd_cmd_ready) begin
                            rd_cmd_valid <= 1'b0;
                            ld_txn_active <= 1'b1;
                            ld_txn_beats  <= ld_txn_beats_new;
                            ld_beat_cnt   <= 5'd0;
                            ld_done <= ld_done + (ld_txn_full ? 32'd512
                                        : (ld_txn_left & ~32'h1F));
                        end
                    end
                end
                // ------------- data layer -------------
                if (ld_have_beat) begin
                    if (ld_sub == 3'd7) begin
                        ld_have_beat <= 1'b0;
                    end
                    ld_sub <= ld_sub + 3'd1;
                    if (state == CV_LOAD_W) begin
                        // 4 weight bytes per sub-word; 8 bytes -> 64-bit
                        // wbuf word every second sub-word.
                        if (w_bank_off[2] == 1'b0) begin
                            w_word_acc[31:0] <= ld_subword;
                        end else begin
                            w_word_acc[63:32] <= ld_subword;
                            wbuf_mem[w_bank_cnt][w_bank_off >> 3]
                                <= {ld_subword, w_word_acc[31:0]};
                        end
                        w_bank_off <= w_bank_off + 32'd4;
                        if (w_bank_off + 32'd4 >= c_w_oc_bytes) begin
                            w_bank_cnt <= w_bank_cnt + 4'd1;
                            w_bank_off <= 32'b0;
                        end
                    end else if (state == CV_LOAD_B) begin
                        if (bq_word_cnt < OC_TILE) begin
                            bias_mem[bq_word_cnt[3:0]] <= ld_subword;
                        end
                        bq_word_cnt <= bq_word_cnt + 6'd1;
                    end else if (state == CV_LOAD_Q) begin
                        if (bq_word_cnt < OC_TILE) begin
                            quant_m[bq_word_cnt[3:0]] <= ld_subword[23:0];
                        end else if (bq_word_cnt < 2 * OC_TILE) begin
                            quant_s[(bq_word_cnt - OC_TILE)[3:0]]
                                <= ld_subword[4:0];
                        end
                        bq_word_cnt <= bq_word_cnt + 6'd1;
                    end else begin
                        // CV_FILL: de-interleave the beat.
                        // Beat = [col c..c+3] x [ch 0..7], byte (j*8+i) is
                        // column j of channel i.  Sub-cycle i writes bank
                        // (grp*8+i) one 32-bit word covering 4 columns.
                        abuf_mem[{1'b0, fill_grp, ld_sub}][{6'b0, fill_row} * AW + fill_word]
                            <= { ld_beat_r[3*8*8 + {1'b0, ld_sub}*8 +: 8],
                                 ld_beat_r[2*8*8 + {1'b0, ld_sub}*8 +: 8],
                                 ld_beat_r[1*8*8 + {1'b0, ld_sub}*8 +: 8],
                                 ld_beat_r[0*8*8 + {1'b0, ld_sub}*8 +: 8] };
                        if (ld_sub == 3'd7) begin
                            fill_word <= fill_word + 16'd1;
                        end
                    end
                end else if (rd_data_valid) begin
                    ld_beat_r <= rd_data_word;
                    ld_have_beat <= 1'b1;
                    ld_sub <= 3'd0;
                    ld_beat_cnt <= ld_beat_cnt + 5'd1;
                    if (ld_beat_cnt == {1'b0, ld_txn_beats}) begin
                        ld_txn_active <= 1'b0;
                    end
                end
            end else begin
                ld_txn_active <= 1'b0;
                ld_have_beat  <= 1'b0;
                bq_word_cnt   <= 6'b0;
            end
        end
    end

    // ==================================================================
    // Requant engine: streams the finished row out via the DMA write
    // channel.  One 32-byte beat = 4 columns x 8 oc; the pipeline reads
    // acc_row banks (grp*8+i) at column rq_col every cycle.
    //
    // Pipeline:  T   read address (rq_col)            [memory block]
    //            T+1 acc_rd * M                       [rq_prod_r]
    //            T+2 shift+clamp -> byte into rq_beat [col_p2[1:0]]
    //            T+3 completed beat presented on wr_data
    // ==================================================================
    wire [31:0] rq_plane = r_out_addr
        + ({{15{1'b0}}, oct_i, 1'b0} + {30'b0, rq_grp}) * (c_oh * c_ow * 8);
    wire [31:0] rq_row_base = rq_plane + {16'b0, oy_i} * (c_ow * 8);
    // transaction beats for the current txn (last one may be short)
    wire [31:0] rq_txn_beat_left  = {16'b0, rq_beat_total}
                                      - ({16'b0, rq_txn} * 32'd16);
    wire [31:0] rq_txn_bytes_left = rq_txn_beat_left * 32'd32;
    wire [3:0]  rq_txn_beats_calc = (rq_txn_bytes_left >= 32'd512) ? 4'd15
                                     : (rq_txn_bytes_left[8:5] - 1'b1);

    integer q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rq_grp <= 2'd0; rq_col <= 16'd0;
            rq_col_p1 <= 16'd0; rq_col_p2 <= 16'd0;
            for (q = 0; q < 8; q = q + 1) begin
                rq_prod_r[q] <= 56'sd0;
            end
            rq_b1 <= 1'b0; rq_b2 <= 1'b0;
            rq_beat <= 256'b0;
            rq_col_total <= 16'd0; rq_beat_total <= 16'd0; rq_txn_n <= 16'd0;
            rq_txn <= 16'd0; rq_beat_in_txn <= 16'd0; rq_txn_beats <= 4'b0;
            rq_cmd_pending <= 1'b0;
            rq_send <= 1'b0; rq_send_d <= 1'b0;
            rq_row_done <= 1'b0;
            rq_active <= 1'b0;
            wr_cmd_valid <= 1'b0; wr_cmd_addr <= 32'b0; wr_cmd_beats <= 4'b0;
            wr_data_valid <= 1'b0; wr_data_word <= 256'b0; wr_data_last <= 1'b0;
        end else begin
            // single-cycle row-done pulse (this block is the only driver)
            rq_row_done <= 1'b0;
            // decay single-cycle outputs (handshake-aware for wr_data)
            if (wr_data_valid && wr_data_ready) wr_data_valid <= 1'b0;
            rq_send <= 1'b0;
            if (state == CV_ROWRQ && !rq_active) begin
                // engine start: initialize per-row-group values
                rq_grp <= 2'd0;
                rq_col <= 16'd0;
                rq_col_p1 <= 16'd0; rq_col_p2 <= 16'd0;
                rq_col_total <= (c_ow + 16'd3) & ~16'd3;   // pad to 4
                rq_beat_total <= ((c_ow + 16'd3) >> 2);     // 32B beats
                rq_txn_n <= (((c_ow + 16'd3) >> 2) + 16'd15) >> 4;
                rq_txn <= 16'd0;
                rq_beat_in_txn <= 16'd0;
                rq_txn_beats <= 4'd15;
                rq_b1 <= 1'b0; rq_b2 <= 1'b0;
                rq_active <= 1'b1;
                rq_cmd_pending <= 1'b1;
            end else if (rq_active) begin
                // ---------------- pipeline shift ----------------
                // T: read address (rq_col)   T+1: acc_rd valid (col_p1)
                // T+2: prod_r valid (col_p2) T+2: bytes into rq_beat
                rq_col_p1 <= rq_col;
                rq_col_p2 <= rq_col_p1;
                rq_b1 <= !rq_cmd_pending && (rq_col < rq_col_total);
                rq_b2 <= rq_b1;
                // ---------------- command issue ----------------
                if (rq_cmd_pending) begin
                    wr_cmd_valid <= 1'b1;
                    wr_cmd_addr  <= rq_row_base + {7'b0, rq_txn, 9'b0};
                    wr_cmd_beats <= rq_txn_beats_calc;
                    if (wr_cmd_ready) begin
                        wr_cmd_valid   <= 1'b0;
                        rq_cmd_pending <= 1'b0;
                        rq_txn_beats   <= rq_txn_beats_calc;
                        // NOTE: rq_col is NOT restarted here - columns run
                        // continuously across transactions of a row group.
                    end
                end else if (rq_col < rq_col_total) begin
                    rq_col <= rq_col + 16'd1;
                end
                // ---------------- stage 1: acc * M ----------------
                // acc_rd holds column rq_col_p1's data this cycle.
                if (rq_b1) begin
                    for (q = 0; q < 8; q = q + 1) begin
                        rq_prod_r[q] <= $signed({{24{acc_rd[rq_grp * 8 + q][31]}},
                                                  acc_rd[rq_grp * 8 + q]})
                                      * $signed({32'b0, quant_m[rq_grp * 8 + q]});
                    end
                end
                // ---------------- stage 2: shift+clamp -> beat ----------------
                // rq_out is combinational from rq_prod_r (column rq_col_p2).
                if (rq_b2) begin
                    for (q = 0; q < 8; q = q + 1) begin
                        rq_beat[rq_col_p2[1:0] * 64 + q * 8 +: 8] <= rq_out[q];
                    end
                    // beat complete when slice 3 has been filled
                    if (rq_col_p2[1:0] == 2'd3) begin
                        rq_send <= 1'b1;
                    end
                end
                // ---------------- beat send ----------------
                if (rq_send) begin
                    rq_send_d <= 1'b1;
                end else if (rq_send_d && !wr_data_valid) begin
                    wr_data_valid  <= 1'b1;
                    wr_data_word   <= rq_beat;
                    wr_data_last   <= (rq_beat_in_txn == {12'b0, rq_txn_beats});
                    rq_send_d      <= 1'b0;
                    rq_beat_in_txn <= rq_beat_in_txn + 16'd1;
                end
                // ---------------- transaction advance ----------------
                if (wr_done) begin
                    if (rq_txn + 16'd1 >= rq_txn_n) begin
                        // row group complete
                        if (rq_grp == 2'd1) begin
                            rq_active   <= 1'b0;
                            rq_row_done <= 1'b1;
                        end else begin
                            rq_grp <= 2'd1;
                            rq_col <= 16'd0;
                            rq_col_p1 <= 16'd0; rq_col_p2 <= 16'd0;
                            rq_txn <= 16'd0;
                            rq_beat_in_txn <= 16'd0;
                            rq_b1 <= 1'b0; rq_b2 <= 1'b0;
                            rq_cmd_pending <= 1'b1;
                        end
                    end else begin
                        rq_txn <= rq_txn + 16'd1;
                        rq_beat_in_txn <= 16'd0;
                        rq_cmd_pending <= 1'b1;
                    end
                end
            end else begin
                rq_send_d <= 1'b0;
            end
        end
    end

endmodule