// ---------------------------------------------------------------------------
// tb_i2s_capture.sv -- full-chain testbench for src/diag/top_i2s_capture.v
//
// Simulates the complete board data path (simulation):
//   PCM1808-master I2S source (BCK 3.072 MHz / LRCK 48 kHz / Philips 1-bit
//   delay, driven on physical pin timing) -> top_i2s_capture (i2s_slave_rx
//   @27 MHz -> Gray CDC FIFO -> i2s_capture_ctrl -> ddr3_ctrl_axi ->
//   behavioral ddr3_wrapper [ddr3_axi_model]) -> UART 115200-style frames
//   sampled back at mid-bit.
//
// The behavioral ddr3_wrapper (defined at the bottom of this file, resolved
// from here because the RTL instantiates it by name) generates core_clk
// 125 MHz, releases core_clk_rst_n, then raises pll_lock / ddrphy_cpd_lock
// / ddr_init_done after a fixed latency, and wires the AXI user side into
// sim/ddr3_axi_model.sv (the shared behavioral DDR3 IP model, resolved via
// "-y sim", same as the ddr3_subsys case).
//
// UART is time-scaled: BAUD_DIV=43 instead of 1085 (25x faster bits,
// identical protocol engine uart_tx/uart_rx), so the export phase fits in
// seconds of wall time. Bit timing is driven with absolute delays.
//
// Deterministic stereo source (audio thread, frame index n):
//   round 1: n <  64 walking  L = n,            R = n ^ 0x8000
//            n < 192 sine     L = 12000*sin,    R = 6000*sin (64-pt table)
//            else    LCG      L, R              (fixed seed)
//   round 2 (S4 re-capture): L = n ^ 0x5A5A,    R = n ^ 0xA5A5
//
// Sample alignment: the audio thread parks on a frame boundary (src_pause
// handshake) while 'C' travels, so word 0 of every capture is exactly the
// next frame the source emits (the S_CLR drain window drops all earlier
// FIFO content deterministically).
//
// Scenes:
//   S0 boot      : "I2SCAP BOOT" and "I2SCAP DDR OK" on the UART stream.
//   S1 full chain: 'C' -> CAPDONE 00000008 -> 'R' 0..7, every frame CRC
//                  checked and all 512 words compared (0 mismatches).
//   S2 bad seq   : 'R' seq=8 (= frame_cnt) and seq=0xFFFF -> 'N'.
//   S3 status    : CAPSTS lines in idle and done states (words / frames /
//                  i2s_err fields exact).
//   S4 duplicate 'C' during capture is ignored: re-capture, a second 'C'
//                  fired mid-capture, frame count stays 8 and frames 0/7
//                  still match the round-2 pattern.
// ---------------------------------------------------------------------------

