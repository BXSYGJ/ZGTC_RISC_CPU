// ---------------------------------------------------------------------------
// tb_mel_engine_48k.sv -- 48 kHz COO-table swap validation for
// src/mel/mel_engine.v (native-48 kHz front-end, MODEL_TRAINING_SPEC
// appendix B step 1).
//
// Structure is tb_mel_engine.sv (mel_credit configuration: the production
// FILL_CREDIT=1280 source, no override) with exactly two 48 kHz deltas:
//
//   * mel_engine is instantiated with COO_HEX_FILE overridden to
//     build/sim/mel_48k/mel_coo_48k.hex (the 48 kHz filterbank: 65 offset
//     words + 1962 entries, fmax 24000). hann_q15 / log2_lut are sampling
//     rate invariants and stay on the production src/mel/*.hex files
//     (per-table sha256 equality was proven by
//     experiments/mel48k/run_check.py, reports/mel48k_truth_chain_
//     20261104.json).
//   * INV_S_IN / ZP_IN are passed explicitly (bit-identical to the
//     standardize.v defaults) so the mel_engine parameter pass-through
//     is exercised on this configuration too.
//
// The golden tables come from experiments/mel48k/gen_sim_tables_48k.py
// (driven by the sim/run_sim.py "mel_48k" prepare hook): PCM is the
// deterministic 440 Hz sine + seeded white noise mix and golden_feat.hex
// is golden_pipeline.run_mel_pipeline(..., mel_tables_48k.json) feat,
// written TRANSPOSED (frame-major, line index = frame*64 + mel) -- the
// T35 note in tb_mel_engine.sv: golden feat is (mel, frame) while the
// engine export index is frame*64 + mel.
//
// Window geometry is rate-invariant (n_fft 2048 / hop 512 / 259 frames /
// 132096 samples), so the cycle budget is the 44.1 kHz one: ~5.14 M
// cycles measured, MAX_CYC 6.5 M and WATCHDOG_LIMIT 8 M both clear the
// 4.77 M frame budget with margin (the historical too-small watchdog
// bug is not repeated here).
// ---------------------------------------------------------------------------
`timescale 1ns/1ps

module tb_mel_engine_48k;

    localparam integer CLK_HALF   = 5;          // 100 MHz
    localparam integer PCM_N      = 132096;
    localparam integer FEAT_N     = 16512;
    localparam integer MAX_CYC    = 6_500_000;
    // Status expectations (rate-invariant engine behaviour, measured on
    // the 44.1 kHz mel_credit baseline): 259 frames, all 132096 samples
    // accepted, at least 1032 export write commands, no timeout.
    localparam integer EXP_FRAMES = 259;
    localparam integer EXP_PCM    = 132096;
    localparam integer EXP_WRCMD  = 1032;

    reg clk   = 1'b0;
    reg rst_n = 1'b0;
    always #(CLK_HALF) clk = ~clk;

    // -----------------------------------------------------------------
    // DUT (48 kHz COO table + explicit QuantStub pass-through)
    // -----------------------------------------------------------------
    reg         win_tick   = 1'b0;
    reg  [15:0] win_id     = 16'd0;

    wire        m2_cmd_valid;
    wire [36:0] m2_cmd;
    wire [255:0] m2_wdata;
    reg         m2_wready    = 1'b0;
    reg         m2_rd_valid = 1'b0;
    wire        m2_rd_ready;
    reg  [255:0] m2_rd_data  = 256'd0;
    reg         m2_done      = 1'b0;

    wire        npu_start;
    wire        feat_page;
    reg  [14:0] feat_rd_addr = 15'd0;
    wire [7:0]  feat_rd_data;

    wire        mel_done;
    wire [31:0] mel_cycles;
    wire        mel_timeout;
    wire        win_miss;
    wire        busy;

    mel_engine #(
        .HAN_HEX_FILE ("src/mel/hann_q15.hex"),
        .COO_HEX_FILE ("build/sim/mel_48k/mel_coo_48k.hex"),
        .LUT_HEX_FILE ("src/mel/log2_lut.hex"),
        .COO_ROM_WORDS (2027),
        // Native 48 kHz INT8 model QuantStub (deploy/medley_48k):
        // s_in 0.0709686279296875, zp_in 47, inv_s_in 236403274 (Q8.24).
        .INV_S_IN     (32'd236403274),
        .ZP_IN        (8'd47),
        .WATCHDOG_LIMIT (8_000_000)
    ) dut (
        .clk          (clk),
        .rst_n        (rst_n),
        .win_tick     (win_tick),
        .win_id       (win_id),
        .diag_tick    (1'b0),
        .diag_base    (28'd0),
        .m2_cmd_valid (m2_cmd_valid),
        .m2_cmd       (m2_cmd),
        .m2_wdata     (m2_wdata),
        .m2_wready    (m2_wready),
        .m2_rd_valid  (m2_rd_valid),
        .m2_rd_ready  (m2_rd_ready),
        .m2_rd_data   (m2_rd_data),
        .m2_done      (m2_done),
        .npu_start    (npu_start),
        .feat_page    (feat_page),
        .feat_rd_addr (feat_rd_addr),
        .feat_rd_data (feat_rd_data),
        .mel_done     (mel_done),
        .mel_cycles   (mel_cycles),
        .mel_timeout  (mel_timeout),
        .win_miss     (win_miss),
        .busy         (busy)
    );

    // -----------------------------------------------------------------
    // PCM window + golden feature tables (48 kHz set)
    // -----------------------------------------------------------------
    reg [15:0] pcm       [0:PCM_N-1];
    reg [7:0]  gold_feat [0:FEAT_N-1];

    initial begin
        $readmemh("build/sim/mel_48k/pcm.hex", pcm);
        $readmemh("build/sim/mel_48k/golden_feat.hex", gold_feat);
        $display("=== tb_mel_engine_48k start ===");
    end

    // -----------------------------------------------------------------
    // Behavioural PCM / spectrum-export responder (master 2) -- identical
    // contract to tb_mel_engine.sv.
    // -----------------------------------------------------------------
    localparam integer R_IDLE = 0;
    localparam integer R_DLY  = 1;
    localparam integer R_RD   = 2;

    reg [2:0]  rsp_state = R_IDLE;
    reg [36:0] c_cmd     = 37'd0;
    reg [27:0] c_addr    = 28'd0;
    reg [4:0]  beat      = 5'd0;
    integer    dly       = 0;

    // observations
    integer cmd_cnt      = 0;
    integer rd_beats     = 0;
    integer wr_cmds      = 0;
    integer addr_err     = 0;

    reg [255:0] pcm_beat_v;

    function [255:0] pcm_beat;
        input [27:0] addr;
        input [4:0]  idx;
        integer base;
        integer lane;
        begin
            base = addr[27:1] + idx * 16;      // sample index of the beat
            pcm_beat = 256'd0;
            for (lane = 0; lane < 16; lane = lane + 1)
                pcm_beat[lane*16 +: 16] = pcm[(base + lane) % PCM_N];
        end
    endfunction

    always @(posedge clk) begin
        m2_done     <= 1'b0;
        m2_wready   <= 1'b0;
        m2_rd_valid <= 1'b0;      // one beat per handshake, default low

        if (!rst_n) begin
            rsp_state <= R_IDLE;
            beat      <= 5'd0;
            dly       <= 0;
        end else begin
            case (rsp_state)
                R_IDLE: begin
                    if (m2_cmd_valid) begin
                        c_cmd     <= m2_cmd;
                        c_addr    <= m2_cmd[35:8];
                        cmd_cnt   <= cmd_cnt + 1;
                        beat      <= 5'd0;
                        dly       <= 2;
                        rsp_state <= R_DLY;
                        if (!m2_cmd[36]) begin
                            // PCM read: window base is 0x0 or 0x84000
                            if (m2_cmd[35:8] > 28'h0008_4000)
                                addr_err <= addr_err + 1;
                        end else begin
                            wr_cmds <= wr_cmds + 1;
                        end
                    end
                end
                R_DLY: begin
                    if (dly > 0) begin
                        dly <= dly - 1;
                    end else if (c_cmd[36]) begin
                        m2_wready <= 1'b1;         // one beat write command
                        m2_done   <= 1'b1;
                        rsp_state <= R_IDLE;
                    end else begin
                        // Drive beat 0 and hold it (valid + data) until
                        // mel_engine samples it in PC_BEAT.
                        m2_done     <= 1'b1;
                        m2_rd_data  <= pcm_beat(c_addr, 5'd0);
                        m2_rd_valid <= 1'b1;
                        beat        <= 5'd0;
                        rsp_state   <= R_RD;
                    end
                end
                R_RD: begin
                    // One beat per accepted handshake: mel_engine only
                    // asserts m2_rd_ready while in PC_BEAT (one beat per
                    // 16 cycles of PC_FEED), so the beat must be held.
                    m2_rd_valid <= 1'b1;
                    if (m2_rd_ready) begin
                        rd_beats <= rd_beats + 1;
                        if (beat == 5'd15) begin
                            beat      <= 5'd0;
                            rsp_state <= R_IDLE;
                        end else begin
                            beat       <= beat + 5'd1;
                            m2_rd_data <= pcm_beat(c_addr, beat + 5'd1);
                        end
                    end
                end
                default: rsp_state <= R_IDLE;
            endcase
        end
    end

    // -----------------------------------------------------------------
    // Feature read-back + 48 kHz golden compare (frame-major index)
    // -----------------------------------------------------------------
    integer feat_mism = 0;
    integer feat_first = -1;
    reg [7:0] feat_exp = 8'd0;
    reg [7:0] feat_obs = 8'd0;
    integer idx;
    integer frame_i, mel_i;

    task automatic read_features;
        begin
            for (idx = 0; idx < FEAT_N; idx = idx + 1) begin
                feat_rd_addr = idx[14:0];
                @(posedge clk);
                @(posedge clk);
                frame_i = idx / 64;
                mel_i   = idx % 64;
                if (feat_rd_data !== gold_feat[idx]) begin
                    feat_mism = feat_mism + 1;
                    if (feat_first < 0) begin
                        feat_first = idx;
                        feat_exp   = gold_feat[idx];
                        feat_obs   = feat_rd_data;
                    end
                end
            end
        end
    endtask

    // -----------------------------------------------------------------
    // Control / reporting
    // -----------------------------------------------------------------
    integer cycles = 0;
    always @(posedge clk)
        if (rst_n) cycles <= cycles + 1;

    integer status_err = 0;

    initial begin
        rst_n = 1'b0;
        repeat (10) @(posedge clk);
        rst_n = 1'b1;
        repeat (5) @(posedge clk);

        // One window beat.  audio_sink raises win_tick and increments win_id
        // on the SAME edge, so the engine sees tick with the NEXT id: window 0
        // has just completed into half 0, and win_id[0] == 1 selects half 0
        // (mel_engine.v: win_base = win_id[0] ? 0 : PCM_WIN_STRIDE).
        win_id   <= 16'd1;
        win_tick <= 1'b1;
        @(posedge clk);
        win_tick <= 1'b0;

        while (!mel_done && !mel_timeout && cycles < MAX_CYC)
            @(posedge clk);

        $display("MEL48K_STATUS cmds=%0d accepted=%0d frames=%0d wr_cmds=%0d timeout=%0b done=%0b cycles=%0d",
                 cmd_cnt, rd_beats * 16, dut.frm_out, wr_cmds,
                 mel_timeout, mel_done, cycles);
        if (addr_err != 0)
            $display("MEL48K_ADDR_ERR %0d out-of-window PCM commands", addr_err);

        if (mel_timeout || !mel_done) begin
            $display("STATUS_CHECK FAILED engine did not complete (timeout=%0b done=%0b frames=%0d cmds=%0d)",
                     mel_timeout, mel_done, dut.frm_out, cmd_cnt);
            $display("RESULT: FAIL tb_mel_engine_48k (window incomplete)");
            $finish;
        end

        // Status-frame check (rate-invariant engine contract): all 259
        // frames done, the full 132096-sample window accepted, the
        // export walked, the generation tag toggled exactly once.
        if (dut.frm_out != EXP_FRAMES) begin
            $display("STATUS_CHECK FAILED frames=%0d expected %0d",
                     dut.frm_out, EXP_FRAMES);
            status_err = status_err + 1;
        end
        if (rd_beats * 16 != EXP_PCM) begin
            $display("STATUS_CHECK FAILED accepted=%0d expected %0d",
                     rd_beats * 16, EXP_PCM);
            status_err = status_err + 1;
        end
        if (wr_cmds < EXP_WRCMD) begin
            $display("STATUS_CHECK FAILED wr_cmds=%0d expected >= %0d",
                     wr_cmds, EXP_WRCMD);
            status_err = status_err + 1;
        end
        if (feat_page !== 1'b1) begin
            $display("STATUS_CHECK FAILED feat_page=%0b expected 1", feat_page);
            status_err = status_err + 1;
        end
        if (addr_err != 0) begin
            $display("STATUS_CHECK FAILED addr_err=%0d", addr_err);
            status_err = status_err + 1;
        end

        $display("MEL48K_DONE mel_cycles=%0d feat_page=%0b status_err=%0d",
                 mel_cycles, feat_page, status_err);
        read_features();
        $display("FEAT48K_SAMPLES %0d mismatch %0d", FEAT_N, feat_mism);
        if (feat_first >= 0)
            $display("FIRST_MISMATCH feat_idx=%0d frame=%0d mel=%0d expected=%0d observed=%0d",
                     feat_first, feat_first / 64, feat_first % 64, feat_exp, feat_obs);
        else
            $display("FIRST_MISMATCH none");

        if (feat_mism == 0 && status_err == 0) begin
            $display("RESULT: PASS tb_mel_engine_48k");
            $finish;
        end else begin
            if (status_err != 0)
                $display("RESULT: FAIL tb_mel_engine_48k (%0d status errors)",
                         status_err);
            else
                $display("RESULT: FAIL tb_mel_engine_48k (%0d feature bytes differ)",
                         feat_mism);
            $fatal(1, "tb_mel_engine_48k mismatch");
        end
    end

    initial begin : watchdog
        #(MAX_CYC * 10ns);
        $display("ERROR: tb_mel_engine_48k wall-clock watchdog fired (cmds=%0d beats=%0d frames=%0d)",
                 cmd_cnt, rd_beats, dut.frm_out);
        $fatal(1, "tb_mel_engine_48k timeout");
    end

endmodule
