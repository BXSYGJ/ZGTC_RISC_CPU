// ---------------------------------------------------------------------------
// tb_diag_longread.sv -- reproduce the board diag_dump long-read stall.
//
// The board symptom: a 255-frame 'R' read stops at frame 25 (0-indexed) and
// the host times out.  This TB runs the SAME 255-frame read through the real
// ddr3_ctrl_axi + behavioural DDR3 model with NO other master (m0 prefill only,
// m1/m2 tied off) to isolate a pure diag_readback / controller read-path bug
// from the mel (m2) arbitration contention seen on the board.
//
// It reports the frame where a stall happens (no frame SOF for > STALL_LIMIT
// cycles) and byte-compares every payload against the deterministic pattern so
// a CRC / stale-fifo corruption shows up as a mismatch instead of a timeout.
// ---------------------------------------------------------------------------
`timescale 1ns/1ps

module tb_diag_longread;

    localparam integer CLK_HALF    = 5;      // 100 MHz simulation clock
    localparam integer TX_FRAME    = 40;     // scaled 10-bit UART frame time
    localparam integer ACK_DLY     = 60;     // PC 'K' delay after a frame
    localparam integer MAX_BYTES   = 70000;  // 255 frames x 264 B = 67320
    localparam integer RD_FRAMES   = 255;    // len = 255 x 256 = 65280 B

    reg clk   = 1'b0;
    reg rst_n = 1'b0;

    always #(CLK_HALF) clk = ~clk;

    // -----------------------------------------------------------------
    // UART byte channel
    // -----------------------------------------------------------------
    reg        cmd_rx_valid = 1'b0;
    reg [7:0]  cmd_rx_data  = 8'd0;
    reg        ack_rx_valid = 1'b0;
    reg [7:0]  ack_rx_data  = 8'h4B;
    wire       rx_valid = cmd_rx_valid | ack_rx_valid;
    wire [7:0] rx_data  = ack_rx_valid ? ack_rx_data : cmd_rx_data;

    wire       tx_valid;
    wire [7:0] tx_data;
    reg        tx_ready = 1'b0;

    // -----------------------------------------------------------------
    // DUT read port + status
    // -----------------------------------------------------------------
    wire        m3_cmd_valid;
    wire [36:0] m3_cmd;
    wire [255:0] m3_rd_data;
    wire        m3_rd_valid;
    wire        m3_rd_ready;
    wire        m3_done;
    wire        diag_lock;
    reg  [15:0] win_id       = 16'd0;
    reg         mel_done     = 1'b0;
    reg         npu_done     = 1'b0;
    reg         logits_valid = 1'b0;
    reg [255:0] logits_hold  = 256'd0;

    diag_readback dut (
        .clk          (clk), .rst_n        (rst_n),
        .rx_valid     (rx_valid), .rx_data (rx_data),
        .tx_valid     (tx_valid), .tx_data (tx_data), .tx_ready (tx_ready),
        .m3_cmd_valid (m3_cmd_valid), .m3_cmd (m3_cmd),
        .m3_rd_data   (m3_rd_data), .m3_rd_valid (m3_rd_valid),
        .m3_rd_ready  (m3_rd_ready), .m3_done (m3_done),
        .diag_lock    (diag_lock),
        .win_id       (win_id), .mel_done (mel_done), .npu_done (npu_done),
        .logits_valid (logits_valid), .logits_in (logits_hold)
    );

    // -----------------------------------------------------------------
    // DDR3 controller + behavioural model (m0 prefill write engine only)
    // -----------------------------------------------------------------
    reg         wr_valid = 1'b0;
    reg  [27:0] wr_addr  = 28'd0;
    reg  [7:0]  wr_len   = 8'd15;
    reg  [8:0]  wr_beat  = 9'd0;

    wire [31:0] wr_off_c  = {19'd0, wr_beat, 5'd0};
    wire [27:0] wr_cur_c  = wr_addr + wr_off_c[27:0];
    wire [255:0] m0_wdata_c;

    function [7:0] pat_byte;
        input [27:0] a;
        begin
            pat_byte = (a * 37 + 90);
        end
    endfunction

    function [255:0] make_beat;
        input [27:0] a;
        integer j;
        begin
            make_beat = 256'd0;
            for (j = 0; j < 32; j = j + 1)
                make_beat[j*8 +: 8] = pat_byte(a + j);
        end
    endfunction

    assign m0_wdata_c = make_beat(wr_cur_c);

    reg  [3:0]  cmd_valid;
    wire [36:0] m0_cmd = {1'b1, wr_addr, wr_len};
    wire [36:0] m1_cmd = 37'd0;
    wire [36:0] m2_cmd = 37'd0;
    wire [36:0] m3_cmd_ctrl = m3_cmd;
    wire [255:0] m1_wdata = 256'd0;
    wire [255:0] m2_wdata = 256'd0;
    wire [255:0] m3_wdata = 256'd0;

    assign cmd_valid = {m3_cmd_valid, 2'b00, wr_valid};

    wire [3:0]  wready_beat;
    wire [3:0]  rd_ready_c = {m3_rd_ready, 3'b000};
    wire [255:0] rd_data_0, rd_data_1, rd_data_2, rd_data_3;
    wire [3:0]  rd_valid_c;
    wire [3:0]  done_c;

    assign m3_rd_data  = rd_data_3;
    assign m3_rd_valid = rd_valid_c[3];
    assign m3_done     = done_c[3];

    wire [31:0] wait_cnt_0, wait_cnt_1, wait_cnt_2, wait_cnt_3;
    wire [3:0]  addr_err;
    wire        to_err;
    wire [3:0]  cmd_to_err;
    wire [2:0]  dbg_to_state;
    wire [7:0]  wlast_miss_cnt;

    wire [27:0] axi_awaddr;
    wire        axi_awuser_ap;
    wire [3:0]  axi_awuser_id, axi_awlen;
    wire        axi_awvalid, axi_awready;
    wire [255:0] axi_wdata;
    wire [31:0] axi_wstrb;
    wire        axi_wready;
    wire [3:0]  axi_wusero_id;
    wire        axi_wusero_last;
    wire [27:0] axi_araddr;
    wire        axi_aruser_ap;
    wire [3:0]  axi_aruser_id, axi_arlen;
    wire        axi_arvalid, axi_arready;
    wire [255:0] axi_rdata;
    wire [3:0]  axi_rid;
    wire        axi_rlast, axi_rvalid;

    ddr3_ctrl_axi u_ctrl (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(cmd_valid),
        .m0_cmd(m0_cmd), .m1_cmd(m1_cmd), .m2_cmd(m2_cmd), .m3_cmd(m3_cmd_ctrl),
        .m0_wdata(m0_wdata_c), .m1_wdata(m1_wdata), .m2_wdata(m2_wdata), .m3_wdata(m3_wdata),
        .wready_beat(wready_beat), .rd_ready(rd_ready_c),
        .rd_data_0(rd_data_0), .rd_data_1(rd_data_1), .rd_data_2(rd_data_2), .rd_data_3(rd_data_3),
        .rd_valid(rd_valid_c), .done(done_c),
        .wait_cnt_0(wait_cnt_0), .wait_cnt_1(wait_cnt_1), .wait_cnt_2(wait_cnt_2), .wait_cnt_3(wait_cnt_3),
        .addr_err(addr_err), .to_err(to_err), .cmd_to_err(cmd_to_err),
        .dbg_to_state(dbg_to_state), .wlast_miss_cnt(wlast_miss_cnt),
        .axi_awaddr(axi_awaddr), .axi_awuser_ap(axi_awuser_ap),
        .axi_awuser_id(axi_awuser_id), .axi_awlen(axi_awlen),
        .axi_awvalid(axi_awvalid), .axi_awready(axi_awready),
        .axi_wdata(axi_wdata), .axi_wstrb(axi_wstrb), .axi_wready(axi_wready),
        .axi_wusero_id(axi_wusero_id), .axi_wusero_last(axi_wusero_last),
        .axi_araddr(axi_araddr), .axi_aruser_ap(axi_aruser_ap),
        .axi_aruser_id(axi_aruser_id), .axi_arlen(axi_arlen),
        .axi_arvalid(axi_arvalid), .axi_arready(axi_arready),
        .axi_rdata(axi_rdata), .axi_rid(axi_rid),
        .axi_rlast(axi_rlast), .axi_rvalid(axi_rvalid)
    );

    reg [31:0] obs_aw_hs, obs_ar_hs, obs_wr_beats, obs_rd_beats;
    reg [31:0] obs_len0_wr, obs_len0_wstrb0, obs_len0_wstrb1, obs_last_marker;

    ddr3_axi_model u_model (
        .clk(clk), .rst_n(rst_n),
        .s_awaddr(axi_awaddr), .s_awvalid(axi_awvalid), .s_awlen(axi_awlen),
        .s_awuser_id(axi_awuser_id), .s_awready(axi_awready),
        .s_wdata(axi_wdata), .s_wstrb(axi_wstrb), .s_wready(axi_wready),
        .s_wusero_last(axi_wusero_last),
        .s_araddr(axi_araddr), .s_arvalid(axi_arvalid), .s_arlen(axi_arlen),
        .s_aruser_id(axi_aruser_id), .s_arready(axi_arready),
        .s_rdata(axi_rdata), .s_rid(axi_rid), .s_rlast(axi_rlast), .s_rvalid(axi_rvalid),
        .obs_aw_hs(obs_aw_hs), .obs_ar_hs(obs_ar_hs),
        .obs_wr_beats(obs_wr_beats), .obs_rd_beats(obs_rd_beats),
        .obs_len0_wr(obs_len0_wr), .obs_len0_wstrb0(obs_len0_wstrb0),
        .obs_len0_wstrb1(obs_len0_wstrb1), .obs_last_marker(obs_last_marker)
    );

    always @(posedge clk) begin
        if (rst_n && wr_valid && wready_beat[0]) wr_beat <= wr_beat + 9'd1;
    end

    // -----------------------------------------------------------------
    // uart_tx stand-in
    // -----------------------------------------------------------------
    reg       tx_busy = 1'b0;
    reg [7:0] tx_frm_cnt = 8'd0;
    wire      tx_take = tx_valid && tx_ready && !tx_busy;

    always @(posedge clk) begin
        if (!rst_n) begin
            tx_ready <= 1'b0; tx_busy <= 1'b0; tx_frm_cnt <= 8'd0;
        end else begin
            tx_ready <= ~tx_busy;
            if (!tx_busy) begin
                if (tx_valid && tx_ready) begin
                    tx_busy <= 1'b1; tx_frm_cnt <= 8'd0;
                end
            end else if (tx_frm_cnt == TX_FRAME - 1) begin
                tx_busy <= 1'b0; tx_frm_cnt <= 8'd0;
            end else begin
                tx_frm_cnt <= tx_frm_cnt + 8'd1;
            end
        end
    end

    // -----------------------------------------------------------------
    // Frame monitor: count frames, byte-compare payload, detect stall
    // -----------------------------------------------------------------
    integer   mon_on    = 0;
    integer   frame_no  = 0;   // 0-based frame index inside the 'R'
    integer   pos       = 0;   // byte position inside the current frame
    integer   mon_errors = 0;
    integer   stall_cnt = 0;   // cycles since the last frame byte
    integer   stalled_frame = -1;
    integer   frames_done = 0;

    reg        ack_req  = 1'b0;
    reg [7:0]  ack_dly  = 8'd0;

    function [15:0] crc16_step;
        input [15:0] crc;
        input [7:0]  b;
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

    reg [15:0] crc_m;
    integer mon_byte;

    always @(posedge clk) begin
        if (!rst_n) begin
            ack_rx_valid <= 1'b0;
            ack_req <= 1'b0; ack_dly <= 8'd0;
            pos = 0; mon_on = 0; frame_no = 0; stall_cnt = 0;
        end else begin
            ack_rx_valid <= 1'b0;

            if (mon_on) begin
                stall_cnt = stall_cnt + 1;
                if (stall_cnt > 500000 && stalled_frame < 0) begin
                    stalled_frame = frame_no;
                    $display("  STALL: no frame %0d after %0d cycles", frame_no, stall_cnt);
                end
            end

            if (ack_req) begin
                if (ack_dly != 8'd0) ack_dly <= ack_dly - 8'd1;
                else begin ack_rx_valid <= 1'b1; ack_req <= 1'b0; end
            end

            if (tx_take) begin
                if (mon_on) stall_cnt = 0;

                if (mon_on) begin
                    if (pos == 0) begin
                        crc_m = 16'hFFFF;
                        if (tx_data != 8'hAA) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d bad SOF0 %02X", frame_no, tx_data);
                        end
                    end else if (pos == 1) begin
                        if (tx_data != 8'h55) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d bad SOF1 %02X", frame_no, tx_data);
                        end
                    end else if (pos == 2) begin
                        crc_m = crc16_step(crc_m, tx_data);
                        if (tx_data != frame_no[7:0]) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d seq low %02X exp %02X", frame_no, tx_data, frame_no[7:0]);
                        end
                    end else if (pos == 3) begin
                        crc_m = crc16_step(crc_m, tx_data);
                        if (tx_data != frame_no[15:8]) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d seq high %02X exp %02X", frame_no, tx_data, frame_no[15:8]);
                        end
                    end else if (pos == 4) begin
                        crc_m = crc16_step(crc_m, tx_data);
                    end else if (pos == 5) begin
                        crc_m = crc16_step(crc_m, tx_data);
                    end else if (pos <= 261) begin
                        crc_m = crc16_step(crc_m, tx_data);
                        mon_byte = pat_byte(frame_no * 256 + (pos - 6));
                        if (tx_data !== mon_byte[7:0]) begin
                            if (mon_errors < 20)
                                $display("  frame %0d byte %0d got %02X exp %02X",
                                         frame_no, pos - 6, tx_data, mon_byte[7:0]);
                            mon_errors = mon_errors + 1;
                        end
                    end else if (pos == 262) begin
                        if (tx_data != crc_m[7:0]) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d crc low %02X exp %02X", frame_no, tx_data, crc_m[7:0]);
                        end
                    end else begin
                        if (tx_data != crc_m[15:8]) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d crc high %02X exp %02X", frame_no, tx_data, crc_m[15:8]);
                        end
                        // frame complete
                        frames_done = frames_done + 1;
                        frame_no = frame_no + 1;
                        ack_req <= 1'b1;
                        ack_dly <= ACK_DLY;
                        if (frame_no == RD_FRAMES) begin
                            mon_on = 0;
                            $display("  read-back complete: %0d frames", RD_FRAMES);
                        end
                    end
                    pos = pos + 1;
                    if (pos == 264) pos = 0;
                end
            end
        end
    end

    // -----------------------------------------------------------------
    // Stimulus
    // -----------------------------------------------------------------
    task automatic send_rx_byte;
        input [7:0] b;
        begin
            @(negedge clk); cmd_rx_data = b; cmd_rx_valid = 1'b1;
            @(negedge clk); cmd_rx_valid = 1'b0;
            @(negedge clk);
        end
    endtask

    task automatic ddr_write;
        input [27:0] addr;
        input [7:0]  len;
        begin
            wr_addr = addr; wr_len = len; wr_beat = 9'd0; wr_valid = 1'b1;
            @(posedge clk);
            while (done_c[0] !== 1'b1) @(posedge clk);
            @(negedge clk);
            wr_valid = 1'b0;
            repeat (4) @(posedge clk);
        end
    endtask

    integer k;
    integer total_errors;

    initial begin
        repeat (20) @(posedge clk);
        rst_n = 1'b1;
        repeat (20) @(posedge clk);

        // ---- prefill 65536 B at 0x000000 (128 x 512 B beats) ----
        for (k = 0; k < 128; k = k + 1)
            ddr_write(k * 28'h200, 8'd15);
        $display("  prefill done: obs_wr_beats=%0d", obs_wr_beats);

        // ---- long read: 'R' addr=0 len=65280 (255 frames) ----
        mon_on = 1;
        frame_no = 0;
        pos = 0;
        send_rx_byte(8'h52);          // 'R'
        send_rx_byte(8'h00);          // addr[7:0]
        send_rx_byte(8'h00);          // addr[15:8]
        send_rx_byte(8'h00);          // addr[23:16]
        send_rx_byte(8'h00);          // addr[31:24]
        send_rx_byte(8'h00);          // len[7:0]  (65280 = 0xFF00)
        send_rx_byte(8'hFF);          // len[15:8]

        // wait for completion or stall
        while (mon_on) @(posedge clk);
        repeat (400) @(posedge clk);

        $display("  frames_done=%0d stalled_frame=%0d mon_errors=%0d",
                 frames_done, stalled_frame, mon_errors);
        $display("  controller: addr_err=%b to_err=%b cmd_to_err=%b dbg=%0d",
                 addr_err, to_err, cmd_to_err, dbg_to_state);
        $display("  ar_hs=%0d rd_beats=%0d", obs_ar_hs, obs_rd_beats);

        if (stalled_frame >= 0) begin
            $display("RESULT: FAIL diag_longread (stall at frame %0d)", stalled_frame);
        end else if (frames_done != RD_FRAMES) begin
            $display("RESULT: FAIL diag_longread (only %0d/%0d frames)", frames_done, RD_FRAMES);
        end else if (mon_errors != 0) begin
            $display("RESULT: FAIL diag_longread (%0d monitor errors)", mon_errors);
        end else begin
            $display("RESULT: PASS diag_longread");
        end
        $finish;
    end

    // Absolute watchdog.
    initial begin
        repeat (30000000) @(posedge clk);
        $display("RESULT: FAIL diag_longread (watchdog, frames_done=%0d stalled=%0d)",
                 frames_done, stalled_frame);
        $finish;
    end

endmodule
