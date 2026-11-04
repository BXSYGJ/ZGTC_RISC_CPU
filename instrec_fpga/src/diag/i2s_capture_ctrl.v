// -----------------------------------------------------------------------------
// File    : i2s_capture_ctrl.v
// Module  : i2s_capture_ctrl
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Application layer of the board I2S capture top (top_i2s_capture).
//
// UART command protocol v0 (single-byte commands, 115200 8N1, core domain):
//   'C' (0x43) start a fixed-length capture of CAP_WORDS stereo words.
//              Ignored while a capture is already running. On completion the
//              controller prints "CAPDONE <frame_cnt>" (hex8) where frame_cnt
//              is the number of 256-byte DDR3 frames (CAP_WORDS/64).
//   'R' (0x52) + seq_lo + seq_hi: export one 256-byte frame. Valid only in
//              the done state; the two seq bytes are always drained. The
//              frame is sent in the weight_loader wire format
//              AA 55 seq[2] len[2]=256 payload[256] crc16[2] (CRC-16/CCITT
//              -FALSE over seq+len+payload), then 'K' is expected within
//              ACK_TIMEOUT_CYCLES (a timeout does not block either). A seq
//              >= frame_cnt answers 'N'. During capture the request is
//              swallowed silently (answering would overflow the 16-deep CDC
//              FIFO: one status byte costs ~87 us = 4.2 stereo words).
//   'S' (0x53) print "CAPSTS state=<..> words=<hex8> frames=<hex8>
//              i2s_err=<hex8>" (state idle / capturing / done, padded to 9
//              characters; line length 72). Answered in idle and done only:
//              during capture the reply would stall the DDR write loop long
//              enough (6.3 ms at 115200) to overflow the CDC FIFO, so the
//              request is dropped - the capture progress stays visible on
//              the LEDs (heartbeat + capturing flag).
//
// Boot messages: "I2SCAP BOOT" after reset; "I2SCAP DDR OK" once pll_lock,
// ddr_init_done and ddrphy_cpd_lock are all high; or "I2SCAP DDR FAIL" after
// DDR_TIMEOUT_CYCLES. All text is generated from ASCII byte tables (no
// string literals; see the 2026-10 uart_debug string bit-order lesson).
//
// DDR3 master-0 protocol (ddr3_ctrl_axi; audio_sink / weight_loader style):
//   write: one command per 64 words = 256 B, m0_cmd = {1'b1, addr, 8'd7}
//          (8 beats x 32 B), m0_cmd_valid held level-style until m0_done,
//          m0_wdata advances on every m0_wready_beat pulse, addr = frame*256.
//   read : one command per exported frame, m0_cmd = {1'b0, seq<<8, 8'd7},
//          m0_rd_ready high for the whole command, 8 beats collected from
//          m0_rd_valid, command closed by m0_done.
//   Capture phase only writes, export phase only reads (single-master time
//   sharing of port m0; no concurrent command is ever issued).
//
// Sample alignment: cap_gate is low from the 'C' accept cycle through the
// S_CLR drain window, so the CDC FIFO write side stops, stale entries are
// drained, then cap_gate rises. The first stereo pair after the gate rises
// is word 0 of the capture (frame-granular alignment, see top header).
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module i2s_capture_ctrl #(
    // Total captured 32-bit stereo words ({R[15:0], L[15:0]}). Must be a
    // multiple of 64 (one 256-byte DDR3 frame per write command).
    // Default: 196608 words = 4.096 s at 48 kHz stereo = 0xC0000 bytes,
    // 3072 frames of 256 B from DDR3 base 0x00000000.
    parameter [31:0] CAP_WORDS = 32'd196608,
    // UART baud divider, 125 MHz / 115200 = 1085 on the board.
    parameter integer BAUD_DIV = 1085,
    // Wait limit for the PC 'K' reply after one exported frame (100 ms).
    parameter [31:0] ACK_TIMEOUT_CYCLES = 32'd12500000,
    // Wait limit for DDR3 initialization (3 s).
    parameter [31:0] DDR_TIMEOUT_CYCLES = 32'd375000000
) (
    input  wire        clk,             // core_clk 125 MHz
    input  wire        rst_n,           // core-domain reset

    // UART byte channels (uart_rx / uart_tx, core domain)
    input  wire        rx_valid,
    input  wire [7:0]  rx_data,
    output reg         tx_valid,
    output reg  [7:0]  tx_data,
    input  wire        tx_ready,

    // Stereo sample stream from the CDC FIFO read side (core domain,
    // valid pulses one cycle after the FIFO read is accepted).
    input  wire        smp_valid,
    input  wire [31:0] smp_data,       // {R[15:0], L[15:0]}
    output wire        smp_rd_en,

    // i2s error telemetry: one-cycle pulse per rising edge of sd_idle
    input  wire        i2s_err_pulse,

    // DDR3 readiness (pll_lock & ddr_init_done & ddrphy_cpd_lock)
    input  wire        ddr_ready,

    // Capture gate into the 27 MHz FIFO write domain
    output reg         cap_gate,

    // Status (encoded in the CAPSTS line and the LEDs)
    output reg  [1:0]  cap_state,       // 0=idle 1=capturing 2=done
    output reg  [17:0] cap_word_cnt,
    output reg  [15:0] cap_i2s_err,

    // DDR3 master-0 port
    output reg         m0_cmd_valid,
    output reg  [36:0] m0_cmd,          // {wr, addr[27:0], len[7:0]}
    output reg  [255:0] m0_wdata,
    input  wire        m0_wready_beat,
    input  wire [255:0] m0_rd_data,
    output reg         m0_rd_ready,
    input  wire        m0_rd_valid,
    input  wire        m0_done
);

    // ------------------------------------------------------------------
    // Local parameters
    // ------------------------------------------------------------------
    localparam [31:0] FRAME_TOTAL = CAP_WORDS >> 6;   // 256 B frames
    localparam [15:0] FRAME_TOTAL_16 = FRAME_TOTAL[15:0];
    localparam [31:0] CLR_CYCLES  = 32'd32;           // drain window

    // Main FSM states
    localparam [3:0] S_BOOTF   = 4'd0;   // fill + send BOOT line
    localparam [3:0] S_WAITDDR = 4'd1;   // wait for DDR3 init
    localparam [3:0] S_CMD     = 4'd2;   // command service loop
    localparam [3:0] S_RSEQ0   = 4'd3;   // 'R': collect seq low byte
    localparam [3:0] S_RSEQ1   = 4'd4;   // 'R': collect seq high byte
    localparam [3:0] S_RCHK    = 4'd5;   // 'R': validate seq, dispatch
    localparam [3:0] S_CLR     = 4'd6;   // drain stale FIFO entries
    localparam [3:0] S_ACC     = 4'd7;   // accumulate 64 words
    localparam [3:0] S_WR      = 4'd8;   // one 256 B write command
    localparam [3:0] S_RDCMD   = 4'd9;   // issue one read command
    localparam [3:0] S_RD      = 4'd10;  // collect 8 read beats
    localparam [3:0] S_ACKW    = 4'd11;  // wait for PC 'K'
    localparam [3:0] S_TXWAIT  = 4'd12;  // wait for the TX engine
    localparam [3:0] S_STSFILL = 4'd13;  // build the CAPSTS line

    // TX stream sources
    localparam [1:0] TXS_NONE  = 2'd0;
    localparam [1:0] TXS_LINE  = 2'd1;
    localparam [1:0] TXS_FRAME = 2'd2;
    localparam [1:0] TXS_BYTE  = 2'd3;

    // ------------------------------------------------------------------
    // CRC-16/CCITT-FALSE single byte step (copied from weight_loader).
    // ------------------------------------------------------------------
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

    function [7:0] hex_ascii;
        input [3:0] n;
        begin
            hex_ascii = (n < 4'd10) ? (8'h30 + {4'd0, n})
                                    : (8'h37 + {4'd0, n});
        end
    endfunction

    // ------------------------------------------------------------------
    // State and data registers
    // ------------------------------------------------------------------
    reg [3:0]   state;
    reg [3:0]   ret_state;      // S_TXWAIT return state
    reg [3:0]   rret_state;     // 'R' drain return state (S_CMD / S_ACC)
    reg [15:0]  rd_seq;         // export frame index
    reg [5:0]   clr_cnt;        // S_CLR drain counter
    reg [6:0]   beat_wptr;      // 0..63 within the current write frame
    reg [2:0]   beat_rptr;      // 0..7 beat index of the write command
    reg [11:0]  wr_frame;       // completed write frames
    reg [2:0]   rd_beats;       // beats collected by the read command
    reg [15:0]  crc_val;        // running CRC of the exported frame
    reg [31:0]  ack_timer;
    reg [31:0]  ddr_timer;

    reg [255:0] beat_buf [0:7];  // 64-word staging buffer (8 beats)
    reg [255:0] exp_buf  [0:7];  // 256 B read-back buffer

    // ASCII line buffer (longest line = CAPSTS, 72 bytes)
    reg [7:0]   tx_line [0:95];

    // TX byte engine (weight_loader S_TX handshake: one-cycle strobe plus
    // a full ready low-then-high period, see weight_loader.v header note)
    reg [1:0]   tx_src;
    reg [8:0]   tx_pos;
    reg [8:0]   tx_len;
    reg [7:0]   tx_single;
    reg         tx_go;
    reg         tx_busy;
    reg         tx_fin;
    reg         tx_pend;
    reg         tx_saw_low;

    // Combinational write data (stable during the whole write command,
    // advances on every accepted beat).
    always @* m0_wdata = beat_buf[beat_rptr];
    // Byte offset of the 32-bit slot inside the selected 256-bit beat.
    wire [7:0] bslot_of = {5'd0, beat_wptr[2:0]} * 8'd32;

    assign smp_rd_en = (state == S_CLR) || (state == S_ACC);

    // ------------------------------------------------------------------
    // Export frame byte selector: AA 55 seq len payload crc16 (264 bytes)
    // ------------------------------------------------------------------
    reg [7:0] tx_byte_sel;
    always @* begin
        tx_byte_sel = 8'h00;
        if (tx_src == TXS_LINE) begin
            tx_byte_sel = tx_line[tx_pos[6:0]];
        end else if (tx_src == TXS_FRAME) begin
            if (tx_pos == 9'd0)       tx_byte_sel = 8'hAA;
            else if (tx_pos == 9'd1)  tx_byte_sel = 8'h55;
            else if (tx_pos == 9'd2)  tx_byte_sel = rd_seq[7:0];
            else if (tx_pos == 9'd3)  tx_byte_sel = rd_seq[15:8];
            else if (tx_pos == 9'd4)  tx_byte_sel = 8'h00;  // len low = 256
            else if (tx_pos == 9'd5)  tx_byte_sel = 8'h01;  // len high
            else if (tx_pos <= 9'd261)
                tx_byte_sel = exp_buf[(tx_pos - 9'd6) >> 5]
                              [((tx_pos - 9'd6) & 9'd31) * 8 +: 8];
            else if (tx_pos == 9'd262) tx_byte_sel = crc_val[7:0];
            else                       tx_byte_sel = crc_val[15:8];
        end else begin
            tx_byte_sel = tx_single;
        end
    end

    // CRC seed over seq + len before the payload beats arrive.
    wire [15:0] crc_pre = crc16_step(
        crc16_step(crc16_step(crc16_step(16'hFFFF, rd_seq[7:0]),
        rd_seq[15:8]), 8'h00), 8'h01);

    // CRC advance for one 256-bit read beat (32 bytes, low byte first).
    wire [15:0] c1  = crc16_step(crc_val, m0_rd_data[7:0]);
    wire [15:0] c2  = crc16_step(c1, m0_rd_data[15:8]);
    wire [15:0] c3  = crc16_step(c2, m0_rd_data[23:16]);
    wire [15:0] c4  = crc16_step(c3, m0_rd_data[31:24]);
    wire [15:0] c5  = crc16_step(c4, m0_rd_data[39:32]);
    wire [15:0] c6  = crc16_step(c5, m0_rd_data[47:40]);
    wire [15:0] c7  = crc16_step(c6, m0_rd_data[55:48]);
    wire [15:0] c8  = crc16_step(c7, m0_rd_data[63:56]);
    wire [15:0] c9  = crc16_step(c8, m0_rd_data[71:64]);
    wire [15:0] c10 = crc16_step(c9, m0_rd_data[79:72]);
    wire [15:0] c11 = crc16_step(c10, m0_rd_data[87:80]);
    wire [15:0] c12 = crc16_step(c11, m0_rd_data[95:88]);
    wire [15:0] c13 = crc16_step(c12, m0_rd_data[103:96]);
    wire [15:0] c14 = crc16_step(c13, m0_rd_data[111:104]);
    wire [15:0] c15 = crc16_step(c14, m0_rd_data[119:112]);
    wire [15:0] c16 = crc16_step(c15, m0_rd_data[127:120]);
    wire [15:0] c17 = crc16_step(c16, m0_rd_data[135:128]);
    wire [15:0] c18 = crc16_step(c17, m0_rd_data[143:136]);
    wire [15:0] c19 = crc16_step(c18, m0_rd_data[151:144]);
    wire [15:0] c20 = crc16_step(c19, m0_rd_data[159:152]);
    wire [15:0] c21 = crc16_step(c20, m0_rd_data[167:160]);
    wire [15:0] c22 = crc16_step(c21, m0_rd_data[175:168]);
    wire [15:0] c23 = crc16_step(c22, m0_rd_data[183:176]);
    wire [15:0] c24 = crc16_step(c23, m0_rd_data[191:184]);
    wire [15:0] c25 = crc16_step(c24, m0_rd_data[199:192]);
    wire [15:0] c26 = crc16_step(c25, m0_rd_data[207:200]);
    wire [15:0] c27 = crc16_step(c26, m0_rd_data[215:208]);
    wire [15:0] c28 = crc16_step(c27, m0_rd_data[223:216]);
    wire [15:0] c29 = crc16_step(c28, m0_rd_data[231:224]);
    wire [15:0] c30 = crc16_step(c29, m0_rd_data[239:232]);
    wire [15:0] c31 = crc16_step(c30, m0_rd_data[247:240]);
    wire [15:0] c32 = crc16_step(c31, m0_rd_data[255:248]);

    // ------------------------------------------------------------------
    // TX byte engine
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tx_src     <= TXS_NONE;
            tx_pos     <= 9'd0;
            tx_len     <= 9'd0;
            tx_single  <= 8'd0;
            tx_go      <= 1'b0;
            tx_busy    <= 1'b0;
            tx_fin     <= 1'b0;
            tx_pend    <= 1'b0;
            tx_saw_low <= 1'b0;
            tx_valid   <= 1'b0;
            tx_data    <= 8'd0;
        end else begin
            tx_go    <= 1'b0;
            tx_fin   <= 1'b0;
            tx_valid <= 1'b0;   // single-cycle strobe (weight_loader note)

            if (tx_go) begin
                tx_busy <= 1'b1;
                tx_pos  <= 9'd0;
            end else if (tx_busy) begin
                if (!tx_pend) begin
                    if (tx_ready) begin
                        tx_data    <= tx_byte_sel;
                        tx_valid   <= 1'b1;   // single-cycle strobe
                        tx_pend    <= 1'b1;
                        tx_saw_low <= 1'b0;
                    end
                end else if (!tx_ready) begin
                    tx_saw_low <= 1'b1;       // frame is being shifted out
                end else if (tx_saw_low) begin
                    tx_pend    <= 1'b0;
                    tx_saw_low <= 1'b0;
                    if (tx_pos == tx_len - 9'd1) begin
                        tx_busy <= 1'b0;
                        tx_fin  <= 1'b1;
                    end else begin
                        tx_pos <= tx_pos + 9'd1;
                    end
                end
            end
        end
    end

    // ------------------------------------------------------------------
    // Status helpers
    // ------------------------------------------------------------------
    wire [31:0] words_hex  = {14'd0, cap_word_cnt};
    wire [31:0] frames_hex = {20'd0, cap_word_cnt[17:6]};
    wire [31:0] errs_hex   = {16'd0, cap_i2s_err};

    // ------------------------------------------------------------------
    // Main FSM
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= S_BOOTF;
            ret_state    <= S_CMD;
            rret_state   <= S_CMD;
            rd_seq       <= 16'd0;
            clr_cnt      <= 6'd0;
            beat_wptr    <= 6'd0;
            beat_rptr    <= 3'd0;
            wr_frame     <= 12'd0;
            rd_beats     <= 3'd0;
            crc_val      <= 16'hFFFF;
            ack_timer    <= 32'd0;
            ddr_timer    <= 32'd0;
            cap_gate     <= 1'b0;
            cap_state    <= 2'd0;
            cap_word_cnt <= 18'd0;
            cap_i2s_err  <= 16'd0;
            m0_cmd_valid <= 1'b0;
            m0_cmd       <= 37'd0;
            m0_rd_ready  <= 1'b0;
        end else begin
            // Telemetry
            if (i2s_err_pulse) cap_i2s_err <= cap_i2s_err + 16'd1;

            case (state)
                // ---- boot banner --------------------------------------
                S_BOOTF: begin
                    // "I2SCAP BOOT\n"
                    tx_line[0]  <= 8'h49;  // I
                    tx_line[1]  <= 8'h32;  // 2
                    tx_line[2]  <= 8'h53;  // S
                    tx_line[3]  <= 8'h43;  // C
                    tx_line[4]  <= 8'h41;  // A
                    tx_line[5]  <= 8'h50;  // P
                    tx_line[6]  <= 8'h20;  // (space)
                    tx_line[7]  <= 8'h42;  // B
                    tx_line[8]  <= 8'h4F;  // O
                    tx_line[9]  <= 8'h4F;  // O
                    tx_line[10] <= 8'h54;  // T
                    tx_line[11] <= 8'h0A;  // \n
                    tx_src      <= TXS_LINE;
                    tx_len      <= 9'd12;
                    tx_go       <= 1'b1;
                    ret_state   <= S_WAITDDR;
                    ddr_timer   <= 32'd0;
                    state       <= S_TXWAIT;
                end

                S_WAITDDR: begin
                    if (ddr_ready) begin
                        // "I2SCAP DDR OK\n"
                        tx_line[0]  <= 8'h49;  // I
                        tx_line[1]  <= 8'h32;  // 2
                        tx_line[2]  <= 8'h53;  // S
                        tx_line[3]  <= 8'h43;  // C
                        tx_line[4]  <= 8'h41;  // A
                        tx_line[5]  <= 8'h50;  // P
                        tx_line[6]  <= 8'h20;  // (space)
                        tx_line[7]  <= 8'h44;  // D
                        tx_line[8]  <= 8'h44;  // D
                        tx_line[9]  <= 8'h52;  // R
                        tx_line[10] <= 8'h20;  // (space)
                        tx_line[11] <= 8'h4F;  // O
                        tx_line[12] <= 8'h4B;  // K
                        tx_line[13] <= 8'h0A;  // \n
                        tx_src      <= TXS_LINE;
                        tx_len      <= 9'd14;
                        tx_go       <= 1'b1;
                        ret_state   <= S_CMD;
                        state       <= S_TXWAIT;
                    end else if (ddr_timer >= DDR_TIMEOUT_CYCLES - 32'd1) begin
                        // "I2SCAP DDR FAIL\n"
                        tx_line[0]  <= 8'h49;  // I
                        tx_line[1]  <= 8'h32;  // 2
                        tx_line[2]  <= 8'h53;  // S
                        tx_line[3]  <= 8'h43;  // C
                        tx_line[4]  <= 8'h41;  // A
                        tx_line[5]  <= 8'h50;  // P
                        tx_line[6]  <= 8'h20;  // (space)
                        tx_line[7]  <= 8'h44;  // D
                        tx_line[8]  <= 8'h44;  // D
                        tx_line[9]  <= 8'h52;  // R
                        tx_line[10] <= 8'h20;  // (space)
                        tx_line[11] <= 8'h46;  // F
                        tx_line[12] <= 8'h41;  // A
                        tx_line[13] <= 8'h49;  // I
                        tx_line[14] <= 8'h4C;  // L
                        tx_line[15] <= 8'h0A;  // \n
                        tx_src      <= TXS_LINE;
                        tx_len      <= 9'd16;
                        tx_go       <= 1'b1;
                        ret_state   <= S_CMD;
                        state       <= S_TXWAIT;
                    end else begin
                        ddr_timer <= ddr_timer + 32'd1;
                    end
                end

                // ---- command service loop (idle / done) ----------------
                S_CMD: begin
                    if (rx_valid) begin
                        if (rx_data == 8'h43) begin
                            // 'C': accept unless already capturing
                            if ((cap_state != 2'd1) && ddr_ready) begin
                                cap_word_cnt <= 18'd0;
                                wr_frame     <= 12'd0;
                                cap_state    <= 2'd1;
                                cap_gate     <= 1'b0;
                                clr_cnt      <= 6'd0;
                                state        <= S_CLR;
                            end
                        end else if (rx_data == 8'h52) begin
                            rret_state <= S_CMD;
                            state      <= S_RSEQ0;
                        end else if (rx_data == 8'h53) begin
                            state <= S_STSFILL;
                        end
                    end
                end

                // ---- 'R' seq collection (bytes always drained) ---------
                S_RSEQ0: begin
                    if (rx_valid) begin
                        rd_seq <= {8'd0, rx_data};
                        state  <= S_RSEQ1;
                    end
                end

                S_RSEQ1: begin
                    if (rx_valid) begin
                        rd_seq <= {rx_data, rd_seq[7:0]};
                        state  <= S_RCHK;
                    end
                end

                S_RCHK: begin
                    if (cap_state != 2'd2) begin
                        // Capture in progress or idle: swallow silently.
                        state <= rret_state;
                    end else if (rd_seq >= FRAME_TOTAL_16) begin
                        // Out of range: answer 'N'.
                        tx_single  <= 8'h4E;
                        tx_src     <= TXS_BYTE;
                        tx_len     <= 9'd1;
                        tx_go      <= 1'b1;
                        ret_state  <= rret_state;
                        state      <= S_TXWAIT;
                    end else begin
                        state <= S_RDCMD;
                    end
                end

                // ---- CAPSTS line fill ----------------------------------
                // Layout (72 bytes, fixed width):
                //   "CAPSTS state=" (13) + 9-char state + " words=" (7)
                //   + hex8 + " frames=" (8) + hex8 + " i2s_err=" (9)
                //   + hex8 + "\n"
                S_STSFILL: begin
                    tx_line[0]  <= 8'h43;  // C
                    tx_line[1]  <= 8'h41;  // A
                    tx_line[2]  <= 8'h50;  // P
                    tx_line[3]  <= 8'h53;  // S
                    tx_line[4]  <= 8'h54;  // T
                    tx_line[5]  <= 8'h53;  // S
                    tx_line[6]  <= 8'h20;  // (space)
                    tx_line[7]  <= 8'h73;  // s
                    tx_line[8]  <= 8'h74;  // t
                    tx_line[9]  <= 8'h61;  // a
                    tx_line[10] <= 8'h74;  // t
                    tx_line[11] <= 8'h65;  // e
                    tx_line[12] <= 8'h3D;  // =
                    if (cap_state == 2'd0) begin
                        // "idle     "
                        tx_line[13] <= 8'h69;  // i
                        tx_line[14] <= 8'h64;  // d
                        tx_line[15] <= 8'h6C;  // l
                        tx_line[16] <= 8'h65;  // e
                        tx_line[17] <= 8'h20;
                        tx_line[18] <= 8'h20;
                        tx_line[19] <= 8'h20;
                        tx_line[20] <= 8'h20;
                        tx_line[21] <= 8'h20;
                    end else if (cap_state == 2'd1) begin
                        // "capturing"
                        tx_line[13] <= 8'h63;  // c
                        tx_line[14] <= 8'h61;  // a
                        tx_line[15] <= 8'h70;  // p
                        tx_line[16] <= 8'h74;  // t
                        tx_line[17] <= 8'h75;  // u
                        tx_line[18] <= 8'h72;  // r
                        tx_line[19] <= 8'h69;  // i
                        tx_line[20] <= 8'h6E;  // n
                        tx_line[21] <= 8'h67;  // g
                    end else begin
                        // "done     "
                        tx_line[13] <= 8'h64;  // d
                        tx_line[14] <= 8'h6F;  // o
                        tx_line[15] <= 8'h6E;  // n
                        tx_line[16] <= 8'h65;  // e
                        tx_line[17] <= 8'h20;
                        tx_line[18] <= 8'h20;
                        tx_line[19] <= 8'h20;
                        tx_line[20] <= 8'h20;
                        tx_line[21] <= 8'h20;
                    end
                    tx_line[22] <= 8'h20;  // (space)
                    tx_line[23] <= 8'h77;  // w
                    tx_line[24] <= 8'h6F;  // o
                    tx_line[25] <= 8'h72;  // r
                    tx_line[26] <= 8'h64;  // d
                    tx_line[27] <= 8'h73;  // s
                    tx_line[28] <= 8'h3D;  // =
                    tx_line[29] <= hex_ascii(words_hex[31:28]);
                    tx_line[30] <= hex_ascii(words_hex[27:24]);
                    tx_line[31] <= hex_ascii(words_hex[23:20]);
                    tx_line[32] <= hex_ascii(words_hex[19:16]);
                    tx_line[33] <= hex_ascii(words_hex[15:12]);
                    tx_line[34] <= hex_ascii(words_hex[11:8]);
                    tx_line[35] <= hex_ascii(words_hex[7:4]);
                    tx_line[36] <= hex_ascii(words_hex[3:0]);
                    tx_line[37] <= 8'h20;  // (space)
                    tx_line[38] <= 8'h66;  // f
                    tx_line[39] <= 8'h72;  // r
                    tx_line[40] <= 8'h61;  // a
                    tx_line[41] <= 8'h6D;  // m
                    tx_line[42] <= 8'h65;  // e
                    tx_line[43] <= 8'h73;  // s
                    tx_line[44] <= 8'h3D;  // =
                    tx_line[45] <= hex_ascii(frames_hex[31:28]);
                    tx_line[46] <= hex_ascii(frames_hex[27:24]);
                    tx_line[47] <= hex_ascii(frames_hex[23:20]);
                    tx_line[48] <= hex_ascii(frames_hex[19:16]);
                    tx_line[49] <= hex_ascii(frames_hex[15:12]);
                    tx_line[50] <= hex_ascii(frames_hex[11:8]);
                    tx_line[51] <= hex_ascii(frames_hex[7:4]);
                    tx_line[52] <= hex_ascii(frames_hex[3:0]);
                    tx_line[53] <= 8'h20;  // (space)
                    tx_line[54] <= 8'h69;  // i
                    tx_line[55] <= 8'h32;  // 2
                    tx_line[56] <= 8'h73;  // s
                    tx_line[57] <= 8'h5F;  // _
                    tx_line[58] <= 8'h65;  // e
                    tx_line[59] <= 8'h72;  // r
                    tx_line[60] <= 8'h72;  // r
                    tx_line[61] <= 8'h3D;  // =
                    tx_line[62] <= hex_ascii(errs_hex[31:28]);
                    tx_line[63] <= hex_ascii(errs_hex[27:24]);
                    tx_line[64] <= hex_ascii(errs_hex[23:20]);
                    tx_line[65] <= hex_ascii(errs_hex[19:16]);
                    tx_line[66] <= hex_ascii(errs_hex[15:12]);
                    tx_line[67] <= hex_ascii(errs_hex[11:8]);
                    tx_line[68] <= hex_ascii(errs_hex[7:4]);
                    tx_line[69] <= hex_ascii(errs_hex[3:0]);
                    tx_line[70] <= 8'h0A;  // \n
                    tx_src      <= TXS_LINE;
                    tx_len      <= 9'd71;
                    tx_go       <= 1'b1;
                    ret_state   <= S_CMD;
                    state       <= S_TXWAIT;
                end

                // ---- capture drain / accumulate / write ----------------
                S_CLR: begin
                    // cap_gate is low; smp_rd_en drains the FIFO.
                    if (clr_cnt == CLR_CYCLES - 6'd1) begin
                        cap_gate <= 1'b1;
                        state    <= S_ACC;
                    end else begin
                        clr_cnt <= clr_cnt + 6'd1;
                    end
                end

                S_ACC: begin
                    // During capture only 'R' is drained (silently);
                    // 'C' and 'S' are ignored - see the header note.
                    if (rx_valid && (rx_data == 8'h52)) begin
                        rret_state <= S_ACC;
                        state      <= S_RSEQ0;
                    end else if (smp_valid) begin
                        // 8-bit slot offset: 7 * 32 = 224 must not wrap at
                        // 6 bits (a 6-bit product truncated slots 2..7 onto
                        // slots 0/1, leaving 192 of the 256 bits unwritten).
                        beat_buf[beat_wptr[5:3]][bslot_of +: 32] <= smp_data;
                        cap_word_cnt <= cap_word_cnt + 18'd1;
                        if (beat_wptr == 6'd63) begin
                            beat_rptr    <= 3'd0;
                            // 37-bit bundle {wr, addr[27:0], len[7:0]}:
                            // addr = wr_frame * 256 (8'd0 + 12-bit frame + 8'h00).
                            m0_cmd       <= {1'b1, 8'd0, wr_frame, 8'h00, 8'd7};
                            m0_cmd_valid <= 1'b1;
                            state        <= S_WR;
                        end else begin
                            beat_wptr <= beat_wptr + 6'd1;
                        end
                    end
                end

                S_WR: begin
                    if (m0_wready_beat) begin
                        beat_rptr <= beat_rptr + 3'd1;
                    end
                    if (m0_done) begin
                        m0_cmd_valid <= 1'b0;
                        wr_frame     <= wr_frame + 12'd1;
                        beat_wptr    <= 6'd0;
                        beat_rptr    <= 3'd0;
                        if (cap_word_cnt == CAP_WORDS) begin
                            cap_state <= 2'd2;
                            cap_gate  <= 1'b0;
                            // "CAPDONE " + hex8 frame count + "\n" (17 B)
                            tx_line[0]  <= 8'h43;  // C
                            tx_line[1]  <= 8'h41;  // A
                            tx_line[2]  <= 8'h50;  // P
                            tx_line[3]  <= 8'h44;  // D
                            tx_line[4]  <= 8'h4F;  // O
                            tx_line[5]  <= 8'h4E;  // N
                            tx_line[6]  <= 8'h45;  // E
                            tx_line[7]  <= 8'h20;  // (space)
                            tx_line[8]  <= hex_ascii(FRAME_TOTAL[31:28]);
                            tx_line[9]  <= hex_ascii(FRAME_TOTAL[27:24]);
                            tx_line[10] <= hex_ascii(FRAME_TOTAL[23:20]);
                            tx_line[11] <= hex_ascii(FRAME_TOTAL[19:16]);
                            tx_line[12] <= hex_ascii(FRAME_TOTAL[15:12]);
                            tx_line[13] <= hex_ascii(FRAME_TOTAL[11:8]);
                            tx_line[14] <= hex_ascii(FRAME_TOTAL[7:4]);
                            tx_line[15] <= hex_ascii(FRAME_TOTAL[3:0]);
                            tx_line[16] <= 8'h0A;  // \n
                            tx_src      <= TXS_LINE;
                            tx_len      <= 9'd17;
                            tx_go       <= 1'b1;
                            ret_state   <= S_CMD;
                            state       <= S_TXWAIT;
                        end else begin
                            state <= S_ACC;
                        end
                    end
                end

                // ---- export read command ------------------------------
                S_RDCMD: begin
                    // 37-bit bundle {wr, addr[27:0], len[7:0]}:
                    // addr = rd_seq * 256 (8'd0 + 12-bit frame + 8'h00).
                    m0_cmd       <= {1'b0, 8'd0, rd_seq, 8'h00, 8'd7};
                    m0_cmd_valid <= 1'b1;
                    m0_rd_ready  <= 1'b1;
                    rd_beats     <= 3'd0;
                    crc_val      <= crc_pre;
                    state        <= S_RD;
                end

                S_RD: begin
                    if (m0_rd_valid) begin
                        exp_buf[rd_beats] <= m0_rd_data;
                        crc_val  <= c32;
                        rd_beats <= rd_beats + 3'd1;
                    end
                    if (m0_done) begin
                        m0_cmd_valid <= 1'b0;
                        m0_rd_ready  <= 1'b0;
                        tx_src       <= TXS_FRAME;
                        tx_len       <= 9'd264;
                        tx_go        <= 1'b1;
                        ret_state    <= S_ACKW;
                        ack_timer    <= 32'd0;
                        state        <= S_TXWAIT;
                    end
                end

                S_ACKW: begin
                    if (rx_valid && rx_data == 8'h4B) begin
                        state <= S_CMD;
                    end else if (ack_timer >= ACK_TIMEOUT_CYCLES - 32'd1) begin
                        state <= S_CMD;
                    end else begin
                        ack_timer <= ack_timer + 32'd1;
                    end
                end

                // ---- TX engine wait ------------------------------------
                S_TXWAIT: begin
                    if (tx_fin) begin
                        state <= ret_state;
                    end
                end

                default: state <= S_CMD;
            endcase
        end
    end

endmodule
