// ---------------------------------------------------------------------------
// tb_diag_readback.sv -- testbench for src/diag/diag_readback.v
//
// Topology (same as the board path, only the DDR3 IP is behavioural):
//   tb UART byte channel  -> diag_readback
//   diag_readback (m3)    -> ddr3_ctrl_axi -> ddr3_axi_model
//   tb m0 write engine    -> ddr3_ctrl_axi (prefill of the regions read back)
//
// The DDR3 content is put there through the real controller write path, so
// the read-back verifies read-after-write, the len = 7 (8 beats x 32 B)
// frame geometry and the dummy-write-before-read side effect.
//
// Scenarios (each one must pass):
//   S1  'R' addr=0x0000_0000 len=1024: 4 frames, byte exact against the
//       deterministic pattern, seq 0..3, CRC-16/CCITT-FALSE correct.
//   S2  bad lengths: len=300 -> 'N'+'1', len=0 -> 'N'+'3'.
//   S3  illegal command 0x41 -> 'N'+'2'.
//   S4  'L'/'U' drive diag_lock, 'S' prints the fixed 61-byte status line.
//   S5  'R' addr=0x0020_0000 len=512 (feat region): 2 frames, byte exact.
//
// The PC flow control ('K' after every frame) is emulated with a fixed
// delay.  The TX sink mimics uart_tx.v: byte_wready is a registered ~busy
// and stays high one extra cycle after an accept (tb_weight_loader.sv).
// ---------------------------------------------------------------------------
`timescale 1ns/1ps

module tb_diag_readback;

    localparam integer CLK_HALF  = 5;      // 100 MHz simulation clock
    localparam integer TX_FRAME  = 40;     // scaled 10-bit UART frame time
    localparam integer ACK_DLY   = 60;     // PC 'K' delay after a frame
    localparam integer MAX_BYTES = 16384;  // capture buffer

    reg clk   = 1'b0;
    reg rst_n = 1'b0;

    always #(CLK_HALF) clk = ~clk;

    // -----------------------------------------------------------------
    // UART byte channel: command sender (stimulus) + 'K' responder
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
    // DDR3 master-3 read-only port of the DUT
    // -----------------------------------------------------------------
    wire        m3_cmd_valid;
    wire [36:0] m3_cmd;
    wire [255:0] m3_rd_data;
    wire        m3_rd_valid;
    wire        m3_rd_ready;
    wire        m3_done;

    // -----------------------------------------------------------------
    // status inputs
    // -----------------------------------------------------------------
    wire        diag_lock;
    reg  [15:0] win_id       = 16'd0;
    reg         mel_done     = 1'b0;
    reg         npu_done     = 1'b0;
    reg         logits_valid = 1'b0;
    reg [255:0] logits_hold  = 256'd0;

    diag_readback dut (
        .clk          (clk),
        .rst_n        (rst_n),
        .rx_valid     (rx_valid),
        .rx_data      (rx_data),
        .tx_valid     (tx_valid),
        .tx_data      (tx_data),
        .tx_ready     (tx_ready),
        .m3_cmd_valid (m3_cmd_valid),
        .m3_cmd       (m3_cmd),
        .m3_rd_data   (m3_rd_data),
        .m3_rd_valid  (m3_rd_valid),
        .m3_rd_ready  (m3_rd_ready),
        .m3_done      (m3_done),
        .diag_lock    (diag_lock),
        .win_id       (win_id),
        .mel_done     (mel_done),
        .npu_done     (npu_done),
        .logits_valid (logits_valid),
        .logits_in    (logits_hold)
    );

    // -----------------------------------------------------------------
    // DDR3 controller + behavioural IP model
    // -----------------------------------------------------------------
    reg         wr_valid = 1'b0;
    reg  [27:0] wr_addr  = 28'd0;
    reg  [7:0]  wr_len   = 8'd15;
    reg  [8:0]  wr_beat  = 9'd0;

    wire [31:0] wr_off_c  = {19'd0, wr_beat, 5'd0};
    wire [27:0] wr_cur_c  = wr_addr + wr_off_c[27:0];
    wire [255:0] m0_wdata_c;

    // Deterministic test pattern: byte at address a = (37*a + 90) mod 256.
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
    wire [255:0] rd_data_0;
    wire [255:0] rd_data_1;
    wire [255:0] rd_data_2;
    wire [255:0] rd_data_3;
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
    wire [3:0]  axi_awuser_id;
    wire [3:0]  axi_awlen;
    wire        axi_awvalid;
    wire        axi_awready;
    wire [255:0] axi_wdata;
    wire [31:0] axi_wstrb;
    wire        axi_wready;
    wire [3:0]  axi_wusero_id;
    wire        axi_wusero_last;
    wire [27:0] axi_araddr;
    wire        axi_aruser_ap;
    wire [3:0]  axi_aruser_id;
    wire [3:0]  axi_arlen;
    wire        axi_arvalid;
    wire        axi_arready;
    wire [255:0] axi_rdata;
    wire [3:0]  axi_rid;
    wire        axi_rlast;
    wire        axi_rvalid;

    ddr3_ctrl_axi u_ctrl (
        .clk             (clk),
        .rst_n           (rst_n),
        .cmd_valid       (cmd_valid),
        .m0_cmd          (m0_cmd),
        .m1_cmd          (m1_cmd),
        .m2_cmd          (m2_cmd),
        .m3_cmd          (m3_cmd_ctrl),
        .m0_wdata        (m0_wdata_c),
        .m1_wdata        (m1_wdata),
        .m2_wdata        (m2_wdata),
        .m3_wdata        (m3_wdata),
        .wready_beat     (wready_beat),
        .rd_ready        (rd_ready_c),
        .rd_data_0       (rd_data_0),
        .rd_data_1       (rd_data_1),
        .rd_data_2       (rd_data_2),
        .rd_data_3       (rd_data_3),
        .rd_valid        (rd_valid_c),
        .done            (done_c),
        .wait_cnt_0      (wait_cnt_0),
        .wait_cnt_1      (wait_cnt_1),
        .wait_cnt_2      (wait_cnt_2),
        .wait_cnt_3      (wait_cnt_3),
        .addr_err        (addr_err),
        .to_err          (to_err),
        .cmd_to_err      (cmd_to_err),
        .dbg_to_state    (dbg_to_state),
        .wlast_miss_cnt  (wlast_miss_cnt),
        .axi_awaddr      (axi_awaddr),
        .axi_awuser_ap   (axi_awuser_ap),
        .axi_awuser_id   (axi_awuser_id),
        .axi_awlen       (axi_awlen),
        .axi_awvalid     (axi_awvalid),
        .axi_awready     (axi_awready),
        .axi_wdata       (axi_wdata),
        .axi_wstrb       (axi_wstrb),
        .axi_wready      (axi_wready),
        .axi_wusero_id   (axi_wusero_id),
        .axi_wusero_last (axi_wusero_last),
        .axi_araddr      (axi_araddr),
        .axi_aruser_ap   (axi_aruser_ap),
        .axi_aruser_id   (axi_aruser_id),
        .axi_arlen       (axi_arlen),
        .axi_arvalid     (axi_arvalid),
        .axi_arready     (axi_arready),
        .axi_rdata       (axi_rdata),
        .axi_rid         (axi_rid),
        .axi_rlast       (axi_rlast),
        .axi_rvalid      (axi_rvalid)
    );

    reg [31:0] obs_aw_hs, obs_ar_hs, obs_wr_beats, obs_rd_beats;
    reg [31:0] obs_len0_wr, obs_len0_wstrb0, obs_len0_wstrb1, obs_last_marker;

    ddr3_axi_model u_model (
        .clk             (clk),
        .rst_n           (rst_n),
        .s_awaddr        (axi_awaddr),
        .s_awvalid       (axi_awvalid),
        .s_awlen         (axi_awlen),
        .s_awuser_id     (axi_awuser_id),
        .s_awready       (axi_awready),
        .s_wdata         (axi_wdata),
        .s_wstrb         (axi_wstrb),
        .s_wready        (axi_wready),
        .s_wusero_last   (axi_wusero_last),
        .s_araddr        (axi_araddr),
        .s_arvalid       (axi_arvalid),
        .s_arlen         (axi_arlen),
        .s_aruser_id     (axi_aruser_id),
        .s_arready       (axi_arready),
        .s_rdata         (axi_rdata),
        .s_rid           (axi_rid),
        .s_rlast         (axi_rlast),
        .s_rvalid        (axi_rvalid),
        .obs_aw_hs       (obs_aw_hs),
        .obs_ar_hs       (obs_ar_hs),
        .obs_wr_beats    (obs_wr_beats),
        .obs_rd_beats    (obs_rd_beats),
        .obs_len0_wr     (obs_len0_wr),
        .obs_len0_wstrb0 (obs_len0_wstrb0),
        .obs_len0_wstrb1 (obs_len0_wstrb1),
        .obs_last_marker (obs_last_marker)
    );

    // Master-0 beat advance: a beat is taken on every wready_beat[0] edge.
    always @(posedge clk) begin
        if (rst_n && wr_valid && wready_beat[0]) wr_beat <= wr_beat + 9'd1;
    end

    // -----------------------------------------------------------------
    // uart_tx stand-in (registered ready, one frame per byte)
    // -----------------------------------------------------------------
    reg       tx_busy = 1'b0;
    reg [7:0] tx_frm_cnt = 8'd0;
    wire      tx_take = tx_valid && tx_ready && !tx_busy;

    always @(posedge clk) begin
        if (!rst_n) begin
            tx_ready   <= 1'b0;
            tx_busy    <= 1'b0;
            tx_frm_cnt <= 8'd0;
        end else begin
            tx_ready <= ~tx_busy;
            if (!tx_busy) begin
                if (tx_valid && tx_ready) begin
                    tx_busy    <= 1'b1;
                    tx_frm_cnt <= 8'd0;
                end
            end else if (tx_frm_cnt == TX_FRAME - 1) begin
                tx_busy    <= 1'b0;
                tx_frm_cnt <= 8'd0;
            end else begin
                tx_frm_cnt <= tx_frm_cnt + 8'd1;
            end
        end
    end

    // -----------------------------------------------------------------
    // TX capture and read-back frame monitor (single writer for every
    // monitor variable; the stimulus process only reads them and drives
    // the req_start / cap_clr strobes).
    // -----------------------------------------------------------------
    reg [7:0] cap [0:MAX_BYTES-1];
    integer   cap_n     = 0;
    integer   mon_errors = 0;

    integer   mon_on    = 0;     // 1 while a 'R' read-back is in flight
    integer   frame_no  = 0;     // frames seen inside the current 'R'
    integer   rd_base   = 0;     // 'R' base address
    integer   rd_frames = 0;     // frames expected for the current 'R'
    integer   pos       = 0;     // byte position inside the current frame
    reg [15:0] crc_m    = 16'hFFFF;
    reg        ack_req  = 1'b0;
    reg [7:0]  ack_dly  = 8'd0;

    reg        req_start  = 1'b0;   // stimulus -> monitor arming strobe
    reg [31:0] req_base   = 32'd0;
    reg [15:0] req_frames = 16'd0;
    reg        cap_clr    = 1'b0;   // stimulus -> monitor capture clear

    integer mon_byte;

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

    always @(posedge clk) begin
        if (!rst_n) begin
            cap_n        <= 0;
            ack_rx_valid <= 1'b0;
            ack_req      <= 1'b0;
            ack_dly      <= 8'd0;
            pos          = 0;
            mon_on       = 0;
        end else begin
            ack_rx_valid <= 1'b0;

            if (cap_clr) cap_n <= 0;

            if (req_start && !mon_on) begin
                mon_on    = 1;
                rd_base   = req_base;
                rd_frames = req_frames;
                frame_no  = 0;
                pos       = 0;
            end

            // PC flow control: one 'K' ACK_DLY cycles after a frame ends.
            if (ack_req) begin
                if (ack_dly != 8'd0) begin
                    ack_dly <= ack_dly - 8'd1;
                end else begin
                    ack_rx_valid <= 1'b1;
                    ack_req      <= 1'b0;
                end
            end

            if (tx_take) begin
                if (cap_n < MAX_BYTES) begin
                    cap[cap_n] <= tx_data;
                    cap_n      <= cap_n + 1;
                end

                if (mon_on) begin
                    if (pos == 0) begin
                        crc_m = 16'hFFFF;
                        if (tx_data != 8'hAA) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d: bad SOF0 %02X", frame_no, tx_data);
                        end
                    end else if (pos == 1) begin
                        if (tx_data != 8'h55) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d: bad SOF1 %02X", frame_no, tx_data);
                        end
                    end else if (pos == 2) begin
                        crc_m = crc16_step(crc_m, tx_data);
                        if (tx_data != frame_no[7:0]) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d: seq low %02X", frame_no, tx_data);
                        end
                    end else if (pos == 3) begin
                        crc_m = crc16_step(crc_m, tx_data);
                        if (tx_data != frame_no[15:8]) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d: seq high %02X", frame_no, tx_data);
                        end
                    end else if (pos == 4) begin
                        crc_m = crc16_step(crc_m, tx_data);
                        if (tx_data != 8'h00) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d: len low %02X", frame_no, tx_data);
                        end
                    end else if (pos == 5) begin
                        crc_m = crc16_step(crc_m, tx_data);
                        if (tx_data != 8'h01) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d: len high %02X", frame_no, tx_data);
                        end
                    end else if (pos <= 261) begin
                        crc_m = crc16_step(crc_m, tx_data);
                        mon_byte = pat_byte(rd_base + frame_no * 256 + (pos - 6));
                        if (tx_data !== mon_byte[7:0]) begin
                            if (mon_errors < 20)
                                $display("  frame %0d byte %0d: got %02X exp %02X",
                                         frame_no, pos - 6, tx_data, mon_byte[7:0]);
                            mon_errors = mon_errors + 1;
                        end
                    end else if (pos == 262) begin
                        if (tx_data != crc_m[7:0]) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d: crc low %02X exp %02X",
                                     frame_no, tx_data, crc_m[7:0]);
                        end
                    end else begin
                        if (tx_data != crc_m[15:8]) begin
                            mon_errors = mon_errors + 1;
                            $display("  frame %0d: crc high %02X exp %02X",
                                     frame_no, tx_data, crc_m[15:8]);
                        end
                        frame_no = frame_no + 1;
                        ack_req  <= 1'b1;
                        ack_dly  <= ACK_DLY;
                        if (frame_no == rd_frames) begin
                            mon_on = 0;
                            $display("  read-back: %0d frame(s) from 0x%07X",
                                     frame_no, rd_base);
                        end
                    end

                    pos = pos + 1;
                    if (pos == 264) pos = 0;
                end
            end
        end
    end

    // -----------------------------------------------------------------
    // Stimulus helpers
    // -----------------------------------------------------------------
    task automatic send_rx_byte;
        input [7:0] b;
        begin
            @(negedge clk);
            cmd_rx_data  = b;
            cmd_rx_valid = 1'b1;
            @(negedge clk);
            cmd_rx_valid = 1'b0;
            @(negedge clk);
        end
    endtask

    task automatic clear_cap;
        begin
            @(negedge clk);
            cap_clr = 1'b1;
            @(negedge clk);
            cap_clr = 1'b0;
        end
    endtask

    task automatic send_read_cmd;
        input [31:0]  addr;
        input [15:0]  len;
        input integer arm;          // 1 = expect read-back frames
        begin
            if (arm != 0) begin
                req_base   = addr;
                req_frames = len >> 8;
                req_start  = 1'b1;
            end
            send_rx_byte(8'h52);
            send_rx_byte(addr[7:0]);
            send_rx_byte(addr[15:8]);
            send_rx_byte(addr[23:16]);
            send_rx_byte(addr[31:24]);
            send_rx_byte(len[7:0]);
            send_rx_byte(len[15:8]);
            req_start = 1'b0;
        end
    endtask

    task automatic ddr_write;
        input [27:0] addr;
        input [7:0]  len;
        begin
            wr_addr  = addr;
            wr_len   = len;
            wr_beat  = 9'd0;
            wr_valid = 1'b1;
            @(posedge clk);
            while (done_c[0] !== 1'b1) @(posedge clk);
            @(negedge clk);
            wr_valid = 1'b0;
            repeat (4) @(posedge clk);
        end
    endtask

    task automatic wait_bytes;
        input integer n;
        begin
            while (cap_n < n) @(posedge clk);
            repeat (6) @(posedge clk);
        end
    endtask

    task automatic expect_two;
        input integer at;
        input [7:0]   a;
        input [7:0]   b;
        begin
            if (cap[at] !== a || cap[at+1] !== b) begin
                tb_errors = tb_errors + 1;
                $display("  expected %02X %02X at %0d, got %02X %02X",
                         a, b, at, cap[at], cap[at+1]);
            end
        end
    endtask

    // -----------------------------------------------------------------
    // Status line expectation (S4): win_id = 0x1234 -> "04660"
    // -----------------------------------------------------------------
    reg [7:0] exp_line [0:60];
    integer   li;
    integer   tb_errors = 0;

    initial begin
        // "DIAG win=04660 locked=1 mel_done=1 npu_done=0 logits_valid=1\n"
        exp_line[0]  = 8'h44;  // 'D'
        exp_line[1]  = 8'h49;  // 'I'
        exp_line[2]  = 8'h41;  // 'A'
        exp_line[3]  = 8'h47;  // 'G'
        exp_line[4]  = 8'h20;  // ' '
        exp_line[5]  = 8'h77;  // 'w'
        exp_line[6]  = 8'h69;  // 'i'
        exp_line[7]  = 8'h6E;  // 'n'
        exp_line[8]  = 8'h3D;  // '='
        exp_line[9]  = 8'h30;  // '0'
        exp_line[10] = 8'h34;  // '4'
        exp_line[11] = 8'h36;  // '6'
        exp_line[12] = 8'h36;  // '6'
        exp_line[13] = 8'h30;  // '0'
        exp_line[14] = 8'h20;  // ' '
        exp_line[15] = 8'h6C;  // 'l'
        exp_line[16] = 8'h6F;  // 'o'
        exp_line[17] = 8'h63;  // 'c'
        exp_line[18] = 8'h6B;  // 'k'
        exp_line[19] = 8'h65;  // 'e'
        exp_line[20] = 8'h64;  // 'd'
        exp_line[21] = 8'h3D;  // '='
        exp_line[22] = 8'h31;  // '1'
        exp_line[23] = 8'h20;  // ' '
        exp_line[24] = 8'h6D;  // 'm'
        exp_line[25] = 8'h65;  // 'e'
        exp_line[26] = 8'h6C;  // 'l'
        exp_line[27] = 8'h5F;  // '_'
        exp_line[28] = 8'h64;  // 'd'
        exp_line[29] = 8'h6F;  // 'o'
        exp_line[30] = 8'h6E;  // 'n'
        exp_line[31] = 8'h65;  // 'e'
        exp_line[32] = 8'h3D;  // '='
        exp_line[33] = 8'h31;  // '1'
        exp_line[34] = 8'h20;  // ' '
        exp_line[35] = 8'h6E;  // 'n'
        exp_line[36] = 8'h70;  // 'p'
        exp_line[37] = 8'h75;  // 'u'
        exp_line[38] = 8'h5F;  // '_'
        exp_line[39] = 8'h64;  // 'd'
        exp_line[40] = 8'h6F;  // 'o'
        exp_line[41] = 8'h6E;  // 'n'
        exp_line[42] = 8'h65;  // 'e'
        exp_line[43] = 8'h3D;  // '='
        exp_line[44] = 8'h30;  // '0'
        exp_line[45] = 8'h20;  // ' '
        exp_line[46] = 8'h6C;  // 'l'
        exp_line[47] = 8'h6F;  // 'o'
        exp_line[48] = 8'h67;  // 'g'
        exp_line[49] = 8'h69;  // 'i'
        exp_line[50] = 8'h74;  // 't'
        exp_line[51] = 8'h73;  // 's'
        exp_line[52] = 8'h5F;  // '_'
        exp_line[53] = 8'h76;  // 'v'
        exp_line[54] = 8'h61;  // 'a'
        exp_line[55] = 8'h6C;  // 'l'
        exp_line[56] = 8'h69;  // 'i'
        exp_line[57] = 8'h64;  // 'd'
        exp_line[58] = 8'h3D;  // '='
        exp_line[59] = 8'h31;  // '1'
        exp_line[60] = 8'h0A;  // '\n'

        $display("=== tb_diag_readback start ===");
    end

    // -----------------------------------------------------------------
    // Main sequence
    // -----------------------------------------------------------------
    integer k;
    integer err_base;
    integer total_errors;

    initial begin
        repeat (20) @(posedge clk);
        rst_n = 1'b1;
        repeat (20) @(posedge clk);

        // ---- prefill: 4 KB at 0x000000, 512 B at 0x00200000 ----
        for (k = 0; k < 8; k = k + 1)
            ddr_write(k * 28'h200, 8'd15);      // 16 beats = 512 B
        ddr_write(28'h200000, 8'd15);
        $display("  prefill done: obs_wr_beats=%0d obs_aw_hs=%0d",
                 obs_wr_beats, obs_aw_hs);

        // ---- S1: 4 KB read-back, 4 frames ----
        clear_cap;
        send_read_cmd(32'h0000_0000, 16'd1024, 1);
        while (mon_on) @(posedge clk);
        repeat (400) @(posedge clk);
        if (cap_n != 4 * 264) begin
            tb_errors = tb_errors + 1;
            $display("  S1: captured %0d bytes, expected %0d", cap_n, 4 * 264);
        end
        $display("  S1: bytes=%0d mon_errors=%0d", cap_n, mon_errors);

        // ---- S2: bad lengths ----
        err_base = tb_errors;
        clear_cap;
        send_read_cmd(32'h0000_0000, 16'd300, 0);   // not a 256 B multiple
        wait_bytes(2);
        expect_two(0, 8'h4E, 8'h31);                // 'N' '1'
        repeat (20) @(posedge clk);

        clear_cap;
        send_read_cmd(32'h0000_0000, 16'd0, 0);     // len == 0
        wait_bytes(2);
        expect_two(0, 8'h4E, 8'h33);                // 'N' '3'
        repeat (20) @(posedge clk);
        $display("  S2: errors=%0d", tb_errors - err_base);

        // ---- S3: illegal command ----
        err_base = tb_errors;
        clear_cap;
        send_rx_byte(8'h41);                        // 'A'
        wait_bytes(2);
        expect_two(0, 8'h4E, 8'h32);                // 'N' '2'
        repeat (20) @(posedge clk);
        $display("  S3: errors=%0d", tb_errors - err_base);

        // ---- S4: lock / unlock / status line ----
        err_base = tb_errors;
        win_id       = 16'h1234;
        mel_done     = 1'b1;
        npu_done     = 1'b0;
        logits_valid = 1'b1;

        clear_cap;
        send_rx_byte(8'h4C);                        // 'L'
        wait_bytes(1);
        if (cap[0] !== 8'h4B) begin
            tb_errors = tb_errors + 1;
            $display("  S4: 'L' reply %02X, expected 4B", cap[0]);
        end
        if (diag_lock !== 1'b1) begin
            tb_errors = tb_errors + 1;
            $display("  S4: diag_lock not set by 'L'");
        end
        repeat (20) @(posedge clk);

        clear_cap;
        send_rx_byte(8'h53);                        // 'S'
        wait_bytes(61);
        if (cap_n != 61) begin
            tb_errors = tb_errors + 1;
            $display("  S4: status line length %0d, expected 61", cap_n);
        end
        for (li = 0; li < 61; li = li + 1) begin
            if (cap[li] !== exp_line[li]) begin
                tb_errors = tb_errors + 1;
                $display("  S4: status byte %0d got %02X exp %02X",
                         li, cap[li], exp_line[li]);
            end
        end
        $display("  S4: status line compared");
        repeat (20) @(posedge clk);

        clear_cap;
        send_rx_byte(8'h55);                        // 'U'
        wait_bytes(1);
        if (cap[0] !== 8'h4B || diag_lock !== 1'b0) begin
            tb_errors = tb_errors + 1;
            $display("  S4: 'U' reply %02X lock %0d", cap[0], diag_lock);
        end
        repeat (20) @(posedge clk);
        $display("  S4: errors=%0d", tb_errors - err_base);

        // ---- S5: feat region 0x0020_0000, 512 B, 2 frames ----
        err_base = mon_errors;
        clear_cap;
        send_read_cmd(32'h0020_0000, 16'd512, 1);
        while (mon_on) @(posedge clk);
        repeat (400) @(posedge clk);
        if (cap_n != 2 * 264) begin
            tb_errors = tb_errors + 1;
            $display("  S5: captured %0d bytes, expected %0d", cap_n, 2 * 264);
        end
        $display("  S5: bytes=%0d mon_errors=%0d", cap_n, mon_errors - err_base);

        // ---- S6: 'G' returns the full logit vector as one frame ----
        err_base = tb_errors;
        logits_hold[31:0]   = -32'sd7;
        logits_hold[63:32]  = 32'sd1;
        logits_hold[95:64]  = -32'sd224;
        logits_hold[127:96] = 32'sd0;
        logits_hold[159:128]= -32'sd1;
        logits_hold[191:160]= 32'sd42;
        logits_hold[223:192]= -32'sd1000;
        logits_hold[255:224]= 32'sd7;
        clear_cap;
        send_rx_byte(8'h47);                        // 'G'
        wait_bytes(264);
        if (cap_n != 264) begin
            tb_errors = tb_errors + 1;
            $display("  S6: 'G' frame length %0d, expected 264", cap_n);
        end else begin
            if (cap[0] !== 8'hAA || cap[1] !== 8'h55 ||
                cap[4] !== 8'h00 || cap[5] !== 8'h01) begin
                tb_errors = tb_errors + 1;
                $display("  S6: frame header %02X %02X len %02X%02X",
                         cap[0], cap[1], cap[5], cap[4]);
            end
            // payload starts at offset 6; the 8 logits occupy the first
            // 32 payload bytes in little-endian order.
            for (li = 0; li < 32; li = li + 1) begin
                if (cap[6 + li] !== logits_hold[li*8 +: 8]) begin
                    tb_errors = tb_errors + 1;
                    $display("  S6: logit byte %0d got %02X exp %02X",
                             li, cap[6 + li], logits_hold[li*8 +: 8]);
                end
            end
        end
        $display("  S6: errors=%0d", tb_errors - err_base);

        // ---- controller health ----
        if (addr_err !== 4'b0000) begin
            tb_errors = tb_errors + 1;
            $display("  ddr3 controller addr_err=%b", addr_err);
        end
        if (to_err !== 1'b0) begin
            tb_errors = tb_errors + 1;
            $display("  ddr3 controller timeout, dbg_to_state=%0d", dbg_to_state);
        end
        $display("  ar_hs=%0d rd_beats=%0d aw_hs=%0d",
                 obs_ar_hs, obs_rd_beats, obs_aw_hs);

        repeat (50) @(posedge clk);
        total_errors = mon_errors + tb_errors;
        if (total_errors == 0) $display("RESULT: PASS diag_readback");
        else                   $display("RESULT: FAIL diag_readback (%0d errors)",
                                        total_errors);
        $finish;
    end

    // Absolute watchdog.
    initial begin
        repeat (20000000) @(posedge clk);
        $display("RESULT: FAIL diag_readback (watchdog)");
        $finish;
    end

endmodule