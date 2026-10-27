// ---------------------------------------------------------------------------
// requant_unit.v -- bit-exact INT8 requantization core (NPU numeric heart)
//
// Task      : T-M2-05 requant_unit (INT8 CNN NPU numeric core)
// Bit truth : scripts/golden_pipeline.py  requant_u8() +
//             round_half_even_shift()  (bit-level golden reference)
// Contract  : scripts/outputs/layer_contract.json  -- M per-channel Q0.31
//             s32 in [2^30, 2^31), shift per-channel 6-bit (measured 37..53
//             across the 6-layer contract), zp_out layer constant 0..255,
//             bias_int32 folded into acc_s32 by the upstream engine.
//
// Golden formula (design.md 4.3, fbgemm bit-level rounding parity):
//     y = sat_u8( round_half_even(acc_s32 * M_s32 >>> shift) + zp_out )
//
// Round-half-to-even (banker's rounding) is THE soul of this unit:
// exact halves resolve to the even neighbour, sign-symmetric
// (-2.5 -> -2, +3.5 -> +4), mirroring PyTorch quantize semantics.
// A plain truncating shift accumulates a systematic half-LSB bias which
// the next 432-tap conv stage amplifies (measured conv2 spread up to
// 32 LSB); with half-even rounding conv1 matches the TorchScript
// reference EXACTLY (0 LSB). See requant_u8() docstring in the golden.
//
// golden round_half_even_shift(x, k) -- abs-based form:
//     sign = (x < 0);  av = sign ? -x : x
//     q    = av >> k                       # floor(av / 2^k)
//     rem  = av & ((1 << k) - 1)           # 0 <= rem < 2^k
//     half = 1 << (k - 1)
//     inc  = (rem > half) | ((rem == half) & (q & 1))
//     q    = q + inc;  return sign ? -q : q
//
// RTL two's-complement direct form (no abs branch, one carry adder):
//     q0  = prod >>> k                      # arithmetic shift = floor
//     rem = prod & (2^k - 1)                # low k bits, 0 <= rem < 2^k
//     inc = (rem > half) | ((rem == half) & q0[0])
//     q   = q0 + inc
// Both forms round the SAME value to even: for prod >= 0 they are
// identical; for prod < 0, |prod| = q_a*2^k + r_a with floor(prod/2^k)
// = -(q_a+1) and rem = 2^k - r_a, and a case split on r_a vs half
// shows both pick the same even neighbour (ties included) because
// round-half-even is sign-symmetric (-even stays even).
//
// Time-division multiplexing across the 16-channel output group
// (TDM beat plan, one physical instance serves the whole group):
//     beat  0      : channel 0  (acc[0], M[0], shift[0])
//     beat  1      : channel 1
//     ...
//     beat  15     : channel 15 -> group result complete
// The conv_engine feeds one channel per cycle (1 multiply/cycle); the
// 16-beat batch hides entirely inside the 9*Cin >= 432-cycle tap scan
// of the next pixel (design.md 4.3 hiding note), except conv1
// (Cin = 1, 9-cycle scan) where the engine stretches the beat plan to
// 16 cycles per group pixel (see conv_engine.v timing budget table).
//
// Pipeline, core_clk 125 MHz (8 ns per stage), throughput 1/cycle,
// 4-cycle latency:
//     S1  register operands (acc, M, shift, zp_out)
//     S2  32x32 signed multiply -> s64 (APM/DSP inferred, ~4 APM)
//     S3  arithmetic barrel shift + tie-to-even carry
//     S4  add zp_out, saturate to [0, 255] -> y_u8
//
// Edge guard: the golden requires k >= 1 (Python 1 << (k-1) raises
// ValueError on k = 0); the measured contract is 37..53. shift == 0 is
// a defensive bypass only: rounding is skipped and prod passes through
// (identity), which equals round_half_even(x, 0) = x.
//
// Reset: asynchronous-active-low, all pipeline stages flushed.
// ---------------------------------------------------------------------------

