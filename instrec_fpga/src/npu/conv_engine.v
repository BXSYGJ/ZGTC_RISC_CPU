// ---------------------------------------------------------------------------
// conv_engine.v -- parameterized 3x3 stride-1 pad-1 INT8 convolution engine
//
// Task      : T-M2-03 conv_engine (INT8 CNN NPU numeric core)
// Bit truth : scripts/golden_pipeline.py  conv2d_int8() + requant_u8()
// Contract  : scripts/outputs/layer_contract.json (per-layer shapes,
//             bias_int32, M Q0.31, shift, zp_in/zp_out, padding_value)
//
// Golden dataflow mirrored here (conv2d_int8, bit-level):
//     acc_s32[c] = sum_(cin,dy,dx) (x_u8[cin] - zp_in) * w_s8[c][cin][dy][dx]
//                  + bias_int32[c]
//     y_u8[c]    = requant_unit(acc_s32[c], M[c], shift[c], zp_out)
// Storage-domain note (bit-level critical): the line buffers keep the
// RAW u8 container values; the zp_in subtraction happens live at the
// MAC beat (x_eff = pad ? 0 : x_u8 - zp_in, a signed 9-bit value).
// Pre-shifting to s8 at ingress would OVERFLOW on loud samples:
// conv1 zp_in = 49 with x_u8 up to 255 gives x - zp = 206 > s8 max
// 127 (the REQ-INF-007 full-scale saturation path), so the u8 store +
// live subtract is the only bit-exact mapping of the golden padded
// array (which is u8 zero-padded with padding_value == zp_in == 49
// and then reduced by zp_in). Pad-1 cells read as 0 in the signed
// domain, i.e. exactly the neutral value; the pad inject is done
// read-side (row/col window guard returns 0), which is bit-identical
// to pre-filling zero rows and zero column phases (tasks.md T-M2-03
// wording) without spending buffer slots on them.
// Accumulator headroom check: |x_eff| <= 255, |w| <= 128, taps <=
// 9*192 = 1728, |bias| < 2^17 -> |acc| < 1728*32640 + 2^17 ~= 5.6e7,
// far inside the s32 accumulator (golden tensordot is int64 but the
// measured contract never leaves s32; requant_unit consumes s32).
//
// Architecture (design.md 4.2, 16-MAC option selected):
//   - 16 parallel INT8 MAC lanes = the 16 output channels of one
//     weight group (group_channels = 16 in the layer contract). Every
//     cycle ONE tap (cin, dy, dx) of the shared input window is
//     broadcast to all 16 lanes, each lane multiplying its own
//     per-channel weight: pe[c] += x * w[c][cin][dy][dx].
//   - The tap index is scanned serially over 9*Cin cycles per output
//     pixel per group (golden flatten order: cin outer, dy*3+dx inner,
//     matching the (dy*3+dx) weight layout).
//   - 16 x s32 accumulators, double-banked (A/B ping-pong): one bank
//     accumulates the current pixel while the snapshot bank drains
//     through the time-multiplexed requant_unit (16-beat TDM).
//   - Row-pipeline: ingress rows stream into a 3-bank sliding-window
//     line buffer (bank = row mod 3); output row r only needs input
//     rows r-1..r+1 (pad rows read as zero). Activations never touch
//     DDR3 (architecture principle 1).
//   - Scan order: out_row -> group -> column -> tap. Weight groups are
//     re-armed per (row, group); the group contract (16 x bias_s32,
//     16 x M_s32, 16 x shift) is double-buffered so the wdma prefetch
//     of the next group overlaps the current group computation.
//
// MAC implementation note (design.md 4.2 selection): int8 x int8
// products are written as plain signed multiplies so synthesis maps
// them onto 8 APM 18x18 tiles (9x9 split, 2 int8 lanes per APM) per
// the design selection; LUT fallback is acceptable within the LUT
// budget. The requant_unit 32x32 multiply adds ~4 more APM blocks,
// for an engine total of ~12 APM (budget <= 40).
//
// Timing budget table (real MAC counts; task note "conv2 432
// taps/pixel = 27 cycles/pixel/16-channel-group" means 432 = 27 x 16:
// 27 MAC cycles per output channel, 16 channels sharing the array,
// i.e. 435 pipe cycles per pixel per group including load/snapshot
// beats):
//   layer | Cin | Cout | out HxW | cycles/px/group | total beats | @125MHz
//   conv1 |   1 |   48 |  64x258 | max(12, 16) = 16|  16512x3x16  =  793k |  6.3 ms
//   conv2 |  48 |   96 |  32x129 | 9*48+3 = 435    |  4128x6x435  = 10.7M | 86.1 ms
//   conv3 |  96 |  192 |  16x64  | 9*96+3 = 867    |  1024x12x867 = 10.6M | 85.2 ms
//   conv4 | 192 |  256 |   8x32  | 9*192+3 = 1731  |  256x16x1731 =  7.1M | 56.7 ms
//   conv total ~= 234 ms -- see RISK note below.
// RISK (reported to team lead): design.md 4.6 counts conv-layer MACs
// on the post-pool shapes (114.6M total, 57.5 ms); the true pre-pool
// count is ~460M, so the 16-MAC array lands at ~234 ms > 200 ms
// budget. This engine implements the specified 16-MAC architecture;
// closing the gap (32-MAC option from design.md 4.2 or two engine
// instances) is a system-level decision.
//
// Beat plan per output pixel per group (TDM channels 0..15 through
// requant_unit are hidden inside the next tap scan; conv1 stretches
// to the requant pace of 16):
//   beat 0        : acc bank <- bias (parallel load of 16 lanes)
//   beat 1..9Cin+1: tap scan (1 read address beat + 1 MAC beat pipe)
//   beat 9Cin+2   : snapshot acc -> drain bank, swap active bank
//   beats 0..15 of the drain overlap the NEXT pixel scan via the
//   requant_unit 16-beat TDM (1 channel per cycle).
//
// INTEGRATION ALIGNMENT POINTS (downstream contracts):
//   [wdma]  weight tap stream: w_valid/w_data carry one 16-lane tap
//           word per MAC beat, tap order (cin outer, dy*3+dx inner),
//           lane i = weight of output channel (grp*16+i). The group
//           contract streams (bias/mult/shft) target the shadow bank
//           and are re-armed per (row, group): grp_advance pulses at
//           every group boundary in scan order. wdma re-reads each
//           group's weights per row (row x group re-read volume is
//           within the DDR3 read budget; wbuf stays single-buffered
//           per design.md 4.1).
//   [pool_engine] egress stream: y_valid/y_u8 come out in scan order
//           (out_row, grp, col, lane 0..15) -- 16 channels of one
//           pixel per 16-beat TDM batch. Pool organizes its 2x2
//           windows per channel independently (max is channel-local).
//
// Clock domain: core_clk 125 MHz. MAC beat pipeline: read address
// (1 beat) -> synchronous RAM read + weight registration (1 beat) ->
// multiply-add registered into the s32 accumulator (1 beat), meeting
// the 8 ns stage budget.
//
// Reset: asynchronous-active-low; all counters and the FSM return to
// idle, line buffers keep old content (rewritten before use).
// ---------------------------------------------------------------------------

