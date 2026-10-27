// -----------------------------------------------------------------------------
// stft_framer - STFT frame supplier with librosa center=True/reflect
//               boundary semantics (tasks.md T-M1-01, design.md Sec. 3.1
//               stage S1 / Sec. 3.2 frame supply, REQ-FTR-002)
// -----------------------------------------------------------------------------
// Bit-exact reference: scripts/golden_pipeline.py frame_pcm_reflect() +
// apply_hann(). Semantics locked by line-by-line verification:
//
//   * PCM length WINDOW_SAMPLES = 132096 (3 s x 44100 hardware window).
//   * Frame count: the golden pipeline produces 259 frames
//     (1 + 132096/512) and truncates to the LAST 258 frames only AFTER
//     the dB stage (golden truncate_frames keep-tail semantics,
//     N_STFT_FRAMES = 259 "before truncation"). This module therefore
//     supplies ALL 259 frames (t = 0..258); the mel_engine consumer
//     performs the 259 -> 258 keep-tail truncation at the dB/spectrum
//     stage (T-M1-04/T-M1-05 alignment point). tasks.md's "258 frames"
//     describes the post-truncation feature tensor, not the framer
//     output (deviation D1, recorded in the task report).
//   * Reflect padding (numpy mode="reflect", edges NOT repeated):
//     padded[i]            = pcm[1024 - i]   for i < 1024    (left pad)
//     padded[1024 + i]     = pcm[i]          for i < 132096  (body)
//     padded[133120 + j]   = pcm[132094 - j] for j < 1024    (right pad)
//     NO zero padding anywhere: 259 hops of 512 plus the 2048 window
//     span exactly 134144 samples = the full reflect-padded array, so
//     frame 258 ([132096, 134144) in padded coordinates) ends exactly
//     at the right edge of the right reflect pad. The task note about
//     "tail zero-fill" is superseded by this golden behavior (pure
//     reflect, no zeros) - deviation D2, recorded in the task report.
//   * Windowing: win_s17 = round_half_up(pcm_s16 * hann_q15 >> 15)
//     = (pcm * hann + 16384) >>> 15, arithmetic shift, ties toward
//     +infinity (golden rhu_shift: floor((x + 2^14) / 2^15); the
//     rounding constant is 16384, NOT 8192). Range analysis:
//     |pcm| <= 32768 and |hann| <= 32767, so the product magnitude is
//     below 2^31 (no s32 overflow after the +16384) and the result
//     lands in [-32768, +32767], which fits the s17 container with NO
//     saturation (golden carries the value in int64 without clipping).
//
// Architecture (padded-stream ring buffer, all storage synchronous
// single-cycle read):
//   win_ring  2560 x 16 : ring buffer over the padded stream, depth =
//                         N_FFT + HOP (2048 + 512); slot = abs mod 2560.
//                         Ring-pointer style (single sliding window, no
//                         ping-pong): while frame j drains, the push
//                         engine may advance up to HOP samples ahead
//                         (frame j+1 readiness) because the push slots
//                         land exactly in the 512 slots PRECEDING the
//                         frame-j window base - disjoint from the
//                         unread window by construction. Steady state:
//                         one frame every 2048 + 3 cycles, 259 frames
//                         plus the head-fill prologue ~= 533k cycles
//                         = 4.3 ms at 125 MHz, matching the design.md
//                         Sec. 3.2 budget (528k + 259th frame overhead).
//   head_ram  1024 x 16 : pcm[0..1023]    (left-reflect source samples)
//   head_extra  1 reg   : pcm[1024]       (first left-reflect tap; numpy
//                         reflect does NOT repeat the edge sample, so
//                         the left pad consumes pcm[1024..1], needing
//                         one sample beyond the first 1024)
//   tail_ram  1024 x 16 : pcm[131071..132094] (right-reflect source;
//                         the right pad reads pcm[132094-j] for
//                         j = 0..1023, i.e. the 1024 samples ending one
//                         BEFORE the last sample - pcm[132095] itself is
//                         never mirrored)
//   hann_rom  (module) : 2048 x Q1.15 periodic Hann coefficients
//
// Push sequence (abs = padded coordinate, one sample per fire; virtual
// samples are generated from head/tail storage, real samples come from
// the PCM stream):
//   PH_FILL   : accept 1025 stream samples pcm[0..1024] into head
//               storage (no ring push yet; mel_engine back-pressured)
//   PH_VLEFT  : push virtual left reflect, abs 0..1023
//               = pcm[1024], pcm[1023], ..., pcm[1]
//   PH_REPLAY : push head replay, abs 1024..2048 = pcm[0..1024]
//   PH_STREAM : push stream samples pcm[1025..132095], abs 2049..133119;
//               samples with index in [131071, 132094] are ALSO captured
//               into tail_ram (right-reflect source)
//   PH_VRIGHT : push virtual right reflect, abs 133120..134143
//               = pcm[132094], pcm[132093], ..., pcm[131071]
//   Total pushes: 1024 + 1025 + 131071 + 1024 = 134144 = 259*512 + 2048.
//
// Push/drain concurrency guard (anti-overwrite): pushing is allowed
// while push_cnt < frame_th + 512, where frame_th = 2048 + 512*frame_idx
// is the readiness threshold of the CURRENT output frame. During the
// drain of frame j the guard caps push_cnt at 512*j + 2560 - 1; the
// next slot (512*j + 2560) mod 2560 is exactly the frame-j window base,
// so the guard halts the push ONE slot before it would overwrite the
// frame-j window head. End-to-end corner verified for PH_VRIGHT: during
// frame 257's drain the guard caps pushes at abs 134143 (frame 258
// readiness), and the frame 258 window [132096, 134144) is fully
// contained in the retained ring range [131584, 134144).
//
// Output interface to fft2048_sdf (integration alignment point,
// design.md Sec. 2.2 mel sub-block contract):
//   win_valid/win_s17 : 2048 back-to-back beats per frame, frame sample
//                       order = rising padded index (identical to the
//                       golden frame_pcm_reflect row order)
//   frame_start       : one-cycle pulse aligned with the FIRST win_valid
//                       beat of each frame (FFT pipeline frame reset)
//   frame_done        : one-cycle pulse aligned with the LAST win_valid
//                       beat of each frame
//   frame_idx[8:0]    : 0..258 while the frame streams out (increments
//                       on frame_done). 9 bits because the golden frame
//                       count 259 needs the terminal index 258 > 255,
//                       which does not fit the task sketch's 8-bit field
//                       (deviation D1).
//   frame_last        : level, high while the FINAL frame (idx 258)
//                       streams out
//   all_done          : one-cycle pulse one beat after the final
//                       frame_done (registered; the push engine
//                       consumes it to release the window)
//
// Input interface from mel_engine (T-M1-05 integration alignment
// point): PCM stream read from DDR3 master port 2, left channel in the
// low 16 bits of the 32-bit packed word, strictly sequential starting
// at pcm[0], exactly 132096 samples per window, valid/ready handshake.
// pcm_rd_ready deasserts whenever the framer cannot safely accept (the
// head-fill phase boundary, or the ring anti-overwrite guard);
// mel_engine must hold pcm_rd_valid until pcm_rd_ready is sampled high.
// Average required acceptance rate: 512 samples per 2051 cycles (~25
// percent duty), far below any realistic DDR3 read scheduling. On the
// frame_go beat pcm_rd_ready stays high and the same-beat push lands in
// the slot just past the frame window (safe by the guard analysis), so
// no stream sample is ever dropped at a frame boundary.
//
// All logic runs in the core_clk (125 MHz) domain; reset is async
// asserted, synchronously released (rst_n from the core reset tree).
// -----------------------------------------------------------------------------
module stft_framer #(
    parameter integer N_FFT          = 2048,   // frame length
    parameter integer HOP            = 512,    // hop size
    parameter integer REFLECT_PAD    = 1024,   // N_FFT/2, each side
    parameter integer WINDOW_SAMPLES = 132096, // 3 s PCM window
    parameter integer FRAME_COUNT    = 259,    // 1 + WINDOW_SAMPLES/HOP
    parameter integer RING_DEPTH     = 2560,   // N_FFT + HOP ring slots
    // Right-reflect capture range (numpy reflect, edges not repeated):
    // tail_ram holds pcm[WINDOW_SAMPLES-1025 .. WINDOW_SAMPLES-2].
    parameter integer TAIL_FIRST     = WINDOW_SAMPLES - REFLECT_PAD - 1,
    parameter integer TAIL_LAST      = WINDOW_SAMPLES - 2,
    // ROM hex file path (relative to the simulator/synthesis working
    // directory; build scripts arrange the search path - see hann_rom).
    parameter         HAN_HEX_FILE   = "hann_q15.hex"
) (
    input  wire        clk,          // core_clk 125 MHz
    input  wire        rst_n,        // core-domain reset
    // control (mel_engine, T-M1-05 alignment point)
    input  wire        win_start,    // one-cycle window start pulse
    output wire        busy,         // 1 = window in progress
    output wire        all_done,     // pulse: all 259 frames drained
    // PCM stream from DDR3 (left channel = low 16 bits)
    input  wire [31:0] pcm_rd_data,
    input  wire        pcm_rd_valid,
    output wire        pcm_rd_ready,
    // windowed sample stream to fft2048_sdf
    output reg  [16:0] win_s17,
    output reg         win_valid,
    output reg         frame_start,
    output reg         frame_done,
    output wire        frame_last,
    output reg  [8:0]  frame_idx
);

    // ------------------------------------------------------------------
    // Derived constants (sized locals avoid integer-parameter bit
    // selects, which not every toolchain accepts).
    // ------------------------------------------------------------------
    localparam [10:0] PAD_W          = REFLECT_PAD;     // 1024
    localparam [9:0]  TAIL_FIRST_LOW = TAIL_FIRST;      // 131071 -> low 10 bits
    localparam [8:0]  LAST_FRAME     = FRAME_COUNT - 1; // 258
    localparam [11:0] RING_LAST      = RING_DEPTH - 1;  // 2559
    localparam [11:0] BASE_WRAP      = RING_DEPTH - HOP; // 2048: base wrap point

    // ------------------------------------------------------------------
    // Storage.
    // ------------------------------------------------------------------
    reg [15:0] win_ring [0:RING_DEPTH-1]; // padded-stream ring buffer
    reg [15:0] head_ram [0:1023];         // pcm[0..1023]
    reg [15:0] head_extra;                // pcm[1024]
    reg [15:0] tail_ram [0:1023];         // pcm[131071..132094]
    reg [15:0] ring_q;                    // synchronous ring read data
    wire [15:0] han_q;                    // hann_rom read data (must be a net:

    // ------------------------------------------------------------------
    // hann_rom instance (1-cycle synchronous read).
    // ------------------------------------------------------------------
    wire [10:0] han_addr;

    hann_rom #(
        .HAN_HEX_FILE (HAN_HEX_FILE)
    ) u_hann_rom (
        .clk  (clk),
        .addr (han_addr),
        .q    (han_q)
    );

    // ------------------------------------------------------------------
    // Push engine phases.
    // ------------------------------------------------------------------
    localparam [2:0] PH_IDLE   = 3'd0;
    localparam [2:0] PH_FILL   = 3'd1;
    localparam [2:0] PH_VLEFT  = 3'd2;
    localparam [2:0] PH_REPLAY = 3'd3;
    localparam [2:0] PH_STREAM = 3'd4;
    localparam [2:0] PH_VRIGHT = 3'd5;
    localparam [2:0] PH_DONE   = 3'd6;

    reg [2:0]  phase;
    reg        started;
    reg [17:0] push_cnt;       // abs coordinate of the NEXT push (0..134144)
    reg [11:0] push_slot;      // ring slot of the NEXT push (abs mod 2560)
    reg [17:0] samp_cnt;       // stream sample index of the NEXT accept
    reg [10:0] replay_cnt;     // PH_REPLAY sub-counter (0..1024)
    reg [10:0] vright_cnt;     // PH_VRIGHT sub-counter (0..1023)

    // Output engine state read back by the push engine (see below).
    reg        out_run;
    reg        all_done_reg;

    // Frame readiness threshold: 2048 + 512*frame_idx (18-bit).
    wire [17:0] frame_th = 18'd2048 + {frame_idx, 9'd0};
    // Anti-overwrite guard: push limit = current frame threshold + HOP.
    wire [17:0] push_limit = frame_th + 18'd512;
    wire        push_open  = (push_cnt < push_limit);
    wire        frame_go   = started && !out_run && (push_cnt == frame_th);

    // Stream acceptance: head-fill phase, or stream phase under the
    // ring anti-overwrite guard. The frame_go beat keeps ready high
    // (out_run is still low there) and the same-beat push lands in the
    // slot just past the frame window, which the guard analysis proves
    // safe - this closes the sample-drop corner at frame boundaries.
    assign pcm_rd_ready = (phase == PH_FILL) ||
                          ((phase == PH_STREAM) && push_open);

    // Push strobe: virtual phases push every cycle the guard is open;
    // the stream phase pushes only on a valid/ready handshake. The
    // guard alone arbitrates push-vs-drain concurrency (no out_run
    // term), enabling the 259-frame throughput of ~533k cycles.
    wire push_fire = started && push_open && (
        (phase == PH_VLEFT)  || (phase == PH_REPLAY) ||
        (phase == PH_VRIGHT) ||
        ((phase == PH_STREAM) && pcm_rd_valid));

    wire [11:0] next_push_slot = (push_slot == RING_LAST)
                               ? 12'd0 : (push_slot + 12'd1);

    // Push data multiplexer (combinational).
    // Left reflect: abs a (0..1023) -> pcm[1024-a]; a = 0 taps pcm[1024]
    // (head_extra), a >= 1 taps head_ram[1024-a].
    wire [10:0] vleft_full     = PAD_W - push_cnt[10:0];  // 1..1024
    wire [9:0]  vleft_ram_idx  = vleft_full[9:0];         // 1024 wraps to 0, masked
    // Right reflect: abs 133120+vr -> pcm[132094-vr] = tail_ram[1023-vr].
    wire [9:0]  vright_ram_idx = 10'd1023 - vright_cnt[9:0];

    reg [15:0] push_data;
    always @* begin
        case (phase)
            PH_VLEFT: begin
                push_data = (push_cnt[10:0] == 11'd0) ? head_extra
                          : head_ram[vleft_ram_idx];
            end
            PH_REPLAY: begin
                // abs 1024+r -> pcm[r]; r = 1024 taps head_extra.
                push_data = (replay_cnt == PAD_W) ? head_extra
                          : head_ram[replay_cnt[9:0]];
            end
            PH_STREAM: begin
                push_data = pcm_rd_data[15:0];
            end
            PH_VRIGHT: begin
                push_data = tail_ram[vright_ram_idx];
            end
            default: begin
                push_data = 16'd0;
            end
        endcase
    end

    // ------------------------------------------------------------------
    // Push engine FSM (also owns the head/tail capture writes).
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            phase      <= PH_IDLE;
            started    <= 1'b0;
            push_cnt   <= 18'd0;
            push_slot  <= 12'd0;
            samp_cnt   <= 18'd0;
            replay_cnt <= 11'd0;
            vright_cnt <= 11'd0;
            head_extra <= 16'd0;
        end else begin
            case (phase)
                PH_IDLE: begin
                    if (win_start) begin
                        phase     <= PH_FILL;
                        started   <= 1'b1;
                        push_cnt  <= 18'd0;
                        push_slot <= 12'd0;
                        samp_cnt  <= 18'd0;
                    end
                end

                PH_FILL: begin
                    // Capture pcm[0..1024]: 1024 RAM words + 1 register.
                    if (pcm_rd_valid && pcm_rd_ready) begin
                        if (samp_cnt <= 17'd1023) begin
                            head_ram[samp_cnt[9:0]] <= pcm_rd_data[15:0];
                        end else begin
                            head_extra <= pcm_rd_data[15:0];
                        end
                        samp_cnt <= samp_cnt + 18'd1;
                        if (samp_cnt == 17'd1024) begin
                            // 1025 samples captured (pcm[0..1024]).
                            phase <= PH_VLEFT;
                        end
                    end
                end

                PH_VLEFT: begin
                    // Push virtual left reflect (abs 0..1023).
                    if (push_fire) begin
                        push_cnt  <= push_cnt + 18'd1;
                        push_slot <= next_push_slot;
                        if (push_cnt == 18'd1023) begin
                            replay_cnt <= 11'd0;
                            phase      <= PH_REPLAY;
                        end
                    end
                end

                PH_REPLAY: begin
                    // Push pcm[0..1024] (abs 1024..2048).
                    if (push_fire) begin
                        push_cnt   <= push_cnt + 18'd1;
                        push_slot  <= next_push_slot;
                        replay_cnt <= replay_cnt + 11'd1;
                        if (replay_cnt == PAD_W) begin
                            // abs 2048 pushed (pcm[1024] just written).
                            phase <= PH_STREAM;
                        end
                    end
                end

                PH_STREAM: begin
                    // Push stream samples (abs 2049..133119).
                    if (pcm_rd_valid && pcm_rd_ready) begin
                        // Right-reflect capture window. The index uses
                        // 10-bit wraparound arithmetic:
                        // (samp_cnt - 131071) mod 1024, exploiting
                        // TAIL_FIRST_LOW = 131071 mod 1024 = 1023.
                        if ((samp_cnt >= TAIL_FIRST) &&
                            (samp_cnt <= TAIL_LAST)) begin
                            tail_ram[samp_cnt[9:0] - TAIL_FIRST_LOW]
                                <= pcm_rd_data[15:0];
                        end
                        push_cnt  <= push_cnt + 18'd1;
                        push_slot <= next_push_slot;
                        samp_cnt  <= samp_cnt + 18'd1;
                        if (samp_cnt == 17'd132095) begin
                            // Last PCM sample accepted.
                            vright_cnt <= 11'd0;
                            phase      <= PH_VRIGHT;
                        end
                    end
                end

                PH_VRIGHT: begin
                    // Push virtual right reflect (abs 133120..134143).
                    if (push_fire) begin
                        push_cnt   <= push_cnt + 18'd1;
                        push_slot  <= next_push_slot;
                        vright_cnt <= vright_cnt + 11'd1;
                        if (vright_cnt == 11'd1023) begin
                            phase <= PH_DONE;
                        end
                    end
                end

                PH_DONE: begin
                    // All pushes complete; wait for the output engine to
                    // drain frame 258, then release the window (started
                    // drops, phase returns to idle for the next start).
                    if (all_done_reg) begin
                        phase   <= PH_IDLE;
                        started <= 1'b0;
                    end
                end

                default: begin
                    phase <= PH_IDLE;
                end
            endcase
        end
    end

    // ------------------------------------------------------------------
    // Ring buffer write port + synchronous read port
    // (pseudo-dual-port RAM; PDS infers DRM blocks). Write and read
    // addresses are provably disjoint during concurrent push/drain
    // (see the guard analysis in the header), so no read-during-write
    // hazard exists on live data.
    // ------------------------------------------------------------------
    reg  [11:0] rd_addr;                  // output-engine read address

    always @(posedge clk) begin
        if (push_fire) begin
            win_ring[push_slot] <= push_data;
        end
        ring_q <= win_ring[rd_addr];
    end

    // ------------------------------------------------------------------
    // Output engine: drain frame j as 2048 windowed beats.
    //   cycle A(k)   : issue ring read rd_addr (abs 512*j + k mod 2560)
    //                  and hann read han_addr = k (window phase)
    //   cycle A(k)+1 : ring_q / han_q hold sample k -> mult_w valid
    //   cycle A(k)+2 : stage_mult holds the product -> win_n valid
    //   cycle A(k)+3 : win_valid = 1, win_s17 = windowed sample k
    // The intermediate product register splits the multiply -> add ->
    // shift path into two short pipeline stages (125 MHz friendly) and
    // registers exactly one beat per sample: 2048 win_valid beats per
    // frame, frame_start on the first, frame_done on the last.
    // ------------------------------------------------------------------
    reg        addr_done;      // 1 = all 2048 addresses issued
    reg [10:0] out_k;          // window phase 0..2047 (hann index)
    reg [11:0] frame_base;     // 512*j mod 2560 of the draining frame
    reg [10:0] out_beat;       // count of registered output beats
    reg        v_data;         // ring_q/han_q valid this cycle
    reg        v_mult;         // stage_mult valid this cycle
    reg signed [31:0] stage_mult;

    // Multiply + round-half-up: (pcm*hann + 16384) >>> 15, signed.
    wire signed [15:0] pcm_s = ring_q;
    wire signed [15:0] han_s = han_q;
    wire signed [31:0] mult_w = pcm_s * han_s;
    wire signed [31:0] rhu_w  = stage_mult + 32'sd16384;
    wire signed [16:0] win_n  = rhu_w[31:15];

    assign han_addr = out_k;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_run      <= 1'b0;
            addr_done    <= 1'b0;
            out_k        <= 11'd0;
            rd_addr      <= 12'd0;
            frame_base   <= 12'd0;
            out_beat     <= 11'd0;
            v_data       <= 1'b0;
            v_mult       <= 1'b0;
            stage_mult   <= 32'sd0;
            win_s17      <= 17'd0;
            win_valid    <= 1'b0;
            frame_start  <= 1'b0;
            frame_done   <= 1'b0;
            all_done_reg <= 1'b0;
            frame_idx    <= 9'd0;
        end else begin
            // Single-cycle pulses.
            frame_start  <= 1'b0;
            frame_done   <= 1'b0;
            all_done_reg <= 1'b0;

            if (!out_run) begin
                if (frame_go) begin
                    out_run   <= 1'b1;
                    addr_done <= 1'b0;
                    out_k     <= 11'd0;
                    out_beat  <= 11'd0;
                    rd_addr   <= frame_base;
                end
            end else begin
                // Stage 1: address issue (2048 cycles).
                if (!addr_done) begin
                    if (rd_addr == RING_LAST) begin
                        rd_addr <= 12'd0;
                    end else begin
                        rd_addr <= rd_addr + 12'd1;
                    end
                    if (out_k == 11'd2047) begin
                        addr_done <= 1'b1;
                    end else begin
                        out_k <= out_k + 11'd1;
                    end
                end

                // Valid-pipe shift: v_data marks "ring_q/han_q hold the
                // sample addressed last cycle"; v_mult marks "stage_mult
                // holds that sample's product"; win_valid follows.
                v_data    <= !addr_done;
                v_mult    <= v_data;
                win_valid <= v_mult;
                if (v_data) begin
                    stage_mult <= mult_w;
                end

                if (v_mult) begin
                    win_s17  <= win_n;
                    out_beat <= out_beat + 11'd1;
                    if (out_beat == 11'd0) begin
                        frame_start <= 1'b1;  // with first win_valid beat
                    end
                    if (out_beat == 11'd2047) begin
                        // Last win_valid beat registers on this edge.
                        frame_done <= 1'b1;
                        out_run    <= 1'b0;
                        addr_done  <= 1'b0;
                        // Window slides by HOP: base += 512 mod 2560.
                        if (frame_base == BASE_WRAP) begin
                            frame_base <= 12'd0;
                        end else begin
                            frame_base <= frame_base + 12'd512;
                        end
                        if (frame_idx == LAST_FRAME) begin
                            frame_idx    <= 9'd0;
                            all_done_reg <= 1'b1;  // releases PH_DONE
                        end else begin
                            frame_idx <= frame_idx + 9'd1;
                        end
                    end
                end
            end
        end
    end

    // Window-level status outputs. busy spans start acceptance through
    // the all_done pulse (started is cleared by the push engine on the
    // all_done cycle); frame_last covers the entire final-frame stream.
    assign busy       = started;
    assign all_done   = all_done_reg;
    assign frame_last = out_run && (frame_idx == LAST_FRAME);

endmodule