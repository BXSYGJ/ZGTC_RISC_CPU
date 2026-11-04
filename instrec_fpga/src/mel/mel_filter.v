// -----------------------------------------------------------------------------
// File    : mel_filter.v
// Module  : mel_filter
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Mel engine stage 3 (T-M1-03): power spectrum + sparse COO mel
//           filtering + log2 conversion (design.md 3.1 S4/S5, 3.3, 3.4).
//
//           Consumes the fft2048_sdf bin stream (bins 0..1024, natural
//           order, s27 real/imag parts), computes the golden power
//           spectrum, applies the COO mel filter and converts each of the
//           64 mel channel powers to the log2 domain (int16 Q8.8).
// ################################################################################
// BIT-LEVEL CONTRACT - golden_pipeline.py is the single source of truth.
// ################################################################################
// Stage A - power spectrum, golden power_spectrum():
//     p = rhu_shift(re^2 + im^2, 10)      re/im are the s27 bin parts
//   The 2^-10 rescale is applied HERE (once, in the power domain), NOT in
//   the FFT (fft2048_sdf is unscaled, see its header contract). Exact
//   integer arithmetic throughout:
//     |re|,|im| <= 2^26 - 1  (fft stage-10 bound 65534 * 2^10 < 2^27),
//     re^2 + im^2 < 2^53            (s54 exact sum),
//     rhu = floor((x + 2^9)/2^10)    (round-half-up, ties to +inf),
//     p < 2^43                        (44 valid bits, kept in a 48-bit
//                                      container p_s48, 4 guard bits).
//   Split-square on two shared 18x18 APMs (the only two multipliers in
//   this module, time-shared with the mel MAC below - never concurrent
//   because the bin stream of frame N and the mel MAC of frame N drain
//   serially):
//     x = {x_hi[17:0] = x[26:9], x_lo[8:0] = x[8:0]}   (x_hi signed,
//                                                       x_lo unsigned)
//     x^2 = x_hi^2 << 18 + 2*(x_hi*x_lo) << 9 + x_lo^2
//     re^2+im^2 = (re_hi^2+im_hi^2)<<18 + 2*(re_hi*re_lo+im_hi*im_lo)<<9
//               + (re_lo^2+im_lo^2)
//   4-cycle beat per bin (matches the fft2048_sdf output cadence of one
//   bin per 4 clk), back-to-back pipelined:
//     T0 (bin_valid): operands straight from the input ports (hi^2),
//     T1 (ph 0):      cross products, capture hi^2 results,
//     T2 (ph 1):      lo^2 products, capture cross results,
//     T3 (ph 2):      capture lo^2 results (APM operands held),
//     T4 (ph 3):      combine into p_s48 and write the power RAM.
//   T4 doubles as the next bin's T0 when bins arrive every 4 cycles.
//
// Stage B - mel filtering, golden mel_filter_coo():
//     mel[ch] = sum(power[bins[i]] * weights[i]),
//               i over the channel-major COO segment of channel ch
//   ORGANIZATION DECISION (deviation from design.md 3.4 "per-bin interval
//   query"): the COO store is CHANNEL-MAJOR (mel_tables.json mel_coo:
//   offsets[65] + contiguous (bin,weight) segments per channel). The RTL
//   scans the COO in exactly the golden order (entry 0..1959) against a
//   1024x48 power RAM that captures the bin stream as it arrives, so the
//   accumulation order per channel is IDENTICAL to the golden integer dot
//   product - bit-identical with zero re-indexing of the exported table
//   (sha256 traceability, REQ-FTR-003). The alternative bin-major layout
//   would need a re-exported table and 64 parallel 66-bit accumulators;
//   the channel-major scan needs ONE accumulator and reuses the golden
//   table verbatim.
//   Entry product: p_s48 (44 valid bits, non-negative) x weight Q1.15
//   (signed 16, table-fixed range 1..532, all positive):
//     p = {p_hi[42:26], p_mid[25:9], p_lo[8:0]}  (17/17/9 valid bits,
//     top container bits [47:43] are zero by the p < 2^43 bound)
//     prod = (p_hi*w) << 26 + (p_mid*w) << 9 + p_lo*w
//   Two APMs take the 17-bit segments (zero-extended to 18-bit signed,
//   hence always non-negative), a CLB shift-add tree (mul_lo9x16, the
//   fft2048_sdf mul_lo idiom) takes the 9-bit tail. One entry per cycle,
//   5-stage pipeline (ROM read / RAM read / APM / combine / accumulate).
//   Accumulator: 66-bit unsigned. Bound proof: p < 2^43, w <= 2^15,
//   single entry < 2^58; worst channel has 119 entries (table-fixed),
//   so the sum < 2^58 * 119 < 2^65 - covered with one guard bit. This
//   supersedes the design.md 3.1 S5 "s56 accumulator" label, which
//   belongs to the pre-rescale s37 power domain (s37+12 = s49 labels,
//   value domain < 2^65 here). Golden uses int64 with the same actual
//   value domain (< 2^60 for real data); both are exact.
//
// Stage C - log2 conversion, golden log2_fixed():
//     e     = floor(log2(p))          leading-one position (0 if p == 0)
//     mant  = p aligned so the leading one sits at bit 8 (9-bit window)
//     idx   = mant[7:0]               (== mant-256 for p>0, == 0 for p==0)
//     out   = ((e - 56) << 8) + lut[idx]      int16 Q8.8
//   The -56 bias is the design.md 3.3 s56-domain convention; it cancels
//   in every later difference (dB = log2 - max_log2). p == 0 yields
//   e = 0, idx = 0, lut[0] = 0 -> out = -14336 = LOG2_ZERO_Q88 exactly as
//   golden. e in 0..65 -> (e-56) in -56..9 -> out in [-14336, 2559],
//   inside int16. No interpolation (design.md 3.3: max LUT error
//   0.0056 in the log2 domain).
//
// ################################################################################
// TABLE FILES (verbatim extraction of scripts/outputs/mel_tables.coe,
// cross-validated against scripts/outputs/mel_tables.json)
// ################################################################################
// mel_coo.hex - 2025 lines, $readmemh into a 27-bit ROM:
//   line 0..64    : channel start offsets, 65 entries, values 0..1960
//                   (offsets[0]=0, offsets[64]=1960=total entries),
//                   13-bit effective, upper ROM bits zero;
//   line 65..2024 : COO entries in channel-major golden order,
//                   27-bit word {bin_idx[26:16] (11 bit, 1..1022),
//                               weight[15:0] (signed Q1.15, 1..532)}.
//   RTL decoding: entry ROM address = 65 + entry_index; offset ROM
//   address = channel (0..64). File sha256 (tracked for REQ-FTR-003):
//     1ca294afbcfb8ab54f11bc810483f379ba607adc28efcc4a7168b6f150b2dd61
//
// log2_lut.hex - 256 lines, 8-bit unsigned Q0.8:
//   entry i = round(log2(1 + i/256) * 256), mantissa domain [1,2).
//   File sha256: d4e13c08aed1f6c660eb17d82b30330e397b76d8ecc340812ba2b57a181192bc
//
// ################################################################################
// POWER RAM ADDRESSING - 1024 deep, write address = bin_idx[9:0].
// ################################################################################
// The table-fixed COO references bins 1..1022 only (mel_tables.json
// stats: min bin 1, max bin 1022, sha256-locked). Bins 0, 1023 and 1024
// are still computed and written (bin 1024 aliases to address 0 where it
// overwrites the equally-unreferenced bin 0 slot), but no entry ever
// reads them back, so the truncation to 10 address bits is safe.
//
// ################################################################################
// DOWNSTREAM CONTRACT (T-M1-04 alignment point)
// ################################################################################
// Output stream per frame: 64 mel_valid pulses carrying mel_ch 0..63 in
// order and mel_q88 (signed int16 Q8.8, golden log2_fixed output), then
// a frame_mel_done pulse. db_norm (T-M1-04) latches this stream into the
// full-spectrum buffer (64 x 258 x 16 bit on-chip, 15 DRM, design.md
// 3.5/3.7 - time-multiplexed with the feature double pages) and runs the
// two-pass dB conversion (global max -> dB -> top_db clamp). mel_filter
// itself stays a pure streaming stage: no full-spectrum storage here
// (design.md 3.5 places the spectrum buffer in the second-pass stage).
//
// ################################################################################
// RESOURCE ESTIMATE (see delivery report for the full table)
// ################################################################################
//   pwr_ram   1024 x 48  = 49 Kb -> 3 DRM (dual-port: bin-stream write,
//                                           MAC read)
//   coo_rom   2025 x 27  = 55 Kb -> 3 DRM (18+9 split at 2048 depth)
//   log2_lut   256 x 8   =  2 Kb -> LUTRAM (or 1 small DRM)
//   APM       2 x 18x18 (shared: power-split square + mel MAC)
//   CLB       1 x 9x16 shift-add (mel lo product)
//   FF        ~350 (66-bit acc, 48-bit RAM read, pipeline regs)
//   Throughput: ~2300 cycles/frame (1960 MAC + 64 x ~5 flush/log2),
//   258 frames = 593k cycles = 4.7 ms at 125 MHz, inside the design.md
//   3.8 first-pass budget.
//
// Reset: synchronous-release core-domain rst_n (design.md 1.3).
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module mel_filter #(
    // ROM hex file paths (relative to the simulator/synthesis working
    // directory; the build scripts arrange the search path).
    parameter COO_HEX_FILE = "mel_coo.hex",
    parameter LUT_HEX_FILE = "log2_lut.hex",
    // COO ROM depth in words: 65 offset lines + N entries.  The frozen
    // 44.1 kHz filterbank carries 1960 entries (2025 words); the 48 kHz
    // filterbank (fmax 24000, mel_coo_48k.hex) carries 1962 entries
    // (2027 words).  Sizing follows the table that COO_HEX_FILE loads.
    parameter integer COO_ROM_WORDS = 2025
) (
    // core_clk domain (125 MHz).
    input  wire        clk,
    input  wire        rst_n,

    // Upstream: fft2048_sdf bin stream (one bin per >= 4 clk cycles,
    // bins 0..1024 natural order, see the fft2048_sdf header contract).
    input  wire        bin_valid,      // one pulse per exported bin
    input  wire [10:0] bin_idx,        // bin index 0..1024
    input  wire [26:0] bin_re_s27,     // real part, s27 golden domain
    input  wire [26:0] bin_im_s27,     // imag part, s27 golden domain
    input  wire        frame_fft_done, // pulse: frame fully exported

    // Downstream: db_norm (T-M1-04 alignment point, see header).
    output reg         mel_valid,      // one pulse per mel channel
    output reg  [5:0]  mel_ch,         // mel channel 0..63
    output reg signed [15:0] mel_q88,  // log2 power, int16 Q8.8
    output reg         frame_mel_done  // pulse: frame fully exported
);

    // -----------------------------------------------------------------
    // Table storage.
    // -----------------------------------------------------------------
    // COO ROM: line 0..64 = offsets, line 65.. = entries (total depth
    // COO_ROM_WORDS, see the parameter comment above).
    localparam [10:0] COO_E_OFF = 11'd65;   // entry region base address
    localparam integer COO_ROM_LAST = COO_ROM_WORDS - 1;

    reg [26:0] coo_rom [0:COO_ROM_LAST];
    reg  [7:0] log2_lut [0:255];

    initial begin
        $readmemh(COO_HEX_FILE, coo_rom);
        $readmemh(LUT_HEX_FILE, log2_lut);
    end

    // Power spectrum RAM: 1024 x 48, dual-ported (write port fed by the
    // bin-stream power pipeline, read port fed by the mel MAC).
    reg [47:0] pwr_ram [0:1023];

    // -----------------------------------------------------------------
    // Frame state machine.
    // -----------------------------------------------------------------
    // ST_IDLE  : wait for the first bin_valid of a frame.
    // ST_PWR   : absorb the 1025-bin stream, run the power pipeline.
    // ST_ROFF  : read offsets[ch] / offsets[ch+1] from the COO ROM
    //            (2 cycles: one synchronous ROM read each).
    // ST_MAC   : stream the channel's COO segment through the 5-stage
    //            MAC pipeline, one entry per cycle.
    // ST_FLUSH : drain the MAC pipeline (5 cycles), hand the channel
    //            accumulator to the log2 pipeline, advance the channel.
    // ST_L2D   : wait for the last channel's log2 pipeline to drain.
    // -----------------------------------------------------------------
    localparam [2:0] ST_IDLE  = 3'd0;
    localparam [2:0] ST_PWR   = 3'd1;
    localparam [2:0] ST_ROFF  = 3'd2;
    localparam [2:0] ST_MAC   = 3'd3;
    localparam [2:0] ST_FLUSH = 3'd4;
    localparam [2:0] ST_L2D   = 3'd5;

    reg [2:0]  state;
    reg [10:0] bin_cnt;    // absorbed bins this frame (0..1025)
    reg [5:0]  ch;         // mel channel under accumulation (0..63)
    reg [11:0] e_idx;      // global COO entry index (0..1960)
    reg [11:0] off_lo;     // offsets[ch]   (segment start)
    reg [11:0] off_hi;     // offsets[ch+1] (segment end)
    reg [1:0]  roff_ph;    // ST_ROFF sub-phase
    reg [2:0]  fl_cnt;     // ST_FLUSH drain counter
    reg        done_seen;  // frame_fft_done latched, awaiting drain

    wire pwr_active  = (state == ST_PWR);
    wire mac_active  = (state == ST_MAC);
    wire flush_active = (state == ST_FLUSH);

    // -----------------------------------------------------------------
    // Stage A: power spectrum pipeline (4-cycle beat per bin).
    // -----------------------------------------------------------------
    reg [26:0] re_r, im_r;   // latched bin parts
    reg [10:0] bin_r;        // latched bin index
    reg [1:0]  pw_ph;        // beat phase 0..3 within one bin
    reg        pw_run;       // a bin is in the 5-cycle window

    // Shared APM operands (both multipliers in this module).
    reg signed [17:0] apm_a, apm_b, apm_c, apm_d;

    // Captured partial products (36-bit signed APM results).
    reg signed [35:0] sq_hi_re_r, sq_hi_im_r;   // hi^2  (ph0 result)
    reg signed [35:0] cross_re_r, cross_im_r;   // hi*lo (ph1 result)
    reg signed [35:0] sq_lo_re_r, sq_lo_im_r;   // lo^2  (ph2 result)

    // Exact sum re^2 + im^2 (< 2^53, non-negative) and the rescaled
    // power p = rhu_shift(sum, 10) < 2^43 in the 48-bit container.
    // Width proofs: |re_hi|,|im_hi| <= 2^17-1, re_lo,im_lo <= 2^9-1 ->
    //   sq_hi_sum <= 2*(2^17-1)^2 < 2^35  (36-bit signed container),
    //   cross_sum in +/- 2*(2^17-1)*(2^9-1), |.| < 2^27 exactly
    //     (28-bit signed container, signed because hi may be negative),
    //   sq_lo_sum <= 2*(2^9-1)^2 = 522242          (20-bit unsigned bound,
    //      carried in an s20 container: the old "s19" note was wrong, an
    //      19-bit signed word stops at 262143 - see the T35 note below).
    // T35: the lo^2 pair sums up to 522242, which needs 20 UNSIGNED bits.
    // The old s19 container tops out at 2^18-1 = 262143, so every bin whose
    // low parts were large wrapped negative: the power came out 2^19 too
    // small (512 in the >>10 domain) or, with hi == 0 and cross == 0, went
    // negative and saturated the 44-bit window to 2^44-1.
    wire signed [35:0] sq_hi_sum = sq_hi_re_r + sq_hi_im_r;
    wire signed [27:0] cross_sum = cross_re_r + cross_im_r;
    wire signed [19:0] sq_lo_sum = sq_lo_re_r + sq_lo_im_r;
    // T35: the three terms are summed directly. Verilog sizes the shift
    // left operand from the ASSIGNMENT CONTEXT (the 54-bit sum container
    // below), not from the operand's own width, so `sq_hi_sum <<< 18`
    // already shifts inside 54 bits - no sign-extension glue is needed.
    // Measured: extending each term to s54 first and summing the bare
    // forms give bit-identical power spectra on all 12288 probed bins
    // (12 frames x 1024) and a byte-exact feature output. T34's
    // "self-determined width truncation" note was wrong.
    wire signed [53:0] pwr_sum_s =
        (sq_hi_sum <<< 18) + (cross_sum <<< 10) + sq_lo_sum;
    wire signed [53:0] pwr_rnd = pwr_sum_s + 54'sd512;  // + 2^9 (rhu)
    wire [47:0] p_s48 = {4'b0, pwr_rnd[53:10]};         // non-negative

    // APM operand steering: see the always @* block following the Stage B
    // declarations (it references the MAC pipeline registers declared
    // there). Power modes occupy ST_PWR, the mel MAC occupies
    // ST_MAC/ST_FLUSH (mutually exclusive by frame protocol):
    // T0 (bin_valid): hi^2 straight from the input ports;
    // T1 (ph 0): cross products from the latched parts;
    // T2..T4 (ph 1..3): lo^2, operands held (result captured at ph 2).

    // The two shared multiplier sites (synthesis maps these onto the
    // two APMs; every product in this module funnels through them).
    reg signed [35:0] apm_ya_r, apm_yc_r;
    always @(posedge clk) begin
        apm_ya_r <= apm_a * apm_b;
        apm_yc_r <= apm_c * apm_d;
    end

    // Power pipeline sequencing + power RAM write.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            re_r    <= 27'd0;
            im_r    <= 27'd0;
            bin_r   <= 11'd0;
            pw_ph   <= 2'd0;
            pw_run  <= 1'b0;
        end else begin
            if (pwr_active && bin_valid) begin
                // T0: latch the bin, start the beat.
                re_r   <= bin_re_s27;
                im_r   <= bin_im_s27;
                bin_r  <= bin_idx;
                pw_ph  <= 2'd0;
                pw_run <= 1'b1;
            end else if (pw_run) begin
                if (pw_ph == 2'd3) begin
                    // T4: window complete (RAM write below); a new bin
                    // arriving this same cycle restarts at ph 0.
                    pw_run <= bin_valid ? 1'b1 : 1'b0;
                    pw_ph  <= 2'd0;
                end else begin
                    pw_ph <= pw_ph + 2'd1;
                end
            end
        end
    end

    // Partial-product capture and the RAM write (ph-indexed).
    always @(posedge clk) begin
        if (pwr_active || pw_run) begin
            if (pwr_active && bin_valid) begin
                // Nothing to capture at T0 (APM computes hi^2).
            end else if (pw_run && pw_ph == 2'd0) begin
                sq_hi_re_r <= apm_ya_r;   // T1: capture hi^2
                sq_hi_im_r <= apm_yc_r;
            end else if (pw_run && pw_ph == 2'd1) begin
                cross_re_r <= apm_ya_r;   // T2: capture hi*lo
                cross_im_r <= apm_yc_r;
            end else if (pw_run && pw_ph == 2'd2) begin
                sq_lo_re_r <= apm_ya_r;   // T3: capture lo^2
                sq_lo_im_r <= apm_yc_r;
            end
        end
        if (pw_run && pw_ph == 2'd3) begin
            // T4: write the rescaled power (write port of pwr_ram).
            pwr_ram[bin_r[9:0]] <= p_s48;
        end
    end

    // -----------------------------------------------------------------
    // Stage B: mel COO MAC pipeline (5 stages, one entry per cycle).
    // -----------------------------------------------------------------
    // F0: issue the COO ROM read (address 65 + e_idx).
    // F1: entry word available; lock the weight and the RAM read address.
    // F2: power RAM data valid (registered read of bin(e_idx)); lock q_p/q_w.
    // F3: q_p/q_w aligned; steer the two APMs + CLB lo product.
    // F4: APM / lo results available; combine into prod.
    // F5: accumulate prod into the channel accumulator.
    //
    // T35: this used to be a 4-deep chain (q_p latched on the F1 edge). The
    // power RAM read is registered too, so on the F1 cycle pwr_q still held
    // power[bin(previous entry)] - every MAC entry was multiplied by its
    // PREDECESSOR's bin power. Measured against golden: 16249/16576 channel
    // sums were wrong, and re-accumulating with bin(i-1) reproduced 96.9%
    // of the RTL values bit-exactly (515/16576 residual). The extra stage
    // below aligns q_p/q_w on the cycle the RAM data actually lands.
    // -----------------------------------------------------------------
    reg [26:0] q_ent;      // F1: entry word {bin[26:16], w[15:0]}
    reg signed [15:0] q_w; // F2: weight of the current entry
    reg signed [15:0] q_w_d; // F3: weight aligned with q_p
    reg [47:0] q_p;        // F3: power value of the current entry
    reg        f1_v, f2_v, f3_v, f4_v, f5_v;   // stage-valid chain
    reg [65:0] acc;        // channel accumulator (unsigned, < 2^65)
    reg [59:0] prod_r;     // F4: combined entry product

    // ROM read address: offsets during ST_ROFF, entries during ST_MAC.
    // Single read port for the whole ROM (one address expression).
    // T35: the offset index must be 7 bits. `ch + 6'd1` is a 6-bit sum, so
    // for the last channel (ch == 63) it wrapped to 0 and offsets[0] (= 0)
    // was read as the segment end: channel 63 issued no MAC entry at all and
    // its log2 came out as log2(0) = -14336 for every frame. The dB stage
    // clamped both the golden and the broken value to the -80 dB floor, so
    // the feature bytes hid the defect.
    wire [6:0]  rom_ch = {1'b0, ch} + ((roff_ph == 2'd0) ? 7'd0 : 7'd1);
    wire [10:0] rom_ra = (state == ST_ROFF)
                       ? {4'b0, rom_ch}
                       : (COO_E_OFF + e_idx[10:0]);
    wire [26:0] rom_q = coo_rom[rom_ra];

    // Power RAM read port (registered, MAC side). The read address is the
    // bin of the entry sitting in q_ent during F1, so pwr_q carries that
    // entry's power on the F2 cycle (T35 pipeline note above).
    wire [9:0] ram_ra = q_ent[25:16];
    reg [47:0] pwr_q;
    always @(posedge clk) begin
        pwr_q <= pwr_ram[ram_ra];
    end

    // Weight sign-extended to the 18-bit APM operand width (F3 alignment).
    wire signed [17:0] w_sext18 = {{2{q_w_d[15]}}, q_w_d};

    // MAC F3 steering flag for the shared APM operand mux.
    wire mac_pipe_f3 = (mac_active || flush_active) && f3_v;

    // Shared APM operand steering (the only always @* driver of the
    // four operand registers; block moved here because it reads the
    // Stage B pipeline registers declared above).
    always @* begin
        apm_a = 18'sd0;
        apm_b = 18'sd0;
        apm_c = 18'sd0;
        apm_d = 18'sd0;
        if (pwr_active && bin_valid) begin
            // T0: {re_hi, re_hi} and {im_hi, im_hi} (signed 18-bit),
            // operands straight from the fft2048_sdf output ports.
            apm_a = bin_re_s27[26:9];
            apm_b = bin_re_s27[26:9];
            apm_c = bin_im_s27[26:9];
            apm_d = bin_im_s27[26:9];
        end else if (pwr_active && pw_run && pw_ph == 2'd0) begin
            // T1: hi * lo (lo zero-extended to a non-negative signed 18).
            apm_a = re_r[26:9];
            apm_b = {9'b0, re_r[8:0]};
            apm_c = im_r[26:9];
            apm_d = {9'b0, im_r[8:0]};
        end else if (pwr_active && pw_run && pw_ph == 2'd1) begin
            // T2..T4: lo^2, operands held for the rest of the window.
            apm_a = {9'b0, re_r[8:0]};
            apm_b = {9'b0, re_r[8:0]};
            apm_c = {9'b0, im_r[8:0]};
            apm_d = {9'b0, im_r[8:0]};
        end else if (mac_pipe_f3) begin
            // MAC F3: p segments x weight. The 17-bit segments are
            // zero-extended into non-negative signed 18-bit operands.
            apm_a = {1'b0, q_p[42:26]};
            apm_b = w_sext18;
            apm_c = {1'b0, q_p[25:9]};
            apm_d = w_sext18;
        end
    end

    // CLB shift-add for the 9-bit low segment: p_lo x w (signed 16 x
    // unsigned 9 -> signed 25), the fft2048_sdf mul_lo idiom. Evaluated
    // during F3 (q_w_d / q_p stable from the F2 edge) and registered at
    // the F3 edge, because q_w_d / q_p are overwritten by the next entry
    // one cycle later (back-to-back streaming, one entry per cycle).
    function signed [24:0] mul_lo9x16;
        input signed [15:0] a;
        input [8:0] b;
        integer i;
        reg signed [24:0] a_acc;
        begin
            a_acc = 25'sd0;
            for (i = 0; i < 9; i = i + 1)
                if (b[i])
                    a_acc = a_acc + ({{9{a[15]}}, a} <<< i);
            mul_lo9x16 = a_acc;
        end
    endfunction

    wire signed [24:0] lo_prod = mul_lo9x16(q_w_d, q_p[8:0]);
    reg  signed [24:0] lo_r;    // F3-registered lo product (non-negative)

    // F4 combine: prod = (p_hi*w)<<26 + (p_mid*w)<<9 + p_lo*w.
    // p_hi/p_mid products are non-negative (p >= 0, w > 0), the APM
    // 36-bit signed containers hold values < 2^32, so the unsigned
    // slices below are exact; lo_r likewise non-negative.
    wire [31:0] ya_u = apm_ya_r[31:0];
    wire [31:0] yc_u = apm_yc_r[31:0];
    wire [59:0] prod_comb = {ya_u, 26'b0}
                          + {27'b0, yc_u, 9'b0}
                          + {35'b0, lo_r};
    // F6 (T26): duplicate declaration of prod_r removed (identical to the
    // declaration at the top of Stage B; no netlist change).

    // -----------------------------------------------------------------
    // Stage B sequencing: MAC pipeline registers + channel accumulator.
    // -----------------------------------------------------------------
    // Pipeline map (one entry per cycle, back-to-back):
    //   F0 (issue): rom_ra = 65 + e_idx, edge latches q_ent, e_idx++.
    //   F1:         q_ent valid, edge latches q_w.
    //   F2:         pwr_q carries power(bin), edge latches q_p and q_w_d.
    //   F3:         APM operands steered (mux above), edge latches the
    //               APM products and lo_r.
    //   F4:         prod_comb combine, edge latches prod_r.
    //   F5:         acc <= acc + prod_r.
    // e_idx stops at off_hi; the valid chain drains during ST_FLUSH, which
    // spans fl_cnt 0..4: the last entry occupies F2..F5 on fl_cnt 0..3
    // (it entered F1 on the ST_MAC -> ST_FLUSH edge), so fl_cnt == 4 is
    // the clear cycle and carries no f5_v - the two never collide.
    // -----------------------------------------------------------------
    wire f0_issue = mac_active && (e_idx < off_hi);
    wire flush_clear = flush_active && (fl_cnt == 3'd4);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            q_ent <= 27'd0;
            q_p   <= 48'd0;
            q_w   <= 16'sd0;
            q_w_d <= 16'sd0;
            lo_r  <= 25'sd0;
            prod_r<= 60'd0;
            f1_v  <= 1'b0;
            f2_v  <= 1'b0;
            f3_v  <= 1'b0;
            f4_v  <= 1'b0;
            f5_v  <= 1'b0;
            acc   <= 66'd0;
        end else begin
            // F0 -> F1: entry word from the single ROM read port.
            // (e_idx advances in the frame-sequencing block below, the
            // single always driver of e_idx.)
            if (f0_issue) begin
                q_ent <= rom_q;
            end
            f1_v <= f0_issue;

            // F1 -> F2: lock the entry weight (q_ent is only guaranteed on
            // this cycle; the RAM address is combinational from it).
            if (f1_v) begin
                q_w <= q_ent[15:0];
            end
            f2_v <= f1_v;

            // F2 -> F3: the registered RAM read of bin(entry) lands here,
            // so q_p and the weight copy are aligned with the APMs.
            if (f2_v) begin
                q_p   <= pwr_q;
                q_w_d <= q_w;
            end
            f3_v <= f2_v;

            // F3 -> F4: CLB lo product (APM results register themselves).
            if (f3_v) begin
                lo_r <= lo_prod;
            end
            f4_v <= f3_v;

            // F4 -> F5: combined entry product.
            if (f4_v) begin
                prod_r <= prod_comb;
            end
            f5_v <= f4_v;

            // F5: accumulate. The flush_clear cycle is one cycle after the
            // last F5 (drain proof: ST_FLUSH spans fl_cnt 0..4 = the five
            // stages F1..F5 of the last entry plus one settle cycle), so the
            // two assignments never collide.
            if (f5_v) begin
                acc <= acc + prod_r;
            end else if (flush_clear) begin
                acc <= 66'd0;    // fresh dot product, golden parity
            end
        end
    end

    // -----------------------------------------------------------------
    // Stage C: log2 pipeline (5 cycles per channel).
    // -----------------------------------------------------------------
    // Channel spacing: ST_ROFF (2) + at least 5 entries + ST_FLUSH (5)
    // = 12 cycles minimum between two l2_start pulses, well above the
    // 5-cycle pipeline depth, so a single sequential ph counter is safe
    // (no overlapping channels ever occupy the pipeline).
    // -----------------------------------------------------------------
    reg [65:0] l2_acc;    // channel power (non-negative)
    reg [5:0]  l2_ch;     // channel tag riding the pipeline
    reg [6:0]  l2_e;      // leading-one position (0 if zero)
    reg [8:0]  l2_mant;   // mantissa window [256,512) (0 if zero)
    reg [7:0]  l2_lut;    // LUT output
    reg [2:0]  l2_ph;     // 0..4
    reg        l2_run;

    wire l2_start = flush_clear;

    // Leading-one scan: lowest-to-highest priority overwrite leaves the
    // highest set bit position in lzc_e = floor(log2(p)); p == 0 keeps
    // the reset value 0 (golden log2_fixed parity).
    reg [6:0] lzc_e;
    integer bi;
    always @* begin
        lzc_e = 7'd0;
        for (bi = 0; bi < 66; bi = bi + 1)
            if (l2_acc[bi])
                lzc_e = 7'd0 + bi;
    end

    // Mantissa window: align the leading one to bit 8 (golden shift =
    // e - 8, right for e >= 8, left for e < 8). Both shift amounts stay
    // inside the 7-bit container; the unselected path may wrap but is
    // never sampled (and a shift >= 66 yields zero anyway).
    wire [65:0] l2_sh_hi = l2_acc >> (l2_e - 7'd8);
    wire [65:0] l2_sh_lo = l2_acc << (7'd8 - l2_e);
    wire [8:0]  l2_mant_mux = (l2_e >= 7'd8) ? l2_sh_hi[8:0]
                                             : l2_sh_lo[8:0];

    // Q8.8 synthesis: ((e - 56) << 8) + lut[idx]. The -56 bias is the
    // design.md 3.3 convention; it cancels in every later difference.
    wire signed [15:0] l2_exp_term = ($signed({1'b0, l2_e}) - 8'sd56) <<< 8;
    wire signed [15:0] l2_q88_comb = l2_exp_term + $signed({8'b0, l2_lut});

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            l2_acc  <= 66'd0;
            l2_ch   <= 6'd0;
            l2_e    <= 7'd0;
            l2_mant <= 9'd0;
            l2_lut  <= 8'd0;
            l2_ph   <= 3'd0;
            l2_run  <= 1'b0;
            mel_valid <= 1'b0;
            mel_ch    <= 6'd0;
            mel_q88   <= 16'sd0;
        end else begin
            mel_valid <= 1'b0;
            if (l2_start) begin
                l2_acc <= acc;
                l2_ch  <= ch;
                l2_ph  <= 3'd0;
                l2_run <= 1'b1;
            end else if (l2_run) begin
                case (l2_ph)
                    3'd0: begin
                        l2_e   <= lzc_e;        // leading-one scan
                        l2_ph  <= 3'd1;
                    end
                    3'd1: begin
                        l2_mant <= l2_mant_mux; // barrel window
                        l2_ph   <= 3'd2;
                    end
                    3'd2: begin
                        l2_lut <= log2_lut[l2_mant[7:0]];
                        l2_ph  <= 3'd3;
                    end
                    3'd3: begin
                        mel_q88   <= l2_q88_comb;
                        mel_ch    <= l2_ch;
                        mel_valid <= 1'b1;
                        l2_ph     <= 3'd4;
                    end
                    3'd4: begin
                        l2_run <= 1'b0;
                    end
                endcase
            end
        end
    end

    // -----------------------------------------------------------------
    // Frame sequencing.
    // -----------------------------------------------------------------
    // ST_PWR leaves on frame_fft_done once the power window has drained
    // (pw_run low, no incoming bin). The fft2048_sdf contract exports
    // exactly 1025 bins before frame_fft_done, so bin_cnt reaches 1025;
    // it is kept as a frame-completeness observation point only.
    // -----------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= ST_IDLE;
            bin_cnt  <= 11'd0;
            ch       <= 6'd0;
            e_idx    <= 12'd0;
            off_lo   <= 12'd0;
            off_hi   <= 12'd0;
            roff_ph  <= 2'd0;
            fl_cnt   <= 3'd0;
            done_seen<= 1'b0;
            frame_mel_done <= 1'b0;
        end else begin
            frame_mel_done <= 1'b0;
            case (state)
                ST_IDLE: begin
                    if (bin_valid) begin
                        state <= ST_PWR;
                        bin_cnt <= 11'd1;
                        done_seen <= 1'b0;
                    end
                end
                ST_PWR: begin
                    if (bin_valid) begin
                        bin_cnt <= bin_cnt + 11'd1;
                    end
                    if (frame_fft_done) begin
                        done_seen <= 1'b1;
                    end
                    if (done_seen && !pw_run && !bin_valid) begin
                        state   <= ST_ROFF;
                        ch      <= 6'd0;
                        roff_ph <= 2'd0;
                    end
                end
                ST_ROFF: begin
                    if (roff_ph == 2'd0) begin
                        off_lo  <= rom_q;      // offsets[ch]
                        roff_ph <= 2'd1;
                    end else begin
                        off_hi  <= rom_q;      // offsets[ch+1]
                        e_idx   <= off_lo;
                        roff_ph <= 2'd0;
                        state   <= ST_MAC;
                    end
                end
                ST_MAC: begin
                    // Advance the entry index while issuing (single
                    // driver of e_idx together with ST_ROFF below).
                    if (f0_issue) begin
                        e_idx <= e_idx + 12'd1;
                    end
                    if (e_idx >= off_hi) begin
                        state  <= ST_FLUSH;
                        fl_cnt <= 3'd0;
                    end
                end
                ST_FLUSH: begin
                    if (fl_cnt == 3'd4) begin
                        if (ch == 6'd63) begin
                            state <= ST_L2D;
                        end else begin
                            ch      <= ch + 6'd1;
                            state   <= ST_ROFF;
                            roff_ph <= 2'd0;
                        end
                    end else begin
                        fl_cnt <= fl_cnt + 3'd1;
                    end
                end
                ST_L2D: begin
                    if (!l2_run) begin
                        frame_mel_done <= 1'b1;
                        state <= ST_IDLE;
                    end
                end
                default: begin
                    state <= ST_IDLE;
                end
            endcase
        end
    end

endmodule