module conv_engine #(
    // Layer shape parameters (all four conv layers share this engine;
    // one instance per layer, per design.md 4.1/4.4):
    //   conv1: CIN=1,   COUT=48,  H_IN=64, W_IN=258
    //   conv2: CIN=48,  COUT=96,  H_IN=32, W_IN=129
    //   conv3: CIN=96,  COUT=192, H_IN=16, W_IN=64
    //   conv4: CIN=192, COUT=256, H_IN=8,  W_IN=32
    parameter CIN  = 48,    // input channels
    parameter COUT = 96,    // output channels (multiple of 16)
    parameter H_IN = 32,    // input rows  (= output rows, pad-1 stride-1)
    parameter W_IN = 129    // input cols (= output cols)
) (
    // clock / reset (core_clk 125 MHz domain)
    input  wire               clk,
    input  wire               rst_n,

    // layer configuration stream (from npu_top contract loader)
    input  wire               cfg_valid,   // strobe: latch zp pair
    input  wire        [7:0]  cfg_zp_in,   // conv1: 49, others 0
    input  wire        [7:0]  cfg_zp_out,  // requant output zero point

    // layer control
    input  wire               layer_start, // pulse: reset scan state
    output wire               layer_done,  // pulse: last requant drained

    // [ingress] activation row stream, u8 container domain.
    // Raster order: column-major within a row -- col 0 carries
    // ch 0..CIN-1, then col 1, etc. One beat per cycle, no backpressure
    // (producer rate <= 1 beat/cycle; row boundaries derived by count).
    input  wire               x_valid,
    input  wire        [7:0]  x_u8,

    // [wdma alignment point] group contract stream, 48 beats per group
    // (16 x bias, 16 x M, 16 x shift), loaded into the shadow contract
    // bank; becomes active at the next grp_advance boundary.
    input  wire               grp_start,   // pulse: restart shadow pointer
    input  wire               bias_valid,  // beats 0..15: bias_s32
    input  wire signed [31:0] bias_s32,
    input  wire               mult_valid,  // beats 0..15: M Q0.31
    input  wire signed [31:0] m_s32,
    input  wire               shft_valid,  // beats 0..15: shift (6-bit used)
    input  wire        [6:0]  shift,

    // [wdma alignment point] weight tap stream: one 16-lane tap word
    // per MAC beat, lane i = w[grp*16+i][cin][dy][dx], tap order
    // cin-major, dy*3+dx minor.
    input  wire               w_valid,
    input  wire        [127:0] w_data,     // {lane15, ..., lane1, lane0} s8
    output wire               w_ready,     // high during MAC consumption beats

    // [pool_engine alignment point] egress: requantized u8 stream in
    // scan order (out_row, grp, col, lane 0..15 TDM).
    output wire               y_valid,
    output wire        [7:0]  y_u8,

    // group boundary strobe: pulses at every (row, group) advance in
    // scan order; wdma arms the next group contract + tap stream here.
    output wire               grp_advance
);

    // -----------------------------------------------------------------------
    // Derived dimensions (constant function must precede its uses)
    // -----------------------------------------------------------------------
    // ceiling log2 with a 1-bit floor, so CIN = 1 (conv1) stays legal
    function integer clog2;
        input integer value;
        integer v;
        begin
            v = value - 1;
            for (clog2 = 0; v > 0; clog2 = clog2 + 1)
                v = v >> 1;
            if (clog2 == 0)
                clog2 = 1;
        end
    endfunction

    localparam GRP_NUM   = COUT / 16;          // 16-channel output groups
    localparam TAP_NUM   = 9 * CIN;            // taps per pixel per group
    localparam LINE_WORDS = CIN * W_IN;        // u8 words per line bank
    localparam RW = clog2(W_IN);               // column index width
    localparam RC = clog2(CIN);                // channel index width
    localparam RR = clog2(H_IN + 1);           // row counter width (0..H_IN)
    localparam RT = clog2(TAP_NUM + 3);        // tap scan counter width
    localparam AW = clog2(LINE_WORDS);         // line RAM address width

    // -----------------------------------------------------------------------
    // Layer configuration registers
    // -----------------------------------------------------------------------
    reg [7:0] zp_in_reg;    // ingress zero point (conv1: 49)
    reg [7:0] zp_out_reg;   // requant zero point

    // -----------------------------------------------------------------------
    // Sliding-window line buffer: 3 rotating banks of CIN x W_IN u8
    // container words. Bank = row mod 3. Write port: activation ingress.
    // Read port: tap scan (one bank, one word per beat). Pseudo-dual-port
    // per bank; the write row (scan row + 2) is never a window row, so
    // write and read never hit the same bank in the same cycle.
    // Pad-1 rows/cols are guarded read-side (return 0 in the signed MAC
    // domain) -- the neutral value, see header.
    // -----------------------------------------------------------------------
    reg [7:0] line_ram0 [0:LINE_WORDS-1];
    reg [7:0] line_ram1 [0:LINE_WORDS-1];
    reg [7:0] line_ram2 [0:LINE_WORDS-1];
    reg [7:0] dout0_q;              // synchronous read data, bank 0
    reg [7:0] dout1_q;              // synchronous read data, bank 1
    reg [7:0] dout2_q;              // synchronous read data, bank 2

    reg [1:0]   wr_bank_ptr;   // bank being written (in_row mod 3)
    reg [RR-1:0] in_row_cnt;   // completed-row counter (0..H_IN)
    reg [RC-1:0] in_ch_cnt;    // ingress channel index within row
    reg [RW-1:0] in_col_cnt;   // ingress column index within row
    reg [H_IN-1:0] row_done;   // per input row completion bitmap

    // -----------------------------------------------------------------------
    // Group contract registers, double-banked (active/shadow)
    // -----------------------------------------------------------------------
    reg signed [31:0] bias_act [0:15];  // active:   current group
    reg signed [31:0] bias_shd [0:15];  // shadow:   loading next group
    reg signed [31:0] m_act     [0:15];
    reg signed [31:0] m_shd     [0:15];
    reg        [6:0]  shft_act  [0:15];
    reg        [6:0]  shft_shd  [0:15];
    reg        [5:0]  cload_cnt;         // shadow load pointer 0..47

    // -----------------------------------------------------------------------
    // Scan state (order: out_row -> grp -> col -> tap)
    // -----------------------------------------------------------------------
    localparam PH_LOAD = 2'd0;      // acc bank <- bias (1 beat)
    localparam PH_SCAN = 2'd1;      // tap scan (TAP_NUM issues + pipe)
    localparam PH_SNAP = 2'd2;      // acc snapshot + bank swap (1 beat)
    localparam [31:0] Y_TOTAL = H_IN * W_IN * GRP_NUM * 16;

    reg               run_reg;        // layer in progress
    reg [RR-1:0]      out_row_cnt;    // 0..H_IN-1
    reg [clog2(GRP_NUM)-1:0] grp_cnt; // 0..GRP_NUM-1
    reg [RW-1:0]      out_col_cnt;    // 0..W_IN-1
    reg [RT-1:0]      tap_cnt;        // taps issued for current pixel
    reg [RT-1:0]      mac_cnt;        // MAC beats retired for current pixel
    reg [1:0]         phase_reg;      // PH_LOAD / PH_SCAN / PH_SNAP
    reg [1:0]         rd_bank_base;   // bank of window row (out_row-1)
    reg [1:0]         dy_cnt;         // window row offset 0..2
    reg [1:0]         dx_cnt;         // window col offset 0..2
    reg [RC-1:0]      cin_cnt;        // tap channel 0..CIN-1

    // tap address generation (registered for the 1-beat RAM latency)
    reg          rd_pad_q;            // pad guard (row/col outside window)
    reg [1:0]    rd_bank_q;           // bank of the window row
    reg [127:0]  w_data_q;            // tap weights aligned with RAM dout
    reg          w_vld_q;             // tap weight beat valid

    // group contract handshake state
    reg               grp_arm;        // active contract bank valid
    reg               shadow_rdy;     // shadow contract bank complete

    // layer completion bookkeeping
    reg [31:0]        y_cnt;           // retired requant results
    reg               done_q;          // layer_done pulse (1 beat)
    reg               advance_q;       // grp_advance pulse (1 beat)

    // -----------------------------------------------------------------------
    // 16-lane s32 accumulators, ping-pong banks + drain snapshot
    // -----------------------------------------------------------------------
    reg signed [31:0] acc_a [0:15];
    reg signed [31:0] acc_b [0:15];
    reg               acc_sel;        // 0: A accumulates / B drains
    reg signed [31:0] acc_snap [0:15];

    // -----------------------------------------------------------------------
    // requant drain state (16-beat TDM through requant_unit)
    // -----------------------------------------------------------------------
    reg [4:0]   rhe_busy_cnt;         // 16 -> 0 countdown
    reg [3:0]   rhe_ch;               // drain channel index 0..15

    // -----------------------------------------------------------------------
    // requant_unit instance (TDM, one physical unit for 16 channels)
    // -----------------------------------------------------------------------
    wire signed [31:0] rq_acc_s32;   // operand muxes, driven in the body
    wire signed [31:0] rq_m_s32;
    wire        [6:0]  rq_shift;
    wire        [7:0]  rq_zp_out;
    wire               rq_in_valid;
    wire        [7:0]  rq_y_u8;
    wire               rq_y_valid;

    requant_unit u_requant (
        .clk       (clk),
        .rst_n     (rst_n),
        .acc_s32   (rq_acc_s32),
        .m_s32     (rq_m_s32),
        .shift     (rq_shift),
        .zp_out    (rq_zp_out),
        .in_valid  (rq_in_valid),
        .y_u8      (rq_y_u8),
        .out_valid (rq_y_valid)
    );

    // =======================================================================
    // BODY: control FSM, line-buffer plumbing, MAC array, requant drain
    // =======================================================================

    // mod-3 rotation helper for the line-bank pointers
    function [1:0] add3;
        input [1:0] a;
        input [1:0] b;
        reg [2:0] s;
        begin
            s = {1'b0, a} + {1'b0, b};
            add3 = (s >= 3'd3) ? (s - 3'd3) : s[1:0];
        end
    endfunction

    integer i;   // contract-bank loop variable

    // -----------------------------------------------------------------------
    // Layer configuration latch (protocol: cfg_valid before layer_start)
    // -----------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            zp_in_reg  <= 8'd0;
            zp_out_reg <= 8'd0;
        end else if (cfg_valid) begin
            zp_in_reg  <= cfg_zp_in;
            zp_out_reg <= cfg_zp_out;
        end
    end

    // -----------------------------------------------------------------------
    // Ingress write path: u8 container values into the rotating banks.
    // Beat order is column-major (col 0 carries ch 0..CIN-1, then
    // col 1, ...) -- matches the TDM group ordering of the upstream
    // pool/mel engines. One beat per cycle, no backpressure.
    // -----------------------------------------------------------------------
    wire       wr_en   = x_valid && (in_row_cnt != H_IN[RR-1:0]);
    wire [AW-1:0] wr_addr = in_ch_cnt * W_IN + in_col_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            in_row_cnt  <= {RR{1'b0}};
            in_ch_cnt   <= {RC{1'b0}};
            in_col_cnt  <= {RW{1'b0}};
            wr_bank_ptr <= 2'd0;
            row_done    <= {H_IN{1'b0}};
        end else if (layer_start) begin
            in_row_cnt  <= {RR{1'b0}};
            in_ch_cnt   <= {RC{1'b0}};
            in_col_cnt  <= {RW{1'b0}};
            wr_bank_ptr <= 2'd0;
            row_done    <= {H_IN{1'b0}};
        end else if (wr_en) begin
            if ((in_ch_cnt == CIN - 1) && (in_col_cnt == W_IN - 1)) begin
                row_done[in_row_cnt] <= 1'b1;      // row complete
                in_row_cnt  <= in_row_cnt + 1'b1;
                in_ch_cnt   <= {RC{1'b0}};
                in_col_cnt  <= {RW{1'b0}};
                wr_bank_ptr <= (wr_bank_ptr == 2'd2)
                               ? 2'd0 : wr_bank_ptr + 2'd1;
            end else if (in_ch_cnt == CIN - 1) begin
                in_ch_cnt  <= {RC{1'b0}};
                in_col_cnt <= in_col_cnt + 1'b1;
            end else begin
                in_ch_cnt <= in_ch_cnt + 1'b1;
            end
        end
    end

    // line RAM banks: one write port (ingress) + one synchronous read
    // port (tap scan). Write row = scan row + 2, never a window row,
    // so write and read never touch the same bank in the same cycle.
    always @(posedge clk) begin
        if (wr_en && (wr_bank_ptr == 2'd0))
            line_ram0[wr_addr] <= x_u8;
        dout0_q <= line_ram0[rd_addr_c];
    end
    always @(posedge clk) begin
        if (wr_en && (wr_bank_ptr == 2'd1))
            line_ram1[wr_addr] <= x_u8;
        dout1_q <= line_ram1[rd_addr_c];
    end
    always @(posedge clk) begin
        if (wr_en && (wr_bank_ptr == 2'd2))
            line_ram2[wr_addr] <= x_u8;
        dout2_q <= line_ram2[rd_addr_c];
    end

    // -----------------------------------------------------------------------
    // Group contract loader. Beat order is free (three independent
    // valid strobes, 16 beats each); the channel index is the shared
    // low nibble of the beat counter. First full round (48 beats)
    // fills the ACTIVE bank and arms the engine; every later round
    // fills the SHADOW bank. At a group boundary the shadow bank is
    // promoted to active (protocol: wdma completes the shadow load
    // before the engine reaches the boundary -- the >=435-cycle group
    // computation gives ample prefetch window).
    // -----------------------------------------------------------------------
    wire [3:0] cload_idx = cload_cnt[3:0];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cload_cnt <= 6'd0;
            grp_arm   <= 1'b0;
            shadow_rdy <= 1'b0;
            for (i = 0; i < 16; i = i + 1) begin
                bias_act[i] <= 32'sd0;
                bias_shd[i] <= 32'sd0;
                m_act[i]    <= 32'sd0;
                m_shd[i]    <= 32'sd0;
                shft_act[i] <= 7'd0;
                shft_shd[i] <= 7'd0;
            end
        end else if (layer_start) begin
            cload_cnt  <= 6'd0;
            grp_arm    <= 1'b0;
            shadow_rdy <= 1'b0;
        end else begin
            if (bias_valid) begin
                if (!grp_arm) bias_act[cload_idx] <= bias_s32;
                else          bias_shd[cload_idx] <= bias_s32;
            end
            if (mult_valid) begin
                if (!grp_arm) m_act[cload_idx] <= m_s32;
                else          m_shd[cload_idx] <= m_s32;
            end
            if (shft_valid) begin
                if (!grp_arm) shft_act[cload_idx] <= shift;
                else          shft_shd[cload_idx] <= shift;
            end
            if (grp_start) begin
                cload_cnt <= 6'd0;
            end else if (bias_valid || mult_valid || shft_valid) begin
                if (cload_cnt == 6'd47) begin
                    cload_cnt <= 6'd0;
                    if (!grp_arm) grp_arm     <= 1'b1;
                    else          shadow_rdy  <= 1'b1;
                end else begin
                    cload_cnt <= cload_cnt + 6'd1;
                end
            end
            if (advance_now) begin
                shadow_rdy <= 1'b0;
                for (i = 0; i < 16; i = i + 1) begin
                    bias_act[i] <= bias_shd[i];
                    m_act[i]    <= m_shd[i];
                    shft_act[i] <= shft_shd[i];
                end
            end
        end
    end

    // -----------------------------------------------------------------------
    // Scan control wires
    // -----------------------------------------------------------------------
    // window row availability: output row r needs input rows r-1..r+1,
    // i.e. row min(r+1, H_IN-1) completed; row r+1 = H_IN is pad (zero)
    wire row_ready = (out_row_cnt == H_IN - 1) ? row_done[H_IN - 1]
                                               : row_done[out_row_cnt + 1];

    // issue window: cycles where a new tap address + weight pair can be
    // consumed (w_ready mirrors this to the wdma tap stream)
    localparam [RT-1:0] TAP_LAST = TAP_NUM;
    wire issue_window = run_reg && (phase_reg == PH_SCAN)
                        && (tap_cnt != TAP_LAST);
    wire issue_beat   = issue_window && w_valid;
    wire mac_beat     = run_reg && (phase_reg == PH_SCAN) && w_vld_q;

    // pixel / group / layer boundary detection
    wire col_end      = (out_col_cnt == W_IN - 1);
    wire grp_end      = col_end && (grp_cnt == GRP_NUM - 1);
    wire layer_end    = grp_end && (out_row_cnt == H_IN - 1);
    wire need_advance = col_end && !layer_end;
    wire boundary_ok  = !need_advance || shadow_rdy;

    // phase transitions (requant drain must be idle before the snapshot
    // register is overwritten -- this stretches conv1 to 16 beats/px)
    wire snapshot_go  = run_reg && (phase_reg == PH_SNAP)
                        && (rhe_busy_cnt == 5'd0) && boundary_ok;
    wire advance_now  = snapshot_go && need_advance;
    wire load_go      = run_reg && (phase_reg == PH_LOAD)
                        && row_ready && grp_arm;
    wire layer_done_comb = run_reg && rq_y_valid && (y_cnt == Y_TOTAL - 32'd1);

    // -----------------------------------------------------------------------
    // Tap read-address generation (combinational on the issue beat):
    // window position (out_row + dy - 1, out_col + dx - 1); pad guard
    // returns x_eff = 0 (the signed-domain neutral value). Row/col are
    // computed as unsigned sums so the -1 underflow maps to 0 == pad.
    // -----------------------------------------------------------------------
    wire [RR+1:0] wy_u   = {2'b00, out_row_cnt} + {{RR{1'b0}}, dy_cnt};
    wire          wy_pad = (wy_u == {(RR+2){1'b0}}) || (wy_u > H_IN);
    wire [RW+1:0] col_u  = {2'b00, out_col_cnt} + {{RW{1'b0}}, dx_cnt};
    wire          col_pad = (col_u == {(RW+2){1'b0}}) || (col_u > W_IN);
    wire          rd_pad_c  = wy_pad || col_pad;
    wire [1:0]    rd_bank_c = add3(rd_bank_base, dy_cnt);
    wire [AW-1:0] rd_addr_c = rd_pad_c ? {AW{1'b0}}
                            : cin_cnt * W_IN + (col_u - {{(RW+1){1'b0}}, 1'b1});

    // -----------------------------------------------------------------------
    // Weight stream alignment: lock the 16-lane tap word and the read
    // guards one cycle so they line up with the synchronous RAM dout.
    // -----------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            w_data_q  <= 128'd0;
            w_vld_q   <= 1'b0;
            rd_pad_q  <= 1'b0;
            rd_bank_q <= 2'd0;
        end else begin
            w_vld_q <= issue_beat;
            if (issue_beat) begin
                w_data_q  <= w_data;
                rd_pad_q  <= rd_pad_c;
                rd_bank_q <= rd_bank_c;
            end
        end
    end

    // -----------------------------------------------------------------------
    // MAC operand: live zp_in subtraction in the signed 9-bit domain
    // (u8 container store, see header storage-domain note)
    // -----------------------------------------------------------------------
    wire [7:0] ram_dout = (rd_bank_q == 2'd0) ? dout0_q :
                          (rd_bank_q == 2'd1) ? dout1_q : dout2_q;
    wire signed [8:0] x_eff = rd_pad_q ? 9'sd0 :
            ($signed({1'b0, ram_dout}) - $signed({1'b0, zp_in_reg}));

    // -----------------------------------------------------------------------
    // 16-lane INT8 MAC array with double-banked s32 accumulators
    // (design.md 4.2: 16 MAC/period, 8 APM 18x18 with 9x9 split = 2 int8
    // lanes per APM; plain signed multiply lets synthesis infer it)
    // -----------------------------------------------------------------------
    genvar g;
    generate
        for (g = 0; g < 16; g = g + 1) begin : mac_lane
            wire signed [7:0]  w_lane = w_data_q[8*g +: 8];
            wire signed [31:0] lane_sum = x_eff * w_lane;

            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    acc_a[g]    <= 32'sd0;
                    acc_b[g]    <= 32'sd0;
                    acc_snap[g] <= 32'sd0;
                end else begin
                    // snapshot: drain bank <- active bank, then swap
                    if (snapshot_go)
                        acc_snap[g] <= acc_sel ? acc_b[g] : acc_a[g];
                    // pixel start: accumulator <- rebuilt int32 bias
                    if (load_go) begin
                        if (!acc_sel) acc_a[g] <= bias_act[g];
                        else          acc_b[g] <= bias_act[g];
                    end else if (mac_beat) begin
                        if (!acc_sel) acc_a[g] <= acc_a[g] + lane_sum;
                        else          acc_b[g] <= acc_b[g] + lane_sum;
                    end
                end
            end
        end
    endgenerate

    // -----------------------------------------------------------------------
    // Main scan FSM. Pixel beat plan per group:
    //   PH_LOAD (1) -> PH_SCAN (TAP_NUM issues + 1 drain beat) ->
    //   PH_SNAP (1, gated by requant idle) -> next pixel.
    // -----------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            run_reg      <= 1'b0;
            phase_reg    <= PH_LOAD;
            out_row_cnt  <= {RR{1'b0}};
            grp_cnt      <= 0;
            out_col_cnt  <= {RW{1'b0}};
            tap_cnt      <= {RT{1'b0}};
            mac_cnt      <= {RT{1'b0}};
            dy_cnt       <= 2'd0;
            dx_cnt       <= 2'd0;
            cin_cnt      <= {RC{1'b0}};
            rd_bank_base <= 2'd2;   // window row -1 (pad) virtual bank
            rhe_busy_cnt <= 5'd0;
            rhe_ch       <= 4'd0;
            acc_sel      <= 1'b0;
            y_cnt        <= 32'd0;
            done_q       <= 1'b0;
            advance_q    <= 1'b0;
        end else begin
            advance_q <= advance_now;
            done_q    <= layer_done_comb;
            if (layer_start) begin
                run_reg      <= 1'b1;
                phase_reg    <= PH_LOAD;
                out_row_cnt  <= {RR{1'b0}};
                grp_cnt      <= 0;
                out_col_cnt  <= {RW{1'b0}};
                tap_cnt      <= {RT{1'b0}};
                mac_cnt      <= {RT{1'b0}};
                dy_cnt       <= 2'd0;
                dx_cnt       <= 2'd0;
                cin_cnt      <= {RC{1'b0}};
                rd_bank_base <= 2'd2;
                rhe_busy_cnt <= 5'd0;
                rhe_ch       <= 4'd0;
                acc_sel      <= 1'b0;
                y_cnt        <= 32'd0;
                done_q       <= 1'b0;
                advance_q    <= 1'b0;
            end else if (run_reg) begin
                if (layer_done_comb)
                    run_reg <= 1'b0;
                // ---- scan FSM ----
                if (load_go) begin
                    phase_reg <= PH_SCAN;
                    tap_cnt   <= {RT{1'b0}};
                    mac_cnt   <= {RT{1'b0}};
                    dy_cnt    <= 2'd0;
                    dx_cnt    <= 2'd0;
                    cin_cnt   <= {RC{1'b0}};
                end else if (phase_reg == PH_SCAN) begin
                    if (issue_beat) begin
                        tap_cnt <= tap_cnt + {{(RT-1){1'b0}}, 1'b1};
                        // tap order: cin outer, dy middle, dx inner
                        // (golden flatten order, dy*3+dx minor)
                        if (dx_cnt == 2'd2) begin
                            dx_cnt <= 2'd0;
                            if (dy_cnt == 2'd2) begin
                                dy_cnt <= 2'd0;
                                cin_cnt <= cin_cnt + 1'b1;
                            end else begin
                                dy_cnt <= dy_cnt + 2'd1;
                            end
                        end else begin
                            dx_cnt <= dx_cnt + 2'd1;
                        end
                    end
                    if (mac_beat) begin
                        mac_cnt <= mac_cnt + 1'b1;
                        if (mac_cnt == TAP_NUM - 1)
                            phase_reg <= PH_SNAP;
                    end
                end else if (snapshot_go) begin
                    phase_reg    <= PH_LOAD;
                    acc_sel      <= ~acc_sel;
                    rhe_busy_cnt <= 5'd16;
                    rhe_ch       <= 4'd0;
                    // scan position advance: col -> grp -> row
                    if (col_end) begin
                        out_col_cnt <= {RW{1'b0}};
                        if (grp_end) begin
                            grp_cnt      <= 0;
                            rd_bank_base <= add3(rd_bank_base, 2'd1);
                            out_row_cnt  <= out_row_cnt + 1'b1;
                        end else begin
                            grp_cnt <= grp_cnt + 1'b1;
                        end
                    end else begin
                        out_col_cnt <= out_col_cnt + 1'b1;
                    end
                end
                // ---- requant drain: 16-beat TDM, hidden in the next
                // pixel's tap scan (snap gate keeps conv1 in lockstep)
                if (rhe_busy_cnt != 5'd0) begin
                    rhe_busy_cnt <= rhe_busy_cnt - 5'd1;
                    rhe_ch       <= rhe_ch + 4'd1;
                end
                // ---- egress result bookkeeping ----
                if (rq_y_valid)
                    y_cnt <= y_cnt + 32'd1;
            end
        end
    end

    // -----------------------------------------------------------------------
    // requant_unit operand muxes (TDM channel select) and egress wiring
    // -----------------------------------------------------------------------
    assign rq_acc_s32  = acc_snap[rhe_ch];
    assign rq_m_s32    = m_act[rhe_ch];
    assign rq_shift    = shft_act[rhe_ch];
    assign rq_zp_out   = zp_out_reg;
    assign rq_in_valid = (rhe_busy_cnt != 5'd0);

    assign y_valid     = rq_y_valid;
    assign y_u8        = rq_y_u8;
    assign layer_done  = done_q;
    assign grp_advance = advance_q;
    assign w_ready     = issue_window;

endmodule