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
// Architecture (two scans; scan 2 uses a 4-beat pipeline):
//   * Scan 1 (max): two-cycle beat, unchanged. Read every element and
//     keep the running max of the signed Q8.8 log2 values.
//   * Scan 2 (dB + statistics): four-beat pipeline. Beat 0 issues the
//     read, beat 1 registers the difference against max_l2, beat 2
//     computes diff*775/256 + clamp into db_s16_q, beat 3 registers the
//     square and writes the dB value back, beat 4 accumulates dB^2.
//     The pipeline splits the former single-cycle
//     DRAM->APM->LUT->APM->LUT->APM chain into four short stages
//     (125 MHz core_clk timing closure, T-M1-06 build fix). It only
//     adds latency: every element still produces the same dB value and
//     contributes exactly once to both sums, so the bit-exact golden
//     parity is unchanged.
//   * Read and write never fire in the same cycle (write is beat 3,
//     read is beat 0 of the next element), so mel_engine may map both
//     ports onto one single-port RAM bank.
//
// Storage / INTEGRATION ALIGNMENT POINTS (buffer NOT instantiated here):
//   * The 64 x 259 int16 log2-spectrum buffer is owned by the mel_engine
//     integration (T-M1-05; first pass writes it - Jiang's line). This
//     module only drives the external read port (spec_rd_*) and the
//     external overwrite port (db_wr_*). Scan 2 reads log2[i] on the RD
//     beat and overwrites the SAME address with dB[i] three beats later
//     (pipeline beat 3). Frame-major addressing: addr = frame * N_MELS + mel;
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
//   scan 2 (dB+sums):  4 cycles/element * 16576 = 66304 cycles
//   total ~99.5k cycles = 0.80 ms, well inside the 3 s window cadence
//   and the M1 150 ms budget (T1.2). The extra two beats per element
//   are the cost of closing 125 MHz timing; no numerical change.
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
    localparam signed [9:0] DB_NUM_S   = DB_SCALE_NUM;        // 775

    // ------------------------------------------------------------------
    // Scan FSM. Scan 1 keeps the two-beat rhythm; scan 2 is a four-beat
    // pipeline so no stage exceeds a 125 MHz core_clk period.
    // ------------------------------------------------------------------
    localparam [2:0] S_IDLE      = 3'd0;
    localparam [2:0] S_MAX_RD    = 3'd1;
    localparam [2:0] S_MAX_CALC  = 3'd2;
    localparam [2:0] S_DB_RD     = 3'd3;
    localparam [2:0] S_DB_DIFF   = 3'd4;
    localparam [2:0] S_DB_MUL    = 3'd5;
    localparam [2:0] S_DB_SQ     = 3'd6;
    localparam [2:0] S_DB_ACC    = 3'd7;

    reg [2:0]        state;
    reg [14:0]       elem_cnt;      // current element address (frame-major)
    reg signed [15:0] max_l2;       // running max of log2_q88 (s16 init min)

    // Scan-2 pipeline registers (one element in flight per stage).
    reg signed [16:0] diff_q;       // log2 - max_l2, registered at beat 1
    reg [14:0]        addr_q;       // element address carried with the pipeline
    reg               is_out_q;     // addr_q belongs to the kept 258 frames
    reg signed [15:0] db_s16_q;     // clamped dB value, registered at beat 2
    reg signed [31:0] db_sq_q;      // db_s16_q * db_s16_q, registered at beat 3

    // ------------------------------------------------------------------
    // dB datapath. Stage 1 (S_DB_DIFF) subtracts max_l2; stage 2
    // (S_DB_MUL) applies the golden db_convert scale and clamps; stage 3
    // (S_DB_SQ) forms the square and writes the dB value back; stage 4
    // (S_DB_ACC) accumulates the square. Splitting the former
    // combinational chain across registers keeps the golden value
    // bit-exact (each stage is the same arithmetic, only later in time).
    // ------------------------------------------------------------------
    wire signed [16:0] diff_c   = spec_rd_data - max_l2;      // <= 0
    wire signed [26:0] db_mul_c = diff_q * DB_NUM_S;          // diff * 775
    // rhu_shift(db_mul, 8) = floor((db_mul + 128) / 256)
    wire signed [26:0] db_rhu_c = $signed(db_mul_c + 27'sd128) >>> 8;
    // merged sat16 + top_db floor + upper clamp (proof in header)
    wire signed [15:0] db_s16_c =
        (db_rhu_c < $signed({{11{DB_TOP_S[15]}}, DB_TOP_S})) ? DB_TOP_S :
        (db_rhu_c > 27'sd0)                                  ? 16'sd0   :
                                                               db_rhu_c[15:0];

    // dB^2 for the variance accumulator (s16*s16 -> s32, <= 20480^2)
    wire signed [31:0] db_sq_c = db_s16_q * db_s16_q;

    // Kept-frame test: addresses below OUT_FIRST_C belong to the dropped
    // head frame (no dB write, no statistics update). Sampled into
    // is_out_q with the address so the write and accumulate stages use
    // the same classification.
    wire is_out_now = (elem_cnt >= OUT_FIRST_C);

    // ------------------------------------------------------------------
    // External RAM ports (read on the scan RD beat, write on pipeline
    // beat 3; never both in one cycle - single-port-bank friendly).
    // ------------------------------------------------------------------
    assign spec_rd_en   = (state == S_MAX_RD) || (state == S_DB_RD);
    assign spec_rd_addr = elem_cnt;
    assign db_wr_en     = (state == S_DB_SQ) && is_out_q;
    assign db_wr_addr   = addr_q;
    assign db_wr_data   = db_s16_q;

    assign busy = (state != S_IDLE);

    // ------------------------------------------------------------------
    // Scan sequencer.
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            elem_cnt    <= 15'd0;
            max_l2      <= -16'sd32768;
            diff_q      <= 17'sd0;
            addr_q      <= 15'd0;
            is_out_q    <= 1'b0;
            db_s16_q    <= 16'sd0;
            db_sq_q     <= 32'sd0;
            sum_db      <= 48'sd0;
            sum_db_sq   <= 48'd0;
            stats_valid <= 1'b0;
        end else begin
            case (state)
                S_IDLE: begin
                    stats_valid <= 1'b0;
                    if (start) begin
                        elem_cnt  <= 15'd0;
                        max_l2    <= -16'sd32768;
                        sum_db    <= 48'sd0;
                        sum_db_sq <= 48'd0;
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
                    state <= S_DB_DIFF;
                end
                // beat 1: capture the synchronous read and the address
                S_DB_DIFF: begin
                    diff_q   <= diff_c;
                    addr_q   <= elem_cnt;
                    is_out_q <= is_out_now;
                    state    <= S_DB_MUL;
                end
                // beat 2: scale + clamp into the registered dB value
                S_DB_MUL: begin
                    db_s16_q <= db_s16_c;
                    state    <= S_DB_SQ;
                end
                // beat 3: write dB back, form the square, accumulate dB
                S_DB_SQ: begin
                    db_sq_q <= db_sq_c;
                    if (is_out_q) begin
                        sum_db <= sum_db + {{32{db_s16_q[15]}}, db_s16_q};
                    end
                    state <= S_DB_ACC;
                end
                // beat 4: accumulate the square, advance / finish
                S_DB_ACC: begin
                    if (is_out_q) begin
                        sum_db_sq <= sum_db_sq +
                                     {{16{db_sq_q[31]}}, db_sq_q};
                    end
                    if (elem_cnt == SPEC_ELEM_LAST) begin
                        stats_valid <= 1'b1;  // sums final, bank overwritten
                        state       <= S_IDLE;
                    end else begin
                        elem_cnt <= elem_cnt + 15'd1;
                        state    <= S_DB_RD;
                    end
                end
                default: begin
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule