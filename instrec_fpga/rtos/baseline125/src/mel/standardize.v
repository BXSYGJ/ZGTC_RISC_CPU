// -----------------------------------------------------------------------------
// standardize - Mel second-pass back half (tasks.md T-M1-04/T-M1-05,
//               design.md Sec. 3.6 / Sec. 3.7 / Sec. 3.1 stages S8-S10):
//               per-sample standardization (mu/sigma) and the QuantStub
//               int8 CNN-input quantization.
// -----------------------------------------------------------------------------
// Bit-exact reference: scripts/golden_pipeline.py standardize() +
// quantize_int8(). Function-by-function semantic mapping:
//
//   golden standardize():                      RTL here:
//   --------------------------------------------------------------------
//   mu_q88 = trunc_div(sum_db, 16512)          S_DIV_MU: 48-cycle
//   (truncation toward zero)                   restoring divider on
//   (s48 accumulator)                          |sum_db| with sign restore
//                                               = trunc-toward-zero parity
//   mu^2 (int64)                               S_MUL_MU: s16*s16 -> s32
//   var_q16 = trunc_div(sum_db_sq, 16512)      S_DIV_VAR: same shared
//   - mu^2, floored at 0                       divider (unsigned floor)
//                                               + S_SUB_VAR max(,0)
//   sigma = math.isqrt(var_q16)                S_SQRT: 24-cycle restoring
//   (EXACT floor sqrt)                         digit-recurrence sqrt -
//                                               bit-exact floor, see D3
//   sigma_eff = max(sigma, 1)                  S_SEL_INV (1-LSB Q8.8 floor
//                                               = the 1e-6 stand-in,
//                                               design.md Sec. 3.6 item 2)
//   inv_sigma = (2^20 + (sigma_eff >> 1))      S_DIV_INV: shared divider
//   // sigma_eff     (round-half-up, positive) on the 2^20+half dividend
//                                               (unsigned floor = rhu)
//   z_q412 = sat16(rhu_shift(                  S_SCAN_Z: (dB-mu)*inv_sigma
//   (dB - mu) * inv_sigma, 8))                 +128 >>> 8, sat16
//   --------------------------------------------------------------------
//   golden quantize_int8() (QuantStub parity,
//   layer_contract.json quant_stub_input_contract):
//   prod = z_q412 * inv_s_in (int64)           S_SCAN_Q: s16 * s32 -> s48
//   x = round_half_even_shift(prod, 24)        bitwise round-half-to-even:
//   + zp_in                                      abs -> q=av>>24 ->
//   clip(x, 0, 255) -> uint8                    rem==half tie -> even q
//                                               -> sign restore -> +ZP_IN
//                                               -> saturate [0, 255]
//
// Fixed-point constant derivations (every constant traceable):
//   * mu = sum_db / 16512: 16512 = 64 * 258 = MEL_ELEMENT_COUNT, the
//     per-sample statistics denominator (design.md Sec. 3.6 item 1).
//   * var_q16 domain: dB_q88 is Q8.8, so dB^2 and mu^2 are Q8.16; the
//     difference is variance in Q8.16. Bounds: mean_sq <= 20480^2 <
//     2^29 and mu^2 <= 20480^2 < 2^29, so var fits u32; sigma =
//     isqrt(var) <= 20480 (Q8.8, 15 bits significant).
//   * inv_sigma = round(2^20 / sigma_q88): sigma_q88 is Q8.8, so
//     inv_sigma = 2^12 / sigma_dB as an integer. Multiplying
//     (dB - mu) [Q8.8] by inv_sigma gives (dB-mu)/sigma * 2^20; the
//     >> 8 shift lands in Q4.12 (value range +/-8 covering +/-6 sigma,
//     design.md Sec. 3.6 item 4).
//   * rhu_shift(x, 8) = floor((x + 2^7) / 2^8): +128 then arithmetic
//     shift (ties toward +infinity).
//   * Quantization: inv_s_in = round(2^24 / s_in) = 267723430 in Q8.24
//     and zp_in = 49, both from layer_contract.json (quant_stub_input_
//     contract, inv_s_in_bits = 32, format Q8.24). prod = z_q412 *
//     inv_s_in has magnitude < 32768 * 2^28 < 2^44 (s48 container).
//   * round_half_even(x >> 24) bitwise form: sign = x < 0; av = |x|;
//     q = av[47:24]; rem = av[23:0]; inc = (rem > 2^23) ||
//     ((rem == 2^23) && q[0]); q += inc; restore sign. Exact halves go
//     to the even neighbour, sign-symmetric (PyTorch fbgemm parity).
//   * Output domain: UNSIGNED uint8 in [0, 255] with the +49 zero-point
//     offset (the quantized-domain zero is 49; all-silent windows give
//     an all-49 feature). design.md Sec. 3.1 S10 / Sec. 3.7 write
//     "qint8 [-128, 127]" but the golden and the layer contract use
//     quint8 [0, 255] - deviation D4, golden wins.
//
// Multi-cycle units (timing / cycle budget, design.md Sec. 3.6):
//   * Shared restoring divider (48 cycles per division, 3 uses):
//     classic MSB-first shift-subtract. Containers: dividend 48b
//     (left-shifted, one bit consumed per cycle), divisor 48b, partial
//     remainder 49b (trial subtraction upper bound 2*D - 1), quotient
//     48b (MSB-first shift-in; the 48-bit container keeps the quotient
//     low-aligned exactly because the dividend is a fixed 48-bit word).
//     Semantics: unsigned floor for the two positive operands; the mu
//     division runs on |sum_db| with a sign flip afterwards = the
//     golden trunc_div toward zero.
//   * Restoring square root (24 cycles): digit-recurrence, two input
//     bits per cycle. Invariants: after k pairs, q = isqrt of the
//     consumed prefix and r < 2q + 1; the trial subtrahend is
//     (q << 2) | 1 (4q + 1). Partial remainder container 27b (4r + pair
//     < 2^27 for r < 2^25). Exact floor matches math.isqrt bit-for-bit
//     (an NR iterator with 2^-10 error would NOT match the golden -
//     deviation D3 vs design.md Sec. 3.6 wording).
//   * Statistics phase total: 48 + 1 + 48 + 1 + 24 + 1 + 48 = 171
//     cycles per window (design.md Sec. 3.6 "3 x 16-cycle divisions"
//     is optimistic about the shared-divider reuse cost; at 3 s per
//     window the difference is irrelevant).
//   * Quantization scan: 6 cycles/element (read -> difference -> multiply
//     -> z round/clamp -> quantization multiply -> quantize/write).
//     Registered DSP inputs and products remove the RAM-to-subtract-to-DSP
//     path and separate multiplication from rounding without changing bits.
//     Total ~99.3k cycles = 0.80 ms @ 125 MHz, below the 3 s cadence.
//
// Storage / INTEGRATION ALIGNMENT POINTS (buffers NOT instantiated here):
//   * The dB spectrum (64 x 258 int16 Q8.8, frame-major, addresses
//     DB_ADDR_OFFSET .. DB_ADDR_OFFSET+16511 in the bank that db_norm
//     overwrote) is read through the external port db_rd_* assuming a
//     1-cycle synchronous read RAM. DB_ADDR_OFFSET = HEAD_DROP *
//     N_MELS = 64 keeps the golden keep-tail frame numbering (frame 0
//     dropped). Set DB_ADDR_OFFSET = 0 if the integration stores the
//     already-truncated 258 frames at address 0 (deviation D1 twin of
//     the db_norm header note).
//   * The quantized feature (64 x 258 uint8) is written through
//     feat_wr_* (frame-major addr = frame_out * N_MELS + mel,
//     0..16511) into the mel_engine ping-pong page buffer (design.md
//     Sec. 3.7); the page select belongs to mel_engine (T-M1-05).
//   * sum_db / sum_db_sq inputs must be held stable while start fires
//     (db_norm holds them from stats_valid until its next start).
// -----------------------------------------------------------------------------