`timescale 1ns / 1ps

module tb_i2s_capture;

    // ------------------------------------------------------------------
    // Scaled protocol timing (BAUD_DIV=43 -> one bit = 43 * 8 ns)
    // ------------------------------------------------------------------
    localparam integer BIT_NS   = 344;
    localparam integer CAP_WORDS = 512;          // 256 stereo frames
    localparam integer CAP_FRAMES = CAP_WORDS / 64;  // 8 DDR3 frames
    localparam integer DDR_INIT_DELAY = 200;     // core cycles

    // ------------------------------------------------------------------
    // Board-level pins
    // ------------------------------------------------------------------
    reg  clk27 = 1'b0;
    reg  rst_n = 1'b0;
    reg  rxd   = 1'b1;
    wire txd;
    reg  bck   = 1'b0;
    reg  lrck  = 1'b0;
    reg  sd    = 1'b1;
    wire [7:0] led;

    always #18.5185 clk27 = ~clk27;    // 27 MHz audio domain
    always #162.76   bck   = ~bck;     // 3.072 MHz I2S bit clock (half period)

    // DDR3 pins left floating (the behavioral wrapper owns the memory)
    wire        mem_cs_n, mem_rst_n, mem_ck, mem_ck_n, mem_cke;
    wire        mem_ras_n, mem_cas_n, mem_we_n, mem_odt;
    wire [14:0] mem_a;
    wire [2:0]  mem_ba;
    wire [3:0]  mem_dm;
    wire [3:0]  mem_dqs, mem_dqs_n;
    wire [31:0] mem_dq;

    top_i2s_capture #(
        .CAP_WORDS         (CAP_WORDS),
        .BAUD_DIV          (43),
        .ACK_TIMEOUT_CYCLES(32'd50000),
        .DDR_TIMEOUT_CYCLES(32'd1000000)
    ) dut (
        .clk     (clk27),
        .rst_n   (rst_n),
        .led     (led),
        .uart_rx (rxd),
        .uart_tx (txd),
        .i2s_bck (bck),
        .i2s_lrck(lrck),
        .i2s_sd  (sd),
        .ref_clk_p(1'b1),
        .ref_clk_n(1'b0),
        .mem_cs_n (mem_cs_n), .mem_rst_n(mem_rst_n), .mem_ck(mem_ck),
        .mem_ck_n (mem_ck_n), .mem_cke(mem_cke), .mem_ras_n(mem_ras_n),
        .mem_cas_n(mem_cas_n), .mem_we_n(mem_we_n), .mem_odt(mem_odt),
        .mem_a(mem_a), .mem_ba(mem_ba), .mem_dm(mem_dm),
        .mem_dqs(mem_dqs), .mem_dqs_n(mem_dqs_n), .mem_dq(mem_dq)
    );

    // ------------------------------------------------------------------
    // Bookkeeping
    // ------------------------------------------------------------------
    integer errors   = 0;
    integer checks   = 0;
    integer mismatch = 0;

    reg [31:0] exp_word [0:2047];
    integer    cap_base = 0;   // source sample index at capture start
    reg [15:0] sin_tab  [0:63];
    reg [7:0]  pay      [0:255];
    reg [7:0]  line_b   [0:95];
    integer    line_len;
    reg [7:0]  exp_line [0:95];
    integer    exp_len;

    integer frame_no = 0;
    integer round_no = 0;
    reg      src_pause = 0;
    reg      src_stop  = 0;
    reg      a_held    = 0;
    integer  lcg        = 32'h12345678;

    function [15:0] hex_hi(input [31:0] v, input integer pos);
        begin
            hex_hi = v >> (pos * 4);
            hex_hi = hex_hi & 16'h000F;
        end
    endfunction

    function [7:0] hex_ch(input [3:0] n);
        begin
            hex_ch = (n < 4'd10) ? (8'h30 + {4'd0, n}) : (8'h37 + {4'd0, n});
        end
    endfunction

    function [15:0] crc16_step(input [15:0] crc, input [7:0] b);
        reg [15:0] c;
        integer i;
        begin
            c = crc ^ {b, 8'h00};
            for (i = 0; i < 8; i = i + 1) begin
                if (c[15]) c = (c << 1) ^ 16'h1021;
                else       c = c << 1;
            end
            crc16_step = c;
        end
    endfunction

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

    // ------------------------------------------------------------------
    // UART physical drivers (tb_uart_app_boot style: bit slots counted on
    // negedge dut.core_clk, so the TB never samples on the same edge that
    // updates uart_tx / evaluates uart_rx).
    // ------------------------------------------------------------------
    task bit_cycles(input level);
        begin
            rxd = level;
            repeat (43) @(negedge dut.core_clk);
        end
    endtask

    task send_byte(input [7:0] v);
        integer b;
        begin
            bit_cycles(1'b0);
            for (b = 0; b < 8; b = b + 1) bit_cycles(v[b]);
            bit_cycles(1'b1);
        end
    endtask

    task recv_serial(output reg [7:0] b);
        integer k;
        begin
            @(negedge txd);
            repeat (22) @(negedge dut.core_clk);   // start-bit center
            for (k = 0; k < 8; k = k + 1) begin
                repeat (43) @(negedge dut.core_clk);
                b[k] = txd;
            end
            repeat (43) @(negedge dut.core_clk);   // stop-bit center
            if (txd !== 1'b1) begin
                errors = errors + 1;
                $display("CHECK FAIL: recv_serial framing error");
            end
        end
    endtask

    // ------------------------------------------------------------------
    // Background receive pump: a real PC UART is full-duplex, so the reply
    // to a single-byte command ('S', 'R'+seq) may start while the TB is
    // still shifting out its own stop bit (uart_rx judges the byte at the
    // 9.5-bit midpoint). A dedicated thread therefore listens on txd for
    // the whole simulation and queues every received byte; the command
    // thread consumes the queue in order.
    // ------------------------------------------------------------------
    reg [7:0] rxq [0:4095];
    integer   rq_wr = 0;
    integer   rq_rd = 0;
    reg [7:0] pump_b;

    initial begin : rx_pump
        forever begin
            recv_serial(pump_b);
            $display("RXQ %02x @%0t", pump_b, $time);
            rxq[rq_wr] = pump_b;
            rq_wr = rq_wr + 1;
        end
    end

    task get_byte(output reg [7:0] b);
        begin
            while (rq_rd == rq_wr)
                @(negedge dut.core_clk);
            b = rxq[rq_rd];
            rq_rd = rq_rd + 1;
        end
    endtask

    task recv_line;
        reg [7:0] b;
        integer i;
        begin
            line_len = 0;
            for (i = 0; i < 96; i = i + 1) begin
                get_byte(b);
                line_b[line_len] = b;
                line_len = line_len + 1;
                if (b == 8'h0A) i = 96;
            end
        end
    endtask

    task line_is(input [511:0] name);
        integer i;
        reg ok;
        begin
            ok = (line_len == exp_len);
            for (i = 0; (i < line_len) && (i < exp_len); i = i + 1)
                if (line_b[i] !== exp_line[i]) ok = 0;
            check(name, ok);
            if (!ok) begin
                $write("GOT : ");
                for (i = 0; i < line_len; i = i + 1) $write("%c", line_b[i] + 0);
                $write("\nEXP : ");
                for (i = 0; i < exp_len; i = i + 1) $write("%c", exp_line[i] + 0);
                $write("\n");
            end
        end
    endtask

    // Build the expected CAPSTS line (mirrors i2s_capture_ctrl S_STSFILL).
    task mksts(input integer st, input [31:0] words, input [31:0] frames,
                input [31:0] errs);
        integer i;
        begin
            exp_line[0]=8'h43; exp_line[1]=8'h41; exp_line[2]=8'h50;
            exp_line[3]=8'h53; exp_line[4]=8'h54; exp_line[5]=8'h53;
            exp_line[6]=8'h20; exp_line[7]=8'h73; exp_line[8]=8'h74;
            exp_line[9]=8'h61; exp_line[10]=8'h74; exp_line[11]=8'h65;
            exp_line[12]=8'h3D;
            if (st == 0) begin
                exp_line[13]=8'h69; exp_line[14]=8'h64; exp_line[15]=8'h6C;
                exp_line[16]=8'h65; exp_line[17]=8'h20; exp_line[18]=8'h20;
                exp_line[19]=8'h20; exp_line[20]=8'h20; exp_line[21]=8'h20;
            end else if (st == 1) begin
                exp_line[13]=8'h63; exp_line[14]=8'h61; exp_line[15]=8'h70;
                exp_line[16]=8'h74; exp_line[17]=8'h75; exp_line[18]=8'h72;
                exp_line[19]=8'h69; exp_line[20]=8'h6E; exp_line[21]=8'h67;
            end else begin
                exp_line[13]=8'h64; exp_line[14]=8'h6F; exp_line[15]=8'h6E;
                exp_line[16]=8'h65; exp_line[17]=8'h20; exp_line[18]=8'h20;
                exp_line[19]=8'h20; exp_line[20]=8'h20; exp_line[21]=8'h20;
            end
            exp_line[22]=8'h20; exp_line[23]=8'h77; exp_line[24]=8'h6F;
            exp_line[25]=8'h72; exp_line[26]=8'h64; exp_line[27]=8'h73;
            exp_line[28]=8'h3D;
            for (i = 0; i < 8; i = i + 1)
                exp_line[29+i] = hex_ch(hex_hi(words, 7-i));
            exp_line[37]=8'h20; exp_line[38]=8'h66; exp_line[39]=8'h72;
            exp_line[40]=8'h61; exp_line[41]=8'h6D; exp_line[42]=8'h65;
            exp_line[43]=8'h73; exp_line[44]=8'h3D;
            for (i = 0; i < 8; i = i + 1)
                exp_line[45+i] = hex_ch(hex_hi(frames, 7-i));
            exp_line[53]=8'h20; exp_line[54]=8'h69; exp_line[55]=8'h32;
            exp_line[56]=8'h73; exp_line[57]=8'h5F; exp_line[58]=8'h65;
            exp_line[59]=8'h72; exp_line[60]=8'h72; exp_line[61]=8'h3D;
            for (i = 0; i < 8; i = i + 1)
                exp_line[62+i] = hex_ch(hex_hi(errs, 7-i));
            exp_line[70]=8'h0A;
            exp_len = 71;
        end
    endtask

    task mkcapdone(input [31:0] frames);
        integer i;
        begin
            exp_line[0]=8'h43; exp_line[1]=8'h41; exp_line[2]=8'h50;
            exp_line[3]=8'h44; exp_line[4]=8'h4F; exp_line[5]=8'h4E;
            exp_line[6]=8'h45; exp_line[7]=8'h20;
            for (i = 0; i < 8; i = i + 1)
                exp_line[8+i] = hex_ch(hex_hi(frames, 7-i));
            exp_line[16]=8'h0A;
            exp_len = 17;
        end
    endtask

    task mkplain(input integer len);
        // exp_line[0..len-1] must be preloaded by the caller.
        begin
            exp_len = len;
        end
    endtask

    // ------------------------------------------------------------------
    // PCM1808-master I2S source (Philips 1-bit delay, 16 significant bits)
    // ------------------------------------------------------------------
    task i2s_send_slot(input lrck_level, input [15:0] s);
        integer b;
        begin
            @(negedge bck);
            lrck = lrck_level;
            sd   = 1'b1;                 // delay bit after the LRCK edge
            for (b = 15; b >= 0; b = b - 1) begin
                @(negedge bck);
                sd = s[b];
            end
            sd = 1'b1;                   // pad to the 32-bit slot
            repeat (15) @(negedge bck);
        end
    endtask

    task i2s_send_frame(input [15:0] l, input [15:0] r);
        begin
            i2s_send_slot(1'b0, l);
            i2s_send_slot(1'b1, r);
        end
    endtask

    // Audio source thread: runs for the whole simulation, parks on frame
    // boundaries while src_pause is set (short enough that the i2s_slave_rx
    // watchdog, 1 ms at 27 MHz, never fires).
    initial begin : audio_thread
        integer n;
        reg [15:0] l, r;
        begin
            forever begin
                while (src_pause) begin
                    a_held = 1'b1;
                    @(negedge bck);
                end
                a_held = 1'b0;
                if (src_stop) disable audio_thread;
                n = frame_no;
                if (round_no == 0) begin
                    if (n < 64) begin
                        l = n[15:0];
                        r = n[15:0] ^ 16'h8000;
                    end else if (n < 192) begin
                        l = sin_tab[(n - 64) % 64];
                        r = {1'b0, sin_tab[(n - 64) % 64][15:1]};
                    end else begin
                        lcg = (lcg * 1103515245 + 12345) & 32'h7FFFFFFF;
                        l = lcg[15:0];
                        lcg = (lcg * 1103515245 + 12345) & 32'h7FFFFFFF;
                        r = lcg[15:0];
                    end
                end else begin
                    l = n[15:0] ^ 16'h5A5A;
                    r = n[15:0] ^ 16'hA5A5;
                end
                exp_word[frame_no] = {r, l};
                i2s_send_frame(l, r);
                frame_no = frame_no + 1;
            end
        end
    end

    // ------------------------------------------------------------------
    // Frame receiver: parses and verifies one exported 256 B frame,
    // compares every word, returns the byte-level verdicts.
    // ------------------------------------------------------------------
    task recv_frame(input integer f);
        reg [7:0] b;
        reg [15:0] crc;
        integer i, w;
        reg [31:0] word;
        begin
            get_byte(b);
            check("frame SOF0 0xAA", b == 8'hAA);
            get_byte(b);
            check("frame SOF1 0x55", b == 8'h55);
            get_byte(b);
            check("frame seq lo", b == (f & 16'h00FF));
            get_byte(b);
            check("frame seq hi", b == 8'h00);
            get_byte(b);
            check("frame len lo", b == 8'h00);
            get_byte(b);
            check("frame len hi", b == 8'h01);
            crc = 16'hFFFF;
            crc = crc16_step(crc, (f & 16'h00FF));
            crc = crc16_step(crc, 8'h00);
            crc = crc16_step(crc, 8'h00);
            crc = crc16_step(crc, 8'h01);
            for (i = 0; i < 256; i = i + 1) begin
                get_byte(b);
                pay[i] = b;
                crc = crc16_step(crc, b);
            end
            get_byte(b);
            if ({b, 8'h00} != {crc[7:0], 8'h00}) begin
                errors = errors + 1;
                $display("CHECK FAIL: frame %0d crc lo got %02x exp %02x",
                         f, b, crc[7:0]);
            end
            get_byte(b);
            if (b != crc[15:8]) begin
                errors = errors + 1;
                $display("CHECK FAIL: frame %0d crc hi got %02x exp %02x",
                         f, b, crc[15:8]);
            end
            for (w = 0; w < 64; w = w + 1) begin
                word = {pay[4*w+3], pay[4*w+2], pay[4*w+1], pay[4*w]};
                if (word !== exp_word[cap_base + f*64 + w]) begin
                    mismatch = mismatch + 1;
                    if (mismatch <= 8)
                        $display("MISMATCH frame %0d word %0d got %08x exp %08x",
                                 f, w, word, exp_word[cap_base + f*64 + w]);
                end
            end
        end
    endtask

    // ------------------------------------------------------------------
    // Start-of-capture alignment: park the source on a frame boundary,
    // send 'C', let the S_CLR drain window pass, resume the source.
    // ------------------------------------------------------------------
    task start_capture;
        begin
            src_pause = 1'b1;
            wait (a_held === 1'b1);
            repeat (4) @(negedge bck);      // settle at the boundary
            cap_base = frame_no;            // first sample after resume
            send_byte(8'h43);               // 'C'
            repeat (64) @(posedge clk27);   // S_CLR = 32 core cycles
            src_pause = 1'b0;
        end
    endtask

    // ------------------------------------------------------------------
    // Command thread: the four scenarios.
    // ------------------------------------------------------------------
    integer f;
    reg [7:0] b;

    initial begin : cmd_thread
        // sine table (64 points, amplitude 12000)
        for (f = 0; f < 64; f = f + 1)
            sin_tab[f] = $rtoi(12000.0 * $sin(6.283185307179586 * f / 64.0));

        // ---- reset --------------------------------------------------
        rst_n = 1'b0;
        repeat (20) @(negedge clk27);
        rst_n = 1'b1;

        // ---- S0: boot banner ----------------------------------------
        exp_line[0]=8'h49; exp_line[1]=8'h32; exp_line[2]=8'h53;
        exp_line[3]=8'h43; exp_line[4]=8'h41; exp_line[5]=8'h50;
        exp_line[6]=8'h20; exp_line[7]=8'h42; exp_line[8]=8'h4F;
        exp_line[9]=8'h4F; exp_line[10]=8'h54; exp_line[11]=8'h0A;
        mkplain(12);
        recv_line;
        line_is("S0 I2SCAP BOOT");

        exp_line[0]=8'h49; exp_line[1]=8'h32; exp_line[2]=8'h53;
        exp_line[3]=8'h43; exp_line[4]=8'h41; exp_line[5]=8'h50;
        exp_line[6]=8'h20; exp_line[7]=8'h44; exp_line[8]=8'h44;
        exp_line[9]=8'h52; exp_line[10]=8'h20; exp_line[11]=8'h4F;
        exp_line[12]=8'h4B; exp_line[13]=8'h0A;
        mkplain(14);
        recv_line;
        line_is("S0 I2SCAP DDR OK");

        // ---- S3a: idle status ---------------------------------------
        send_byte(8'h53);                   // 'S'
        mksts(0, 32'd0, 32'd0, 32'd0);
        recv_line;
        line_is("S3 idle CAPSTS");

        // ---- S1: full-chain capture + export ------------------------
        start_capture;
        mkcapdone(32'd8);
        recv_line;
        line_is("S1 CAPDONE frames=8");

        // ---- S3b: done status ---------------------------------------
        send_byte(8'h53);
        mksts(2, 32'd512, 32'd8, 32'd0);
        recv_line;
        line_is("S3 done CAPSTS");

        // ---- S2: out-of-range seq -> 'N' ----------------------------
        send_byte(8'h52); send_byte(8'h08); send_byte(8'h00);
        get_byte(b);
        check("S2 seq=8 answers 'N'", b == 8'h4E);
        send_byte(8'h52); send_byte(8'hFF); send_byte(8'hFF);
        get_byte(b);
        check("S2 seq=0xFFFF answers 'N'", b == 8'h4E);

        // ---- S1: export all 8 frames, compare every word -----------
        for (f = 0; f < 8; f = f + 1) begin
            send_byte(8'h52);
            send_byte(f & 8'hFF);
            send_byte(8'h00);
            recv_frame(f);
            send_byte(8'h4B);               // 'K'
        end
        $display("S1 export complete: %0d word mismatches over %0d words",
                 mismatch, CAP_WORDS);

        // ---- S4: re-capture with a duplicate 'C' mid-flight --------
        round_no = 1;
        frame_no = 0;
        start_capture;
        #(1_250_000);                       // ~60 frames into the capture
        send_byte(8'h43);                   // duplicate 'C': must be ignored
        mkcapdone(32'd8);
        recv_line;
        line_is("S4 CAPDONE still frames=8");

        for (f = 0; f < 8; f = f + 1) begin
            send_byte(8'h52);
            send_byte(f & 8'hFF);
            send_byte(8'h00);
            if ((f == 0) || (f == 7)) begin
                recv_frame(f);              // full compare on 0 and 7
            end else begin
                recv_frame(f);              // all frames re-verified
            end
            send_byte(8'h4B);
        end

        // ---- summary -------------------------------------------------
        if ((errors == 0) && (mismatch == 0)) begin
            $display("RESULT: PASS i2s_capture: S0 boot, S1 %0d-word round trip 0 mismatch, S2 bad-seq N, S3 idle+done CAPSTS, S4 duplicate-C ignored",
                     2 * CAP_WORDS);
        end else begin
            $display("RESULT: FAIL i2s_capture: %0d failed checks, %0d word mismatches",
                     errors, mismatch);
        end
        src_stop = 1'b1;
        #1000;
        $finish;
    end

    // Global watchdog (simulation time; the whole run is ~20 ms).
    initial begin
        #60_000_000;
        $display("RESULT: FAIL i2s_capture: global timeout");
        $finish;
    end

endmodule

// ---------------------------------------------------------------------------
// Behavioral replacement of the DDR3 hard-IP shell. The RTL instantiates
// ddr3_wrapper by name, so defining it here lets the whole top compile in
// simulation. It owns: 125 MHz core_clk generation, reset release, the
// staged pll_lock / ddrphy_cpd_lock / ddr_init_done handshake (INIT_DELAY
// core cycles after reset release), and the user-side AXI contract through
// sim/ddr3_axi_model.sv (resolved via "-y sim").
// ---------------------------------------------------------------------------
module ddr3_wrapper (
    input  wire        ref_clk_p,
    input  wire        ref_clk_n,
    input  wire        resetn,
    output wire        core_clk,
    output reg         core_clk_rst_n,
    output reg         ddr_init_done,
    output reg         pll_lock,
    output reg         ddrphy_cpd_lock,
    input  wire [27:0] axi_awaddr,
    input  wire        axi_awuser_ap,
    input  wire [3:0]  axi_awuser_id,
    input  wire [3:0]  axi_awlen,
    input  wire        axi_awvalid,
    output wire        axi_awready,
    input  wire [255:0] axi_wdata,
    input  wire [31:0] axi_wstrb,
    output wire        axi_wready,
    output wire [3:0]  axi_wusero_id,
    output wire        axi_wusero_last,
    input  wire [27:0] axi_araddr,
    input  wire        axi_aruser_ap,
    input  wire [3:0]  axi_aruser_id,
    input  wire [3:0]  axi_arlen,
    input  wire        axi_arvalid,
    output wire        axi_arready,
    output wire [255:0] axi_rdata,
    output wire [3:0]  axi_rid,
    output wire        axi_rlast,
    output wire        axi_rvalid,
    output wire        mem_cs_n,
    output wire        mem_rst_n,
    output wire        mem_ck,
    output wire        mem_ck_n,
    output wire        mem_cke,
    output wire        mem_ras_n,
    output wire        mem_cas_n,
    output wire        mem_we_n,
    output wire        mem_odt,
    output wire [14:0] mem_a,
    output wire [2:0]  mem_ba,
    output wire [3:0]  mem_dm,
    inout  wire [3:0]  mem_dqs,
    inout  wire [3:0]  mem_dqs_n,
    inout  wire [31:0] mem_dq
);
    localparam integer INIT_DELAY = 200;

    reg core_clk_r = 1'b0;
    always #4 core_clk_r = ~core_clk_r;    // 125 MHz
    assign core_clk = core_clk_r;

    reg [31:0] ready_cnt;

    always @(posedge core_clk_r or negedge resetn) begin
        if (!resetn) begin
            core_clk_rst_n <= 1'b0;
            ready_cnt      <= 32'd0;
            pll_lock       <= 1'b0;
            ddrphy_cpd_lock<= 1'b0;
            ddr_init_done  <= 1'b0;
        end else begin
            if (core_clk_rst_n && (ready_cnt < INIT_DELAY))
                ready_cnt <= ready_cnt + 32'd1;
            core_clk_rst_n <= 1'b1;
            pll_lock        <= (ready_cnt > 5);
            ddrphy_cpd_lock <= (ready_cnt > 10);
            ddr_init_done   <= (ready_cnt >= INIT_DELAY - 1);
        end
    end

    ddr3_axi_model u_model (
        .clk          (core_clk_r),
        .rst_n        (core_clk_rst_n),
        .s_awaddr     (axi_awaddr),
        .s_awvalid    (axi_awvalid),
        .s_awlen      (axi_awlen),
        .s_awuser_id  (axi_awuser_id),
        .s_awready    (axi_awready),
        .s_wdata      (axi_wdata),
        .s_wstrb      (axi_wstrb),
        .s_wready     (axi_wready),
        .s_wusero_last(axi_wusero_last),
        .s_araddr     (axi_araddr),
        .s_arvalid    (axi_arvalid),
        .s_arlen      (axi_arlen),
        .s_aruser_id  (axi_aruser_id),
        .s_arready    (axi_arready),
        .s_rdata      (axi_rdata),
        .s_rid        (axi_rid),
        .s_rlast      (axi_rlast),
        .s_rvalid     (axi_rvalid),
        .obs_aw_hs    (),
        .obs_ar_hs    (),
        .obs_wr_beats (),
        .obs_rd_beats (),
        .obs_len0_wr  (),
        .obs_len0_wstrb0(),
        .obs_len0_wstrb1(),
        .obs_last_marker()
    );

    // Physical DDR3 pins are unused in simulation.
    assign mem_cs_n  = 1'b1;
    assign mem_rst_n = 1'b1;
    assign mem_ck    = 1'b0;
    assign mem_ck_n  = 1'b1;
    assign mem_cke   = 1'b1;
    assign mem_ras_n = 1'b1;
    assign mem_cas_n = 1'b1;
    assign mem_we_n  = 1'b1;
    assign mem_odt   = 1'b0;
    assign mem_a     = 15'd0;
    assign mem_ba    = 3'd0;
    assign mem_dm    = 4'd0;



// ---------------------------------------------------------------------------
// Temporary handshake probe (removed once the DDR3 path is proven).
// Sampled on the falling edge so combinational handshakes are stable.
// ---------------------------------------------------------------------------
`ifdef I2SCAP_PROBE
initial begin : dbg_probe
    integer cmd_n, done_n, wb_n, rv_n, dbg_smp_n, dbg_pv_n, dbg_rf_n;
    integer dbg_rb_n, dbg_rb_last;
    cmd_n = 0; done_n = 0; wb_n = 0; rv_n = 0; dbg_smp_n = 0; dbg_pv_n = 0; dbg_rf_n = 0;
    dbg_rb_n = 0; dbg_rb_last = 0;
    forever begin
        @(negedge dut.clk);
        if (dut.cap_m0_cmd_valid && cmd_n < 6) begin
            cmd_n = cmd_n + 1;
            $display("DBGCMD n=%0d t=%0t cmd=%h awvalid=%b awready=%b awaddr=%h awuser=%h cur_master=%b awlen=%h wready=%b",
                     cmd_n, $time, dut.cap_m0_cmd, dut.axi_awvalid_a,
                     dut.ddr3_wrapper.axi_awready, dut.axi_awaddr_a, dut.axi_awuser_id_a,
                     dut.u_ctrl_design.cur_master, dut.u_ctrl_design.axi_awlen,
                     dut.ddr3_wrapper.axi_wready);
        end

        if (dut.smp_valid && dbg_smp_n < 8) begin
            dbg_smp_n = dbg_smp_n + 1;
            $display("DBGSMP n=%0d t=%0t data=%h gcnt=%0d", dbg_smp_n, $time,
                     dut.smp_data, dut.cap_word_cnt);
        end
        if (dut.pcm_valid && dbg_pv_n < 8) begin
            dbg_pv_n = dbg_pv_n + 1;
            $display("DBGPV n=%0d t=%0t l=%h r=%h", dbg_pv_n, $time, dut.pcm_l, dut.pcm_r);
        end
        if (dut.cdc_rd_fire && dbg_rf_n < 10) begin
            dbg_rf_n = dbg_rf_n + 1;
            $display("DBGRF n=%0d t=%0t bin=%0d wg=%h mem=%h", dbg_rf_n, $time,
                     dut.cdc_rd_bin, dut.cdc_wr_gray_sync2, dut.cdc_mem[dut.cdc_rd_bin[3:0]]);
        end
        if (dut.ddr3_wrapper.u_model.obs_rd_beats != dbg_rb_last) begin
            dbg_rb_last = dut.ddr3_wrapper.u_model.obs_rd_beats;
            if (dbg_rb_n < 4) begin
                dbg_rb_n = dbg_rb_n + 1;
                $display("DBGRB n=%0d t=%0t beats=%0d", dbg_rb_n, $time, dbg_rb_last);
            end
        end
        if (dut.done_a[0] && done_n < 8) begin
            done_n = done_n + 1;
            $display("DBGDONE n=%0d t=%0t", done_n, $time);
        end
        if (dut.wready_beat_a[0] && wb_n < 10) begin
            wb_n = wb_n + 1;
            $display("DBGWB n=%0d t=%0t wdata=%h", wb_n, $time, dut.cap_m0_wdata);
        end
        if (dut.cap_m0_rd_valid && rv_n < 4) begin
            rv_n = rv_n + 1;
            $display("DBGRV n=%0d t=%0t data0=%h", rv_n, $time, dut.rd_data_0_a);
        end
    end
end
`endif

endmodule

