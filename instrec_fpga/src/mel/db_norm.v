// -----------------------------------------------------------------------------
// db_norm - Mel second-pass front half (tasks.md T-M1-04, design.md Sec. 3.5
//           and Sec. 3.1 stages S7/S8): global max scan over the log2
//           spectrum, dB conversion, top_db=80 truncation and the mu/sigma
//           statistics accumulation.
// -----------------------------------------------------------------------------
// Bit-exact reference: scripts/golden_pipeline.py db_convert() +
// truncate_frames(), plus the accumulation half of standardize().
// Function-by-function semantic mapping (golden -> RTL):
//
//   golden db_convert():                       RTL scan 1 + scan 2:
//   --------------------------------------------------------------------
//   max_l2 = max(log2_q88_full)                scan 1 over ALL
//   (max over the FULL 259-frame spectrum,     SPEC_FRAME_COUNT frames -
//   librosa ref=np.max parity)                 frame 0 (the reflect-lead
//                                               frame) INCLUDED in the max
//   diff   = log2_q88 - max_l2 (int64)         diff_s17 = log2 - max_l2
//   scaled = rhu_shift(diff * 775, 8)          scaled = (diff*775 + 128)
//                                               >>> 8 (floor, ties to +inf)
//   scaled = sat16(scaled)                     merged into a single
//   scaled = max(scaled, -20480)               clip(scaled, -20480, 0) -
//   scaled = min(scaled, 0)                    equivalence proof below
//   --------------------------------------------------------------------
//   golden truncate_frames(): keep the LAST    HEAD_DROP = SPEC_FRAME_COUNT
//   258 of 259 frames (frame 0 dropped);       - OUT_FRAME_COUNT = 1 frame
//   standardize() statistics run over the      dropped: no dB write and no
//   kept 258 frames (16512 elements) only      sum_db/sum_db_sq update for
//                                               addresses 0..N_MELS-1
//
// Fixed-point constant derivations (every constant traceable):
//   * dB scale: physical dB = (log2 - max) * 10*log10(2)
//     = (log2 - max) * 3.01029996. The golden uses the rational form
//     diff * 775 / 256 (775/256 = 3.02734375). The scale error vs the
//     physical constant is +0.017 dB per log2 unit (worst +0.45 dB at
//     the -80 dB floor). design.md Sec. 3.5 quotes "0.003 dB" which
//     underestimates it (deviation D2); the golden is the acceptance
//     truth source, so the RTL replicates 775/256 bit-for-bit.
//   * rhu_shift(x, 8) = floor((x + 2^7) / 2^8): rounding constant +128
//     followed by an ARITHMETIC right shift by 8 (floor semantics).
//   * top_db floor: -80 dB in Q8.8 = -80 * 256 = -20480 (REQ-FTR-004).
//   * Domain bounds (from golden log2_fixed, LOG2_BIAS = -56, exponent
//     e in [0..55], mantissa LUT output in [0..255]): log2_q88 lies in
//     [-14336, -1], so diff in [-14336, 0], diff*775 in [-11110400, 0]
//     (fits s27 with the +128 rounding constant), and the pre-clamp
//     scaled value lies in [-43400, 0].
//   * Statistics: sum_db in [-16512*20480, 0] (magnitude < 2^29, s48
//     container per design.md Sec. 3.1 S8); sum_db_sq in
//     [0, 16512*20480^2] = [0, 6925634764800] < 2^43 (s48 container).
//
// sat16 + clamp merge proof (why a single clip is bit-exact):
//   The golden order is sat16 -> clamp(-20480) -> clamp(0). The clamp
//   range [-20480, 0] lies strictly inside the s16 range, and the input
//   scaled <= 0 always holds (diff <= 0 -> diff*775 + 128 <= 128 ->
//   floor(x/256) <= 0), so:
//     - any scaled < -20480 maps to -20480 under both forms (the inner
//       sat16 clamp to -32768 is subsumed by the -20480 floor),
//     - any scaled in (-20480, 0] passes through unchanged in both,
//     - any scaled > 0 (cannot occur; kept as +/-1 LSB jitter defense
//       around the maximum, mirroring the golden form) maps to 0.
//   Hence clip(scaled, -20480, 0) equals the golden chain exactly.
//
// Architecture (two scans, two cycles per element plus a final drain):
//   * Scan 1 (max): read every element, keep the running max of the
//     signed Q8.8 log2 values.
//   * Scan 2 (dB + statistics): recompute dB for every element; elements
//     at addresses >= HEAD_DROP*N_MELS (the kept 258 frames) are written
//     back to the spectrum bank and accumulated into sum_db/sum_db_sq.
//   * Two-cycle element beat: RD beat presents spec_rd_en/spec_rd_addr,
//     CALC beat samples spec_rd_data (assumes a 1-cycle synchronous read
//     RAM, PDS DRM style) and presents db_wr_en/db_wr_addr/db_wr_data.
//     Read and write never fire in the same cycle, so mel_engine may map
//     both ports onto one single-port RAM bank.
//
// Storage / INTEGRATION ALIGNMENT POINTS (buffer NOT instantiated here):
//   * The 64 x 259 int16 log2-spectrum buffer is owned by the mel_engine
//     integration (T-M1-05; first pass writes it - Jiang's line). This
//     module only drives the external read port (spec_rd_*) and the
//     external overwrite port (db_wr_*). Scan 2 reads log2[i] on the RD
//     beat and overwrites the SAME address with dB[i] on the CALC beat
//     (in-place log2 -> dB bank reuse, design.md Sec. 3.7 ping-pong bank
//     scheme). Frame-major addressing: addr = frame * N_MELS + mel;
//     frame-0 addresses 0..63 are never written (dB occupies 64..16575).
//   * SPEC_FRAME_COUNT defaults to 259 for golden parity. If the first
//     pass stores only the truncated 258 frames (design.md Sec. 3.5
//     wording), set SPEC_FRAME_COUNT = 258: HEAD_DROP becomes 0 and all
//     stored frames join the max - a max-domain deviation vs the golden
//     259-frame max (the dropped reflect-lead frame missing) that must
//     be re-validated at T-M1-05 integration (deviation D1).
//   * sum_db/sum_db_sq are held stable after stats_valid until the next
//     start, so the consumer (standardize, start wireable to
//     stats_valid) may sample them on any later cycle as well.
//
// Cycle budget (125 MHz core_clk, REQ-FTR-007 / design.md Sec. 3.8):
//   scan 1 (max):      2 cycles/element * 16576 = 33152 cycles
//   scan 2 (dB+sums):  2 cycles/element * 16576 = 33152 cycles
//   total ~66.3k cycles = 0.53 ms, inside the Sec. 3.5/3.8 second-pass
//   budget (2x16512x4 = 132k cycles for both scans) with 2x headroom.
//   Full second pass (db_norm + standardize) ~ 116k cycles = 0.93 ms,
//   far below the 3 s window cadence (21x margin on the whole engine).
// -----------------------------------------------------------------------------