module standardize #(
    parameter integer N_MELS            = 64,       // Mel channels
    parameter integer OUT_FRAME_COUNT   = 258,      // kept frames
    parameter integer MEL_ELEMENT_COUNT = 16512,    // 64*258 statistics N
    parameter integer DB_ADDR_OFFSET    = 64,       // HEAD_DROP*N_MELS
    // QuantStub input contract, layer_contract.json
    // quant_stub_input_contract (T-GP-03, Wu's contract):
    //   inv_s_in = 267723430 (Q8.24), zp_in = 49.
    parameter [31:0] INV_S_IN           = 32'd267723430,
    parameter [7:0] ZP_IN               = 8'd49
) (
    input  wire               clk,          // core_clk 125 MHz
    input  wire               rst_n,        // core-domain reset, active low
    // control (start may be wired to db_norm.stats_valid)
    input  wire               start,        // one-cycle pulse, sums stable
    output wire               busy,         // 1 = standardize in progress
    // statistics inputs from db_norm
    input  wire signed [47:0] sum_db,       // s48, sum of kept dB values
    input  wire [47:0]        sum_db_sq,    // s48, sum of dB values squared
    // dB-spectrum read port (external RAM, 1-cycle synchronous read)
    output wire               db_rd_en,
    output wire [14:0]        db_rd_addr,   // frame-major, 64..16575
    input  wire signed [15:0] db_rd_data,   // int16 Q8.8 dB domain
    // quantized feature write port (uint8 CNN input, quint8 domain)
    output wire               feat_valid,   // per-element write strobe
    output wire               feat_wr_en,
    output wire [14:0]        feat_wr_addr, // frame-major, 0..16511
    output wire [7:0]         feat_wr_data, // saturated uint8 feature byte
    output reg                feat_done     // pulse: whole window finished
);

    // ------------------------------------------------------------------
    // Derived constants (sized locals; 15-bit addresses fit 64*259).
    // ------------------------------------------------------------------
    localparam [14:0] OUT_ELEM_LAST     = MEL_ELEMENT_COUNT - 1; // 16511
    localparam [14:0] DB_ADDR_OFFSET_C  = DB_ADDR_OFFSET;        // 64
    localparam [47:0] DIV_N_C           = MEL_ELEMENT_COUNT;     // 16512
    localparam signed [31:0] INV_S_IN_S = INV_S_IN;              // Q8.24
    localparam signed [26:0] ZP_IN_S    = ZP_IN;                 // 49

    // ------------------------------------------------------------------
    // Main FSM. Statistics phase (shared divider + sqrt), then a
    // Six-beat scan, with stable scan_cnt until the final feature write.
    // ------------------------------------------------------------------
    localparam [3:0] S_IDLE     = 4'd0;
    localparam [3:0] S_DIV_MU   = 4'd1;
    localparam [3:0] S_MUL_MU   = 4'd2;
    localparam [3:0] S_DIV_VAR  = 4'd3;
    localparam [3:0] S_SUB_VAR  = 4'd4;
    localparam [3:0] S_SQRT     = 4'd5;
    localparam [3:0] S_SEL_INV  = 4'd6;
    localparam [3:0] S_DIV_INV  = 4'd7;
    localparam [3:0] S_SCAN_RD  = 4'd8;
    localparam [3:0] S_SCAN_Z   = 4'd9;
    localparam [3:0] S_SCAN_Q   = 4'd10;
    localparam [3:0] S_SCAN_D   = 4'd11;
    localparam [3:0] S_SCAN_M   = 4'd12;
    localparam [3:0] S_SCAN_QM  = 4'd13;
    localparam [3:0] S_SCAN_QW  = 4'd14;   // quantized feature write beat

    reg [3:0]         state;

    // statistics results
    reg signed [15:0] mu_q88;        // Q8.8 mean
    reg signed [31:0] mu_sq_s32;    // Q8.16 mean squared
    reg [47:0]        mean_sq_u48;  // Q8.16 mean of dB^2
    reg [31:0]        var_q16_u32;  // Q8.16 variance, floored at 0
    reg [23:0]        sigma_u24;    // Q8.8 floor sqrt of var
    reg [20:0]        inv_sigma_u21;// 2^20 / sigma_eff multiplier
    reg signed [15:0] z_reg;        // Q4.12 standardized value
    reg signed [16:0] d_reg;
    reg signed [38:0] z_prod_reg;
    reg signed [47:0] qprod_reg;
    reg [7:0]         feat_byte_reg;  // registered quantized feature byte

    // scan position (feature-element index 0..16511)
    reg [14:0]        scan_cnt;

    // ------------------------------------------------------------------
    // Shared 48-cycle restoring divider datapath (unsigned operands;
    // signed handling done by the callers via abs + sign flip).
    // ------------------------------------------------------------------
    reg [47:0] div_n;               // dividend magnitude, MSB-first feed
    reg [47:0] div_d;               // divisor
    reg [48:0] div_r;               // partial remainder (49b container)
    reg [47:0] div_q;               // quotient, MSB-first shift-in
    reg [5:0]  div_cnt;             // step counter 48..0
    reg        div_neg;             // quotient sign (mu division only)

    wire        div_nbit = div_n[47];
    wire [48:0] div_r_shift = {div_r[47:0], div_nbit};
    wire        div_ge = (div_r_shift >= {1'b0, div_d});
    wire [48:0] div_r_next = div_ge ? (div_r_shift - {1'b0, div_d})
                                    : div_r_shift;
    wire [47:0] div_q_next = {div_q[46:0], div_ge};

    // ------------------------------------------------------------------
    // 24-cycle restoring square root datapath (2 bits/cycle, exact
    // floor). Invariant: r < 2q + 1; trial subtrahend (q << 2) | 1.
    // ------------------------------------------------------------------
    reg [47:0] sqrt_x;              // radicand, 2 bits consumed/cycle
    reg [26:0] sqrt_r;              // partial remainder (27b container)
    reg [23:0] sqrt_rt;             // root, MSB-first build
    reg [5:0]  sqrt_cnt;            // step counter 24..0

    wire [1:0]  sqrt_pair = sqrt_x[47:46];
    wire [26:0] sqrt_r_shift = {sqrt_r[24:0], sqrt_pair};  // 4r + pair
    wire [25:0] sqrt_c_sub = {sqrt_rt[23:0], 2'b01};       // (q<<2)|1
    wire        sqrt_ge = (sqrt_r_shift >= {1'b0, sqrt_c_sub});
    wire [26:0] sqrt_r_next = sqrt_ge ? (sqrt_r_shift - {1'b0, sqrt_c_sub})
                                      : sqrt_r_shift;
    wire [23:0] sqrt_rt_next = {sqrt_rt[22:0], sqrt_ge};

    // variance: var = mean_sq - mu^2, floored at 0 (golden max(var, 0)).
    // Combinational from the registered statistics (kept as a wire with
    // a distinct name; the registered var_q16_u32 above is the snapshot
    // latched when the scan phase starts).
    wire signed [31:0] var_sub_s32 = $signed(mean_sq_u48[31:0]) - mu_sq_s32;
    wire [31:0] var_q16_comb = (var_sub_s32 < 32'sd0) ? 32'd0 : var_sub_s32;

    // sigma_eff = max(sigma, 1) then dividend = 2^20 + (sigma_eff >> 1)
    wire [20:0] sigma_eff_w = (sigma_u24 == 24'd0) ? 21'd1 : sigma_u24[20:0];
    wire [21:0] inv_dividend_w = 22'd1048576 + {1'b0, sigma_eff_w[20:1]};

    // ------------------------------------------------------------------
    // Quantization-scan combinational datapaths.
    // Beat Z: z = sat16(rhu_shift((dB - mu) * inv_sigma, 8))  (Q4.12)
    // ------------------------------------------------------------------
    wire signed [16:0] d_s17 = db_rd_data - mu_q88;
    wire signed [21:0] inv_sigma_s22 = {1'b0, inv_sigma_u21}; // positive
    wire signed [38:0] z_prod_s39 = d_reg * inv_sigma_s22;
    wire signed [38:0] z_rhu_s39 = $signed(z_prod_reg + 39'sd128) >>> 8;
    wire signed [15:0] z_sat_s16 =
        (z_rhu_s39 > 39'sd32767)   ? 16'sd32767  :
        (z_rhu_s39 < -39'sd32768)  ? -16'sd32768 :
                                     z_rhu_s39[15:0];

    // ------------------------------------------------------------------
    // Beat Q: x_u8 = sat_u8(rhe_shift(z * inv_s_in, 36) + zp_in) with
    // bitwise round-half-to-even (golden round_half_even_shift).
    // z is Q4.12 and inv_s_in is Q8.24, so the product carries 36
    // fractional bits (12 + 24).  The historical >>24 dropped the z
    // scale and left a 2^12 gain that saturated the uint8 feature;
    // found 2026-11-04, see
    // reports/float_vs_quant_domain_diag_20261104.json.
    // ------------------------------------------------------------------
    wire signed [47:0] qprod_s48 = z_reg * INV_S_IN_S;
    wire               q_neg = qprod_reg[47];
    wire [47:0]        q_abs = q_neg ? (~qprod_reg + 48'd1) : qprod_reg;
    wire [11:0]        q_shift = q_abs[47:36];
    wire [35:0]        q_rem = q_abs[35:0];
    // tie threshold 2^35: rem > half, or rem == half and q odd -> +1
    wire               rhe_inc = (q_rem > 36'h800000000) ||
                                 ((q_rem == 36'h800000000) && q_shift[0]);
    wire [12:0]        q_rnd = {1'b0, q_shift} + (rhe_inc ? 13'd1 : 13'd0);
    wire signed [13:0] q_res_s14 = q_neg ? -$signed({1'b0, q_rnd})
                                          : $signed({1'b0, q_rnd});
    wire signed [26:0] x_q_s27 = {{13{q_res_s14[13]}}, q_res_s14} + ZP_IN_S;
    wire [7:0]         feat_byte = (x_q_s27 < 27'sd0)   ? 8'd0   :
                                   (x_q_s27 > 27'sd255) ? 8'd255 :
                                                          x_q_s27[7:0];

    // ------------------------------------------------------------------
    // External RAM / feature ports (combinational, one beat each).
    // ------------------------------------------------------------------
    assign db_rd_en     = (state == S_SCAN_RD);
    assign db_rd_addr   = scan_cnt + DB_ADDR_OFFSET_C;
    assign feat_wr_en   = (state == S_SCAN_QW);
    assign feat_valid   = feat_wr_en;
    assign feat_wr_addr = scan_cnt;
    assign feat_wr_data = feat_byte_reg;

    assign busy = (state != S_IDLE);

    // ------------------------------------------------------------------
    // Statistics + scan sequencer.
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= S_IDLE;
            mu_q88       <= 16'sd0;
            mu_sq_s32    <= 32'sd0;
            mean_sq_u48  <= 48'd0;
            var_q16_u32  <= 32'd0;
            sigma_u24    <= 24'd0;
            inv_sigma_u21<= 21'd0;
            z_reg        <= 16'sd0;
            d_reg        <= 17'sd0;
            z_prod_reg   <= 39'sd0;
            qprod_reg    <= 48'sd0;
            feat_byte_reg<= 8'd0;
            scan_cnt     <= 15'd0;
            feat_done    <= 1'b0;
            div_n        <= 48'd0;
            div_d        <= 48'd0;
            div_r        <= 49'd0;
            div_q        <= 48'd0;
            div_cnt      <= 6'd0;
            div_neg      <= 1'b0;
            sqrt_x       <= 48'd0;
            sqrt_r       <= 27'd0;
            sqrt_rt      <= 24'd0;
            sqrt_cnt     <= 6'd0;
        end else begin
            case (state)
                S_IDLE: begin
                    feat_done <= 1'b0;
                    if (start) begin
                        // divider setup: |sum_db| / 16512, sign restore
                        div_n   <= sum_db[47] ? (-sum_db) : sum_db;
                        div_d   <= DIV_N_C;
                        div_neg <= sum_db[47];
                        div_r   <= 49'd0;
                        div_q   <= 48'd0;
                        div_cnt <= 6'd48;
                        scan_cnt<= 15'd0;
                        state   <= S_DIV_MU;
                    end
                end
                // ---- mu = trunc_div(sum_db, 16512) ------------------
                S_DIV_MU: begin
                    div_r <= div_r_next;
                    div_q <= div_q_next;
                    div_n <= {div_n[46:0], 1'b0};
                    if (div_cnt == 6'd1) begin
                        mu_q88 <= div_neg ? -$signed(div_q_next[15:0])
                                          : $signed(div_q_next[15:0]);
                        // divider re-setup for the variance mean
                        // (overrides the shift updates above this cycle)
                        div_n   <= sum_db_sq;
                        div_d   <= DIV_N_C;
                        div_neg <= 1'b0;
                        div_r   <= 49'd0;
                        div_q   <= 48'd0;
                        div_cnt <= 6'd48;
                        state   <= S_MUL_MU;
                    end else begin
                        div_cnt <= div_cnt - 6'd1;
                    end
                end
                // ---- mu^2 (Q8.8 x Q8.8 -> Q8.16) --------------------
                S_MUL_MU: begin
                    mu_sq_s32 <= mu_q88 * mu_q88;
                    state     <= S_DIV_VAR;
                end
                // ---- mean_sq = sum_db_sq / 16512 (unsigned floor) ---
                S_DIV_VAR: begin
                    div_r <= div_r_next;
                    div_q <= div_q_next;
                    div_n <= {div_n[46:0], 1'b0};
                    if (div_cnt == 6'd1) begin
                        mean_sq_u48 <= div_q_next;
                        state       <= S_SUB_VAR;
                    end else begin
                        div_cnt <= div_cnt - 6'd1;
                    end
                end
                // ---- var = mean_sq - mu^2, floored at 0 -------------
                S_SUB_VAR: begin
                    // var_q16_comb is combinational (mean_sq, mu_sq set)
                    // sqrt setup: radicand right-aligned in 48b word
                    var_q16_u32 <= var_q16_comb;  // snapshot for observation
                    sqrt_x   <= {16'd0, var_q16_comb};
                    sqrt_r   <= 27'd0;
                    sqrt_rt  <= 24'd0;
                    sqrt_cnt <= 6'd24;
                    state    <= S_SQRT;
                end
                // ---- sigma = exact floor sqrt(var) ------------------
                S_SQRT: begin
                    sqrt_r  <= sqrt_r_next;
                    sqrt_rt <= sqrt_rt_next;
                    sqrt_x  <= {sqrt_x[45:0], 2'b00};
                    if (sqrt_cnt == 6'd1) begin
                        sigma_u24 <= sqrt_rt_next;
                        state     <= S_SEL_INV;
                    end else begin
                        sqrt_cnt <= sqrt_cnt - 6'd1;
                    end
                end
                // ---- sigma_eff + inv_sigma divider setup ------------
                S_SEL_INV: begin
                    // dividend = 2^20 + (sigma_eff >> 1)  (rhu form)
                    div_n   <= {26'd0, inv_dividend_w};
                    div_d   <= {27'd0, sigma_eff_w};
                    div_neg <= 1'b0;
                    div_r   <= 49'd0;
                    div_q   <= 48'd0;
                    div_cnt <= 6'd48;
                    state   <= S_DIV_INV;
                end
                // ---- inv_sigma = dividend / sigma_eff --------------
                S_DIV_INV: begin
                    div_r <= div_r_next;
                    div_q <= div_q_next;
                    div_n <= {div_n[46:0], 1'b0};
                    if (div_cnt == 6'd1) begin
                        inv_sigma_u21 <= div_q_next[20:0];
                        state         <= S_SCAN_RD; // scan_cnt already 0
                    end else begin
                        div_cnt <= div_cnt - 6'd1;
                    end
                end
                // ---- scan beat 1: issue the dB read -----------------
                S_SCAN_RD: begin
                    state <= S_SCAN_D;
                end
                S_SCAN_D: begin
                    d_reg <= d_s17; // synchronous RAM result from RD
                    state <= S_SCAN_M;
                end
                S_SCAN_M: begin
                    z_prod_reg <= z_prod_s39;
                    state <= S_SCAN_Z;
                end
                // ---- scan beat 2: z = sat16((dB-mu)*inv_sigma >> 8) -
                S_SCAN_Z: begin
                    z_reg <= z_sat_s16;
                    state <= S_SCAN_QM;
                end
                S_SCAN_QM: begin
                    qprod_reg <= qprod_s48;
                    state <= S_SCAN_Q;
                end
                // ---- scan beat 3: latch the quantized feature byte ----
                // feat_byte (round-half-even -> negate -> +zp -> clamp) is
                // a 7-level combinational chain off the DSP qprod_reg.
                // Latching it here splits that path in half so the feature
                // write data is a clean register output; value is identical.
                S_SCAN_Q: begin
                    feat_byte_reg <= feat_byte;
                    state         <= S_SCAN_QW;
                end
                // ---- scan beat 4: write the registered feature byte ----
                S_SCAN_QW: begin
                    if (scan_cnt == OUT_ELEM_LAST) begin
                        feat_done <= 1'b1;  // pulse, sampled in S_IDLE
                        state     <= S_IDLE;
                    end else begin
                        scan_cnt <= scan_cnt + 15'd1;
                        state    <= S_SCAN_RD;
                    end
                end
                default: begin
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule
