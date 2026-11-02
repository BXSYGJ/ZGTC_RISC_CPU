// -----------------------------------------------------------------------------
// File    : audio_cdc_fifo.v
// Module  : audio_cdc_fifo
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Dual-clock sample FIFO bridging the I2S receive domain into the
//           DDR3 core domain (T-M0-03, design.md section 1.4 CDC table row
//           "216M(nco) -> 125M(core) PCM sample stream").
//
//           Write side : clk_nco (216 MHz, GPLL_D), consumes the i2s_rx
//                        word interface (pcm_valid / pcm_l / pcm_r).
//           Read side  : clk_core (125 MHz, DDR3 IP output), consumed by
//                        audio_sink (T-M0-06) which aggregates 4 samples
//                        per beat into 64-bit DDR3 write bursts.
//
// Entry granularity - frame-pair packing (deviation from the plain
// "write on every pcm_valid" reading of the task text, see the deviation
// log in the delivery report; rationale):
//   i2s_rx pulses pcm_valid on EVERY completed 16-bit word, i.e. 88.2 kHz
//   pulses/s with left and right words STRICTLY ALTERNATING (left word
//   completes at the start of a right half frame, right word at the
//   start of the next left half frame). Writing {pcm_l, pcm_r} on every
//   pulse would store 88.2k entries/s where half of each entry is stale,
//   doubling the watermark and leaving audio_sink unable to recover the
//   per-channel sample streams (no word_ch sideband exists on i2s_rx).
//   Instead this FIFO writes ONE entry per completed frame PAIR:
//     wr_en = pcm_valid & ~i2s_lrck      (right word just completed)
//   Phase proof (i2s_clk_gen.v + i2s_rx.v register timing, verified):
//     * i2s_clk_gen toggles i2s_lrck in the SAME clock cycle in which
//       bck_phase wraps 31 -> 0, so the new half-frame level is present
//       on i2s_lrck one cycle BEFORE the bit0 sample tick of that half
//       frame;
//     * i2s_rx completes a word (bit0 sample) at tick T = phase==0 of
//       half frame H+1 and pulses pcm_valid at T+1, with the completed
//       word belonging to the PREVIOUS half frame H;
//     * therefore during the pcm_valid pulse i2s_lrck already shows the
//       H+1 level: i2s_lrck = 0 (left half frame) -> completed word was
//       the RIGHT one; i2s_lrck = 1 -> completed word was the LEFT one.
//   At a right-word completion: pcm_r = this frame's right sample (just
//   updated) and pcm_l = this frame's left sample (updated half a frame
//   earlier and unchanged since) -> the entry is a complete, aligned
//   {left, right} pair. Write rate = 44.1 kHz entries/s. i2s_lrck is a
//   clk_nco-domain register output (same domain as pcm_valid, fixed
//   phase relationship) so sampling it next to pcm_valid needs NO
//   synchronizer.
//
// FIFO structure (standard Gray-coded dual-clock FIFO):
//   * storage    : 512 x 32 bit, one dual-clock RAM array
//                  (reg [31:0] mem [0:511], write port on clk_nco,
//                  registered read port on clk_core). PDS should infer
//                  one 18 Kb dual-clock DRM block; a LUTRAM inference
//                  is also acceptable within the resource budget
//                  (512 x 32 = 16 Kb, T-M0-03 task note).
//   * pointers   : 10-bit binary (9 address bits + 1 wrap bit), each
//                  converted to Gray code before crossing;
//   * synchronizers: 2-flop Gray synchronizers in each domain;
//   * full       : write-domain compare, wr_gray vs synchronized
//                  rd_gray with the two MSBs inverted;
//   * empty      : read-domain compare, rd_gray == synchronized
//                  wr_gray (exact equality);
//   * overflow   : audio must NEVER back-pressure (i2s_rx has no flow
//                  control), so on full the NEW sample is dropped
//                  (write pointer NOT advanced) and overflow_cnt
//                  saturates up (16-bit, stops at 0xFFFF). The counter
//                  lives in the write domain; the consumer (sys_ctrl /
//                  uart_debug) crosses it with its own 2-flop
//                  synchronizer (REQ-MNT-001 overflow warning path).
//
// Watermark analysis ("no overflow" assertion for T-M0-10):
//   * write rate  : 44.1k entries/s (one stereo pair per audio frame);
//   * read side   : audio_sink in the 125 MHz core domain needs only
//                   44.1k reads/s = 1 read per 2832 core cycles;
//   * capacity    : 512 entries = 11.6 ms of stereo audio at 44.1 kHz
//                   (this matches the tasks.md T-M0-03 "11.6 ms buffer"
//                   figure);
//   * assertion   : overflow cannot happen while audio_sink services
//                   the FIFO at least once every 11.6 ms on average
//                   (its DDR3 write path budget is ~0.18 MB/s stereo,
//                   orders of magnitude below the 285 MB/s DDR3 limit,
//                   so the only realistic overflow source is the core
//                   domain staying in reset, see below).
//
// Reset scheme (design.md section 1.3 reset tree):
//   wr_rst_n comes from rst_sync_nco (216 MHz domain), rd_rst_n from
//   rst_sync_core (125 MHz domain). Both are asynchronous-assert /
//   synchronous-release resets provided by the top level; each side of
//   the FIFO clears ONLY its own pointers and Gray synchronizer flops
//   with its own reset. The two resets release at different times (the
//   core domain stays in reset until DDR3 calibration finishes,
//   typically ~100 ms after GPLL_D locks). Behaviour in that window:
//     * the write side starts filling entries; the read-side Gray
//       synchronizer is held at 0 by rd_rst_n, so the write side sees
//       "rd_ptr = 0", fills all 512 entries, then drops new samples and
//       counts overflows (audio captured during DDR3 calibration is
//       lost - acceptable, DDR3 is not writable yet anyway);
//     * the read side sees "wr_ptr = 0" while in reset -> empty, no
//       reads issued;
//     * after rd_rst_n releases, the synchronizer tracks the current
//       wr_gray within 2 core cycles and normal operation resumes with
//       the oldest 512 entries intact in order. No pointer corruption
//       is possible because Gray-coded values are sampled with 2-flop
//       synchronizers and only monotonic pointer increments cross.
//
// Read-side contract for audio_sink (T-M0-06):
//   * protocol : rd_en is asserted for exactly one clk_core cycle when
//                the consumer wants the next entry; it must only be
//                asserted while empty = 0 (the consumer is expected to
//                gate rd_en with ~empty itself; asserting rd_en during
//                empty is harmless - the pointer does not move and no
//                data is returned);
//   * latency  : registered synchronous read, rd_data / rd_valid are
//                valid ONE clk_core cycle after rd_en was accepted
//                (rd_valid = accepted read indicator, rd_data holds the
//                entry payload {pcm_l[15:0], pcm_r[15:0]} in that cycle,
//                MSB half = left channel);
//   * back-to-back reads are supported (one entry per cycle while the
//                FIFO is non-empty);
//   * empty/full are registered-domain combinational views (Gray
//                compares), pessimistic by at most the synchronizer
//                latency of the opposite domain - always in the safe
//                direction (empty looks "more empty", full looks
//                "more full").
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module audio_cdc_fifo #(
    // Address width: 9 -> depth 512 (512 x 32 bit = 16 Kb, 1 DRM block).
    parameter [3:0] ADDR_W = 4'd9,
    // Data width: one stereo pair {left[15:0], right[15:0]}.
    parameter [5:0] DATA_W = 6'd32
) (
    // -----------------------------------------------------------------
    // Write side - clk_nco domain (216 MHz).
    // -----------------------------------------------------------------
    input  wire        clk_nco,
    // 216 MHz-domain reset (rst_sync_nco from the top-level reset tree).
    input  wire        wr_rst_n,
    // i2s_rx word interface (clk_nco domain, valid/data protocol).
    input  wire        pcm_valid,
    input  wire [15:0] pcm_l,
    input  wire [15:0] pcm_r,
    // Frame clock level from i2s_clk_gen (clk_nco domain register
    // output, fixed phase vs pcm_valid - see header phase proof).
    input  wire        i2s_lrck,

    // -----------------------------------------------------------------
    // Read side - clk_core domain (125 MHz, DDR3 IP output).
    // -----------------------------------------------------------------
    input  wire        clk_core,
    // 125 MHz-domain reset (rst_sync_core from the top-level reset tree).
    input  wire        rd_rst_n,
    // Read request from audio_sink (one-cycle pulse, see contract).
    input  wire        rd_en,
    output wire [31:0] rd_data,
    output wire        rd_valid,
    // Status flags (combinational Gray-compare views, see contract).
    output wire        empty,
    output wire        full,

    // Overflow counter (clk_nco domain, saturating; consumer crosses it
    // with its own 2-flop synchronizer - quasi-static error telemetry).
    output wire [15:0] overflow_cnt
);

    // Pointer width = address bits + 1 wrap bit.
    localparam [3:0] PTR_W = ADDR_W + 4'd1;

    // -----------------------------------------------------------------
    // Storage array: dual-clock RAM, write port on clk_nco, registered
    // read port on clk_core (inferred as one dual-clock DRM block, or
    // LUTRAM - both acceptable per T-M0-03 resource note).
    // -----------------------------------------------------------------
    reg [31:0] mem [0:(1 << ADDR_W) - 1];

    // -----------------------------------------------------------------
    // Write-domain pointers and Gray conversion.
    // -----------------------------------------------------------------
    reg [PTR_W-1:0] wr_bin;
    reg [PTR_W-1:0] wr_gray;

    // Frame-aligned write enable: right word just completed -> write the
    // complete {left, right} pair (see header for the phase proof).
    wire wr_req = pcm_valid & ~i2s_lrck;

    // Gray encoding function (binary ^ binary >> 1).
    function [PTR_W-1:0] bin2gray;
        input [PTR_W-1:0] bin_val;
        begin
            bin2gray = bin_val ^ (bin_val >> 1);
        end
    endfunction

    // Registered full flag. Compute from the accepted next write pointer
    // so the final free entry is accepted and the following write is blocked.
    // The Gray comparison no longer lies on the high-speed RAM write enable.
    wire [PTR_W-1:0] rd_gray_wsync;
    reg full_w;

    // Actual write strobe: drop the new sample when full (audio stream
    // is never back-pressured, overflow counted instead).
    wire wr_fire = wr_req & ~full_w;
    wire [PTR_W-1:0] wr_bin_next = wr_bin + wr_fire;
    wire [PTR_W-1:0] wr_gray_next = bin2gray(wr_bin_next);
    wire full_next = (wr_gray_next == {~rd_gray_wsync[PTR_W-1:PTR_W-2],
                                      rd_gray_wsync[PTR_W-3:0]});

    always @(posedge clk_nco or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            wr_bin  <= {PTR_W{1'b0}};
            wr_gray <= {PTR_W{1'b0}};
            full_w  <= 1'b0;
        end else begin
            wr_bin  <= wr_bin_next;
            wr_gray <= wr_gray_next;
            full_w  <= full_next;
        end
    end

    // Storage write port.
    always @(posedge clk_nco) begin
        if (wr_fire)
            mem[wr_bin[ADDR_W-1:0]] <= {pcm_l, pcm_r};
    end

    // Overflow counter: saturating increment on a dropped sample.
    // Saturate at 0xFFFF so the telemetry never wraps back to zero and
    // masks a persistent overflow condition.
    reg [15:0] overflow_cnt_r;

    always @(posedge clk_nco or negedge wr_rst_n) begin
        if (!wr_rst_n)
            overflow_cnt_r <= 16'd0;
        else if (wr_req && full_w && (overflow_cnt_r != 16'hFFFF))
            overflow_cnt_r <= overflow_cnt_r + 16'd1;
    end

    assign overflow_cnt = overflow_cnt_r;

    // -----------------------------------------------------------------
    // Read-domain pointers and Gray conversion.
    // -----------------------------------------------------------------
    reg [PTR_W-1:0] rd_bin;
    reg [PTR_W-1:0] rd_gray;

    // Synchronized write Gray pointer (read-domain view).
    wire [PTR_W-1:0] wr_gray_rsync;

    // Empty flag (read-domain view): exact Gray equality.
    wire empty_r = (rd_gray == wr_gray_rsync);

    // Accepted read: rd_en while not empty advances the read pointer.
    wire rd_fire = rd_en & ~empty_r;

    always @(posedge clk_core or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            rd_bin  <= {PTR_W{1'b0}};
            rd_gray <= {PTR_W{1'b0}};
        end else if (rd_fire) begin
            rd_bin  <= rd_bin + {{(PTR_W-1){1'b0}}, 1'b1};
            rd_gray <= bin2gray(rd_bin + {{(PTR_W-1){1'b0}}, 1'b1});
        end
    end

    // -----------------------------------------------------------------
    // Gray-code pointer crossing (2-flop synchronizers each direction).
    // Gray coding guarantees that a synchronizer sampling a moving
    // pointer only ever sees a single-bit change, so the recovered
    // value is always a valid recent pointer value (never a glitch
    // mixture of two steps) - the classic dual-clock FIFO safety
    // argument. Pessimism direction: the reader lags the writer (may
    // see "less data"), the writer lags the reader (may see "more
    // data used") - both in the safe direction.
    // -----------------------------------------------------------------
    // Read Gray pointer into the write domain.
    reg [PTR_W-1:0] rd_gray_sync1;
    reg [PTR_W-1:0] rd_gray_sync2;

    always @(posedge clk_nco or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            rd_gray_sync1 <= {PTR_W{1'b0}};
            rd_gray_sync2 <= {PTR_W{1'b0}};
        end else begin
            rd_gray_sync1 <= rd_gray;
            rd_gray_sync2 <= rd_gray_sync1;
        end
    end

    assign rd_gray_wsync = rd_gray_sync2;

    // Write Gray pointer into the read domain.
    reg [PTR_W-1:0] wr_gray_sync1;
    reg [PTR_W-1:0] wr_gray_sync2;

    always @(posedge clk_core or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            wr_gray_sync1 <= {PTR_W{1'b0}};
            wr_gray_sync2 <= {PTR_W{1'b0}};
        end else begin
            wr_gray_sync1 <= wr_gray;
            wr_gray_sync2 <= wr_gray_sync1;
        end
    end

    assign wr_gray_rsync = wr_gray_sync2;

    // -----------------------------------------------------------------
    // Registered read port: rd_data / rd_valid valid one clk_core cycle
    // after the accepted rd_en (synchronous RAM read, back-to-back
    // reads supported).
    // -----------------------------------------------------------------
    reg [31:0] rd_data_r;
    reg        rd_valid_r;

    always @(posedge clk_core or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            rd_data_r  <= 32'd0;
            rd_valid_r <= 1'b0;
        end else begin
            rd_valid_r <= rd_fire;
            if (rd_fire)
                rd_data_r <= mem[rd_bin[ADDR_W-1:0]];
        end
    end

    assign rd_data  = rd_data_r;
    assign rd_valid = rd_valid_r;

    // Status flag outputs.
    assign empty = empty_r;
    assign full  = full_w;

endmodule