module db_norm #(
    parameter integer N_MELS           = 64,    // Mel channels
    parameter integer SPEC_FRAME_COUNT = 259,   // full log2 spectrum frames
    parameter integer OUT_FRAME_COUNT  = 258,   // frames kept (tail keep)
    parameter integer DB_SCALE_NUM     = 775,   // dB = diff * 775 / 256
    parameter integer DB_TOP_DB_Q88    = -20480 // -80 dB Q8.8 top_db floor
) (
    input  wire               clk,          // core_clk 125 MHz
    input  wire               rst_n,        // core-domain reset, active low
    // control (mel_engine, T-M1-05 alignment point)
    input  wire               start,        // one-cycle start pulse
    output wire               busy,         // 1 = scans in progress
    // log2-spectrum read port (external RAM, 1-cycle synchronous read)
    output wire               spec_rd_en,
    output wire [14:0]        spec_rd_addr, // frame-major: frame*N_MELS+mel
    input  wire signed [15:0] spec_rd_data, // int16 Q8.8 log2 domain
    // dB-spectrum write port (same external bank, in-place overwrite)
    output wire               db_wr_en,
    output wire [14:0]        db_wr_addr,   // frame-major, 64..16575 used
    output wire signed [15:0] db_wr_data,   // int16 Q8.8 dB domain
    // statistics handoff to standardize (golden standardize() input sums)
    output reg  signed [47:0] sum_db,       // s48, sum of kept dB values
    output reg  [47:0]        sum_db_sq,    // s48, sum of dB values squared
    output reg                stats_valid   // pulse: sums final, dB written
);

    // ------------------------------------------------------------------
    // Derived constants (sized locals; addr width fits 64x259 = 16576
    // < 2^15 - revisit if the frame geometry parameters change).
    // ------------------------------------------------------------------
    localparam integer HEAD_DROP       = SPEC_FRAME_COUNT - OUT_FRAME_COUNT;
    localparam integer OUT_FIRST       = HEAD_DROP * N_MELS; // first kept addr
    localparam integer SPEC_ELEM_TOTAL = SPEC_FRAME_COUNT * N_MELS;
    localparam [14:0] SPEC_ELEM_LAST   = SPEC_ELEM_TOTAL - 1;  // 16575
    localparam [14:0] OUT_FIRST_C      = OUT_FIRST;           // 64
    localparam signed [15:0] DB_TOP_S  = DB_TOP_DB_Q88;       // -20480
    localparam signed [10:0] DB_NUM_S   = DB_SCALE_NUM;       // 775 (needs 11 bits signed; 10 bits capped at 511)

    // ------------------------------------------------------------------
    // consumes spec_rd_data one cycle later (sync RAM latency).
    // ------------------------------------------------------------------
    localparam [2:0] S_IDLE      = 3'd0;
    localparam [2:0] S_MAX_RD    = 3'd1;
    localparam [2:0] S_MAX_CALC  = 3'd2;
    localparam [2:0] S_DB_RD     = 3'd3;
    localparam [2:0] S_DB_CALC   = 3'd4;
    localparam [2:0] S_DB_FLUSH  = 3'd5;
    localparam [2:0] S_DB_SQ_FLUSH = 3'd6;
    localparam [2:0] S_DB_SUM_FLUSH = 3'd7;

    reg [2:0]        state;
    reg [14:0]       elem_cnt;      // current element address (frame-major)
    reg signed [15:0] max_l2;       // running max of log2_q88 (s16 init min)
    reg signed [15:0] db_value_pipe;
    reg               db_value_pipe_valid;
    reg        [31:0] db_sq_pipe;
    reg               db_sq_pipe_valid;

    // ------------------------------------------------------------------
    // dB datapath (combinational, golden db_convert bit-exact).
    // ------------------------------------------------------------------
    wire signed [16:0] diff_s17 = spec_rd_data - max_l2;      // <= 0
    wire signed [26:0] db_mul_s27 = diff_s17 * DB_NUM_S;      // diff * 775
    // rhu_shift(db_mul, 8) = floor((db_mul + 128) / 256)
    wire signed [26:0] db_rhu_s27 = $signed(db_mul_s27 + 27'sd128) >>> 8;
    // merged sat16 + top_db floor + upper clamp (proof in header)
    wire signed [15:0] db_s16 =
        (db_rhu_s27 < $signed({{11{DB_TOP_S[15]}}, DB_TOP_S})) ? DB_TOP_S :
        (db_rhu_s27 > 27'sd0)                                   ? 16'sd0   :
                                                                    db_rhu_s27[15:0];

    // Kept-frame test: addresses below OUT_FIRST_C belong to the dropped
    // head frame (no dB write, no statistics update).
    wire is_out_now = (elem_cnt >= OUT_FIRST_C);

    // ------------------------------------------------------------------
    // External RAM ports (pure combinational: read on RD beats, write on
    // CALC beats - never both in one cycle, single-port-bank friendly).
    // ------------------------------------------------------------------
    assign spec_rd_en   = (state == S_MAX_RD) || (state == S_DB_RD);
    assign spec_rd_addr = elem_cnt;
    assign db_wr_en     = (state == S_DB_CALC) && is_out_now;
    assign db_wr_addr   = elem_cnt;
    assign db_wr_data   = db_s16;

    assign busy = (state != S_IDLE);

    // ------------------------------------------------------------------
    // Scan sequencer.
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            elem_cnt    <= 15'd0;
            max_l2      <= -16'sd32768;
            sum_db      <= 48'sd0;
            sum_db_sq   <= 48'd0;
            stats_valid <= 1'b0;
            db_value_pipe <= 16'sd0;
            db_value_pipe_valid <= 1'b0;
            db_sq_pipe <= 32'd0;
            db_sq_pipe_valid <= 1'b0;
        end else begin
            case (state)
                S_IDLE: begin
                    stats_valid <= 1'b0;
                    if (start) begin
                        elem_cnt  <= 15'd0;
                        max_l2    <= -16'sd32768;
                        sum_db    <= 48'sd0;
                        sum_db_sq <= 48'd0;
                        db_sq_pipe_valid <= 1'b0;
                        db_value_pipe_valid <= 1'b0;
                        state     <= S_MAX_RD;
                    end
                end
                // -------- scan 1: global max over the full spectrum ----
                S_MAX_RD: begin
                    state <= S_MAX_CALC;
                end
                S_MAX_CALC: begin
                    if (spec_rd_data > max_l2) begin
                        max_l2 <= spec_rd_data;
                    end
                    if (elem_cnt == SPEC_ELEM_LAST) begin
                        elem_cnt <= 15'd0;
                        state    <= S_DB_RD;
                    end else begin
                        elem_cnt <= elem_cnt + 15'd1;
                        state    <= S_MAX_RD;
                    end
                end
                // -------- scan 2: dB conversion + statistics -----------
                S_DB_RD: begin
                    db_sq_pipe <= db_value_pipe * db_value_pipe;
                    db_sq_pipe_valid <= db_value_pipe_valid;
                    state <= S_DB_CALC;
                end
                S_DB_CALC: begin
                    if (db_sq_pipe_valid) begin
                        sum_db_sq <= sum_db_sq + {16'd0, db_sq_pipe};
                    end
                    db_value_pipe <= db_s16;
                    db_value_pipe_valid <= is_out_now;
                    if (is_out_now) begin
                        sum_db    <= sum_db + {{32{db_s16[15]}}, db_s16};
                    end
                    if (elem_cnt == SPEC_ELEM_LAST) begin
                        state <= S_DB_FLUSH;
                    end else begin
                        elem_cnt <= elem_cnt + 15'd1;
                        state    <= S_DB_RD;
                    end
                end
                S_DB_FLUSH: begin
                    db_sq_pipe <= db_value_pipe * db_value_pipe;
                    db_sq_pipe_valid <= db_value_pipe_valid;
                    state <= S_DB_SUM_FLUSH;
                end
                S_DB_SUM_FLUSH: begin
                    if (db_sq_pipe_valid) begin
                        sum_db_sq <= sum_db_sq + {16'd0, db_sq_pipe};
                    end
                    db_sq_pipe_valid <= 1'b0;
                    db_value_pipe_valid <= 1'b0;
                    stats_valid <= 1'b1;
                    state <= S_IDLE;
                end
                default: begin
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule


