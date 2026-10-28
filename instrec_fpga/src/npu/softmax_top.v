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
//   percent = round_half_up(p_q16 * 100 / 65536)
//
// The input is the signed logits container (fc2_u8 - zp_out), already
// subtracted by the caller.
//
// Timing note: the eight exp lookups are serialized (one combinationally
// addressed LUT read per cycle), then all eight round-half-up divisions
// run combinationally in the S_CALC beat. This trades area/timing for a
// short, easy-to-audit state machine; softmax is not on the critical
// inference path (it runs once per 3 s window).
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

    localparam [2:0] S_IDLE = 3'd0;
    localparam [2:0] S_EXP  = 3'd1;
    localparam [2:0] S_CALC = 3'd2;
    localparam [2:0] S_OUT  = 3'd3;
    reg [2:0] state;

    reg signed [31:0] lq [0:7];
    reg signed [31:0] lmax;
    reg [15:0]        expv [0:7];
    reg [31:0]        esum;
    reg [15:0]        pq [0:7];
    reg [7:0]         pc [0:7];
    reg [3:0]         lane;
    reg [3:0]         best_i;
    reg [15:0]        best_p;
    reg [31:0]        pfull;

    localparam signed [31:0] Q69_SAT = -32'sd16384;

    wire signed [31:0] dsel = lq[lane] - lmax;
    wire signed [31:0] d69 = $signed(dsel) >>> 6;
    wire signed [31:0] d69s = ($signed(d69) < Q69_SAT) ? Q69_SAT : d69;
    wire [31:0] mag = $signed(-d69s) >>> 4;
    wire [8:0] idx_w = (mag > 32'd511) ? 9'd511 : mag[8:0];

    wire [15:0] e_cur = exp_lut[idx_w];

    // Combination round-half-up division: (e << 16 + sum/2) / sum.
    function [31:0] p_q16_calc;
        input [15:0] e;
        input [31:0] s;
        reg [31:0] num;
        begin
            if (s == 32'd0) p_q16_calc = 32'd0;
            else begin
                num = ({16'd0, e} << 16) + (s >> 1);
                p_q16_calc = num / s;
            end
        end
    endfunction

    // Eight 8-way max tree over the registered l_q values.
    function [31:0] max8;
        input signed [31:0] a0, a1, a2, a3, a4, a5, a6, a7;
        reg signed [31:0] m01, m23, m45, m67, m03, m47;
        begin
            m01 = (a0 > a1) ? a0 : a1;
            m23 = (a2 > a3) ? a2 : a3;
            m45 = (a4 > a5) ? a4 : a5;
            m67 = (a6 > a7) ? a6 : a7;
            m03 = (m01 > m23) ? m01 : m23;
            m47 = (m45 > m67) ? m45 : m67;
            max8 = (m03 > m47) ? m03 : m47;
        end
    endfunction

    wire signed [31:0] l0 = $signed(logits[31:0]);
    wire signed [31:0] l1 = $signed(logits[63:32]);
    wire signed [31:0] l2 = $signed(logits[95:64]);
    wire signed [31:0] l3 = $signed(logits[127:96]);
    wire signed [31:0] l4 = $signed(logits[159:128]);
    wire signed [31:0] l5 = $signed(logits[191:160]);
    wire signed [31:0] l6 = $signed(logits[223:192]);
    wire signed [31:0] l7 = $signed(logits[255:224]);

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
                        lq[0] <= l0 * S_Q15;
                        lq[1] <= l1 * S_Q15;
                        lq[2] <= l2 * S_Q15;
                        lq[3] <= l3 * S_Q15;
                        lq[4] <= l4 * S_Q15;
                        lq[5] <= l5 * S_Q15;
                        lq[6] <= l6 * S_Q15;
                        lq[7] <= l7 * S_Q15;
                        lmax  <= max8(l0 * S_Q15, l1 * S_Q15, l2 * S_Q15, l3 * S_Q15,
                                      l4 * S_Q15, l5 * S_Q15, l6 * S_Q15, l7 * S_Q15);
                        lane  <= 4'd0;
                        esum  <= 32'd0;
                        state <= S_EXP;
                    end
                end

                S_EXP: begin
                    // Combinational LUT address from the just-registered
                    // l_q[lane]; one lane per cycle.
                    expv[lane] <= e_cur;
                    esum       <= esum + e_cur;
                    lane       <= lane + 4'd1;
                    if (lane == 4'd7) begin
                        lane  <= 4'd0;
                        state <= S_CALC;
                    end
                end

                S_CALC: begin
                    // One shared round-half-up divider, one lane per cycle.
                    pfull = p_q16_calc(expv[lane], esum);
                    pq[lane] <= (pfull > 32'd65535) ? 16'd65535 : pfull[15:0];
                    lane <= lane + 4'd1;
                    if (lane == 4'd7) begin
                        lane  <= 4'd0;
                        state <= S_OUT;
                    end
                end

                S_OUT: begin
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