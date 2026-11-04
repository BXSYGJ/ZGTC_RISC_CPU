// -----------------------------------------------------------------------------
// File    : mel_engine.v
// Module  : mel_engine
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Mel engine top-level integration (T-M1-05, M1 close-out):
//           PCM window read-in -> STFT/Hann -> FFT2048 -> power/mel/log2
//           -> dB normalization -> standardize/quantize -> feature export
//           (design.md 2.2.6, 3.8, 5.1; tasks.md T-M1-05/T-M1-06).
//
// ################################################################################
// INTEGRATION WIRING CHECKLIST (port x instance x neighbor contract)
// ################################################################################
// Every connection below was verified against the ACTUAL port declarations
// of the five accepted submodules (no memory-based wiring):
//
//   stft_framer (530 lines, T-M1-01):
//     .win_start      <- pcm window start pulse (this module, ST_RUN entry)
//     .pcm_rd_data    <- pcm_feed_data[31:0]   (low 16 bits = left sample,
//                        framer header contract "left channel in the low
//                        16 bits of the 32-bit packed word")
//     .pcm_rd_valid   <- pcm_feed_valid        (held until ready, framer
//                        header: "mel_engine must hold pcm_rd_valid until
//                        pcm_rd_ready is sampled high")
//     .pcm_rd_ready   -> pcm_feed_ready        (ring guard back-pressure)
//     .win_s17/.win_valid/.frame_start/.frame_done/.frame_idx/.frame_last
//                     -> fft2048_sdf inputs (2048 back-to-back win beats
//                        per frame, frame_start aligned to the FIRST beat -
//                        matches the fft LOAD contract "one sample per
//                        cycle", in_s17 s17 domain)
//     .busy/.all_done -> window observation (all_done = 259th frame_done)
//
//   fft2048_sdf (642 lines, T-M1-02):
//     .frame_start    <- framer.frame_start (pulse per frame)
//     .in_valid/.in_s17 <- framer.win_valid/.win_s17 (in_ready sampled but
//                        not throttled - see FRAME THROTTLING below for why
//                        this is safe)
//     .bin_valid/.bin_idx/.bin_re_s27/.bin_im_s27/.frame_fft_done
//                     -> mel_filter inputs (4-cycle beat cadence, natural
//                        order 0..1024, s27 golden domain)
//
//   mel_filter (674 lines, T-M1-03):
//     .bin_*          <- fft2048_sdf bin stream (direct wiring)
//     .mel_valid/.mel_ch/.mel_q88 -> spectrum bank write port (first pass)
//     .frame_mel_done -> frame completion count (drives frm_out 0..258)
//
//   db_norm (249 lines, T-M1-04):
//     .start          <- this module (ST_DB entry, after the 259th
//                        frame_mel_done - the bank holds the FULL 259-frame
//                        log2 spectrum incl. the reflect-lead frame 0, the
//                        golden max domain)
//     .spec_rd_en/.spec_rd_addr -> bank read port A (1-cycle sync read)
//     .db_wr_en/.db_wr_addr/.db_wr_data -> bank write port B (never same
//                        cycle as its own read - db_norm header contract)
//     .sum_db/.sum_db_sq/.stats_valid -> standardize inputs (held stable
//                        after the pulse - db_norm header contract)
//
//   standardize (424 lines, T-M1-05a):
//     .start          <- this module (AFTER the DDR3 spectrum export
//                        finished - the export must read the dB values
//                        before standardize overwrites the bank with feat)
//     .sum_db/.sum_db_sq <- db_norm outputs (levels, still stable)
//     .db_rd_en/.db_rd_addr -> bank read port A (1-cycle sync read)
//     .feat_wr_en/.feat_wr_addr/.feat_wr_data -> bank write port B with
//                        +64 offset mapping (physical = feat_wr_addr + 64:
//                        in-place dB -> feat element overwrite, see the
//                        SPECTRUM BANK section)
//     .feat_done      -> window completion
//
// ################################################################################
// FRAME THROTTLING - pcm credit closed loop (integration-critical)
// ################################################################################
// The framer can produce one frame every ~2051 cycles (512-sample hop),
// but the fft2048_sdf frame period is ~18.5k cycles (2048 LOAD + ~8236
// RUN + 8192 DRAIN, its own header budget). Neither the framer output
// nor the fft input has a frame-level back-pressure signal, so an
// unthrottled PCM feed would make the framer emit frames 9x faster than
// the fft can accept them (frame_start pulses during ST_RUN would be
// silently dropped - LOST FRAMES).
//
// This module therefore paces the PCM feed with a sample credit that is
// REFILLED ON FFT FRAME COMPLETION:
//   * window start: credit = FILL_CREDIT = 1280 = 5 x 256 (the framer PH_FILL
//     requirement is 1025 = head ram pcm[0..1023] plus the head_extra sample
//     pcm[1024], but a read command is all-or-nothing 256 samples, so the
//     grant must be rounded UP to a whole number of commands);
//     T26 NOTE: the original value was the bare 1025.  1025 // 256 = 4
//     commands = 1024 samples, one sample short of PH_FILL, so the framer
//     could never finish frame 0 and frame_fft_done (the only refill) could
//     never arrive: the engine deadlocked at exactly 4 read commands
//     (board STATUS C=4 / D=1024, reproduced cycle-exactly by the
//     build/sim_mel testbench, see build/mel_resp_model.py);
//   * every frame_fft_done: credit += 512 (exactly one hop - the next
//     frame only needs 512 NEW samples; the window overlap comes from the
//     ring);
//   * the PCM reader only issues a 256-sample read command when
//     credit >= 256, and decrements per fed sample.
//
// Induction: after frame t-1 completes, total credit granted is
// 1280 + t*512, and frame t needs pcm[0 .. t*512+1023] = t*512+1024
// samples - granted supply exceeds demand by 256 samples at every step,
// and because 1280 and 512 are both multiples of 256 the issue granularity
// never strands a remainder (this is exactly what 1025 violated). The
// framer ring guard (pcm_rd_ready) is the second safety net; it only ever
// pauses the feed, never the frames.
// Cost: ~600 idle cycles per frame while 2 read commands land (~1.2 ms
// over 259 frames) - folded into the timing budget below.
//
// ################################################################################
// DDR3 MASTER PORT 2 SCHEDULING (m2 time-division, no second master)
// ################################################################################
// Two traffic classes share m2, strictly time-divided by the FSM state:
//   * ST_RUN : PCM reads. 516 commands of len=15 (512 B = 256 samples),
//     base = win_id[0] ? 0x84000 : 0x0 (audio_sink ping-pong windows,
//     264 KB = 0x42000 each, design.md 5.1), sequential, no idle gaps
//     needed between commands.
//   * ST_SPECEX : dB-spectrum export writes to 0x0020_0000 (design.md
//     5.1 "Mel log2 spectrum export region", 64 KB, UI/board snapshot).
//     16512 elements x 2 B = 33024 B. DECISION: 1032 single-beat len=0
//     commands instead of 65 len=15 bursts - the ctrl_axi write path
//     asserts wready_beat back-to-back during S_W (1 beat/clk), while
//     the bank read side produces one 16-element beat per 16 cycles
//     (16-bit element port); a single-beat command per 16-element group
//     hides the read latency inside the next AW handshake (~20 cycles
//     per command, 1032 x 20 = ~21k cycles = 0.17 ms). Bandwidth cost:
//     33 KB per 3 s window = 11 KB/s average (design.md 5.4 P2 row
//     tolerates 38 MB/s burst; the short-command efficiency loss is
//     covered by the 2 GB/s available budget with >10x margin).
//     Deviation vs design.md 5.3 "all long bursts len=15": recorded as
//     D-05 (PCM reads and weight streams keep len=15; only the export
//     walk uses len=0).
//
// ################################################################################
// SPECTRUM BANK - single 16576 x 16 resource, role-flow per window
// ################################################################################
// One on-chip bank (16576 x 16 bit = 264 Kb ~ 15 DRM, design.md 10
// "log2 spectrum / feature reuse, 15 blocks dual-use") carries the whole
// second-pass state machine of the data, IN PLACE, frame-major address
// = frame*64 + mel (db_norm/standardize contract):
//   ST_RUN   : mel_filter writes the log2 spectrum (all 16576 words,
//              frames 0..258 - frame 0 joins the global max, golden
//              259-frame max domain);
//   ST_DB    : db_norm reads log2, overwrites dB in place (words
//              64..16575; words 0..63 keep stale frame-0 log2 values,
//              never read again - harmless);
//   ST_SPECEX: export engine reads dB words 64..16575 to DDR3;
//   ST_STD   : standardize reads dB element e (addr 64+e) and writes
//              the quantized uint8 feature back to THE SAME word
//              (physical = feat_wr_addr + 64, {8'h00, feat_data}): the
//              element-level pipeline reads word 64+e several cycles
//              before overwriting it, read/write never collide on the
//              same word (dual-port A-read/B-write DRM).
//   ST_IDLE  : the bank IS the feature page (uint8 in the low byte of
//              every word 64..16575); the NPU export port below reads
//              it (see the FEATURE EXPORT contract).
//
// FEATURE EXPORT contract (T-M2 alignment point):
//   The design.md 2.2.6 "on-chip double page, page 0/1 alternating"
//   clause is downgraded to a SINGLE on-chip page plus the DDR3 export
//   snapshot as the de-facto second page (deviation D-06): after
//   feat_done the NPU has the full 3 s window (mel_done -> npu_start
//   pulse) before the next win_tick re-enters ST_RUN and rewrites the
//   bank; consumption bound: 16512 single-cycle reads = 132 us vs the
//   3 s window cadence (22000x margin). feat_page toggles per window
//   as the generation tag the NPU can latch with npu_start.
//
// ################################################################################
// TIMING BUDGET (125 MHz, REQ-FTR-007 / design.md 3.8 re-derived)
// ################################################################################
//   ST_RUN     : fft-bound: 259 frames x ~18.5k cycles + ~600/frame PCM
//                landing gap + 1.5k fill lead-in ~= 4.95M cycles = 39.6 ms
//                (framer 533k and mel_filter 595k cycles are fully hidden
//                inside the fft frame gaps; the design.md 3.8 line "780k
//                cycles first pass" assumed 1 sample/cycle SDF - the
//                accepted fft2048_sdf is the 4-cycle/2-APM variant, its
//                own header budget 38.1 ms is the truth, 3.9x margin)
//   ST_DB      : 66.3k cycles = 0.53 ms (db_norm header budget)
//   ST_SPECEX  : ~21k cycles = 0.17 ms (1032 len=0 commands)
//   ST_STD     : ~50k cycles = 0.40 ms (standardize 16512 elements,
//                time-shared divider)
//   TOTAL      : ~5.1M cycles ~= 40.7 ms << 150 ms Mel budget (3.7x),
//                watchdog at 200 ms (25M cycles, mel_timeout sticky).
//
// Top-level note (instrec_top, T-M2/M3): this module hangs on the m2
// master port of ddr3_ctrl_axi (currently idle in the M0 build); the
// integration task wires mel_engine.m2_* into the per-bit master buses
// (cmd_valid[2], m2_cmd, wready_beat[2], rd_ready[2], rd_data_2,
// rd_valid[2], done[2]) exactly like audio_sink does for m0.
//
// Reset: synchronous-release core-domain rst_n (design.md 1.3).
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module mel_engine #(
    // Hex file paths forwarded to the submodules (relative to the
    // synthesis/simulation working directory, see hann_rom).
    parameter         HAN_HEX_FILE = "hann_q15.hex",
    parameter         COO_HEX_FILE = "mel_coo.hex",
    parameter         LUT_HEX_FILE = "log2_lut.hex",
    // COO ROM depth forwarded to mel_filter: 65 offsets + entries of the
    // table that COO_HEX_FILE loads (2025 for the 44.1 kHz filterbank,
    // 2027 for the 48 kHz one). See mel_filter.v for the sizing note.
    parameter integer COO_ROM_WORDS = 2025,
    // QuantStub input contract forwarded to standardize (layer_contract
    // json quant_stub_input_contract): INV_S_IN is the Q8.24 inverse
    // input scale, ZP_IN the quint8 zero point. Defaults are bit
    // identical to the standardize.v module defaults, so passing them
    // through changes nothing until a new model overrides them.
    parameter [31:0]  INV_S_IN     = 32'd267723430,
    parameter [7:0]   ZP_IN        = 8'd49,
    // DDR3 byte address of the dB-spectrum export snapshot (design.md
    // 5.1 "Mel log2 spectrum export region").
    parameter [27:0]  SPEC_EX_BASE = 28'h0020_0000,
    // Watchdog limit in core_clk cycles (200 ms at 125 MHz).
    parameter integer WATCHDOG_LIMIT = 25_000_000
) (
    // core_clk domain (125 MHz).
    input  wire        clk,
    input  wire        rst_n,

    // Window beat from audio_sink: pulse when a 132096-sample left
    // window is complete in DDR3; win_id[0] selects the ping-pong
    // window (0 -> base 0x0, 1 -> base 0x84000).
    input  wire        win_tick,
    input  wire [15:0] win_id,

    // DDR3 master port 2 (per-master signals; instrec_top packs them
    // into the ddr3_ctrl_axi buses - m2_cmd level-held until done_m2).
    output reg         m2_cmd_valid,
    output reg  [36:0] m2_cmd,       // {wr, addr[27:0], len[7:0]}
    output reg  [255:0] m2_wdata,
    input  wire        m2_wready,    // wready_beat[2]: beat captured
    input  wire        m2_rd_valid,  // rd_valid[2]
    output wire        m2_rd_ready,  // rd_ready[2]
    input  wire [255:0] m2_rd_data,  // rd_data_2
    input  wire        m2_done,      // done[2]: command completion pulse

    // Feature export to the NPU (T-M2 alignment point, see header):
    // npu_start pulses with mel_done; feat_rd_addr is the logical
    // frame-major feature index 0..16511 (frame*64 + mel), mapped
    // internally to bank word addr + 64; 1-cycle synchronous read.
    output reg         npu_start,
    output reg         feat_page,    // generation tag, toggles per window
    input  wire [14:0] feat_rd_addr,
    output wire [7:0]  feat_rd_data,

    // Status / observation.
    output reg         mel_done,     // pulse: window feature complete
    output reg  [31:0] mel_cycles,   // start -> mel_done cycle count
    output reg         mel_timeout,  // sticky watchdog flag
    output reg         win_miss,     // sticky: win_tick during non-IDLE
    output wire        busy          // engine outside ST_IDLE
);

    // -----------------------------------------------------------------
    // Window geometry constants (all derived, no magic numbers).
    // -----------------------------------------------------------------
    localparam integer PCM_WIN_SAMPLES = 132096; // 3 s x 44100
    localparam integer PCM_SAMPLE_BYTES = 2;
    localparam integer PCM_CMD_SAMPLES = 256;    // 512 B len=15 command
    localparam integer PCM_CMD_COUNT   = 516;    // 132096/256 exact
    localparam [27:0]  PCM_WIN_STRIDE = 28'h0008_4000; // 264 KB ping-pong
    localparam integer FILL_CREDIT    = 1280;    // PH_FILL rounded up to 256
    localparam integer HOP_CREDIT     = 512;     // per completed frame
    localparam integer SPEC_ELEMS     = 16512;   // 64 x 258 dB/feat words
    localparam integer SPEC_PHYS_BASE = 64;      // frame-0 head drop
    localparam [14:0]  SPEC_LAST_WORD = 15'd16575;

    // -----------------------------------------------------------------
    // Main FSM.
    // -----------------------------------------------------------------
    localparam [2:0] ST_IDLE   = 3'd0;
    localparam [2:0] ST_RUN    = 3'd1;   // PCM feed + pass-1 pipeline
    localparam [2:0] ST_DB     = 3'd2;   // db_norm scans
    localparam [2:0] ST_SPECEX = 3'd3;   // DDR3 dB-spectrum export
    localparam [2:0] ST_STD    = 3'd4;   // standardize + feat writeback
    localparam [2:0] ST_DONE   = 3'd5;   // mel_done pulse

    reg [2:0]  state;
    reg [27:0] win_base;      // PCM window base address (win_id[0] mux)
    reg [8:0]  frm_out;       // completed mel frames this window 0..258
    reg        stats_seen;    // db_norm stats_valid captured


    wire run_active   = (state == ST_RUN);
    wire db_active    = (state == ST_DB);
    wire ex_active    = (state == ST_SPECEX);
    wire std_active   = (state == ST_STD);

    assign busy = (state != ST_IDLE);

    // -----------------------------------------------------------------
    // Submodule instances (wiring verified per the header checklist).
    // -----------------------------------------------------------------
    wire        fr_busy, fr_all_done, fr_frame_last;
    wire [16:0] fr_win_s17;
    wire        fr_win_valid, fr_frame_start, fr_frame_done;
    wire [8:0]  fr_frame_idx;

    reg         pcm_feed_valid;
    reg  [31:0] pcm_feed_data;
    wire        pcm_feed_ready;

    stft_framer #(
        .HAN_HEX_FILE (HAN_HEX_FILE)
    ) u_stft_framer (
        .clk           (clk),
        .rst_n         (rst_n),
        .win_start     (win_start_pulse),
        .busy          (fr_busy),
        .all_done      (fr_all_done),
        .out_ready     (fft_idle),
        .pcm_rd_data   (pcm_feed_data),
        .pcm_rd_valid  (pcm_feed_valid),
        .pcm_rd_ready  (pcm_feed_ready),
        .win_s17       (fr_win_s17),
        .win_valid     (fr_win_valid),
        .frame_start   (fr_frame_start),
        .frame_done    (fr_frame_done),
        .frame_last    (fr_frame_last),
        .frame_idx     (fr_frame_idx)
    );

    wire        fft_in_ready;
    wire        bin_valid;
    wire [10:0] bin_idx;
    wire [26:0] bin_re_s27, bin_im_s27;
    wire        frame_fft_done;

    // F5 (T26): the framer may only start a frame while the fft is idle.
    // Two virtual PH_VRIGHT frames used to be pushed while the fft was still
    // draining the previous frame; the fft drops frame_start outside ST_IDLE
    // and both frames were lost (259 exported, 257 accepted, no mel_done).
    reg fft_busy;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)              fft_busy <= 1'b0;
        else if (frame_fft_done) fft_busy <= 1'b0;
        else if (fr_frame_start) fft_busy <= 1'b1;
    end
    wire fft_idle = !fft_busy;

    // One-beat input alignment shim: the framer asserts frame_start
    // ALIGNED with its first win_valid beat (framer header contract),
    // but fft2048_sdf enters ST_LOAD (in_ready high) one cycle AFTER
    // the frame_start pulse - a direct wiring would drop the first
    // sample of every frame. The shim delays the sample stream by one
    // cycle so the first beat lands exactly when in_ready rises. The
    // 2048-beat back-to-back stream property is preserved (a uniform
    // pipeline shift). Neither accepted submodule is modified.
    reg        win_v_d;
    reg [16:0] win_s17_d;
    always @(posedge clk) begin
        win_v_d   <= fr_win_valid;
        win_s17_d <= fr_win_s17;
    end

    fft2048_sdf u_fft2048_sdf (
        .clk           (clk),
        .rst_n         (rst_n),
        .frame_start   (fr_frame_start),
        .in_ready      (fft_in_ready),
        .in_valid      (win_v_d),
        .in_s17        (win_s17_d),
        .bin_valid     (bin_valid),
        .bin_idx       (bin_idx),
        .bin_re_s27    (bin_re_s27),
        .bin_im_s27    (bin_im_s27),
        .frame_fft_done(frame_fft_done)
    );

    wire        mel_valid;
    wire [5:0]  mel_ch;
    wire signed [15:0] mel_q88;
    wire        frame_mel_done;

    mel_filter #(
        .COO_HEX_FILE  (COO_HEX_FILE),
        .LUT_HEX_FILE  (LUT_HEX_FILE),
        .COO_ROM_WORDS (COO_ROM_WORDS)
    ) u_mel_filter (
        .clk           (clk),
        .rst_n         (rst_n),
        .bin_valid     (bin_valid),
        .bin_idx       (bin_idx),
        .bin_re_s27    (bin_re_s27),
        .bin_im_s27    (bin_im_s27),
        .frame_fft_done(frame_fft_done),
        .mel_valid     (mel_valid),
        .mel_ch        (mel_ch),
        .mel_q88       (mel_q88),
        .frame_mel_done(frame_mel_done)
    );

    wire        db_busy, db_stats_valid;
    wire        db_spec_rd_en;
    wire [14:0] db_spec_rd_addr;
    wire        db_wr_en;
    wire [14:0] db_wr_addr;
    wire signed [15:0] db_wr_data;
    wire signed [47:0] sum_db;
    wire [47:0]  sum_db_sq;

    db_norm u_db_norm (
        .clk           (clk),
        .rst_n         (rst_n),
        .start         (db_start_pulse),
        .busy          (db_busy),
        .spec_rd_en    (db_spec_rd_en),
        .spec_rd_addr  (db_spec_rd_addr),
        .spec_rd_data  (bank_q),
        .db_wr_en      (db_wr_en),
        .db_wr_addr    (db_wr_addr),
        .db_wr_data    (db_wr_data),
        .sum_db        (sum_db),
        .sum_db_sq     (sum_db_sq),
        .stats_valid   (db_stats_valid)
    );

    wire        std_busy, std_feat_done;
    wire        std_db_rd_en;
    wire [14:0] std_db_rd_addr;
    wire        std_feat_wr_en;
    wire [14:0] std_feat_wr_addr;
    wire [7:0]  std_feat_wr_data;
    // Observation tap: standardize also emits a streaming feat_valid beat
    // (per-element write strobe). The engine consumes the feat bank via
    // feat_wr_en/addr/data below, so the beat itself is tapped here for
    // debug visibility only (kept off the synthesis prune list).
    wire        std_feat_valid;

    standardize #(
        .INV_S_IN      (INV_S_IN),
        .ZP_IN         (ZP_IN)
    ) u_standardize (
        .clk           (clk),
        .rst_n         (rst_n),
        .start         (std_start_pulse),
        .busy          (std_busy),
        .sum_db        (sum_db),
        .sum_db_sq     (sum_db_sq),
        .db_rd_en      (std_db_rd_en),
        .db_rd_addr    (std_db_rd_addr),
        .db_rd_data    (bank_q),
        .feat_valid    (std_feat_valid),
        .feat_wr_en    (std_feat_wr_en),
        .feat_wr_addr  (std_feat_wr_addr),
        .feat_wr_data  (std_feat_wr_data),
        .feat_done     (std_feat_done)
    );

    // -----------------------------------------------------------------
    // Spectrum bank: 16576 x 16 bit, dual-port (A read mux, B write mux),
    // frame-major address = frame*64 + mel. Role flow per window: log2
    // (ST_RUN) -> dB (ST_DB) -> exported (ST_SPECEX) -> feat uint8 in
    // the low byte (ST_STD) -> NPU export reads (ST_IDLE/DONE). See the
    // header SPECTRUM BANK section for the in-place overwrite proofs.
    // -----------------------------------------------------------------
    // Split at the power-of-two boundary to avoid a 32768 x 16 mapping.
    reg [15:0] spec_bank_lo [0:16383];
    reg [15:0] spec_bank_hi [0:191];
    reg [15:0] bank_q_lo, bank_q_hi;
    reg bank_hi_q;
    wire [15:0] bank_q = bank_hi_q ? bank_q_hi : bank_q_lo;
    reg bank_we;
    reg [14:0] bank_wa;
    reg [15:0] bank_wd;
    // Port A synchronous read data stays one cycle.
    reg [14:0] bank_ra;       // port A address (state-muxed)

    always @* begin
        bank_ra = 15'd0;
        if (db_active)
            bank_ra = db_spec_rd_addr;      // db_norm log2 read
        else if (std_active)
            bank_ra = std_db_rd_addr;       // standardize dB read
        else if (ex_active)
            bank_ra = ex_rd_addr;           // export engine dB read
        else
            bank_ra = {1'b0, feat_rd_addr} + 15'd64; // NPU feat export
    end

    always @(posedge clk) begin
        bank_q_lo <= spec_bank_lo[bank_ra[13:0]];
        bank_q_hi <= spec_bank_hi[bank_ra[7:0]];
        bank_hi_q <= bank_ra[14];
    end

    // Port B write mux: the three writers are state-exclusive (first
    // pass mel_filter / db_norm overwrite / standardize feat writeback
    // with the +64 physical offset, {8'h00, feat} low byte).
    always @* begin
        bank_we = 1'b0;
        bank_wa = 15'd0;
        bank_wd = 16'd0;
        if (run_active && mel_valid) begin
            bank_we = 1'b1;
            bank_wa = {frm_out, mel_ch};
            bank_wd = mel_q88;
        end else if (db_active && db_wr_en) begin
            bank_we = 1'b1;
            bank_wa = db_wr_addr;
            bank_wd = db_wr_data;
        end else if (std_active && std_feat_wr_en) begin
            bank_we = 1'b1;
            bank_wa = {1'b0, std_feat_wr_addr} + 15'd64;
            bank_wd = {8'h00, std_feat_wr_data};
        end
    end
    always @(posedge clk) begin
        if (bank_we && !bank_wa[14])
            spec_bank_lo[bank_wa[13:0]] <= bank_wd;
        if (bank_we && bank_wa[14])
            spec_bank_hi[bank_wa[7:0]] <= bank_wd;
    end

    assign feat_rd_data = bank_q[7:0];

    // -----------------------------------------------------------------
    // Start pulses to the submodules (single-cycle, FSM-generated).
    // -----------------------------------------------------------------
    reg win_start_pulse, db_start_pulse, std_start_pulse;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            win_start_pulse <= 1'b0;
            db_start_pulse  <= 1'b0;
            std_start_pulse <= 1'b0;
        end else begin
            win_start_pulse <= (state == ST_IDLE) && win_tick;
            // The 259th frame_mel_done (frm_out == 258) completes the
            // full log2 spectrum including the reflect-lead frame 0.
            db_start_pulse  <= run_active && frame_mel_done
                               && (frm_out == 9'd258);
            // Export finished (ex_fin) releases standardize; the sums
            // are still stable (db_norm holds them until next start).
            std_start_pulse <= ex_active && ex_fin;
        end
    end

    // -----------------------------------------------------------------
    // PCM read engine (m2 reads, ST_RUN only): credit-throttled.
    // -----------------------------------------------------------------
    // PC_IDLE : issue a len=15 read command (256 samples) when credit
    //           covers it and the 516-command budget is open;
    // PC_CMD  : hold m2_cmd_valid until m2_done (level contract);
    // PC_BEAT : pull m2_rd_ready, latch one 256-bit beat from the
    //           controller FIFO (16 beats per command);
    // PC_FEED : push the 16 samples of the beat into the framer, one
    //           per cycle, valid held until ready (framer contract).
    // -----------------------------------------------------------------
    localparam [1:0] PC_IDLE = 2'd0;
    localparam [1:0] PC_CMD  = 2'd1;
    localparam [1:0] PC_BEAT = 2'd2;
    localparam [1:0] PC_FEED = 2'd3;

    reg [1:0]     pc_state;
    reg [9:0]     pc_cmd_cnt;    // commands issued this window 0..516
    reg [4:0]     pc_beat_cnt;   // beats taken from the current command
    reg [255:0]   pc_beat_buf;
    reg [3:0]     pc_samp_ph;    // sample phase inside the beat 0..15
    reg [18:0]    pc_credit;     // framer-safe sample credit

    wire pc_issue = run_active && (pc_state == PC_IDLE)
                    && (pc_cmd_cnt < PCM_CMD_COUNT)
                    && (pc_credit >= PCM_CMD_SAMPLES);

    // Credit refill: 1025 at window start + 512 per completed fft frame
    // (see the header FRAME THROTTLING induction). The 516-command cap
    // alone bounds the total feed at exactly 132096 samples, so the
    // credit can never overfill the framer ring beyond its guard.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pc_credit <= 19'd0;
        end else if ((state == ST_IDLE) && win_tick) begin
            pc_credit <= FILL_CREDIT[18:0];
        end else begin
            pc_credit <= pc_credit + (frame_fft_done ? HOP_CREDIT[18:0] : 19'd0)
                              - (pc_issue ? PCM_CMD_SAMPLES[18:0] : 19'd0);
        end
    end

    // Beat issue address: win_base + cmd_cnt * 512 (byte address).
    wire [27:0] pc_cmd_addr = win_base + {18'd0, pc_cmd_cnt, 9'd0};

    // Sample lane: beat_buf[samp_ph * 16 +: 16], zero-extended into the
    // 32-bit packed word (left channel in the low 16 bits).
    wire [15:0] pc_lane = pc_beat_buf[{pc_samp_ph, 4'd0} +: 16];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pc_state    <= PC_IDLE;
            pc_cmd_cnt  <= 10'd0;
            pc_beat_cnt <= 5'd0;
            pc_beat_buf <= 256'd0;
            pc_samp_ph  <= 4'd0;
        end else if ((state == ST_IDLE) && win_tick) begin
            pc_state    <= PC_IDLE;
            pc_cmd_cnt  <= 10'd0;
            pc_beat_cnt <= 5'd0;
            pc_samp_ph  <= 4'd0;
        end else begin
            case (pc_state)
                PC_IDLE: begin
                    if (pc_issue) begin
                        pc_state <= PC_CMD;
                    end
                end
                PC_CMD: begin
                    if (m2_done) begin
                        pc_state    <= PC_BEAT;
                        pc_beat_cnt <= 5'd0;
                    end
                end
                PC_BEAT: begin
                    if (m2_rd_valid) begin
                        pc_beat_buf <= m2_rd_data;
                        pc_state    <= PC_FEED;
                        pc_samp_ph  <= 4'd0;
                    end
                end
                PC_FEED: begin
                    if (pcm_feed_ready) begin
                        if (pc_samp_ph == 4'd15) begin
                            if (pc_beat_cnt == 5'd15) begin
                                pc_cmd_cnt  <= pc_cmd_cnt + 10'd1;
                                pc_state    <= PC_IDLE;
                            end else begin
                                pc_beat_cnt <= pc_beat_cnt + 5'd1;
                                pc_state    <= PC_BEAT;
                            end
                        end else begin
                            pc_samp_ph <= pc_samp_ph + 4'd1;
                        end
                    end
                end
                default: begin
                    pc_state <= PC_IDLE;
                end
            endcase
        end
    end

    // Framer feed lane (level: valid held through the ready handshake).
    always @* begin
        pcm_feed_valid = (pc_state == PC_FEED);
        pcm_feed_data  = {16'd0, pc_lane};
    end

    // m2 read-side pacing: only while fetching a beat (the controller
    // FIFO back-pressures internally otherwise, design.md 5.3).
    assign m2_rd_ready = (pc_state == PC_BEAT);

    // -----------------------------------------------------------------
    // dB-spectrum export engine (m2 writes, ST_SPECEX only): 1032
    // single-beat (len=0) commands, one per 16-element group.
    // -----------------------------------------------------------------
    // EX_READ : 17 cycles of bank reads (element 15 first: the shift
    //           register fills low-to-high so element 0 lands in
    //           wdata[15:0], the DDR3 byte order) -> EX_CMD;
    // EX_CMD  : hold the len=0 write command + wdata until m2_done;
    // EX_FIN  : last group done - fires std_start_pulse.
    // -----------------------------------------------------------------
    localparam [1:0] EX_READ = 2'd0;
    localparam [1:0] EX_CMD  = 2'd1;
    localparam [1:0] EX_FIN  = 2'd2;

    reg [1:0]   ex_state;
    reg [14:0]  ex_elem;      // next group base, logical 0..16496
    reg [4:0]   ex_ph;        // read phase 0..16 (16 addr + 1 data)
    reg [255:0] ex_shift;     // 16-element beat under assembly

    wire ex_last_group = (ex_elem == 15'd16496);
    wire ex_fin = (ex_state == EX_FIN);

    // Bank read address: physical word = 64 + element; the element
    // phase walks 15 down to 0 (shift direction note above).
    wire [14:0] ex_rd_addr = {1'b0, ex_elem} + 15'd64
                             + (15 - ex_ph[3:0]);

    // Write command: {wr, SPEC_EX_BASE + elem*2, len=0}; elem is
    // 16-aligned so the byte address is 32-byte aligned (design.md
    // 5.1 / 5.3 address rule).
    wire [27:0] ex_cmd_addr = SPEC_EX_BASE + {13'd0, ex_elem, 1'b0};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ex_state <= EX_READ;
            ex_elem  <= 15'd0;
            ex_ph    <= 5'd0;
            ex_shift <= 256'd0;
        end else if (std_start_pulse) begin
            // Consumer released - park until the next window.
            ex_state <= EX_READ;
            ex_elem  <= 15'd0;
        end else if (ex_active) begin
            case (ex_state)
                EX_READ: begin
                    // Phase 0..15: present addresses; the synchronous
                    // bank_q data of phase p registers at p+1, so the
                    // first data word latches at phase 1. Phase 16
                    // latches the final word, then the beat is ready.
                    if (ex_ph < 5'd16) begin
                        if (ex_ph > 5'd0)
                            ex_shift <= {ex_shift[239:0], bank_q};
                        ex_ph <= ex_ph + 5'd1;
                    end else begin
                        ex_shift <= {ex_shift[239:0], bank_q};
                        ex_ph    <= 5'd0;
                        ex_state <= EX_CMD;
                    end
                end
                EX_CMD: begin
                    if (m2_done) begin
                        if (ex_last_group) begin
                            ex_state <= EX_FIN;
                        end else begin
                            ex_elem  <= ex_elem + 15'd16;
                            ex_state <= EX_READ;
                        end
                    end
                end
                default: begin
                    ex_state <= EX_FIN;
                end
            endcase
        end
    end

    // m2 write command valid (level-held until done, audio_sink style).
    wire ex_cmd_valid = ex_active && (ex_state == EX_CMD);

    // -----------------------------------------------------------------
    // m2 bus mux: reads (ST_RUN, PC engine) vs writes (ST_SPECEX,
    // export engine) - strictly state-exclusive.
    // -----------------------------------------------------------------
    always @* begin
        m2_cmd_valid = 1'b0;
        m2_cmd       = 37'd0;
        m2_wdata     = 256'd0;
        if (run_active && (pc_state == PC_CMD)) begin
            m2_cmd_valid = 1'b1;
            m2_cmd       = {1'b0, pc_cmd_addr, 8'd15};
        end else if (ex_cmd_valid) begin
            m2_cmd_valid = 1'b1;
            m2_cmd       = {1'b1, ex_cmd_addr, 8'd0};
            m2_wdata     = ex_shift;
        end
    end

    // -----------------------------------------------------------------
    // Main FSM + watchdog + cycle meter.
    // -----------------------------------------------------------------
    reg [24:0] wd_cnt;
    reg [31:0] mel_cycle_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= ST_IDLE;
            win_base    <= 28'd0;
            frm_out     <= 9'd0;
            stats_seen  <= 1'b0;
            win_miss    <= 1'b0;
            mel_timeout <= 1'b0;
            mel_done    <= 1'b0;
            npu_start   <= 1'b0;
            feat_page   <= 1'b0;
            mel_cycles  <= 32'd0;
            mel_cycle_cnt <= 32'd0;
            wd_cnt      <= 25'd0;
        end else begin
            mel_done  <= 1'b0;
            npu_start <= 1'b0;
            if (win_tick && (state != ST_IDLE)) begin
                win_miss <= 1'b1;    // sticky observation (75x margin)
            end
            // Watchdog: 200 ms window, sticky flag (board escalation).
            if (state != ST_IDLE) begin
                if (wd_cnt < WATCHDOG_LIMIT[24:0]) begin
                    wd_cnt <= wd_cnt + 25'd1;
                end else begin
                    mel_timeout <= 1'b1;
                end
            end else begin
                wd_cnt <= 25'd0;
            end
            // Cycle meter: window start through the mel_done beat.
            if (state != ST_IDLE) begin
                mel_cycle_cnt <= mel_cycle_cnt + 32'd1;
            end
            case (state)
                ST_IDLE: begin
                    if (win_tick) begin
                        state    <= ST_RUN;
                        win_base <= win_id[0] ? PCM_WIN_STRIDE : 28'd0;
                        frm_out  <= 9'd0;
                        stats_seen <= 1'b0;
                        mel_cycle_cnt <= 32'd0;
                    end
                end
                ST_RUN: begin
                    if (frame_mel_done) begin
                        frm_out <= frm_out + 9'd1;
                    end
                    if (db_start_pulse) begin
                        state <= ST_DB;
                    end
                end
                ST_DB: begin
                    if (db_stats_valid) begin
                        stats_seen <= 1'b1;
                        state      <= ST_SPECEX;
                    end
                end
                ST_SPECEX: begin
                    if (ex_fin) begin
                        state <= ST_STD;
                    end
                end
                ST_STD: begin
                    if (std_feat_done) begin
                        state <= ST_DONE;
                    end
                end
                ST_DONE: begin
                    mel_done      <= 1'b1;
                    npu_start     <= 1'b1;
                    feat_page     <= ~feat_page;
                    mel_cycles    <= mel_cycle_cnt;
                    state         <= ST_IDLE;
                end
                default: begin
                    state <= ST_IDLE;
                end
            endcase
        end
    end

endmodule