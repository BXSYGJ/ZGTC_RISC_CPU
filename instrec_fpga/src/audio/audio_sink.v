// -----------------------------------------------------------------------------
// File    : audio_sink.v
// Module  : audio_sink
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : PCM ring-buffer write manager + UI waveform column downsampler
//           (design.md section 2.2.4 contract, tasks.md T-M0-06).
//
// Domain : ALL logic runs in the core_clk (125 MHz, DDR3 IP output)
//          domain, EXCEPT the column-buffer read port and the pix-domain
//          status synchronizers, which use pix_clk (148.5 MHz, from
//          hdmi_tx_if). CDC points are marked "CDC:" in the comments.
//
// Upstream  : audio_cdc_fifo read side (this author's contract, T-M0-03):
//             rd_en held high while the consumer wants data; rd_data /
//             rd_valid valid ONE core_clk cycle after rd_en was accepted
//             (1-cycle synchronous read, back-to-back capable); entries
//             are frame-aligned stereo pairs {pcm_l[31:16], pcm_r[15:0]}
//             at 48 kHz. The FIFO is drained in "catch-up" mode: while
//             non-empty one entry is read per cycle, so the long-term
//             frame pace is exactly the write-side pace (locked to the
//             NCO/BCK audio timing) - no independent core-domain rate
//             generator is needed and no drift can accumulate.
//
// Downstream (DDR3) : ddr3_ctrl_axi master port 0 (design.md 2.2.5):
//             m0_cmd = {wr, addr[27:0], len[7:0]} (37 bit - see the
//             integration note below), m0_wdata[255:0], m0_done.
//             INTEGRATION ALIGNMENT POINT (T-M0-09): design.md 2.2.5
//             labels the cmd bus "38 bit" while {1+28+8} = 37; this
//             module uses 37 bit (mathematically consistent packing,
//             wr = bit[36], addr = bits[35:8], len = bits[7:0]). If the
//             ctrl_axi implementation (Sun) ends up with a different
//             width/packing, align at top-level integration.
//             Handshake model assumed here: m0_cmd_valid is asserted
//             LEVEL-style and held (with wdata stable) until m0_done
//             pulses, i.e. at most one command is outstanding. If the
//             final ctrl_axi samples cmd_valid as a single-cycle pulse
//             instead, holding it until done is still safe (no second
//             command can be issued meanwhile) - also an integration
//             alignment note.
//
// Burst split (audio vs ctrl_axi division of labour): this module only
//             issues "page-level" writes of ONE 256-bit beat (len=0,
//             32 B) per command - 16 frames of one channel aggregated
//             into 16 x 16-bit samples = 256 bit. Audio write rate is
//             44100/16 = 2756 commands/s per channel, i.e. ~5.5k
//             commands/s total: at ~150 ns command overhead each this
//             is < 0.1% of the DDR3 budget, so short bursts are fine
//             (design.md 5.4 grants audio 0.18 MB/s; net payload here is
//             the same 0.176 MB/s). Longer bursts (design.md 5.3 prefers
//             len=15 for bulk data) remain the ctrl_axi/Mel/weight side
//             business - NOT the audio path. If integration later
//             requires fewer commands, AGG_FRAMES can be raised and the
//             shift register widened accordingly.
//
// DDR3 address map (design.md section 5.1, byte addresses, 32 B aligned):
//   PCM left  : base 0x0000_0000, TWO ping-pong windows of 264 KB
//               (0x42000 each -> [0x0, 0x84000)); window selected by
//               win_id[0]; 132096 samples x 2 B = 264192 B = 8256 pages
//               of 32 B fit with 6144 B margin per window.
//   PCM right : base 0x0008_4000, ONE 264 KB archive window (REQ-AUD-005:
//               right channel is archive-only, never fed to features);
//               the page offset is the mirror of the left window (same
//               page offset, same window roll-over rhythm).
//   Each 16-frame page -> one 32 B beat: left page first, then the right
//   mirror page (alternating, "left/right region alternating packing" of
//   design.md 2.2.4). Page offset = page_no[13:0] << 5, page_no 0..8255
//   (8256 pages needs 14 bit: 2^13 = 8192 < 8256).
//
// Window beat (REQ-PRF-001 / REQ-MEM-002): every 132096 LEFT-channel
//   samples (i.e. 132096 accepted frames, 2.752 s at 48 kHz) a
//   single-cycle win_tick pulse is produced and win_id increments; the
//   left window alternates and the Mel engine (M1) starts on win_tick.
//   win_id is 16 bit per design.md 2.2.4 (the task brief's "[7:0]" is
//   recorded as a deviation in favour of the contract table).
//
// Mute semantics (REQ-REL-003) - three distinct conditions, deliberately
//   kept separate internally, merged into the exported mute_flag:
//   1. fifo empty     : upstream stall (clk_nco domain still in reset /
//                       GPLL_D unlocked - the "reset window" case, which
//                       is EXPECTED during bring-up). Frame acceptance is
//                       then sustained by INJECTED zero frames at a
//                       2604-cycle (20.8 us, 48 kHz) cadence so the
//                       write pointer and the win_tick beat keep running
//                       and the pipeline never stalls. Injected frames
//                       are dropped while a DDR3 page write is in flight
//                       (agg freeze, < 100 us): during an upstream stall
//                       the win beat is virtual anyway, and real frames
//                       are never lost - the CDC FIFO retains them.
//                       Note: the 2604-cycle cadence is 0.007% fast vs
//                       the native 48 kHz rate (125M/48000 = 2604.17); the
//                       error only affects the (temporary) injection
//                       window and does not accumulate once real data
//                       resumes (catch-up read re-locks to the source).
//   2. sd_idle        : audio source silent (from i2s_rx, clk_nco
//                       domain) - crossed into core with a 2FF sync.
//                       The I2S receiver keeps producing frames (the SD
//                       line is decoded as constant silence), so NO
//                       injection is needed: the pipeline keeps running
//                       on real all-silent frames.
//   3. all-zero stream: 4096 consecutive zero frames (92.9 ms) - the
//                       decoded content itself is silence.
//   mute_flag = any of the three; UI shows the mute hint overlay.
//
// UI waveform column downsampler (design.md 7.4):
//   132096 left samples per window -> 1920 columns of {min,max} s16
//   envelope pairs. 68.8 samples/column is implemented EXACTLY with a
//   384-group scheme: 344 samples = 5 columns (69+69+69+69+68), and
//   384 x 344 = 132096 exactly - the per-column width only jitters by
//   1 sample (1.5%) between 68 and 69, invisible on screen. The update
//   is O(1) per sample: a running {cur_min, cur_max} accumulator pair
//   is updated per frame; at column boundaries it is committed to the
//   column buffer and reset.
//   Column buffer: two ping-pong pages of 1920 x 2 x 16 bit
//   (col_min_mem / col_max_mem, 3840 words each, ~122 Kb total ~ 7 DRM
//   per design.md 7.4). WRITE port on core_clk (commit at column
//   boundary), READ port on pix_clk serving the waveform_disp contract
//   (this author's, T-M0-08): wave_rd_addr is a combinational copy of
//   pix_x, data returned one pix_clk later, wave_valid quasi-static.
//   Page switching happens ONLY at the vertical blanking anchor:
//   vsync_pulse (pix domain, from ui_renderer) is 2FF-synchronized into
//   core_clk and edge-detected; at that edge page_rd latches the most
//   recently COMPLETED write page (pending_page). A window completes
//   every ~3 s while frames last 16.7 ms, so the display always repeats
//   the last completed page between updates (REQ-UI-007 keep-last).
//
// Error sentinel (design.md 5.2 scenario 2 "write pointer overrun",
// consumed by T-M0-10 "no roll-over error in 60 s"): err_cnt counts
//   DDR3 write-done TIMEOUTS. A command outstanding for more than
//   2^22 core cycles (33.5 ms - versus a normal P0-priority latency of
//   < 100 us) means the write path stalled; the FSM then re-issues the
//   command (never gives up - audio is P0 and sys_ctrl watchdogs the
//   system level) and err_cnt saturates at 0xFFFF. A stalled write path
//   is exactly the observable form of a ring-buffer roll-over fault:
//   the write pointer stops advancing, the window beat breaks, and the
//   board test sees it as err_cnt != 0. err_cnt is quasi-static
//   telemetry; the consumer crosses it with its own 2FF synchronizer.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module audio_sink #(
    // Frames (stereo pairs) aggregated into one 256-bit DDR3 beat:
    // 16 frames x 16 bit per channel = 256 bit = 32 B = one beat.
    parameter [4:0] AGG_FRAMES = 5'd16,
    // Injection cadence while the CDC FIFO is empty, in core_clk cycles:
    // 125e6 / 48000 = 2604.17 -> 2604 (0.007% fast, injection-only).
    // Native 48 kHz frontend (MODEL_TRAINING_SPEC 2.1): the resampler is
    // gone, so the empty-FIFO injection cadence must match the PCM1808
    // rate; real FIFO frames always take priority over injection.
    parameter [13:0] INJECT_GAP_CYCLES = 14'd2604,
    // Consecutive zero frames counted as "sustained silence" (92.9 ms).
    parameter [13:0] ZERO_SUSTAIN_FRAMES = 14'd4096,
    // Consecutive empty cycles counted as "sustained upstream stall"
    // (92.9 ms - longer than the bring-up reset window).
    parameter [13:0] EMPTY_SUSTAIN_CYCLES = 14'd4096,
    // DDR3 write-done timeout in core_clk cycles (33.5 ms).
    parameter [22:0] WR_TIMEOUT_CYCLES = 23'd4_194_304
) (
    // -----------------------------------------------------------------
    // core_clk domain (125 MHz).
    // -----------------------------------------------------------------
    input  wire        clk,
    input  wire        rst_n,

    // CDC FIFO read side (audio_cdc_fifo, this author's contract).
    output wire        fifo_rd_en,
    input  wire [31:0] fifo_rd_data,
    input  wire        fifo_rd_valid,
    input  wire        fifo_empty,

    // Diagnostic window lock (DIAG_READBACK_PLAN_20261110): while high the
    // sink stops accepting frames so the completed window's DDR image and the
    // Mel output stay stable for readback.  Default 0 = no effect on the
    // normal datapath.
    input  wire        diag_lock,

    // Source-idle flag from i2s_rx (clk_nco domain register output).
    // CDC: 2-flop synchronizer into core_clk inside this module.
    input  wire        sd_idle,

    // DDR3 master port 0 (ddr3_ctrl_axi, design.md 2.2.5; integration
    // alignment points documented in the header).
    output reg         m0_cmd_valid,
    output reg  [36:0] m0_cmd,       // {wr, addr[27:0], len[7:0]}
    output reg  [255:0] m0_wdata,
    input  wire        m0_done,

    // Window beat (REQ-PRF-001) and telemetry.
    output reg         win_tick,
    output reg  [15:0] win_id,
    output reg         mute_flag,
    output wire [15:0] err_cnt,
    output reg  [31:0] freeze_cycles,   // agg_freeze cycles in the last window
    // Page-write accounting for the current window (latched at win_tick).
    // A full window must show page_cnt = 8256 (one page_go per 16 frames)
    // and done_cnt = 16512 (one m0_done per left and per right command).
    //   page_cnt < 8256  => the aggregator never requested those pages
    //                       (front-end / frame-loss problem)
    //   page_cnt = 8256 but fewer pages carry data in DDR => the write
    //                       command was accepted (done returned) yet the
    //                       data did not land (controller/IP problem)
    output reg  [17:0] page_cnt_lat,
    output reg  [17:0] done_cnt_lat,

    // -----------------------------------------------------------------
    // pix_clk domain (148.5 MHz, from hdmi_tx_if) - only the column
    // buffer read port and the status synchronizers live here.
    // -----------------------------------------------------------------
    input  wire        pix_clk,

    // Frame anchor from ui_renderer (pix domain single-cycle pulse).
    // CDC: 2-flop synchronizer + edge detect into core_clk.
    input  wire        vsync_pulse,

    // Column read channel towards waveform_disp (pix domain contract:
    // combinational address in, data out one pix_clk later).
    input  wire [10:0] wave_rd_addr,
    output reg  [15:0] wave_min,
    output reg  [15:0] wave_max,

    // Column buffer ready flag (pix domain, 2FF-synchronized here).
    output wire        wave_valid,

    // Mute indication towards ui_renderer (pix domain, 2FF here).
    output wire        mute_flag_sync
);

    // -----------------------------------------------------------------
    // Address-map constants (design.md section 5.1).
    // -----------------------------------------------------------------
    localparam [27:0] PCM_L_BASE   = 28'h0000_000;
    localparam [27:0] PCM_R_BASE   = 28'h0008_4000;
    localparam [27:0] WIN_BYTES    = 28'h0004_2000;   // 264 KB per window
    // Frames per window (132096) and pages per window (8256 = 132096/16).
    // WIN_FRAMES needs 18 bit: 2^17 = 131072 < 132096, so a 17-bit
    // declaration truncated it to 1024 and collapsed the 2.752 s window
    // into 1023 frames (23.2 ms). Keep the counter and the comparison in
    // the same 18-bit domain.
    localparam [17:0] WIN_FRAMES   = 18'd132_096;
    // Pages per window (8256) needs 14 bit: 2^13 = 8192 < 8256.
    localparam [13:0] PAGES_PER_WIN = 14'd8256;

    // Column scheme: 384 groups x 344 samples = 132096; 5 columns per
    // group with boundaries 69 / 138 / 207 / 276 (69+69+69+69+68).
    localparam [8:0] GRP_BOUND_0 = 9'd69;
    localparam [8:0] GRP_BOUND_1 = 9'd138;
    localparam [8:0] GRP_BOUND_2 = 9'd207;
    localparam [8:0] GRP_BOUND_3 = 9'd276;
    localparam [8:0] GRP_LAST    = 9'd343;
    localparam [10:0] COLS_PER_PAGE = 11'd1920;

    // -----------------------------------------------------------------
    // CDC: sd_idle (clk_nco) -> core_clk, 2-flop synchronizer.
    // -----------------------------------------------------------------
    reg sd_idle_meta;
    reg sd_idle_sync;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sd_idle_meta <= 1'b0;
            sd_idle_sync <= 1'b0;
        end else begin
            sd_idle_meta <= sd_idle;
            sd_idle_sync <= sd_idle_meta;
        end
    end

    // -----------------------------------------------------------------
    // Frame source: catch-up FIFO read + cadence injection on empty.
    // -----------------------------------------------------------------
    // Read request: only while non-empty AND the aggregator is not
    // frozen waiting for a DDR3 page write (data stays in the FIFO).
    wire agg_freeze;
    assign fifo_rd_en = ~fifo_empty & ~agg_freeze & ~diag_lock;

    // Injection cadence counter: only while the SOURCE IS IDLE.  The FIFO
    // is naturally empty between frames (the 125 MHz read side drains a
    // single entry long before the next 48 kHz write), so gating injection
    // on `fifo_empty` alone injected a zero frame in almost every frame gap
    // and filled the window with silence: measured 19% real frames on the
    // board and 69% in the audio_chain simulation.  Injection is a fallback
    // for "no I2S at all" (sd_idle_sync, the 1 ms PCM1808 watchdog), not for
    // "the next real frame has not arrived yet".
    reg [13:0] empty_gap_cnt;
    wire inject_tick = sd_idle_sync & fifo_empty & ~agg_freeze & ~diag_lock
                     & (empty_gap_cnt == INJECT_GAP_CYCLES - 14'd1);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            empty_gap_cnt <= 14'd0;
        else if (sd_idle_sync & fifo_empty & ~agg_freeze)
            empty_gap_cnt <= empty_gap_cnt + 14'd1;
        else
            empty_gap_cnt <= 14'd0;
    end

    // Frame event: a real frame arriving from the FIFO (1-cycle valid
    // after the accepted rd_en) or an injected zero frame. The two are
    // mutually exclusive by construction (rd_en is gated by ~fifo_empty,
    // inject_tick requires fifo_empty).
    wire frame_event = (fifo_rd_valid | inject_tick) & ~diag_lock;

    // Frame payload (left sample feeds the ring buffer AND the column
    // downsampler; right sample only feeds the mirror ring buffer).
    wire [15:0] frame_l = fifo_rd_valid ? fifo_rd_data[31:16] : 16'h0000;
    wire [15:0] frame_r = fifo_rd_valid ? fifo_rd_data[15:0]  : 16'h0000;

    // -----------------------------------------------------------------
    // Sustained-condition detectors feeding mute_flag.
    // -----------------------------------------------------------------
    // Sustained all-zero frames (92.9 ms).
    reg [13:0] zero_run_cnt;
    reg        all_zero_sustain;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            zero_run_cnt     <= 14'd0;
            all_zero_sustain <= 1'b0;
        end else if (!frame_event) begin
            zero_run_cnt     <= zero_run_cnt;
            all_zero_sustain <= all_zero_sustain;
        end else if ((frame_l == 16'h0000) && (frame_r == 16'h0000)) begin
            zero_run_cnt <= zero_run_cnt + 14'd1;
            if (zero_run_cnt == ZERO_SUSTAIN_FRAMES - 14'd1)
                all_zero_sustain <= 1'b1;
        end else begin
            zero_run_cnt     <= 14'd0;
            all_zero_sustain <= 1'b0;
        end
    end

    // Sustained FIFO empty (upstream stall, 92.9 ms - reset window).
    reg [13:0] empty_run_cnt;
    reg        empty_sustain;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            empty_run_cnt <= 14'd0;
            empty_sustain <= 1'b0;
        end else if (fifo_empty) begin
            empty_run_cnt <= empty_run_cnt + 14'd1;
            if (empty_run_cnt == EMPTY_SUSTAIN_CYCLES - 14'd1)
                empty_sustain <= 1'b1;
        end else begin
            empty_run_cnt <= 14'd0;
            empty_sustain <= 1'b0;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            mute_flag <= 1'b0;
        else
            mute_flag <= sd_idle_sync | all_zero_sustain | empty_sustain;
    end

    // -----------------------------------------------------------------
    // 16-frame page aggregator: two 256-bit shift registers (left/right
    // channel lanes). When the 16th frame of a page is accepted the
    // page is frozen and handed to the DDR3 write FSM (agg_freeze),
    // which clears the freeze after both (left, right) commands done.
    // -----------------------------------------------------------------
    reg [255:0] agg_l_shift;
    reg [255:0] agg_r_shift;
    reg [4:0]   agg_cnt;          // 0..15 frames in current page
    reg [13:0]  page_no;          // page index inside the window 0..8255
    reg         page_go;          // page write request pulse

    wire page_full = frame_event & (agg_cnt == AGG_FRAMES - 5'd1);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            agg_l_shift <= 256'h0;
            agg_r_shift <= 256'h0;
            agg_cnt     <= 5'd0;
            page_go     <= 1'b0;
        end else begin
            page_go <= 1'b0;
            if (frame_event) begin
                agg_l_shift <= {agg_l_shift[239:0], frame_l};
                agg_r_shift <= {agg_r_shift[239:0], frame_r};
                if (agg_cnt == AGG_FRAMES - 5'd1) begin
                    agg_cnt <= 5'd0;
                    page_go <= 1'b1;            // 16th frame just shifted in
                end else begin
                    agg_cnt <= agg_cnt + 5'd1;
                end
            end
        end
    end

    // Latched page parameters (page number of the page being written).
    // The latch is triggered by page_full (the 16th frame of the page),
    // one cycle BEFORE page_go rises, because the write FSM samples
    // addr_left in the cycle it sees page_go: latching on page_go would
    // hand it the PREVIOUS page number (a one-page address lag).  The
    // window selector is latched at the same instant so the last page of
    // a window still lands in the window it belongs to (win_id increments
    // in the same cycle that page 8255 completes).
    reg [13:0] page_no_wr;
    reg        page_win_wr;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            page_no_wr  <= 14'd0;
            page_win_wr <= 1'b0;
        end else if (page_full) begin
            page_no_wr  <= page_no;
            page_win_wr <= win_id[0];
        end
    end

    // Page byte offset inside the window: page_no x 32 B.
    wire [27:0] page_off = {page_no_wr[13:0], 5'b00000};

    // Window frame counter: counts accepted frames within the window,
    // 0..132095; the frame that reaches 132096 rolls it over, emits
    // win_tick and advances win_id (window = 2.752 s at 48 kHz).
    // The page counter rolls in lockstep (132096 = 8256 x 16 exactly),
    // so page_no advances ONCE per completed 16-frame page (page_go),
    // not once per frame.
    reg [17:0] win_frame_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            win_frame_cnt <= 18'd0;
            win_tick      <= 1'b0;
            win_id        <= 16'd0;
            page_no       <= 14'd0;
        end else begin
            win_tick <= 1'b0;
            if (frame_event) begin
                if (win_frame_cnt == WIN_FRAMES - 18'd1) begin
                    win_frame_cnt <= 18'd0;
                    win_tick      <= 1'b1;
                    win_id        <= win_id + 16'd1;
                    page_no       <= 14'd0;
                end else begin
                    win_frame_cnt <= win_frame_cnt + 18'd1;
                    // page_full marks the 16th frame of the page, so the
                    // page index advances here (page_go only rises one
                    // cycle later and would lag the address latch).
                    if (page_full) begin
                        if (page_no == PAGES_PER_WIN - 14'd1)
                            page_no <= 14'd0;
                        else
                            page_no <= page_no + 14'd1;
                    end
                end
            end
        end
    end

    // -----------------------------------------------------------------
    // DDR3 write FSM: left page command -> done -> right mirror page
    // command -> done -> unfreeze the aggregator. One command is
    // outstanding at most; m0_cmd_valid is held level-style until done
    // (header integration note). A done timeout (write path stalled)
    // counts into err_cnt and re-issues the command.
    // -----------------------------------------------------------------
    localparam [1:0] ST_IDLE = 2'b00;   // no command outstanding
    localparam [1:0] ST_WL   = 2'b01;   // left page command outstanding
    localparam [1:0] ST_WR   = 2'b10;   // right mirror command outstanding
    localparam [1:0] ST_GAP  = 2'b11;   // one-cycle gap between L and R

    reg [1:0]  wr_state;
    reg [22:0] wr_timeout_cnt;
    reg [15:0] err_cnt_r;

    // Command fields (registered, held stable until done).
    // Left address: window selected by the CURRENT win_id bit (the
    // window being filled); right address: mirror page in the archive.
    wire [27:0] addr_left = PCM_L_BASE
                          + (page_win_wr ? WIN_BYTES : 28'h0)
                          + page_off;
    wire [27:0] addr_right = PCM_R_BASE + page_off;

    assign err_cnt = err_cnt_r;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_state        <= ST_IDLE;
            m0_cmd_valid    <= 1'b0;
            m0_cmd          <= 37'h0;
            m0_wdata        <= 256'h0;
            wr_timeout_cnt  <= 23'd0;
            err_cnt_r       <= 16'd0;
        end else begin
            wr_timeout_cnt <= wr_timeout_cnt + 23'd1;
            case (wr_state)
                ST_IDLE: begin
                    if (page_go) begin
                        wr_state      <= ST_WL;
                        m0_cmd_valid  <= 1'b1;
                        m0_cmd        <= {1'b1, addr_left, 8'd0};
                        m0_wdata      <= agg_l_shift;
                        wr_timeout_cnt <= 23'd0;
                    end
                end
                ST_WL: begin
                    if (m0_done) begin
                        // Drop cmd_valid for one cycle before presenting the
                        // right-page command: the controller must retire the
                        // left burst before it sees new address/data (without
                        // this gap the right command's completion was lost and
                        // the aggregator froze forever: only ~19% of a window
                        // received real frames).
                        m0_cmd_valid   <= 1'b0;
                        wr_state       <= ST_GAP;
                        wr_timeout_cnt <= 23'd0;
                    end else if (wr_timeout_cnt == WR_TIMEOUT_CYCLES - 23'd1) begin
                        // Stalled left write: re-issue, count the fault.
                        wr_timeout_cnt <= 23'd0;
                        if (err_cnt_r != 16'hFFFF)
                            err_cnt_r <= err_cnt_r + 16'd1;
                    end
                end
                ST_GAP: begin
                    m0_cmd_valid   <= 1'b1;
                    m0_cmd         <= {1'b1, addr_right, 8'd0};
                    m0_wdata       <= agg_r_shift;
                    wr_timeout_cnt <= 23'd0;
                    wr_state       <= ST_WR;
                end
                ST_WR: begin
                    if (m0_done) begin
                        wr_state      <= ST_IDLE;
                        m0_cmd_valid  <= 1'b0;
                        wr_timeout_cnt <= 23'd0;
                    end else if (wr_timeout_cnt == WR_TIMEOUT_CYCLES - 23'd1) begin
                        // Stalled right write: re-issue, count the fault.
                        wr_timeout_cnt <= 23'd0;
                        if (err_cnt_r != 16'hFFFF)
                            err_cnt_r <= err_cnt_r + 16'd1;
                    end
                end
                default: begin
                    wr_state      <= ST_IDLE;
                    m0_cmd_valid  <= 1'b0;
                end
            endcase
        end
    end

    // Freeze-cycle accumulator: how long (in core cycles) the aggregator was
    // frozen during the CURRENT window.  A healthy window freezes for only a
    // few thousand cycles (0.03% of 344 M); if a page write stalls, this is
    // the number that exposes it.  Latched at win_tick and cleared for the
    // next window.
    reg [31:0] freeze_cyc_cnt;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            freeze_cyc_cnt <= 32'd0;
            freeze_cycles  <= 32'd0;
        end else begin
            if (agg_freeze)
                freeze_cyc_cnt <= freeze_cyc_cnt + 32'd1;
            if (win_tick) begin
                freeze_cycles  <= freeze_cyc_cnt;
                freeze_cyc_cnt <= 32'd0;
            end
        end
    end

    // Aggregator freeze: from page_go until both commands completed.
    reg agg_freeze_r;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            agg_freeze_r <= 1'b0;
        else if (page_go)
            agg_freeze_r <= 1'b1;
        else if ((wr_state == ST_WR) && m0_done)
            agg_freeze_r <= 1'b0;
        // NOTE (2026-11-08): a timeout-based fail-safe release was tried and
        // REVERTED.  Releasing the aggregator while the write FSM is still in
        // ST_WL/ST_WR is NOT safe: the FSM keeps cmd_valid high and only the
        // ST_IDLE branch accepts page_go, so the next page's command is never
        // issued and its 16 frames are silently dropped while win_frame_cnt
        // keeps counting them (silent data corruption).  A real fail-safe must
        // also abort/reset the write FSM and mark the window invalid; that is
        // not implemented, so the freeze is kept as-is and only observed.
    end

    assign agg_freeze = agg_freeze_r;

    // -----------------------------------------------------------------
    // Page-write accounting (see the port comment).  Two 18-bit counters
    // plus their window latches: 8256 page requests and 16512 done pulses
    // in a healthy window.
    // -----------------------------------------------------------------
    reg [17:0] page_cnt_r;
    reg [17:0] done_cnt_r;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            page_cnt_r   <= 18'd0;
            done_cnt_r   <= 18'd0;
            page_cnt_lat <= 18'd0;
            done_cnt_lat <= 18'd0;
        end else begin
            if (page_go && (page_cnt_r != 18'h3FFFF))
                page_cnt_r <= page_cnt_r + 18'd1;
            if (m0_done && (done_cnt_r != 18'h3FFFF))
                done_cnt_r <= done_cnt_r + 18'd1;
            if (win_tick) begin
                page_cnt_lat <= page_cnt_r;
                done_cnt_lat <= done_cnt_r;
                page_cnt_r   <= 18'd0;
                done_cnt_r   <= 18'd0;
            end
        end
    end

    // -----------------------------------------------------------------
    // UI waveform column downsampler (design.md 7.4), core_clk side.
    // O(1) per frame: running min/max accumulators; column boundary in
    // the 344-sample group commits {cur_min, cur_max} to the write page
    // of the column buffer and resets the accumulators.
    // -----------------------------------------------------------------
    reg [8:0]  grp_cnt;        // sample offset inside the 344-sample group
    reg [10:0] col_cnt;        // column index inside the page 0..1919
    reg [15:0] cur_min;        // running minimum (s16)
    reg [15:0] cur_max;        // running maximum (s16)
    reg        page_wr;        // column buffer write page selector
    reg        page_done;      // at least one page completed (wave_valid)
    reg        pending_page;   // most recently completed page number

    wire col_end = (grp_cnt == GRP_BOUND_0 - 9'd1)
                || (grp_cnt == GRP_BOUND_1 - 9'd1)
                || (grp_cnt == GRP_BOUND_2 - 9'd1)
                || (grp_cnt == GRP_BOUND_3 - 9'd1)
                || (grp_cnt == GRP_LAST);

    // Signed comparisons for the running envelope.
    wire sample_lt_min = ($signed(frame_l) < $signed(cur_min));
    wire sample_gt_max = ($signed(frame_l) > $signed(cur_max));

    wire page_complete = col_end & (col_cnt == COLS_PER_PAGE - 11'd1);

    // Column buffer storage: two ping-pong pages, 1920 words each
    // (word = 16 bit), separate memories for min and max. Write port
    // on core_clk, read port on pix_clk (dual-clock RAM -> PDS should
    // infer dual-clock DRM, ~7 blocks total for min+max, design.md 7.4).
    reg [15:0] col_min_mem [0:3839];
    reg [15:0] col_max_mem [0:3839];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            grp_cnt      <= 9'd0;
            col_cnt      <= 11'd0;
            cur_min      <= 16'h7FFF;   // s16 max as reset minimum
            cur_max      <= 16'h8000;   // s16 min as reset maximum
            page_wr      <= 1'b0;
            page_done    <= 1'b0;
            pending_page <= 1'b0;
        end else if (frame_event) begin
            // Update the running envelope with the left sample.
            if (sample_lt_min)
                cur_min <= frame_l;
            if (sample_gt_max)
                cur_max <= frame_l;
            if (grp_cnt == GRP_LAST)
                grp_cnt <= 9'd0;
            else
                grp_cnt <= grp_cnt + 9'd1;
            if (col_end) begin
                // Commit the completed column into the write page.
                col_min_mem[{page_wr, col_cnt}] <= cur_min;
                col_max_mem[{page_wr, col_cnt}] <= cur_max;
                // Reset the envelope for the next column.
                cur_min <= 16'h7FFF;
                cur_max <= 16'h8000;
                if (col_cnt == COLS_PER_PAGE - 11'd1) begin
                    // Page full: it becomes the pending display page.
                    col_cnt      <= 11'd0;
                    pending_page <= page_wr;
                    page_done    <= 1'b1;
                    page_wr      <= ~page_wr;
                end else begin
                    col_cnt <= col_cnt + 11'd1;
                end
            end
        end
    end

    // NOTE on the envelope reset: the first sample of a new column is
    // compared against the reset extremes (s16 max/min), so it always
    // replaces them - the reset values never leak into committed data.

    // -----------------------------------------------------------------
    // CDC: vsync_pulse (pix domain) -> core_clk, 2FF + edge detect.
    // The edge strobe is the vertical-blanking anchor at which the
    // display read page is switched to the pending completed page.
    // -----------------------------------------------------------------
    reg vsync_meta;
    reg vsync_sync;
    reg vsync_sync_d;
    wire vsync_edge = vsync_sync & ~vsync_sync_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            vsync_meta   <= 1'b0;
            vsync_sync   <= 1'b0;
            vsync_sync_d <= 1'b0;
        end else begin
            vsync_meta   <= vsync_pulse;
            vsync_sync   <= vsync_meta;
            vsync_sync_d <= vsync_sync;
        end
    end

    // Display page register: updated ONLY at the blanking anchor.
    reg page_rd;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            page_rd <= 1'b0;
        else if (vsync_edge)
            page_rd <= pending_page;
    end

    // -----------------------------------------------------------------
    // Column buffer pix_clk read port (waveform_disp contract:
    // wave_rd_addr combinational in, wave_min/wave_max out one
    // pix_clk later). No page mixing: the address is concatenated
    // with the CURRENT page_rd, and page_rd only changes at the
    // blanking anchor (address bit 11 stable during a whole frame).
    // -----------------------------------------------------------------
    always @(posedge pix_clk) begin
        wave_min <= col_min_mem[{page_rd, wave_rd_addr}];
        wave_max <= col_max_mem[{page_rd, wave_rd_addr}];
    end

    // -----------------------------------------------------------------
    // CDC: quasi-static status flags core -> pix, 2FF synchronizers.
    // wave_valid: column buffer has at least one completed page.
    // mute_flag_sync: mute indication for the UI overlay hint.
    // -----------------------------------------------------------------
    reg wave_valid_meta;
    reg wave_valid_pix;

    always @(posedge pix_clk) begin
        wave_valid_meta <= page_done;
        wave_valid_pix  <= wave_valid_meta;
    end

    assign wave_valid = wave_valid_pix;

    reg mute_sync_meta;
    reg mute_sync_pix;

    always @(posedge pix_clk) begin
        mute_sync_meta  <= mute_flag;
        mute_sync_pix   <= mute_sync_meta;
    end

    assign mute_flag_sync = mute_sync_pix;

endmodule