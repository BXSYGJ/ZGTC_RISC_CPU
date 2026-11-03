// ---------------------------------------------------------------------------
// tb_uart_app_boot.sv -- physical serial testbench for src/boot/uart_app_boot.v
//
// Drives the real uart_rxd pin at 115200 baud / 125 MHz core clock
// (BIT_CYCLES = 1085, same bit timing as tb_uart_rx.sv) and samples the
// DUT reply on uart_txd at mid-bit, so both reused engines uart_rx and
// uart_tx run at their true serial timing.
//
// Scenes (stop-and-wait: one frame, then its reply is collected):
//   S1 normal load   : 3 chunks (512+512+80 = 1104 B, crossing the 512 B
//                      chunk boundary) + good EXEC -> all ACKs, app_ready,
//                      entry latched, IRAM first / boundary / last word.
//   S2 corrupt chunk : one payload byte flipped on the wire -> NAK reason 1,
//                      loader does not advance, retransmission accepted,
//                      final EXEC still passes.
//   S3 seq disorder   : skipped seq -> NAK reason 2, correct seq continues.
//   S4 bad EXEC       : image_crc wrong / total_len over received /
//                      unaligned entry -> NAK 1 / 3 / 4, app_ready stays 0.
//   S5 abort          : partial load, ABORT clears the session, a full
//                      reload from seq 0 succeeds.
//   S6 over capacity  : EXEC total_len = 5000 > 4096 -> NAK reason 3.
// ---------------------------------------------------------------------------
`timescale 1ns/1ps

module tb_uart_app_boot;

    localparam integer BIT_CYCLES = 1085;
    localparam integer START_MID  = 543;    // (1085+1)/2, uart_rx contract
    localparam integer IMG        = 1104;   // S1 image: 3 chunks

    reg clk = 1'b0;
    always #4 clk = ~clk;                   // 125 MHz

    reg  rst_n = 1'b0;
    reg  rxd   = 1'b1;
    wire txd;

    reg  [9:0]  iram_raddr = 10'd0;
    wire [31:0] iram_rdata;
    wire        app_ready;
    wire [31:0] app_entry;
    wire        busy;
    wire [3:0]  status_state;
    wire [15:0] bytes_received;
    wire [7:0]  last_error;
    wire [7:0]  last_nak_seq;

    uart_app_boot #(.BAUD_DIV(1085)) dut (
        .clk(clk), .rst_n(rst_n),
        .uart_rxd(rxd), .uart_txd(txd),
        .iram_raddr(iram_raddr), .iram_rdata(iram_rdata),
        .app_ready(app_ready), .app_entry(app_entry),
        .busy(busy), .status_state(status_state),
        .bytes_received(bytes_received),
        .last_error(last_error), .last_nak_seq(last_nak_seq)
    );

    // ------------------------------------------------------------------
    // Image and frame buffers
    // ------------------------------------------------------------------
    reg [7:0] image [0:IMG-1];
    reg [7:0] send_pay [0:511];
    integer   send_plen;
    integer   errors = 0;
    integer   checks = 0;
    integer   scene_errors = 0;
    integer   i;

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

    // standard CRC-32 (IEEE 802.3) over image[off .. off+len-1]
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
    // Serial drivers (physical pin timing, tb_uart_rx.sv style)
    // ------------------------------------------------------------------
    task bit_time(input reg level);
        begin
            rxd = level;
            repeat (BIT_CYCLES) @(negedge clk);
        end
    endtask

    task send_byte(input reg [7:0] value);
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
    task send_frame(input [7:0] ftype, input [7:0] seq, input integer corrupt_off);
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
            c = c ^ 32'hFFFFFFFF;    // standard CRC-32 final value on wire
            send_byte(c[7:0]);
            send_byte(c[15:8]);
            send_byte(c[23:16]);
            send_byte(c[31:24]);
        end
    endtask

    task send_chunk(input [7:0] seq, input integer off, input integer len,
                    input integer corrupt_off);
        integer k;
        begin
            for (k = 0; k < len; k = k + 1) send_pay[k] = image[off + k];
            send_plen = len;
            send_frame(8'h01, seq, corrupt_off);
        end
    endtask

    task send_exec(input [7:0] seq, input [31:0] entry,
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

    task send_abort(input [7:0] seq);
        begin
            send_plen = 0;
            send_frame(8'h03, seq, -1);
        end
    endtask

    // ------------------------------------------------------------------
    // Serial reply sampler (mid-bit, mirrors uart_rx sampling positions)
    // ------------------------------------------------------------------
    task recv_serial(output reg [7:0] b);
        integer t;
        integer k;
        begin
            t = 0;
            while (txd === 1'b1 && t < 600000) begin
                @(negedge clk);
                t = t + 1;
            end
            if (txd !== 1'b0) begin
                errors = errors + 1;
                checks = checks + 1;
                $display("CHECK FAIL: recv_serial timeout (no start bit)");
                $display("DIAG state=%0d busy=%0b last_err=%0d bytes=%0d",
                         status_state, busy, last_error, bytes_received);
                b = 8'hFF;
            end else begin
                repeat (START_MID) @(negedge clk);   // start-bit center
                for (k = 0; k < 8; k = k + 1) begin
                    repeat (BIT_CYCLES) @(negedge clk);
                    b[k] = txd;
                end
                repeat (BIT_CYCLES) @(negedge clk); // stop-bit center
                if (txd !== 1'b1) begin
                    errors = errors + 1;
                    checks = checks + 1;
                    $display("CHECK FAIL: recv_serial framing error");
                end
            end
        end
    endtask

    // ------------------------------------------------------------------
    // Checks
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

    task expect_ack(input [7:0] seq);
        reg [7:0] b0, b1;
        begin
            recv_serial(b0);
            recv_serial(b1);
            $display("OBS reply: %02x %02x (expect 4b %02x)", b0, b1, seq);
            check("reply ACK 'K'+seq", b0 == 8'h4B && b1 == seq);
        end
    endtask

    task expect_nak(input [7:0] seq, input [7:0] reason);
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

    task reset_dut;
        begin
            rst_n = 1'b0;
            rxd = 1'b1;
            repeat (10) @(negedge clk);
            rst_n = 1'b1;
            repeat (5) @(negedge clk);
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

    // read one IRAM word through the DUT synchronous read port
    task iram_peek(input [9:0] waddr, output [31:0] wdata);
        begin
            iram_raddr = waddr;
            @(negedge clk);
            @(negedge clk);
            wdata = iram_rdata;
        end
    endtask

    // ------------------------------------------------------------------
    // Stimulus
    // ------------------------------------------------------------------
    reg [31:0] w0, w128, w275;

    initial begin
        // deterministic image: bytes cross every chunk boundary
        for (i = 0; i < IMG; i = i + 1)
            image[i] = (i * 7 + 3) & 255;

        // ==============================================================
        // S1: normal load, 3 chunks (512+512+80) + EXEC
        // ==============================================================
        scene_begin;
        reset_dut;
        send_chunk(8'd0, 0, 512, -1);    expect_ack(8'd0);
        send_chunk(8'd1, 512, 512, -1);  expect_ack(8'd1);
        send_chunk(8'd2, 1024, 80, -1);  expect_ack(8'd2);
        send_exec(8'd3, 32'd64, 32'd1104, crc32_img(1104, 0));
        expect_ack(8'd3);
        repeat (4) @(negedge clk);
        check("S1 app_ready set", app_ready === 1'b1);
        check("S1 app_entry == 64", app_entry == 32'd64);
        check("S1 bytes_received == 1104", bytes_received == 16'd1104);
        check("S1 last_error == 0", last_error == 8'd0);

        iram_peek(10'd0, w0);
        iram_peek(10'd128, w128);        // bytes 512..515: chunk boundary
        iram_peek(10'd275, w275);        // bytes 1100..1103: last word
        check("S1 IRAM word0 matches image[0..3]",
              w0 == {image[3], image[2], image[1], image[0]});
        check("S1 IRAM word128 matches image[512..515]",
              w128 == {image[515], image[514], image[513], image[512]});
        check("S1 IRAM word275 matches image[1100..1103]",
              w275 == {image[1103], image[1102], image[1101], image[1100]});
        scene_end(1, "normal load 1104B + EXEC");

        // ==============================================================
        // S2: corrupt chunk payload -> NAK 1, no advance, recovery
        // ==============================================================
        scene_begin;
        reset_dut;
        send_chunk(8'd0, 0, 512, -1);    expect_ack(8'd0);
        send_chunk(8'd1, 512, 512, 37);  expect_nak(8'd1, 8'd1);
        repeat (4) @(negedge clk);
        check("S2 loader did not advance (512)",
              bytes_received == 16'd512);
        check("S2 last_error == 1", last_error == 8'd1);
        check("S2 last_nak_seq == 1", last_nak_seq == 8'd1);
        check("S2 app_ready still 0", app_ready === 1'b0);
        send_chunk(8'd1, 512, 512, -1);  expect_ack(8'd1);
        send_chunk(8'd2, 1024, 80, -1);  expect_ack(8'd2);
        send_exec(8'd3, 32'd64, 32'd1104, crc32_img(1104, 0));
        expect_ack(8'd3);
        repeat (4) @(negedge clk);
        check("S2 recovery EXEC passes", app_ready === 1'b1);
        iram_peek(10'd128, w128);
        check("S2 IRAM boundary word restored",
              w128 == {image[515], image[514], image[513], image[512]});
        scene_end(2, "corrupt chunk NAK + retransmit recovery");

        // ==============================================================
        // S3: seq skip -> NAK 2, correct seq continues
        // ==============================================================
        scene_begin;
        reset_dut;
        send_chunk(8'd0, 0, 512, -1);    expect_ack(8'd0);
        send_chunk(8'd2, 512, 512, -1);  expect_nak(8'd2, 8'd2);
        repeat (4) @(negedge clk);
        check("S3 loader did not advance (512)",
              bytes_received == 16'd512);
        check("S3 last_error == 2", last_error == 8'd2);
        send_chunk(8'd1, 512, 512, -1);  expect_ack(8'd1);
        send_exec(8'd2, 32'd0, 32'd1024, crc32_img(1024, 0));
        expect_ack(8'd2);
        repeat (4) @(negedge clk);
        check("S3 EXEC after seq recovery", app_ready === 1'b1);
        scene_end(3, "seq skip NAK + resume");

        // ==============================================================
        // S4: bad EXEC variants, app_ready stays 0
        // ==============================================================
        scene_begin;
        reset_dut;
        send_chunk(8'd0, 0, 512, -1);    expect_ack(8'd0);
        send_chunk(8'd1, 512, 512, -1);  expect_ack(8'd1);
        send_chunk(8'd2, 1024, 80, -1);  expect_ack(8'd2);

        send_exec(8'd3, 32'd64, 32'd1104, crc32_img(1104, 0) ^ 32'd1);
        expect_nak(8'd3, 8'd1);
        repeat (4) @(negedge clk);
        check("S4a app_ready stays 0", app_ready === 1'b0);

        send_exec(8'd3, 32'd64, 32'd1105, crc32_img(1104, 0));
        expect_nak(8'd3, 8'd3);
        repeat (4) @(negedge clk);
        check("S4b app_ready stays 0", app_ready === 1'b0);

        send_exec(8'd3, 32'd65, 32'd1104, crc32_img(1104, 0));
        expect_nak(8'd3, 8'd4);
        repeat (4) @(negedge clk);
        check("S4c app_ready stays 0", app_ready === 1'b0);
        check("S4 bytes_received still 1104", bytes_received == 16'd1104);
        scene_end(4, "bad EXEC crc/total/entry");

        // ==============================================================
        // S5: ABORT clears the session, full reload succeeds
        // ==============================================================
        scene_begin;
        reset_dut;
        send_chunk(8'd0, 0, 512, -1);    expect_ack(8'd0);
        send_abort(8'd1);                expect_ack(8'd1);
        repeat (4) @(negedge clk);
        check("S5 abort cleared bytes_received", bytes_received == 16'd0);
        check("S5 abort cleared app_ready", app_ready === 1'b0);
        send_chunk(8'd0, 0, 512, -1);    expect_ack(8'd0);
        send_chunk(8'd1, 512, 512, -1);  expect_ack(8'd1);
        send_chunk(8'd2, 1024, 80, -1);  expect_ack(8'd2);
        send_exec(8'd3, 32'd64, 32'd1104, crc32_img(1104, 0));
        expect_ack(8'd3);
        repeat (4) @(negedge clk);
        check("S5 full reload EXEC passes", app_ready === 1'b1);
        scene_end(5, "abort mid-session + full reload");

        // ==============================================================
        // S6: over-capacity EXEC total_len = 5000 -> NAK 3
        // ==============================================================
        scene_begin;
        reset_dut;
        send_chunk(8'd0, 0, 512, -1);    expect_ack(8'd0);
        send_exec(8'd1, 32'd0, 32'd5000, crc32_img(1104, 0));
        expect_nak(8'd1, 8'd3);
        repeat (4) @(negedge clk);
        check("S6 app_ready stays 0", app_ready === 1'b0);
        check("S6 last_error == 3", last_error == 8'd3);
        scene_end(6, "over-capacity EXEC");

        // ==============================================================
        // Summary
        // ==============================================================
        if (errors == 0) begin
            $display("TB_UART_APP_BOOT: PASS (%0d checks)", checks);
            $display("RESULT: PASS tb_uart_app_boot");
            $finish;
        end else begin
            $display("TB_UART_APP_BOOT: FAIL (%0d failed / %0d checks)",
                     errors, checks);
            $display("RESULT: FAIL tb_uart_app_boot");
            $fatal(1, "tb_uart_app_boot failed");
        end
    end

    initial begin : watchdog
        #(5s);
        $display("ERROR: tb_uart_app_boot watchdog (state=%0d busy=%0b app_ready=%0b)",
                 status_state, busy, app_ready);
        $fatal(1, "tb_uart_app_boot timeout");
    end

endmodule
