// ---------------------------------------------------------------------------
// tb_integration_lab.sv -- system-level testbench for top_integration_lab.
//
// One clock / reset domain, all three v0 lab modules live together behind
// the flat MMIO-style write decoder.  Physical 115200 serial timing on
// uart_rxd (BIT_CYCLES = 1085 at 125 MHz, same as tb_uart_app_boot).
//
//   S1 load & monitor : 256 B deterministic image + EXEC over real serial
//                       -> ACKs, app_ready, iram_probe equals the first
//                       four instruction words from app_entry (entry 64).
//   S2 scene switch   : scene A (2 TEXT + 1 BAR) via MMIO -> COMMIT ->
//                       full-frame capture with spot pixel checks; scene B
//                       (1 RECT + 2 BAR) written while scanning continues
//                       (4096-pixel sampled write-isolation) -> COMMIT ->
//                       new frame, non-zero diff against scene A.
//   S3 snapshot loop  : fake-NPU LCG model replayed bit-exactly in the TB;
//                       automatic latch every 4 frames, 16-slot readback,
//                       manual SNAP_CTRL latch, SNAP_META frame/epoch
//                       fields, epoch clear drops snap_valid.
//   S4 bad-frame guard: ABORT, corrupt-CRC chunk -> NAK, retransmit, EXEC
//                       still succeeds; renderer keeps scanning scene B
//                       (4096 px sampled) and the snapshot keeps latching
//                       the frozen vector during the open window.
//
// Emits "SCENE n PASS/FAIL" per scene and a final
// "TB_INTEGRATION_LAB: PASS/FAIL" plus "RESULT: PASS/FAIL" for run_sim.
// ---------------------------------------------------------------------------
`timescale 1ns/1ps

module tb_integration_lab;

    localparam integer BIT_CYCLES   = 1085;
    localparam integer START_MID    = 543;   // (1085+1)/2, uart_rx contract
    localparam integer IMG          = 256;
    localparam integer FRAME_PIXELS = 640 * 360;

    reg clk = 1'b0;
    always #4 clk = ~clk;                    // 125 MHz

    reg  rst_n = 1'b0;
    reg  rxd   = 1'b1;
    wire txd;

    reg  [31:0] mmio_addr  = 32'd0;
    reg  [31:0] mmio_wdata = 32'd0;
    reg         mmio_wen   = 1'b0;

    wire [23:0]  rgb;
    wire         de, hs, vs;
    wire         app_ready;
    wire [31:0]  app_entry;
    wire [15:0]  app_bytes;
    wire [127:0] iram_probe;
    wire         iram_probe_valid;
    wire [31:0]  snap_idx_q;
    wire [31:0]  snap_meta_q;
    wire         snap_valid;
    wire [7:0]   snap_epoch;
    wire [7:0]   probe_frame_id;
    wire         commit_ack;
    wire         active_bank;

    top_integration_lab #(.BAUD_DIV(1085)) dut (
        .clk            (clk),
        .rst_n          (rst_n),
        .uart_rxd       (rxd),
        .uart_txd       (txd),
        .mmio_addr      (mmio_addr),
        .mmio_wdata     (mmio_wdata),
        .mmio_wen       (mmio_wen),
        .rgb            (rgb),
        .de             (de),
        .hs             (hs),
        .vs             (vs),
        .app_ready      (app_ready),
        .app_entry      (app_entry),
        .app_bytes      (app_bytes),
        .iram_probe     (iram_probe),
        .iram_probe_valid(iram_probe_valid),
        .snap_idx_q     (snap_idx_q),
        .snap_meta_q    (snap_meta_q),
        .snap_valid     (snap_valid),
        .snap_epoch     (snap_epoch),
        .probe_frame_id (probe_frame_id),
        .commit_ack     (commit_ack),
        .active_bank    (active_bank)
    );

    // ------------------------------------------------------------------
    // TB frame mirror: counts vsync edges while app_ready, frozen and
    // resumed exactly like the DUT fake-NPU frame counter.
    // ------------------------------------------------------------------
    reg     vs_d_tb       = 1'b0;
    reg     frame_cnt_en  = 1'b0;
    integer tb_frame      = 0;

    always @(posedge clk) begin
        vs_d_tb <= vs;
        if (frame_cnt_en && app_ready && vs && !vs_d_tb)
            tb_frame <= tb_frame + 1;
    end

    // ------------------------------------------------------------------
    // Image / frame buffers
    // ------------------------------------------------------------------
    reg [7:0]  image [0:IMG-1];
    reg [7:0]  send_pay [0:511];
    integer    send_plen;

    reg [23:0] cap_buf     [0:FRAME_PIXELS-1];
    reg [23:0] frame_a_buf [0:FRAME_PIXELS-1];
    reg [23:0] frame_b_buf [0:FRAME_PIXELS-1];
    integer    cap_n;

    integer    errors  = 0;
    integer    checks  = 0;
    integer    scene_errors = 0;
    integer    i, t, mm2, ok2, diff_cnt, slot_bad;
    integer    k_auto, k_man, k_auto2, k_pre, k4f;
    reg  [7:0] epoch_prev;
    reg  [7:0] epoch_exp;

    // ------------------------------------------------------------------
    // CRC-32 (IEEE 802.3 reflected), identical to the loader RTL
    // ------------------------------------------------------------------
    function [31:0] crc32_step;
        input [31:0] crc;
        input [7:0]  b;
        reg [31:0] c;
        integer k;
        begin
            c = crc ^ {24'd0, b};
            for (k = 0; k < 8; k = k + 1) begin
                if (c[0]) c = {1'b0, c[31:1]} ^ 32'hEDB88320;
                else      c = {1'b0, c[31:1]};
            end
            crc32_step = c;
        end
    endfunction

    function [31:0] crc32_img;
        input integer len;
        input integer off;
        reg [31:0] c;
        integer k;
        begin
            c = 32'hFFFFFFFF;
            for (k = 0; k < len; k = k + 1)
                c = crc32_step(c, image[off + k]);
            crc32_img = c ^ 32'hFFFFFFFF;
        end
    endfunction

    // ------------------------------------------------------------------
    // Fake-NPU expectation model (bit-exact mirror of the RTL generator):
    // x = 1664525*x + 1013904223 (mod 2^32), seed 0x5EED0001, one step per
    // frame; slot i of frame k = lcg(k) + i*0x11111111 (mod 2^32).
    // ------------------------------------------------------------------
    function [31:0] lcg_next_f;
        input [31:0] x;
        reg [63:0] p;
        begin
            p = 32'd1664525 * x;
            lcg_next_f = p[31:0] + 32'd1013904223;
        end
    endfunction

    function [31:0] lcg_at;
        input integer k;
        reg [31:0] c;
        integer j;
        begin
            c = 32'h5EED0001;
            for (j = 0; j < k; j = j + 1)
                c = lcg_next_f(c);
            lcg_at = c;
        end
    endfunction

    function [31:0] exp_logit;
        input integer slot;
        input integer k;
        reg [31:0] base;
        begin
            base = lcg_at(k);
            exp_logit = base + slot * 32'h11111111;
        end
    endfunction

    // ------------------------------------------------------------------
    // Serial drivers (physical pin timing, tb_uart_app_boot style)
    // ------------------------------------------------------------------
    task automatic bit_time(input reg level);
        begin
            rxd = level;
            repeat (BIT_CYCLES) @(negedge clk);
        end
    endtask

    task automatic send_byte(input reg [7:0] value);
        integer b;
        begin
            bit_time(1'b0);
            for (b = 0; b < 8; b = b + 1) bit_time(value[b]);
            bit_time(1'b1);
        end
    endtask

    // Sends one frame from send_pay[0..send_plen-1]; when corrupt_off >= 0
    // the wire value of payload byte corrupt_off is flipped but the CRC
    // still covers the original byte (self-inconsistent frame).
    task automatic send_frame(input [7:0] ftype, input [7:0] seq,
                              input integer corrupt_off);
        reg [31:0] c;
        integer k;
        reg [7:0]  b;
        begin
            c = 32'hFFFFFFFF;
            send_byte(8'hA5);
            send_byte(8'h5A);
            send_byte(ftype);            c = crc32_step(c, ftype);
            send_byte(seq);              c = crc32_step(c, seq);
            send_byte(send_plen[7:0]);   c = crc32_step(c, send_plen[7:0]);
            send_byte(send_plen[15:8]);  c = crc32_step(c, send_plen[15:8]);
            for (k = 0; k < send_plen; k = k + 1) begin
                b = send_pay[k];
                c = crc32_step(c, b);
                if (corrupt_off >= 0 && k == corrupt_off) b = b ^ 8'h5A;
                send_byte(b);
            end
            c = c ^ 32'hFFFFFFFF;
            send_byte(c[7:0]);
            send_byte(c[15:8]);
            send_byte(c[23:16]);
            send_byte(c[31:24]);
        end
    endtask

    task automatic send_chunk(input [7:0] seq, input integer off,
                              input integer len, input integer corrupt_off);
        integer k;
        begin
            for (k = 0; k < len; k = k + 1) send_pay[k] = image[off + k];
            send_plen = len;
            send_frame(8'h01, seq, corrupt_off);
        end
    endtask

    task automatic send_exec(input [7:0] seq, input [31:0] entry,
                             input [31:0] total_len, input [31:0] img_crc);
        begin
            send_pay[0]  = entry[7:0];
            send_pay[1]  = entry[15:8];
            send_pay[2]  = entry[23:16];
            send_pay[3]  = entry[31:24];
            send_pay[4]  = total_len[7:0];
            send_pay[5]  = total_len[15:8];
            send_pay[6]  = total_len[23:16];
            send_pay[7]  = total_len[31:24];
            send_pay[8]  = img_crc[7:0];
            send_pay[9]  = img_crc[15:8];
            send_pay[10] = img_crc[23:16];
            send_pay[11] = img_crc[31:24];
            send_plen = 12;
            send_frame(8'h02, seq, -1);
        end
    endtask

    task automatic send_abort(input [7:0] seq);
        begin
            send_plen = 0;
            send_frame(8'h03, seq, -1);
        end
    endtask

    // Serial reply sampler (mid-bit, mirrors uart_rx sampling positions)
    task automatic recv_serial(output reg [7:0] b);
        integer wt;
        integer k;
        begin
            wt = 0;
            while (txd === 1'b1 && wt < 600000) begin
                @(negedge clk);
                wt = wt + 1;
            end
            if (txd !== 1'b0) begin
                errors = errors + 1;
                checks = checks + 1;
                $display("CHECK FAIL: recv_serial timeout (no start bit)");
                b = 8'hFF;
            end else begin
                repeat (START_MID) @(negedge clk);
                for (k = 0; k < 8; k = k + 1) begin
                    repeat (BIT_CYCLES) @(negedge clk);
                    b[k] = txd;
                end
                repeat (BIT_CYCLES) @(negedge clk);
                if (txd !== 1'b1) begin
                    errors = errors + 1;
                    checks = checks + 1;
                    $display("CHECK FAIL: recv_serial framing error");
                end
            end
        end
    endtask

    task automatic expect_ack(input [7:0] seq);
        reg [7:0] b0, b1;
        begin
            recv_serial(b0);
            recv_serial(b1);
            $display("OBS reply: %02x %02x (expect 4b %02x)", b0, b1, seq);
            check("reply ACK 'K'+seq", b0 == 8'h4B && b1 == seq);
        end
    endtask

    task automatic expect_nak(input [7:0] seq, input [7:0] reason);
        reg [7:0] b0, b1, b2;
        begin
            recv_serial(b0);
            recv_serial(b1);
            recv_serial(b2);
            $display("OBS reply: %02x %02x %02x (expect 4e %02x %02x)",
                     b0, b1, b2, seq, reason);
            check("reply NAK 'N'+seq+reason",
                  b0 == 8'h4E && b1 == seq && b2 == reason);
        end
    endtask

    // ------------------------------------------------------------------
    // Checks and scene bookkeeping
    // ------------------------------------------------------------------
    task check(input [511:0] name, input ok);
        begin
            checks = checks + 1;
            if (ok) $display("CHECK PASS: %0s", name);
            else begin
                errors = errors + 1;
                $display("CHECK FAIL: %0s", name);
            end
        end
    endtask

    task scene_begin;
        begin
            scene_errors = errors;
        end
    endtask

    task scene_end(input integer num, input [511:0] name);
        begin
            if (errors == scene_errors)
                $display("SCENE %0d PASS  %0s", num, name);
            else
                $display("SCENE %0d FAIL  %0s (%0d failed checks)", num, name,
                         errors - scene_errors);
        end
    endtask

    // ------------------------------------------------------------------
    // MMIO write: one clock-wide write strobe, then two idle cycles so
    // every registered effect (rd_idx, latch, commit_req) is visible when
    // the task returns.
    // ------------------------------------------------------------------
    task automatic mmio_write(input [31:0] a, input [31:0] d);
        begin
            @(negedge clk);
            mmio_addr  = a;
            mmio_wdata = d;
            mmio_wen   = 1'b1;
            @(negedge clk);
            mmio_wen   = 1'b0;
            repeat (2) @(negedge clk);
        end
    endtask

    // ------------------------------------------------------------------
    // Scene programming through the flat MMIO window
    //   descriptor word  : 0x000 + (slot*8 + word)
    //   glyph byte       : 0x400 + index
    // ------------------------------------------------------------------
    task automatic write_desc(input integer wa, input [31:0] d);
        begin
            mmio_write(wa, d);
        end
    endtask

    task automatic write_glyph(input integer ga, input [7:0] g);
        begin
            mmio_write(32'h400 + ga, {24'd0, g});
        end
    endtask

    // Scene A: slot0 TEXT "UI LAB" (40,40), slot1 TEXT "SCENE" (40,100),
    //          slot2 BAR 50% (40,200) 400x40 colour 0x2090FF.
    task automatic write_scene_a;
        begin
            write_desc(0,  32'h00010001);
            write_desc(1,  (40 * 4096) + 40);
            write_desc(2,  (32 * 4096) + 96);
            write_desc(3,  32'h00FFFFFF);
            write_desc(4,  32'd6);
            write_desc(5,  32'd0);
            write_desc(8,  32'h00010001);
            write_desc(9,  (100 * 4096) + 40);
            write_desc(10, (32 * 4096) + 80);
            write_desc(11, 32'h0030FF30);
            write_desc(12, 32'd5);
            write_desc(13, 32'd16);
            write_desc(16, 32'h00010002);
            write_desc(17, (200 * 4096) + 40);
            write_desc(18, (40 * 4096) + 400);
            write_desc(19, 32'h002090FF);
            write_desc(20, 32'd500);
            // glyph sequence: "UI LAB" at 0, "SCENE" at 16
            write_glyph(0,  8'h55); write_glyph(1,  8'h49);
            write_glyph(2,  8'h20); write_glyph(3,  8'h4C);
            write_glyph(4,  8'h41); write_glyph(5,  8'h42);
            write_glyph(16, 8'h53); write_glyph(17, 8'h43);
            write_glyph(18, 8'h45); write_glyph(19, 8'h4E);
            write_glyph(20, 8'h45);
        end
    endtask

    // Scene B: slot0 RECT (100,100) 200x100 colour 0xFF8000,
    //          slot1 BAR 80% (100,220) 300x30 colour 0x00FF80,
    //          slot2 BAR 30% (100,260) 300x30 colour 0xFF0080.
    task automatic write_scene_b;
        begin
            write_desc(0,  32'h00010003);
            write_desc(1,  (100 * 4096) + 100);
            write_desc(2,  (100 * 4096) + 200);
            write_desc(3,  32'h00FF8000);
            write_desc(8,  32'h00010002);
            write_desc(9,  (220 * 4096) + 100);
            write_desc(10, (30 * 4096) + 300);
            write_desc(11, 32'h0000FF80);
            write_desc(12, 32'd800);
            write_desc(16, 32'h00010002);
            write_desc(17, (260 * 4096) + 100);
            write_desc(18, (30 * 4096) + 300);
            write_desc(19, 32'h00FF0080);
            write_desc(20, 32'd300);
        end
    endtask

    // ------------------------------------------------------------------
    // Frame capture: start at the next vs_out rising edge, then collect
    // exactly FRAME_PIXELS de-qualified pixels in scan order.
    // ------------------------------------------------------------------
    task automatic capture_frame;
        begin
            @(posedge vs);
            cap_n = 0;
            while (cap_n < FRAME_PIXELS) begin
                @(posedge clk);
                #1;
                if (de) begin
                    cap_buf[cap_n] = rgb;
                    cap_n = cap_n + 1;
                end
            end
        end
    endtask

    // Sampled write-isolation probe: from the next vsync edge compare npx
    // de-qualified pixels against a captured reference frame
    // (which = 0 -> frame_a_buf, 1 -> frame_b_buf).
    task automatic probe_frame_ref(input integer which, input integer npx,
                                   output integer mmis);
        integer cnt;
        reg [23:0] got;
        begin
            @(posedge vs);
            cnt = 0;
            mmis = 0;
            while (cnt < npx) begin
                @(posedge clk);
                #1;
                if (de) begin
                    got = rgb;
                    if (which == 0) begin
                        if (got !== frame_a_buf[cnt]) mmis = mmis + 1;
                    end else begin
                        if (got !== frame_b_buf[cnt]) mmis = mmis + 1;
                    end
                    cnt = cnt + 1;
                end
            end
        end
    endtask

    // COMMIT through MMIO 0x100 and bounded wait for commit_ack.
    task automatic commit_and_wait(output integer okk);
        integer wt;
        begin
            mmio_write(32'h00000100, 32'h1);
            wt = 0;
            okk = 1;
            while (commit_ack !== 1'b1 && wt < 400000) begin
                @(posedge clk);
                wt = wt + 1;
            end
            if (commit_ack !== 1'b1) begin
                $display("ERROR: commit_ack timeout (%0d cycles)", wt);
                okk = 0;
            end
        end
    endtask

    // ------------------------------------------------------------------
    // Stimulus
    // ------------------------------------------------------------------
    initial begin
        // deterministic image: 256 B, entry at 64 (4-byte aligned)
        for (i = 0; i < IMG; i = i + 1)
            image[i] = (i * 5 + 11) & 255;

        // ==============================================================
        // S1: physical serial load of a 256 B image + EXEC + monitor
        // ==============================================================
        scene_begin;
        rst_n = 1'b0;
        rxd   = 1'b1;
        repeat (10) @(negedge clk);
        rst_n = 1'b1;
        repeat (5) @(negedge clk);

        check("S1 fake NPU frame counter idle before EXEC", probe_frame_id == 8'd0);

        send_chunk(8'd0, 0, IMG, -1);
        expect_ack(8'd0);
        send_exec(8'd1, 32'd64, 32'd256, crc32_img(IMG, 0));
        expect_ack(8'd1);

        t = 0;
        while (iram_probe_valid !== 1'b1 && t < 2000) begin
            @(negedge clk);
            t = t + 1;
        end
        check("S1 exec monitor completed", iram_probe_valid === 1'b1);
        check("S1 app_ready set after EXEC", app_ready === 1'b1);
        check("S1 app_entry latched to 64", app_entry == 32'd64);
        check("S1 bytes_received == 256", app_bytes == 16'd256);
        check("S1 probe word0 == image[64..67]",
              iram_probe[31:0]   == {image[67], image[66], image[65], image[64]});
        check("S1 probe word1 == image[68..71]",
              iram_probe[63:32]  == {image[71], image[70], image[69], image[68]});
        check("S1 probe word2 == image[72..75]",
              iram_probe[95:64]  == {image[75], image[74], image[73], image[72]});
        check("S1 probe word3 == image[76..79]",
              iram_probe[127:96] == {image[79], image[78], image[77], image[76]});

        // calibrate the TB frame mirror on the next frame boundary
        @(posedge vs);
        #1;
        tb_frame     = probe_frame_id;
        frame_cnt_en = 1'b1;
        check("S1 frame mirror calibrated near zero", probe_frame_id <= 8'd2);
        scene_end(1, "UART load 256B + exec monitor");

        // ==============================================================
        // S2: scene switch through the flat MMIO window
        // ==============================================================
        scene_begin;
        write_scene_a;
        commit_and_wait(ok2);
        check("S2 scene A commit_ack", ok2 == 1);
        capture_frame;
        for (i = 0; i < FRAME_PIXELS; i = i + 1)
            frame_a_buf[i] = cap_buf[i];
        check("S2 A bar fill pixel colour",
              frame_a_buf[220 * 640 + 100] == 24'h2090FF);
        check("S2 A background stays black",
              frame_a_buf[300 * 640 + 500] == 24'h000000);

        // write scene B into the back bank while scene A keeps scanning
        fork
            write_scene_b;
            probe_frame_ref(0, 4096, mm2);
        join
        check("S2 renderer immune to back-bank writes (4096 px sampled)",
              mm2 == 0);

        commit_and_wait(ok2);
        check("S2 scene B commit_ack", ok2 == 1);
        capture_frame;
        for (i = 0; i < FRAME_PIXELS; i = i + 1)
            frame_b_buf[i] = cap_buf[i];
        check("S2 B rect pixel colour",
              frame_b_buf[150 * 640 + 200] == 24'hFF8000);
        check("S2 B bar1 fill pixel colour",
              frame_b_buf[235 * 640 + 150] == 24'h00FF80);

        diff_cnt = 0;
        for (i = 0; i < FRAME_PIXELS; i = i + 1)
            if (frame_a_buf[i] !== frame_b_buf[i]) diff_cnt = diff_cnt + 1;
        $display("OBS frame diff scene A vs scene B: %0d pixels", diff_cnt);
        check("S2 scene A and scene B frames differ", diff_cnt > 0);
        scene_end(2, "scene switch through MMIO");

        // ==============================================================
        // S3: logits snapshot closed loop
        // ==============================================================
        scene_begin;
        epoch_prev = snap_epoch;
        mmio_write(32'h00000204, 32'h00000002);
        check("S3 epoch clear drops snap_valid", snap_valid === 1'b0);
        check("S3 epoch register incremented",
              snap_epoch == epoch_prev + 8'd1);
        epoch_exp = snap_epoch;

        t = 0;
        while (snap_valid !== 1'b1 && t < 1500000) begin
            @(posedge clk);
            t = t + 1;
        end
        check("S3 automatic latch fired (every 4 frames)", snap_valid === 1'b1);
        k_auto = tb_frame;
        check("S3 auto snap frame id == TB frame mirror",
              snap_meta_q[7:0] == k_auto);
        check("S3 auto snap frame id is a multiple of 4", (k_auto % 4) == 0);
        check("S3 meta valid_count == 16", snap_meta_q[31:24] == 8'd16);
        check("S3 meta epoch field kept after clear",
              snap_meta_q[23:16] == epoch_exp);
        check("S3 meta mode field == 0", snap_meta_q[15:8] == 8'd0);

        slot_bad = 0;
        for (i = 0; i < 16; i = i + 1) begin
            mmio_write(32'h00000200, i);
            if (snap_idx_q !== exp_logit(i, k_auto)) begin
                slot_bad = slot_bad + 1;
                $display("OBS auto slot %0d got=%h exp=%h",
                         i, snap_idx_q, exp_logit(i, k_auto));
            end
        end
        check("S3 all 16 slots match the LCG model", slot_bad == 0);

        // manual SNAP_CTRL latch on a non-automatic frame
        @(posedge vs);
        repeat (3) @(posedge clk);
        k_man = tb_frame;
        mmio_write(32'h00000204, 32'h00000001);
        check("S3 manual latch frame id", snap_meta_q[7:0] == k_man);
        mmio_write(32'h00000200, 32'd0);
        check("S3 manual slot0 value", snap_idx_q == exp_logit(0, k_man));
        mmio_write(32'h00000200, 32'd7);
        check("S3 manual slot7 value", snap_idx_q == exp_logit(7, k_man));
        mmio_write(32'h00000200, 32'd15);
        check("S3 manual slot15 value", snap_idx_q == exp_logit(15, k_man));
        check("S3 manual latch epoch field",
              snap_meta_q[23:16] == epoch_exp);

        // the next automatic latch overwrites the manual snapshot
        t = 0;
        while (snap_meta_q[7:0] == k_man && t < 1500000) begin
            @(posedge clk);
            t = t + 1;
        end
        k_auto2 = tb_frame;
        check("S3 second auto latch frame id", snap_meta_q[7:0] == k_auto2);
        check("S3 second auto frame id is a multiple of 4", (k_auto2 % 4) == 0);
        mmio_write(32'h00000200, 32'd3);
        check("S3 second auto slot3 value",
              snap_idx_q == exp_logit(3, k_auto2));
        mmio_write(32'h00000200, 32'd11);
        check("S3 second auto slot11 value",
              snap_idx_q == exp_logit(11, k_auto2));
        scene_end(3, "logits snapshot closed loop");

        // ==============================================================
        // S4: bad-frame injection with module isolation
        // ==============================================================
        scene_begin;
        @(posedge vs);
        repeat (3) @(posedge clk);
        k_pre = tb_frame;
        mmio_write(32'h00000204, 32'h00000001);
        check("S4 snapshot latches before teardown", snap_valid === 1'b1);
        mmio_write(32'h00000200, 32'd7);
        check("S4 pre-abort slot7 value", snap_idx_q == exp_logit(7, k_pre));

        send_abort(8'd2);
        expect_ack(8'd2);
        check("S4 abort dropped app_ready", app_ready === 1'b0);
        k4f = tb_frame;
        mmio_write(32'h00000204, 32'h00000001);
        check("S4 snapshot latches during the open window",
              snap_valid === 1'b1);
        mmio_write(32'h00000200, 32'd0);
        check("S4 frozen slot0 value", snap_idx_q == exp_logit(0, k4f));

        // corrupt-CRC chunk -> NAK, retransmit, EXEC, all while the
        // renderer keeps scanning scene B
        fork
            probe_frame_ref(1, 4096, mm2);
            begin
                send_chunk(8'd0, 0, IMG, 17);
                expect_nak(8'd0, 8'd1);
                send_chunk(8'd0, 0, IMG, -1);
                expect_ack(8'd0);
                send_exec(8'd1, 32'd64, 32'd256, crc32_img(IMG, 0));
                expect_ack(8'd1);
            end
        join
        check("S4 renderer stable during error injection (4096 px sampled)",
              mm2 == 0);
        check("S4 EXEC succeeds after recovery", app_ready === 1'b1);
        t = 0;
        while (tb_frame <= k4f && t < 1500000) begin
            @(posedge clk);
            t = t + 1;
        end
        check("S4 frame counter resumed", tb_frame > k4f);
        scene_end(4, "bad-CRC injection + recovery, modules isolated");

        // ==============================================================
        // Summary
        // ==============================================================
        if (errors == 0) begin
            $display("TB_INTEGRATION_LAB: PASS (%0d checks)", checks);
            $display("RESULT: PASS tb_integration_lab");
            $finish;
        end else begin
            $display("TB_INTEGRATION_LAB: FAIL (%0d failed / %0d checks)",
                     errors, checks);
            $display("RESULT: FAIL tb_integration_lab");
            $fatal(1, "tb_integration_lab failed");
        end
    end

    initial begin : watchdog
        #(3s);
        $display("ERROR: tb_integration_lab watchdog (state=%0d app_ready=%0b snap_valid=%0b)",
                 dut.status_state_w, app_ready, snap_valid);
        $fatal(1, "tb_integration_lab timeout");
    end

endmodule