module requant_unit (
    // clock / reset (core_clk 125 MHz domain)
    input  wire               clk,
    input  wire               rst_n,
    // operand stream: one channel per beat (16-beat TDM per group)
    input  wire signed [31:0] acc_s32,   // s32 accumulator, bias folded in
    input  wire signed [31:0] m_s32,     // Q0.31 multiplier in [2^30,2^31)
    input  wire        [6:0]  shift,     // 6-bit effective (37..53 measured)
    input  wire        [7:0]  zp_out,    // output zero point, 0..255
    input  wire               in_valid,  // operand beat valid
    // result stream
    output reg         [7:0]  y_u8,      // sat_u8 requantized value
    output reg                out_valid  // pipelined, 4 cycles after in_valid
);

    // -----------------------------------------------------------------------
    // Pipeline registers
    // -----------------------------------------------------------------------
    reg signed [31:0] acc_q;    // S1: latched accumulator
    reg signed [31:0] m_q;      // S1: latched multiplier
    reg        [6:0]  shift_q;  // S1: latched shift amount
    reg        [7:0]  zp_q;     // S1: latched output zero point
    reg               v1_q;     // S1 valid

    reg signed [63:0] prod_q;   // S2: acc * M, exact in s64
    reg               v2_q;     // S2 valid

    reg signed [63:0] rhe_q;    // S3: round_half_even(prod >>> shift)
    reg               v3_q;     // S3 valid

    // -----------------------------------------------------------------------
    // S1 -> S2 combinational: signed 32x32 multiply, exact into 64 bits.
    // Synthesis maps this onto APM 18x18 tiles (4 blocks with sign
    // extension) or LUT multipliers, per the resource budget table.
    // -----------------------------------------------------------------------
    wire signed [63:0] prod_c = acc_q * m_q;

    // -----------------------------------------------------------------------
    // S2 -> S3 combinational: bit-level mirror of golden
    // round_half_even_shift(). shift == 0 guard: q0 passes prod through
    // and inc is forced to 0 (identity; golden itself requires k >= 1).
    // -----------------------------------------------------------------------
    wire shift_zero = (shift_q == 7'd0);

    // q0 = floor(prod / 2^shift): arithmetic barrel shift
    wire signed [63:0] q0 = shift_zero ? prod_q : (prod_q >>> shift_q);

    // rem = prod & (2^shift - 1): low shift bits, unsigned 0..2^shift-1
    wire [63:0] rem_mask = ~(~64'd0 << shift_q);
    wire [63:0] rem      = prod_q & rem_mask;

    // half = 2^(shift-1): one-hot barrel shift (tie donor bit)
    wire [63:0] half     = 64'd1 << (shift_q - 7'd1);

    // three-way compare via a single 64-bit subtract:
    //   rem - half -> borrow = rem < half, zero = rem == half
    wire [63:0] rem_d    = rem - half;
    wire        rem_lt   = rem_d[63];            // borrow: rem <  half
    wire        rem_eq   = (rem_d == 64'd0);     //           rem == half
    wire        rem_gt   = ~rem_lt & ~rem_eq;    //           rem >  half

    // tie-to-even carry: round up on rem > half, or on an exact tie
    // when the truncated quotient is odd (ties go to the even neighbour)
    wire        inc      = ~shift_zero &
                           (rem_gt | (rem_eq & q0[0]));

    wire signed [63:0] rhe_c = q0 + {{63{1'b0}}, inc};

    // -----------------------------------------------------------------------
    // S3 -> S4 combinational: + zp_out, saturate to [0, 255]
    // (golden: np.clip(round_half_even(...) + zp_out, 0, 255))
    // -----------------------------------------------------------------------
    wire signed [64:0] y_sum  = {rhe_q[63], rhe_q} +
                                $signed({{57{1'b0}}, zp_q});

    wire y_lt0   = y_sum[64];                       // negative rail
    wire y_gt255 = (~y_sum[64]) & (|y_sum[62:8]);   // >= 256 upper rail
    wire [7:0] y_sat_c = y_lt0   ? 8'd0   :
                         y_gt255 ? 8'd255 :
                                   y_sum[7:0];

    // -----------------------------------------------------------------------
    // Pipeline sequencing (single always block, no hazard: every stage
    // consumes only the previous stage register).
    // -----------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc_q     <= 32'sd0;
            m_q       <= 32'sd0;
            shift_q   <= 7'd0;
            zp_q      <= 8'd0;
            v1_q      <= 1'b0;
            prod_q    <= 64'sd0;
            v2_q      <= 1'b0;
            rhe_q     <= 64'sd0;
            v3_q      <= 1'b0;
            y_u8      <= 8'd0;
            out_valid <= 1'b0;
        end else begin
            // S1: operand capture
            acc_q   <= acc_s32;
            m_q     <= m_s32;
            shift_q <= shift;
            zp_q    <= zp_out;
            v1_q    <= in_valid;
            // S2: multiply
            prod_q  <= prod_c;
            v2_q    <= v1_q;
            // S3: round-half-even shift
            rhe_q   <= rhe_c;
            v3_q    <= v2_q;
            // S4: add zp_out and saturate
            y_u8    <= y_sat_c;
            out_valid <= v3_q;
        end
    end

endmodule