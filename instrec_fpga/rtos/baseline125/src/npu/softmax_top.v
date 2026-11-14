// ---------------------------------------------------------------------------
// softmax_top.v -- fixed-point 8-class softmax (design.md 4.5)
//
// Bit truth: golden_pipeline.softmax_fixed().
//   l_int   = fc2_u8 - zp_out                     (signed container)
//   l_q     = l_int * S_Q15                       (Q16.15 pre-scale)
//   d       = l_q - max(l_q)                      (<= 0)
//   d_q69   = d >>> 6                             (Q6.9, sat -16384)
//   idx     = min((-d_q69) >>> 4, 511)
//   exp     = exp_lut[idx]                        (Q0.16, 512 x uint16)
//   p_q16   = min((exp << 16 + sum/2) / sum, 65535)
//   percent = round_half_even(p_q16 * 100 / 65536)
//
// The input is the signed logits container (fc2_u8 - zp_out), already
// subtracted by the caller.
//
// Timing: every arithmetic op is registered and no stage holds more than
// one adder / one comparator tree level, so the previous 267-level
// combinational chain (8 parallel constant multiplies -> max tree ->
// 32-bit subtract -> LUT read -> combinational / divide -> best_p) is
// gone.  The constant multiply is split into two beats using
//   S_Q15 = 9197 = 8192 + 1024 - 16 - 2 - 1
// and the division is a byte-serial restoring divider (one quotient bit
// per cycle) instead of a combinational / operator.
//
// Stage beats (8 lanes unless noted):
//   S_MUL   16  mul_phase 0: m_hi/m_lo partial sums; phase 1: lq[lane]
//   S_MAX1   1  four pair maxima
//   S_MAX2   1  two pair maxima
//   S_MAX3   1  lmax
//   S_DSEL   8  dsel[lane] = lq[lane] - lmax
//   S_IDX    8  d69 / sat / idx pushed into a 72-bit shift register
//   S_LUT    8  expv[lane] = exp_lut[idx_sr top 9 bits] (no 8:1 mux)
//   S_ACC    8  esum += expv[lane]
//   S_DINIT  1  load numerator/divisor per channel
//   S_DIV   33  restoring divide, one bit per cycle
//   S_DIVW   1  pq[ch] = saturate(quotient)
//   S_PCT    8  out_q16 / out_pct / best_p
// Total 16+3+8+8+8+8+8*(1+33+1)+8 = 340 beats at 125 MHz.  Softmax runs
// once per 3 s window, so the latency is irrelevant.
// ---------------------------------------------------------------------------

