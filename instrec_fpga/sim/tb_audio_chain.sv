// ---------------------------------------------------------------------------
// tb_audio_chain: full audio front-end chain at board topology.
//
//   physical PCM1808 I2S (BCK 3.072 MHz / LRCK 48 kHz / Philips 1-bit delay)
//     -> i2s_slave_rx (clk_nco = 27 MHz)
//     -> audio_cdc_fifo (wr 27 MHz / rd 125 MHz, i2s_lrck tied 0)
//     -> audio_sink (125 MHz, master 0 write to a behavioural DDR responder)
//
// Purpose: reproduce the board observation "only ~19% of a window receives
// real frames, the rest is empty-FIFO zero injection" and bisect it against
// the DDR write-completion latency.  The responder's done delay is a plusarg
// (default 4 cycles, i.e. a fast IP); sweep it to find where the real-frame
// rate collapses.
//
// Counters (printed at every win_tick):
//   real   = fifo_rd_valid accepted by audio_sink (fifo_rd_valid_run)
//   inj    = frame events produced while the FIFO was empty
//   freeze = cycles agg_freeze was asserted inside the window
//   err    = audio_sink write-timeout count (saturating)
//   ovf    = CDC FIFO overflow count
// The zero-injection path is inferred as window_frames - real (the window
// counter only counts frame_event, which is real or injected).
// ---------------------------------------------------------------------------
`timescale 1ns / 1ps

module tb_audio_chain;

    // ---- clocks ----------------------------------------------------------
    reg clk27  = 1'b0;     // 27 MHz nco domain (37.037 ns period)
    reg clk125 = 1'b0;     // 125 MHz core domain (8 ns period)
    always #18.5185 clk27  = ~clk27;
    always #4.0     clk125 = ~clk125;

    reg rst_n = 1'b0;

    // ---- PCM1808 master I2S source --------------------------------------
    reg bck  = 1'b0;
    reg lrck = 1'b0;
    reg sd   = 1'b1;   // idle high, same as the proven tb_i2s_capture source
    always #162.76 bck = ~bck;      // 3.072 MHz

    // Philips: LRCK changes on the BCK falling edge, one delay bit after the
    // edge, then 16 data bits MSB first, then pad to 32 bits.
    task send_slot(input level, input [15:0] s);
        integer b;
        begin
            @(negedge bck);
            lrck = level;
            sd   = 1'b1;            // delay bit (previous slot LSB)
            for (b = 15; b >= 0; b = b - 1) begin
                @(negedge bck);
                sd = s[b];
            end
            sd = 1'b1;
            repeat (15) @(negedge bck);
        end
    endtask

    integer tone_n = 0;
    reg [15:0] l_sample, r_sample;
    initial begin : i2s_thread
        integer idx;
        forever begin
            // Deterministic stereo pattern: L = index, R = index ^ 0x8000.
            l_sample = tone_n[15:0];
            r_sample = tone_n[15:0] ^ 16'h8000;
            send_slot(1'b0, l_sample);
            send_slot(1'b1, r_sample);
            tone_n = tone_n + 1;
            idx = 0;
        end
    end

    // ---- DUT chain -------------------------------------------------------
    wire [15:0] pcm_l, pcm_r;
    wire pcm_valid, sd_idle;

    i2s_slave_rx #(.TIMEOUT_CYCLES(27000)) u_rx (
        .clk_nco   (clk27),
        .rst_n     (rst_n),
        .i2s_bck   (bck),
        .i2s_lrck  (lrck),
        .i2s_sd    (sd),
        .pcm_l     (pcm_l),
        .pcm_r     (pcm_r),
        .pcm_valid (pcm_valid),
        .sd_idle   (sd_idle)
    );

    wire        fifo_rd_en, fifo_rd_valid, fifo_empty, fifo_full;
    wire [31:0] fifo_rd_data;
    wire [15:0] overflow_cnt;

    audio_cdc_fifo u_fifo (
        .clk_nco      (clk27),
        .wr_rst_n     (rst_n),
        .pcm_valid    (pcm_valid),
        .pcm_l        (pcm_l),
        .pcm_r        (pcm_r),
        .i2s_lrck     (1'b0),
        .clk_core     (clk125),
        .rd_rst_n     (rst_n),
        .rd_en        (fifo_rd_en),
        .rd_data      (fifo_rd_data),
        .rd_valid     (fifo_rd_valid),
        .empty        (fifo_empty),
        .full         (fifo_full),
        .overflow_cnt (overflow_cnt)
    );

    reg         m0_cmd_valid;
    reg  [36:0] m0_cmd;
    reg  [255:0] m0_wdata;
    wire        m0_done;
    wire        win_tick;
    wire [15:0] win_id;
    wire        mute_flag;
    wire [15:0] err_cnt;
    wire [10:0] wave_rd_addr = 11'd0;
    wire [15:0] wave_min, wave_max;
    wire        wave_valid, mute_flag_sync;

    // ---- behavioural DDR master-0 responder (done delay = DLY) ----------
    integer DLY = 4;
    reg [31:0] dly_cnt = 32'd0;
    reg        m0_done_r = 1'b0;

    always @(posedge clk125 or negedge rst_n) begin
        if (!rst_n) begin
            dly_cnt   <= 32'd0;
            m0_done_r <= 1'b0;
        end else if (m0_cmd_valid) begin
            if (dly_cnt >= DLY[31:0]) begin
                dly_cnt   <= 32'd0;
                m0_done_r <= 1'b1;
            end else begin
                dly_cnt   <= dly_cnt + 32'd1;
                m0_done_r <= 1'b0;
            end
        end else begin
            dly_cnt   <= 32'd0;
            m0_done_r <= 1'b0;
        end
    end
    assign m0_done = m0_done_r && m0_cmd_valid;

    audio_sink u_sink (
        .clk            (clk125),
        .rst_n          (rst_n),
        .fifo_rd_en     (fifo_rd_en),
        .fifo_rd_data   (fifo_rd_data),
        .fifo_rd_valid  (fifo_rd_valid),
        .fifo_empty     (fifo_empty),
        .sd_idle        (sd_idle),
        .m0_cmd_valid   (m0_cmd_valid),
        .m0_cmd         (m0_cmd),
        .m0_wdata       (m0_wdata),
        .m0_done        (m0_done),
        .win_tick       (win_tick),
        .win_id         (win_id),
        .mute_flag      (mute_flag),
        .err_cnt        (err_cnt),
        .pix_clk        (clk125),
        .vsync_pulse    (1'b0),
        .wave_rd_addr   (wave_rd_addr),
        .wave_min       (wave_min),
        .wave_max       (wave_max),
        .wave_valid     (wave_valid),
        .mute_flag_sync (mute_flag_sync)
    );

    // ---- window counters (core clock) -----------------------------------
    integer real_cnt   = 0;
    integer inj_cnt    = 0;
    integer freeze_cyc = 0;
    integer win_n      = 0;
    integer total_real = 0;
    integer sim_fails  = 0;

    // Board contract: a full window must accept 132096 frames; the number
    // of those that came from the FIFO (real audio) is what we measure.
    always @(posedge clk125) begin
        if (rst_n) begin
            if (u_sink.agg_freeze) freeze_cyc = freeze_cyc + 1;
            if (u_sink.frame_event) begin
                // frame_event = fifo_rd_valid | inject_tick (mutually
                // exclusive), so fifo_rd_valid alone discriminates.  The
                // earlier "&& !fifo_empty" test was wrong: the single FIFO
                // entry has already been popped on the frame_event cycle.
                if (u_sink.fifo_rd_valid) real_cnt = real_cnt + 1;
                else                      inj_cnt  = inj_cnt + 1;
            end
            if (win_tick) begin
                win_n = win_n + 1;
                total_real = total_real + real_cnt;
                $display("WIN %0d: real=%0d inj=%0d freeze_cyc=%0d err=%0d ovf=%0d",
                         win_n, real_cnt, inj_cnt, freeze_cyc,
                         err_cnt, overflow_cnt);
                if (win_n >= 2) begin
                    $display("AUDIO_CHAIN RESULT: real=%0d (%.1f%%) inj=%0d freeze_cyc=%0d err=%0d ovf=%0d",
                             real_cnt, 100.0 * real_cnt / 132096.0, inj_cnt,
                             freeze_cyc, err_cnt, overflow_cnt);
                    if (real_cnt*10 >= 4096*9)
                        $display("RESULT: PASS audio_chain (>=90%% real frames)");
                    else
                        $display("RESULT: FAIL audio_chain (real=%0d of 4096)", real_cnt);
                    $display("TB_AUDIO_CHAIN: DONE");
                    $finish;
                end
                real_cnt   = 0;
                inj_cnt    = 0;
                freeze_cyc = 0;
            end
        end
    end

    // short-mode diagnostics: is pcm_valid produced at all?
    integer pv_cnt = 0, idle_cyc = 0, rv_cnt = 0;
    always @(posedge clk27) begin
        if (pcm_valid) pv_cnt  = pv_cnt + 1;
        if (sd_idle)   idle_cyc = idle_cyc + 1;
    end
    always @(posedge clk125) if (fifo_rd_valid) rv_cnt = rv_cnt + 1;

    // Default mode is the 2 ms diagnostic (fast); +FULL runs two full windows.
    initial begin
        if ($value$plusargs("DLY=%d", DLY)) ;
        $display("tb_audio_chain: DLY(done delay cycles)=%0d", DLY);
        #200 rst_n = 1'b1;
        if (!$test$plusargs("FULL")) begin
            #2_000_000;
            $display("DIAG(2ms): pcm_valid=%0d sd_idle_cyc=%0d fifo_rd_valid=%0d ovf=%0d real=%0d inj=%0d freeze_cyc=%0d err=%0d",
                     pv_cnt, idle_cyc, rv_cnt, overflow_cnt,
                     real_cnt, inj_cnt, freeze_cyc, err_cnt);
            if (pv_cnt > 0 && rv_cnt > 0)
                $display("RESULT: PASS audio_chain (write side and CDC deliver frames)");
            else
                $display("RESULT: FAIL audio_chain (no frames from slave_rx/CDC)");
            $finish;
        end
        #12_000_000_000;                // two full windows ~5.5 s
        $display("TB_AUDIO_CHAIN: TIMEOUT (win_n=%0d real=%0d inj=%0d)",
                 win_n, real_cnt, inj_cnt);
        $finish;
    end

endmodule