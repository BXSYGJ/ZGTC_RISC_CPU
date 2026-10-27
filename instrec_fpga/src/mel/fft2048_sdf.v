// -----------------------------------------------------------------------------
// File    : fft2048_sdf.v
// Module  : fft2048_sdf
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : 2048-point serial-pipeline FFT for the Mel engine (T-M1-02,
//           design.md sections 3.1 S2/S3 and 3.2).
//
//           Single-path delay-feedback (SDF) radix-2 DIT pipeline, 11
//           stages, one real input sample per 4 clk cycles, natural-order
//           bin output 0..1024 (one-half spectrum, Hermitian symmetry).
//
// ################################################################################
// BIT-LEVEL CONTRACT - golden_pipeline.py is the single source of truth.
// ################################################################################
// The RTL reproduces golden_pipeline.fft_radix2_scaled() EXACTLY (the
// golden function supersedes the design.md 3.2 "per-stage /2" scaling:
// the golden docstring records that per-stage round-half-up /2 injects
// +/-0.5 LSB eleven times, lifting true-zero bins to 1..3 in the 2^-11
// domain and breaking REQ-ACC-001 with a measured r ~ 0.92 against
// librosa; the unscaled butterfly moves the full 2^22 factor into a
// single power-domain rescale - the design.md 3.2 R-03 / BFP upgrade
// clause. Recorded as a deviation in the delivery report):
//
//   golden stage s = 1..11 (RTL stage k = s-1 = 0..10):
//     half    = 2^(s-1)             butterfly pairing distance
//     tw_step = 2048 >> s           twiddle index stride
//     j       = 0..half-1           butterfly index within the block
//     prod    = rhu_shift(W[j*tw_step] * d, 15)      per component
//     A       = a + prod;  D = a - prod              NO stage scaling
//
//   RTL mapping (identical arithmetic, streamed):
//     * input order : golden consumes x[:, bitrev]  -> the frame is
//                     stored natural-order into in_buf and READ in
//                     bit-reversed order (bitrev of the sample counter),
//                     so the SDF receives exactly the golden input order.
//     * stage k delay-line depth = 2^k = half of golden stage s = k+1
//                     (pairing distance), total 2047 words.
//     * pass/butterfly phase: sample counter bit n_cnt[k] (the phase
//                     within the 2^(k+1) block: low half pass-through,
//                     high half butterfly, j = n_cnt[k-1:0]).
//     * twiddle ROM: stage k reads word j directly from
//                     twiddle_s{k+1}.hex (pre-strided by
//                     export_twiddle_hex.py: line j = tw[j * (2048>>s)]),
//                     bit-identical to make_twiddle_q15().
//     * stage 0 (golden stage 1, single twiddle W^0 = 1):
//                     prod = rhu(32767*d, 15) == d exactly for all
//                     |d| < 2^30 (32767*d + 16384 < 32768*(d+1) iff
//                     d <= 16384; for d > 16384 the floor lands on d;
//                     sign-symmetric), so stage 0 is a pure add/subtract
//                     with no multiplier and no ROM.
//     * output: DIT with bit-reversed input yields NATURAL-order bins,
//                     so no output-side reordering buffer is needed; the
//                     natural output counter IS the bin index and only
//                     bins 0..1024 are exported (golden returns
//                     re[:, :1025]) - bins 1025..2047 are dropped on
//                     the fly (conjugate mirrors of the real input).
//
//   Width growth (unscaled butterfly, exact integer domain):
//     |prod| <= |d|  (proven: floor((32767|d|+16384)/32768) <= |d| for
//                     every integer d), so |stage output| <= |a|+|prod|
//                     <= 2*|stage input bound| and by induction
//     V_k = 65534 * 2^k < 2^(16+k)  (stage k output value bound).
//     Containers: stage k input s(16+k), stage k output / delay line
//     s(17+k); stage 10 output is s27 (a strict subset of the golden
//     int32 domain; the port is bin_re_s27 / bin_im_s27).
//
//   Downstream contract (mel_filter, T-M1-03): power spectrum applies the
//     golden power_spectrum() rescale rhu_shift(re^2 + im^2, 10) into
//     the s49 power domain - NOT re-applied here.
//
// ################################################################################
// PIPELINE ORGANIZATION - 4 clk cycles per sample, all stages in lockstep.
// ################################################################################
// Throughput budget: 2048 samples x 4 cycles + 40 cycles pipeline drain
// = 8232 cycles of RUN per frame plus 2048 LOAD cycles (single-page input
// buffer, serialized) -> ~10280 cycles/frame; 258 frames = 2.65M cycles =
// 21.2 ms at 125 MHz, 7x inside the 150 ms Mel budget (design.md 3.8).
// The relaxed 4-cycle beat exists to keep every stage on TWO shared APMs
// (phase-multiplexed) and give the CLB lo-part multipliers a shallow
// shift-add tree: 2 APM x 10 stages = 20 APM total (design.md section 10
// lists 4 for the FFT row - see the deviation log; 20 keeps the whole
// design far inside the 144 APM budget).
//
// Per stage k = 1..10, within the 4-cycle window of one sample:
//   phase 0: capture input d (from stage k-1 phase-3 register); present
//            the delay-line RAM read address (slot n_cnt mod 2^k) and
//            the twiddle ROM address (j = n_cnt[k-1:0]);
//   phase 1: ROM Q valid (one-cycle latency); shared APM pair computes
//            wr*d_hi_re and wi*d_hi_re (registered); the four CLB lo
//            products are computed and registered; RAM Q is captured;
//   phase 2: shared APM pair computes wr*d_hi_im and wi*d_hi_im
//            (registered) - the SAME two multipliers, operand-muxed;
//   phase 3: combine (hi << SH) +/- lo products, round-half-up >>15
//            (add 2^14, take bits [.. :15]), butterfly a +/- p, write
//            the delay line (pass-through stores d, butterfly stores
//            a - p), register the stage output, advance n_cnt.
//   Stage 0 (single-sample delay register, no multiplier) runs on the
//   same 4-cycle beat: phase 1 captures d and the delay register, phase
//   3 emits a +/- d and rewrites the delay register.
//
// Data hi/lo split (stage k >= 2): input width 16+k > 18 exceeds the
//   18x18 APM operand width, so d = {d_hi[17:0], d_lo[k-3:0]} and
//   tw*d = (tw*d_hi) << SH + tw*d_lo with SH = k-2. The lo product is a
//   CLB shift-add tree over at most 8 bits (function mul_lo, 9-bit
//   operand with a stage mask), registered at phase 1. Stage 1 (17-bit
//   input) needs no split (SH = 0, lo = 0). Exact integer arithmetic -
//   the split is algebraically transparent, bit-identical to a full
//   multiplier.
//
// ################################################################################
// FRAME PROTOCOL
// ################################################################################
//   frame_start (pulse)  -> ST_LOAD: in_ready high, one sample per cycle,
//                            natural order, 2048 samples into in_buf;
//   auto                  -> ST_RUN: bit-reversed read-out feeds the SDF;
//                            results stream out as bin_valid/bin_idx/
//                            bin_re_s27/bin_im_s27 (natural order 0..1024);
//   last bin              -> frame_fft_done pulse, back to ST_IDLE.
//
// Reset: synchronous-release core-domain rst_n (design.md 1.3).
//
// Resource estimate (see delivery report for the full table):
//   delay lines ~106 Kb (6-7 DRM) + in_buf 2048x18 (2 DRM) + twiddle ROMs
//   (stage 10/9 in DRM: 3, small stages LUTRAM) ~= 12 DRM total - over
//   the design.md section 10 FFT row (5 DRM); reduction options are
//   logged in the delivery report (R-11).
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module fft2048_sdf (
    // core_clk domain (125 MHz).
    input  wire        clk,
    input  wire        rst_n,

    // Frame handshake (from stft_framer, T-M1-01).
    input  wire        frame_start,    // pulse: begin loading a frame
    output wire        in_ready,       // high while loading (1 sample/cycle)
    input  wire        in_valid,       // sample strobe (ignored outside LOAD)
    input  wire [16:0] in_s17,         // windowed real sample (imag == 0)

    // Result stream, natural order bins 0..1024 (1025 bins).
    output reg         bin_valid,      // one pulse per exported bin
    output reg  [10:0] bin_idx,        // bin index 0..1024
    output reg  [26:0] bin_re_s27,     // real part, golden-parity domain
    output reg  [26:0] bin_im_s27,     // imag part, golden-parity domain
    output reg         frame_fft_done  // pulse: frame fully exported
);

    // -----------------------------------------------------------------
    // Frame state machine.
    //
    // The SDF delay lines hold residual stage data at the end of a frame
    // (already-consumed butterfly tails). Before the next frame they
    // MUST be flushed with dummy samples (valid = 0), otherwise the
    // first 2^k pop-outs of stage k would deliver stale values into the
    // next frame's datapath. ST_DRAIN therefore pushes 2048 dummy
    // samples (>= deepest delay 1024 + the 11-stage pipeline) through
    // the cascade; the valid chain shadows them so nothing reaches the
    // output counters. Frame period = 2048 LOAD + ~8236 RUN + 8192
    // DRAIN ~ 18.5k cycles -> 258 frames = 4.77M cycles = 38.1 ms at
    // 125 MHz, 3.9x inside the 150 ms Mel budget (design.md 3.8).
    //
    // Per-frame sample counting: run_cnt runs 0..2047 (live feed),
    // 2048 (feed stopped, pipeline drain) during ST_RUN, then 2048..4095
    // (dummy flush) during ST_DRAIN; in_buf is read bit-reversed with
    // run_cnt[10:0] wrapping (dummy reads are harmless, valid = 0).
    // -----------------------------------------------------------------
    localparam [1:0] ST_IDLE  = 2'd0;
    localparam [1:0] ST_LOAD  = 2'd1;
    localparam [1:0] ST_RUN   = 2'd2;
    localparam [1:0] ST_DRAIN = 2'd3;

    reg [1:0]  state;
    reg [11:0] ld_cnt;      // LOAD sample counter 0..2047
    reg [11:0] run_cnt;     // RUN/DRAIN beat sample counter (see header)
    reg [1:0]  ph2;         // 4-phase beat, shared by all stages
    reg [10:0] out_cnt;     // stage-10 valid output counter 0..2047
    reg        out_done;    // all 2048 valid outputs seen this frame

    wire load_active  = (state == ST_LOAD);
    wire run_active   = (state == ST_RUN);
    wire drain_active = (state == ST_DRAIN);
    wire beat_active  = run_active | drain_active;

    // Stage sample counters clear at the LOAD->RUN boundary (the last
    // loaded sample cycle) so every stage restarts its block phase.
    wire clr_n = load_active && in_valid && (ld_cnt == 12'd2047);

    assign in_ready = load_active;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= ST_IDLE;
            ld_cnt    <= 12'd0;
            run_cnt   <= 12'd0;
            ph2       <= 2'd0;
            out_cnt   <= 11'd0;
            out_done  <= 1'b0;
            frame_fft_done <= 1'b0;
        end else begin
            frame_fft_done <= 1'b0;
            case (state)
                ST_IDLE: begin
                    if (frame_start) begin
                        state  <= ST_LOAD;
                        ld_cnt <= 12'd0;
                    end
                end
                ST_LOAD: begin
                    if (in_valid) begin
                        if (ld_cnt == 12'd2047) begin
                            state   <= ST_RUN;
                            run_cnt <= 12'd0;
                            ph2     <= 2'd0;
                        end else begin
                            ld_cnt <= ld_cnt + 12'd1;
                        end
                    end
                end
                ST_RUN: begin
                    // 4-phase beat; the beat sample counter advances each
                    // beat and saturates at 2048 (feed stopped, pipeline
                    // draining until the valid chain finishes).
                    if (ph2 == 2'd3) begin
                        ph2 <= 2'd0;
                        if (run_cnt != 12'd2048)
                            run_cnt <= run_cnt + 12'd1;
                    end else begin
                        ph2 <= ph2 + 2'd1;
                    end
                    if (out_done) begin
                        state <= ST_DRAIN;   // valid outputs complete
                    end
                end
                ST_DRAIN: begin
                    if (ph2 == 2'd3) begin
                        ph2 <= 2'd0;
                        if (run_cnt == 12'd4095) begin
                            state <= ST_IDLE;           // frame complete
                            frame_fft_done <= 1'b1;     // notify consumer
                            run_cnt <= 12'd0;
                        end else begin
                            run_cnt <= run_cnt + 12'd1;
                        end
                    end else begin
                        ph2 <= ph2 + 2'd1;
                    end
                end
                default: state <= ST_IDLE;
            endcase
            // Output sample counting driven by the stage-10 valid beat.
            if (s_out_vld[10]) begin
                if (out_cnt == 11'd2047)
                    out_done <= 1'b1;
                else
                    out_cnt <= out_cnt + 11'd1;
            end
            if (state == ST_IDLE)
                out_cnt <= 11'd0;
        end
    end

    // -----------------------------------------------------------------
    // Input buffer: 2048 x 18 bit (s17 sample sign-extended). Written in
    // natural order during LOAD, read in bit-reversed order during RUN
    // (the golden DIT input permutation x[:, bitrev]).
    // -----------------------------------------------------------------
    reg [17:0] in_buf [0:2047];

    // 11-bit bit reversal (golden _bit_reverse_indices for n = 2^11).
    function [10:0] bitrev11;
        input [10:0] v;
        begin
            bitrev11 = {v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
                        v[8], v[9], v[10]};
        end
    endfunction

    // Stage-0 input stream: one sample per 4-cycle beat, phase 0 reads
    // the buffer at the bit-reversed slot; Q (uniform one-cycle RAM
    // latency plus output register, see stage code) is captured in the
    // stage-0 block.
    wire [10:0] in_rd_addr = bitrev11(run_cnt[10:0]);
    reg  [17:0] in_q_r;

    always @(posedge clk) begin
        if (load_active && in_valid)
            in_buf[ld_cnt[10:0]] <= {in_s17[16], in_s17};
    end

    // Synchronous read port (natural for both DRM and LUTRAM inference).
    // Reads run through RUN and DRAIN (dummy reads wrap harmlessly).
    always @(posedge clk) begin
        if (beat_active)
            in_q_r <= in_buf[in_rd_addr];
    end

    // -----------------------------------------------------------------
    // Per-stage twiddle ROMs (k = 1..10). Files generated by
    // scripts/export_twiddle_hex.py from the golden make_twiddle_q15().
    // Stage addresses are wired from inside the generate loop below.
    // -----------------------------------------------------------------
    wire [31:0] tw_q    [1:10];
    wire [9:0]  tw_addr [1:10];

    tw_rom_s #(.AW(1),  .TW_FILE("src/mel/twiddle_s2.hex"))  u_tw_s2  (.clk(clk), .addr(tw_addr[1][0:0]),  .q(tw_q[1]));
    tw_rom_s #(.AW(2),  .TW_FILE("src/mel/twiddle_s3.hex"))  u_tw_s3  (.clk(clk), .addr(tw_addr[2][1:0]),  .q(tw_q[2]));
    tw_rom_s #(.AW(3),  .TW_FILE("src/mel/twiddle_s4.hex"))  u_tw_s4  (.clk(clk), .addr(tw_addr[3][2:0]),  .q(tw_q[3]));
    tw_rom_s #(.AW(4),  .TW_FILE("src/mel/twiddle_s5.hex"))  u_tw_s5  (.clk(clk), .addr(tw_addr[4][3:0]),  .q(tw_q[4]));
    tw_rom_s #(.AW(5),  .TW_FILE("src/mel/twiddle_s6.hex"))  u_tw_s6  (.clk(clk), .addr(tw_addr[5][4:0]),  .q(tw_q[5]));
    tw_rom_s #(.AW(6),  .TW_FILE("src/mel/twiddle_s7.hex"))  u_tw_s7  (.clk(clk), .addr(tw_addr[6][5:0]),  .q(tw_q[6]));
    tw_rom_s #(.AW(7),  .TW_FILE("src/mel/twiddle_s8.hex"))  u_tw_s7x (.clk(clk), .addr(tw_addr[7][6:0]),  .q(tw_q[7]));
    tw_rom_s #(.AW(8),  .TW_FILE("src/mel/twiddle_s9.hex"))  u_tw_s9  (.clk(clk), .addr(tw_addr[8][7:0]),  .q(tw_q[8]));
    tw_rom_s #(.AW(9),  .TW_FILE("src/mel/twiddle_s10.hex")) u_tw_s10 (.clk(clk), .addr(tw_addr[9][8:0]),  .q(tw_q[9]));
    tw_rom_s #(.AW(10), .TW_FILE("src/mel/twiddle_s11.hex")) u_tw_s11 (.clk(clk), .addr(tw_addr[10][9:0]), .q(tw_q[10]));

    // -----------------------------------------------------------------
    // Stage interconnect: stage k output (s17+k wide, stored in a 27-bit
    // container, sign-extended) and its valid beat.
    // -----------------------------------------------------------------
    wire [26:0] s_out_re [0:10];
    wire [26:0] s_out_im [0:10];
    wire        s_out_vld [0:10];

    // Stage-0 input sample valid: only live RUN samples are valid; the
    // DRAIN beats push dummy (valid = 0) samples through the cascade.
    wire samp_vld = run_active && (run_cnt < 12'd2048);

    // -----------------------------------------------------------------
    // SDF stage cascade.
    // -----------------------------------------------------------------

    // =================================================================
    // Stage 0 (golden stage 1): single twiddle W^0 = 1, prod = d exactly
    // (proof in the module header), so the butterfly degenerates to a
    // pure add/subtract with a one-sample delay register. The imaginary
    // path is identically zero (real input, W real): golden stage-1
    // im = rhu(0*d + 0*d, 15) = 0.
    // =================================================================
    reg  [16:0] st0_dly;    // one-sample delay register (real path)
    reg  [16:0] st0_d_r;    // input captured at phase 1 (in_buf Q)
    reg  [16:0] s0_re_r;    // registered output (real)
    reg         s0_vld_r;

    // 17-bit sum/difference with one guard bit, truncated back to the
    // s17 container (values |a +/- d| <= 65534 fit exactly).
    wire [17:0] st0_sum = {st0_dly[16], st0_dly} + {st0_d_r[16], st0_d_r};
    wire [17:0] st0_dif = {st0_dly[16], st0_dly} - {st0_d_r[16], st0_d_r};

    always @(posedge clk) begin
        if (ph2 == 2'd1)
            st0_d_r <= in_q_r[16:0];
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st0_dly  <= 17'd0;
            s0_re_r  <= 17'd0;
            s0_vld_r <= 1'b0;
        end else if (ph2 == 2'd3) begin
            if (run_cnt[0]) begin
                // Butterfly half: pair (pop a, live d).
                s0_re_r <= st0_sum[16:0];   // upper branch A = a + d
                st0_dly <= st0_dif[16:0];   // lower branch D = a - d
            end else begin
                // Pass-through half: push d, pop the tail.
                s0_re_r <= st0_dly;
                st0_dly <= st0_d_r;
            end
            s0_vld_r <= samp_vld;
        end
    end

    assign s_out_re[0]   = {{10{s0_re_r[16]}}, s0_re_r};
    assign s_out_im[0]   = 27'd0;
    assign s_out_vld[0]  = s0_vld_r;

    // =================================================================
    // Stages k = 1..10 (golden stages s = k+1). See the module header
    // for the 4-phase beat plan and the hi/lo split rationale.
    // =================================================================
    genvar k;
    generate
    for (k = 1; k <= 10; k = k + 1) begin : g_stage

        // Widths: stage input s(16+k), stage output / delay line s(17+k).
        localparam integer IW = 16 + k;
        localparam integer OW = 17 + k;

        // -----------------------------------------------------------------
        // Sample counter (cleared at the LOAD->RUN boundary) and phase
        // decode. Within a 2^(k+1) block: n_cnt[k] = 0 -> pass-through
        // half, = 1 -> butterfly half with j = n_cnt[k-1:0].
        // -----------------------------------------------------------------
        reg [10:0] n_cnt;

        always @(posedge clk or negedge rst_n) begin
            if (!rst_n)
                n_cnt <= 11'd0;
            else if (clr_n)
                n_cnt <= 11'd0;
            else if (ph2 == 2'd3)
                n_cnt <= n_cnt + 11'd1;   // wraps mod 2048
        end

        wire fly = n_cnt[k];

        // -----------------------------------------------------------------
        // Input capture (phase 0): the previous stage's phase-3 output
        // register is combinationaly stable this cycle.
        // -----------------------------------------------------------------
        reg [IW-1:0] d_re_r;
        reg [IW-1:0] d_im_r;

        wire [IW-1:0] prev_re = s_out_re[k-1][IW-1:0];
        wire [IW-1:0] prev_im = s_out_im[k-1][IW-1:0];

        always @(posedge clk) begin
            if (ph2 == 2'd0) begin
                d_re_r <= prev_re;
                d_im_r <= prev_im;
            end
        end

        // -----------------------------------------------------------------
        // Delay line: 2^k x OW dual-port RAM (read address issued phase 0,
        // data registered one or two cycles later; written at phase 3
        // into the same slot - a classic shift register in RAM form).
        // -----------------------------------------------------------------
        reg [OW-1:0] dly_re [0:(1 << k) - 1];
        reg [OW-1:0] dly_im [0:(1 << k) - 1];

        wire [k-1:0] ram_addr = n_cnt[k-1:0];
        reg  [OW-1:0] ram_q_re;
        reg  [OW-1:0] ram_q_im;

        always @(posedge clk) begin
            ram_q_re <= dly_re[ram_addr];
            ram_q_im <= dly_im[ram_addr];
        end

        // -----------------------------------------------------------------
        // Twiddle: per-stage ROM (pre-strided), addressed directly by j.
        // Q is valid from phase 1 on (one-cycle ROM latency, uniform).
        // -----------------------------------------------------------------
        assign tw_addr[k] = {{(10-k){1'b0}}, n_cnt[k-1:0]};

        wire signed [15:0] tw_re = tw_q[k][15:0];
        wire signed [15:0] tw_im = tw_q[k][31:16];

        // -----------------------------------------------------------------
        // hi/lo split of the data operand (stage 1: none, the 17-bit input
        // goes straight into the 18x18 APMs; stage k >= 2: 18-bit hi into
        // the APM pair, (k-2)-bit lo into CLB shift-add multipliers).
        // The conditional generate keeps every part-select range legal
        // for the elaborated branch only.
        // -----------------------------------------------------------------
        // Shift applied to the hi product (constant 0 for stage 1).
        localparam integer SH = (k >= 2) ? (k - 2) : 0;
        // Mask selecting the lo bits (all-zero for stage 1; written so
        // that the shift amount is never negative in either branch).
        localparam [8:0] LO_MASK =
            ((9'd1 << ((k >= 2) ? (k - 2) : 0)) - ((k >= 2) ? 9'd1 : 9'd0));

        wire signed [17:0] d_hi_re;
        wire signed [17:0] d_hi_im;
        wire [8:0] d_lo_re;
        wire [8:0] d_lo_im;

        // PDS 2022.2 parser compatibility (T-M1-06 build fix): the
        // conditional generate below is NESTED inside the enclosing
        // generate-for loop. IEEE 1364/1800 allow nested generate
        // regions, but the PDS parser rejects a bare inner
        // generate/endgenerate pair (Verilog-4005). Dropping the inner
        // keywords keeps the identical elaboration semantics (a bare
        // if-else inside a generate-for body IS a conditional generate
        // construct) and parses everywhere; branch labels are made
        // unique as good practice.
        if (k == 1) begin : g_split_hi
            assign d_hi_re = {d_re_r[16], d_re_r};
            assign d_hi_im = {d_im_r[16], d_im_r};
            assign d_lo_re = 9'd0;
            assign d_lo_im = 9'd0;
        end else begin : g_split_lo
            assign d_hi_re = d_re_r[IW-1:k-2];
            assign d_hi_im = d_im_r[IW-1:k-2];
            assign d_lo_re = d_re_r[8:0] & LO_MASK;
            assign d_lo_im = d_im_r[8:0] & LO_MASK;
        end

        // -----------------------------------------------------------------
        // Shared APM pair (two 16x18 signed multipliers, phase-multiplexed
        // between the re and im data halves). Products are registered at
        // the end of phase 1 (wr*d_hi_re, wi*d_hi_re) and phase 2
        // (wr*d_hi_im, wi*d_hi_im).
        // -----------------------------------------------------------------
        wire signed [17:0] apm_d = (ph2 == 2'd1) ? d_hi_re : d_hi_im;

        // 16 x 18 signed products (mapped into two GTP_APM 18x18 blocks).
        wire signed [33:0] m_a = tw_re * apm_d;
        wire signed [33:0] m_b = tw_im * apm_d;

        reg signed [33:0] m_rr;   // wr * dr_hi  (phase 1, A)
        reg signed [33:0] m_ir;   // wi * dr_hi  (phase 1, B)
        reg signed [33:0] m_ri;   // wr * di_hi  (phase 2, A)
        reg signed [33:0] m_ii;   // wi * di_hi  (phase 2, B)

        always @(posedge clk) begin
            if (ph2 == 2'd1) begin
                m_rr <= m_a;
                m_ir <= m_b;
            end else if (ph2 == 2'd2) begin
                m_ri <= m_a;
                m_ii <= m_b;
            end
        end

        // -----------------------------------------------------------------
        // CLB lo products (16 x <=8-bit shift-add trees), registered at
        // the end of phase 1. Exact signed arithmetic: the twiddle
        // component sign is carried by the sign extension of the shift.
        // -----------------------------------------------------------------
        function signed [24:0] mul_lo;
            input signed [15:0] a;
            input [8:0] b;
            integer i;
            reg signed [24:0] acc;
            begin
                acc = 25'sd0;
                for (i = 0; i < 9; i = i + 1)
                    if (b[i])
                        acc = acc + ({{9{a[15]}}, a} <<< i);
                mul_lo = acc;
            end
        endfunction

        reg signed [24:0] lo_rr;   // wr * dr_lo
        reg signed [24:0] lo_ir;   // wi * dr_lo
        reg signed [24:0] lo_ri;   // wr * di_lo
        reg signed [24:0] lo_ii;   // wi * di_lo

        always @(posedge clk) begin
            if (ph2 == 2'd1) begin
                lo_rr <= mul_lo(tw_re, d_lo_re);
                lo_ir <= mul_lo(tw_im, d_lo_re);
                lo_ri <= mul_lo(tw_re, d_lo_im);
                lo_ii <= mul_lo(tw_im, d_lo_im);
            end
        end

        // -----------------------------------------------------------------
        // Phase 3 combine: golden butterfly arithmetic.
        //   pr_full = wr*dr - wi*di = (hi parts << SH) +/- (lo parts)
        //   pi_full = wr*di + wi*dr
        //   p       = rhu_shift(full, 15) = floor((full + 2^14) / 2^15)
        //            -> add 2^14 and take bits [.. 15] (two's complement
        //               truncation equals the arithmetic shift here
        //               because |p| <= |d| fits the container).
        //   A = a + p (forwarded), D = a - p (written back).
        // -----------------------------------------------------------------
        wire signed [45:0] pr_full =
              ({{12{m_rr[33]}}, m_rr} <<< SH) + {{21{lo_rr[24]}}, lo_rr}
            - ({{12{m_ii[33]}}, m_ii} <<< SH) - {{21{lo_ii[24]}}, lo_ii};
        wire signed [45:0] pi_full =
              ({{12{m_ri[33]}}, m_ri} <<< SH) + {{21{lo_ri[24]}}, lo_ri}
            + ({{12{m_ir[33]}}, m_ir} <<< SH) + {{21{lo_ir[24]}}, lo_ir};

        wire signed [45:0] pr_hu = pr_full + 46'sd16384;
        wire signed [45:0] pi_hu = pi_full + 46'sd16384;

        wire signed [IW-1:0] p_re = pr_hu[15+IW-1:15];
        wire signed [IW-1:0] p_im = pi_hu[15+IW-1:15];

        // Butterfly (container-safe: |a +/- p| <= 2*V < 2^(17+k)).
        wire signed [OW-1:0] a_r = ram_q_re;
        wire signed [OW-1:0] ai_r = ram_q_im;
        wire signed [OW-1:0] sum_re = a_r + p_re;
        wire signed [OW-1:0] dif_re = a_r - p_re;
        wire signed [OW-1:0] sum_im = ai_r + p_im;
        wire signed [OW-1:0] dif_im = ai_r - p_im;

        // -----------------------------------------------------------------
        // Output register and delay-line write (phase 3).
        // -----------------------------------------------------------------
        reg [OW-1:0] s_re_r;
        reg [OW-1:0] s_im_r;
        reg          s_vld_r;

        // Stage input valid = previous stage output valid (pipeline of
        // the valid beat, unconditionally refreshed every phase 3).
        wire prev_vld = s_out_vld[k-1];

        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                s_re_r  <= {OW{1'b0}};
                s_im_r  <= {OW{1'b0}};
                s_vld_r <= 1'b0;
            end else if (ph2 == 2'd3) begin
                if (fly) begin
                    s_re_r  <= sum_re;
                    s_im_r  <= sum_im;
                    dly_re[ram_addr] <= dif_re;
                    dly_im[ram_addr] <= dif_im;
                end else begin
                    s_re_r  <= a_r;
                    s_im_r  <= ai_r;
                    dly_re[ram_addr] <= {{(OW-IW){d_re_r[IW-1]}}, d_re_r};
                    dly_im[ram_addr] <= {{(OW-IW){d_im_r[IW-1]}}, d_im_r};
                end
                s_vld_r <= prev_vld;
            end
        end

        assign s_out_re[k]  = {{(27-OW){s_re_r[OW-1]}}, s_re_r};
        assign s_out_im[k]  = {{(27-OW){s_im_r[OW-1]}}, s_im_r};
        assign s_out_vld[k] = s_vld_r;

    end
    endgenerate

    // =================================================================
    // Output section: natural-order bins 0..1024 (one-half spectrum).
    // The DIT cascade with bit-reversed input produces natural-order
    // bins, so the stage-10 output counter IS the bin index. Bins
    // 1025..2047 are conjugate mirrors of the real input and are simply
    // not exported (golden returns re[:, :1025]).
    // =================================================================
    wire [26:0] last_re  = s_out_re[10];
    wire [26:0] last_im  = s_out_im[10];
    wire        last_vld = s_out_vld[10];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bin_valid  <= 1'b0;
            bin_idx    <= 11'd0;
            bin_re_s27 <= 27'd0;
            bin_im_s27 <= 27'd0;
        end else begin
            bin_valid <= 1'b0;
            if (last_vld && (out_cnt <= 11'd1024)) begin
                bin_valid  <= 1'b1;
                bin_idx    <= out_cnt;
                bin_re_s27 <= last_re;
                bin_im_s27 <= last_im;
            end
        end
    end

endmodule