module softmax_top #(
    parameter signed [31:0] S_Q15 = 32'sd9197    // round(s_out * 2^15), fc2
) (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        start,           // one-cycle trigger
    input  wire [255:0] logits,         // 8 x s32, lane i = logits[i]

    output reg         out_valid,
    output reg  [15:0] out_q16,         // probability Q0.16
    output reg  [7:0]  out_pct,         // 0..100
    output reg  [3:0]  out_idx,
    output reg  [3:0]  top1_idx,
    output reg         done
);

    reg [15:0] exp_lut [0:511];

    initial begin
        $readmemh("src/mel/exp_lut.hex", exp_lut);
    end

    localparam [3:0] S_IDLE  = 4'd0;
    localparam [3:0] S_MUL   = 4'd1;
    localparam [3:0] S_MAX1  = 4'd2;
    localparam [3:0] S_MAX2  = 4'd3;
    localparam [3:0] S_MAX3  = 4'd4;
    localparam [3:0] S_DSEL  = 4'd5;
    localparam [3:0] S_IDX   = 4'd6;
    localparam [3:0] S_LUT   = 4'd7;
    localparam [3:0] S_ACC   = 4'd8;
    localparam [3:0] S_DINIT = 4'd9;
    localparam [3:0] S_DIV   = 4'd10;
    localparam [3:0] S_DIVW  = 4'd11;
    localparam [3:0] S_PCT   = 4'd12;

    reg [3:0] state;

    reg signed [31:0] lq [0:7];
    reg signed [31:0] lmax;
    reg signed [31:0] dsel [0:7];
    reg [71:0]        idx_sr;   // 8 x 9-bit LUT index, lane 0 in [71:63]
    reg [15:0]        expv [0:7];
    reg [31:0]        esum;
    reg [15:0]        pq [0:7];

    reg signed [31:0] m_hi;
    reg signed [31:0] m_lo;
    reg signed [31:0] mx01;
    reg signed [31:0] mx23;
    reg signed [31:0] mx45;
    reg signed [31:0] mx67;
    reg signed [31:0] mx03;
    reg signed [31:0] mx47;

    reg [32:0] div_sh;      // shifting dividend, MSB consumed each beat
    reg [20:0] div_rem;     // partial remainder (den < 2^19, rem < 2^20)
    reg [32:0] div_quo;     // quotient, one bit per beat
    reg [5:0]  bit_cnt;     // 0..32 divider beat index

    reg [3:0] lane;
    reg [2:0] ch;
    reg       mul_phase;
    reg [3:0] best_i;
    reg [15:0] best_p;

    localparam signed [31:0] Q69_SAT = -32'sd16384;

    wire signed [31:0] l0 = $signed(logits[31:0]);
    wire signed [31:0] l1 = $signed(logits[63:32]);
    wire signed [31:0] l2 = $signed(logits[95:64]);
    wire signed [31:0] l3 = $signed(logits[127:96]);
    wire signed [31:0] l4 = $signed(logits[159:128]);
    wire signed [31:0] l5 = $signed(logits[191:160]);
    wire signed [31:0] l6 = $signed(logits[223:192]);
    wire signed [31:0] l7 = $signed(logits[255:224]);

    // 8:1 lane select for the serialized constant multiplier.
    reg signed [31:0] lsel;
    always @* begin
        case (lane)
            4'd0: lsel = l0;
            4'd1: lsel = l1;
            4'd2: lsel = l2;
            4'd3: lsel = l3;
            4'd4: lsel = l4;
            4'd5: lsel = l5;
            4'd6: lsel = l6;
            default: lsel = l7;
        endcase
    end

    // l_int * 9197 as two registered partial sums (one add per beat).
    wire signed [31:0] mul_hi_n = (lsel << 13) + (lsel << 10);
    wire signed [31:0] mul_lo_n = (lsel << 4) + (lsel << 1) + lsel;
    wire signed [31:0] mul_n    = m_hi - m_lo;

    // Q16.15 -> Q6.9 with s15 saturation, then LUT index.
    wire signed [31:0] dsel_n = lq[lane] - lmax;
    wire signed [31:0] d69_n  = $signed(dsel[lane]) >>> 6;
    wire signed [31:0] d69s_n = (d69_n < Q69_SAT) ? Q69_SAT : d69_n;
    wire signed [31:0] mag_n  = -d69s_n;
    wire [31:0]        magq_n = $signed(mag_n) >>> 4;
    wire [8:0]         idx_n  = (magq_n > 32'd511) ? 9'd511 : magq_n[8:0];

    // Restoring divider operands: num = (exp << 16) + esum/2, den = esum.
    // exp <= 0xFFFF and esum <= 8 * 0xFFFF, so num <= 4295163900 needs 33
    // bits (a 32-bit container would wrap to a tiny numerator and return a
    // zero probability for the dominant class, which golden does not).
    // esum < 2^19, so 21 bits hold 2*den + 1.
    wire [32:0] div_num_n = ({17'd0, expv[ch]} << 16) + {1'b0, esum >> 1};
    wire [20:0] den_ext   = {2'b00, esum[18:0]};
    wire [20:0] rem_n     = {div_rem[19:0], div_sh[32]};
    wire [20:0] rem_sub   = rem_n - den_ext;
    wire        rem_ge    = (rem_n >= den_ext);

    // round_half_even(pq * 100 / 65536)
    function [7:0] pct_rhe;
        input [15:0] p;
        reg [31:0] prod;
        reg [31:0] q;
        reg [31:0] rem;
        begin
            prod = {16'd0, p} * 32'd100;
            q    = prod >> 16;
            rem  = prod & 32'hFFFF;
            if (rem > 32'd32768 || (rem == 32'd32768 && q[0]))
                q = q + 32'd1;
            pct_rhe = (q > 32'd100) ? 8'd100 : q[7:0];
        end
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= S_IDLE;
            lane      <= 4'd0;
            ch        <= 3'd0;
            bit_cnt   <= 6'd0;
            mul_phase <= 1'b0;
            esum      <= 32'd0;
            out_valid <= 1'b0;
            out_q16   <= 16'd0;
            out_pct   <= 8'd0;
            out_idx   <= 4'd0;
            top1_idx  <= 4'd0;
            done      <= 1'b0;
            best_i    <= 4'd0;
            best_p    <= 16'd0;
            lmax      <= 32'sd0;
        end else begin
            out_valid <= 1'b0;
            done      <= 1'b0;

            case (state)
                S_IDLE: begin
                    if (start) begin
                        lane      <= 4'd0;
                        esum      <= 32'd0;
                        mul_phase <= 1'b0;
                        state     <= S_MUL;
                    end
                end

                // One lane every two beats: partial sums then the subtract.
                S_MUL: begin
                    if (mul_phase == 1'b0) begin
                        m_hi      <= mul_hi_n;
                        m_lo      <= mul_lo_n;
                        mul_phase <= 1'b1;
                    end else begin
                        lq[lane]  <= mul_n;
                        mul_phase <= 1'b0;
                        lane      <= lane + 4'd1;
                        if (lane == 4'd7) begin
                            lane  <= 4'd0;
                            state <= S_MAX1;
                        end
                    end
                end

                S_MAX1: begin
                    mx01  <= (lq[0] > lq[1]) ? lq[0] : lq[1];
                    mx23  <= (lq[2] > lq[3]) ? lq[2] : lq[3];
                    mx45  <= (lq[4] > lq[5]) ? lq[4] : lq[5];
                    mx67  <= (lq[6] > lq[7]) ? lq[6] : lq[7];
                    state <= S_MAX2;
                end

                S_MAX2: begin
                    mx03  <= (mx01 > mx23) ? mx01 : mx23;
                    mx47  <= (mx45 > mx67) ? mx45 : mx67;
                    state <= S_MAX3;
                end

                S_MAX3: begin
                    lmax  <= (mx03 > mx47) ? mx03 : mx47;
                    state <= S_DSEL;
                end

                S_DSEL: begin
                    dsel[lane] <= dsel_n;
                    lane       <= lane + 4'd1;
                    if (lane == 4'd7) begin
                        lane  <= 4'd0;
                        state <= S_IDX;
                    end
                end

                S_IDX: begin
                    idx_sr <= {idx_sr[62:0], idx_n};
                    lane   <= lane + 4'd1;
                    if (lane == 4'd7) begin
                        lane  <= 4'd0;
                        state <= S_LUT;
                    end
                end

                // LUT address comes straight from the shift register, so
                // this beat is only the 512:1 LUT read plus a register.
                S_LUT: begin
                    expv[lane] <= exp_lut[idx_sr[71:63]];
                    idx_sr     <= {idx_sr[62:0], 9'd0};
                    lane       <= lane + 4'd1;
                    if (lane == 4'd7) begin
                        lane  <= 4'd0;
                        state <= S_ACC;
                    end
                end

                S_ACC: begin
                    esum <= esum + expv[lane];
                    lane <= lane + 4'd1;
                    if (lane == 4'd7) begin
                        lane  <= 4'd0;
                        ch    <= 3'd0;
                        state <= S_DINIT;
                    end
                end

                S_DINIT: begin
                    div_sh  <= div_num_n;
                    div_rem <= 21'd0;
                    div_quo <= 33'd0;
                    bit_cnt <= 6'd0;
                    state   <= S_DIV;
                end

                // Restoring division: shift in the next dividend bit, then
                // subtract the divisor when the partial remainder fits.
                // esum == 0 keeps the quotient at zero (p_q16_calc guard).
                S_DIV: begin
                    div_sh  <= {div_sh[31:0], 1'b0};
                    bit_cnt <= bit_cnt + 6'd1;
                    if (esum != 32'd0 && rem_ge) begin
                        div_rem <= rem_sub;
                        div_quo <= {div_quo[31:0], 1'b1};
                    end else begin
                        div_rem <= rem_n;
                        div_quo <= {div_quo[31:0], 1'b0};
                    end
                    if (bit_cnt == 6'd32) begin
                        bit_cnt <= 6'd0;
                        state   <= S_DIVW;
                    end
                end

                S_DIVW: begin
                    pq[ch] <= (div_quo > 33'd65535) ? 16'd65535
                                                    : div_quo[15:0];
                    if (ch == 3'd7) begin
                        ch    <= 3'd0;
                        state <= S_PCT;
                    end else begin
                        ch    <= ch + 3'd1;
                        state <= S_DINIT;
                    end
                end

                S_PCT: begin
                    out_valid <= 1'b1;
                    out_q16   <= pq[lane];
                    // Percent uses round-half-to-even to match golden's
                    // np.rint; a plain +32768 shift is round-half-up and
                    // differs on exact ties (e.g. pq=8192 -> 12, not 13).
                    out_pct   <= pct_rhe(pq[lane]);
                    out_idx   <= lane;
                    if (pq[lane] > best_p) begin
                        best_p <= pq[lane];
                        best_i <= lane;
                    end
                    lane <= lane + 4'd1;
                    if (lane == 4'd7) begin
                        // lane 7 update is visible one beat later; fold it
                        // into the final top-1 decision here.
                        done     <= 1'b1;
                        top1_idx <= (pq[7] > best_p) ? 4'd7 : best_i;
                        state    <= S_IDLE;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule