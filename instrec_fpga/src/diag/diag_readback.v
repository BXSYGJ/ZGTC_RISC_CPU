// ---------------------------------------------------------------------------
// diag_readback.v -- board read-back diagnostic channel (UART <-> DDR3 m3)
// ---------------------------------------------------------------------------
// Design basis: docs/DIAG_READBACK_PLAN_20261110.md (one bitstream, many
// read-back experiments).  The PC locks the audio window, then pulls any
// DDR3 region back over the existing 115200 baud UART frame protocol, so the
// golden chain can be compared segment by segment without rebuilding.
//
// Commands (one ASCII byte, core clock domain, BAUD_DIV 1085):
//   'L' 0x4C : diag_lock <= 1, reply 'K'
//   'U' 0x55 : diag_lock <= 0, reply 'K'
//   'S' 0x53 : reply one fixed 61-byte status line:
//              "DIAG win=WWWWW locked=D mel_done=D npu_done=D logits_valid=D\n"
//              WWWWW is win_id as five zero padded decimal digits; D is 0/1.
//   'R' 0x52 : followed by addr[31:0] LE and len[15:0] LE, no CRC on the
//              command itself.  len must be a non-zero multiple of 256,
//              otherwise 'N' + '1' (len == 0 replies 'N' + '3'; the 16 bit
//              length field can never exceed 1 MB, see the plan note).
//   any other byte : reply 'N' + '2'.
//
// Read-back framing (same 256 B frame as weight_loader):
//   0xAA 0x55 | seq[2] LE | len[2] LE (= 0x0100) | payload[256] | crc16[2]
//   seq counts frames inside one 'R' command, starting at 0.
//   payload is the DDR3 byte stream in ascending address order; every
//   256-bit beat expands little endian (bits 7:0 first).
//   crc16 = CRC-16/CCITT-FALSE (init 0xFFFF, poly 0x1021) over seq, len and
//   payload, transmitted little endian.
//   After each frame the module waits for the PC's 'K' (100 ms timeout, then
//   the next frame is fetched anyway; the PC owns the flow control).
//
// DDR3 master 3 (read only; self_test master during inference):
//   one command per 256 B frame.  The command bundle is
//   {wr(1), addr[27:0], len[7:0]} with len = beats-1 and 32 B per beat
//   (see the ddr3_ctrl_axi.v header), so a 256 B frame is len = 7 (8 beats).
//   Production mel reads use len = 15 (16 beats = 512 B, mel_engine.v), i.e.
//   half of one production command per diagnostic frame.
//   m3_cmd_valid is held until m3_done; m3_rd_ready paces the controller's
//   elastic read fifo (the IP itself has no rready).
//
// Storage: the 256 B frame lives in eight 256-bit registers, the same 2 KiB
// the weight_loader frame engine uses (distributed RAM, no new block RAM).
//
// diag_lock is a plain level output used by the audio_sink side; this module
// does not gate frame events itself.
//
// Text is rendered from explicit ASCII case tables only: no string literal
// appears here (PDS string literal byte order is not reproducible, see the
// uart_debug.v incident in HANDOFF_SNAPSHOT_20261027.md).
// ---------------------------------------------------------------------------
module diag_readback #(
    // PC 'K' flow-control timeout: 12500000 cycles = 100 ms at 125 MHz.
    parameter integer ACK_TIMEOUT = 12500000
) (
    input  wire         clk,          // core_clk 125 MHz
    input  wire         rst_n,        // core-domain reset, sync release

    // UART byte channel (from uart_rx / to uart_tx, top level arbitrates)
    input  wire         rx_valid,
    input  wire [7:0]   rx_data,
    output reg          tx_valid,
    output reg  [7:0]   tx_data,
    input  wire         tx_ready,

    // DDR3 master-3 (read only): {wr, addr[27:0], len[7:0]}
    output reg          m3_cmd_valid,
    output reg  [36:0]  m3_cmd,
    input  wire [255:0] m3_rd_data,
    input  wire         m3_rd_valid,
    output reg          m3_rd_ready,
    input  wire         m3_done,

    // window lock request (audio_sink freezes new frames while high)
    output reg          diag_lock,

    // status snapshot inputs
    input  wire [15:0]  win_id,
    input  wire         mel_done,
    input  wire         npu_done,
    input  wire         logits_valid,
    // Full 8-lane logit vector (8 x int32) of the last completed window; the
    // 'G' command returns it as one 256-byte frame without touching DDR.
    input  wire [255:0] logits_in
);

    // ------------------------------------------------------------------
    // Constants
    // ------------------------------------------------------------------
    localparam [2:0] S_IDLE    = 3'd0;   // waiting for a command byte
    localparam [2:0] S_ARG     = 3'd1;   // collecting addr[31:0] + len[15:0]
    localparam [2:0] S_RD_SET  = 3'd2;   // program one 256 B read command
    localparam [2:0] S_RD_BEAT = 3'd3;   // collect eight 32 B beats
    localparam [2:0] S_TX      = 3'd4;   // shift the current message out
    localparam [2:0] S_ACK     = 3'd5;   // wait for the PC 'K' (100 ms)

    localparam [1:0] KIND_K      = 2'd0; // single 'K' acknowledgement
    localparam [1:0] KIND_NAK    = 2'd1; // 'N' + one decimal error digit
    localparam [1:0] KIND_STATUS = 2'd2; // 61-byte status line
    localparam [1:0] KIND_FRAME  = 2'd3; // 264-byte read-back frame

    localparam [23:0] ACK_TO = ACK_TIMEOUT;

    // ------------------------------------------------------------------
    // State and data registers
    // ------------------------------------------------------------------
    reg [2:0]   state;

    reg [31:0]  arg_addr;      // 'R' argument, little endian on the wire
    reg [15:0]  arg_len;
    reg [2:0]   arg_idx;
    reg [2:0]   nak_code;      // 1 / 2 / 3, the byte after 'N'

    reg [12:0]  frame_idx;     // frames already fetched in this 'R'
    reg [12:0]  frame_total;   // len >> 8
    reg [15:0]  seq_tx;        // frame sequence number inside this 'R'

    reg [255:0] beat_buf [0:7];// eight 32 B beats of one 256 B frame
    reg [3:0]   beat_cnt;
    reg         done_seen;     // m3_done sampled while draining the fifo

    reg [23:0]  ack_cnt;

    // Transmitter engine (single byte at a time, one idle cycle after every
    // accepted byte: uart_tx byte_wready is a registered ~busy and stays high
    // for one extra cycle, the hazard documented in weight_loader.v).
    reg [1:0]   tx_kind;
    reg [8:0]   tx_pos;
    reg         tx_active;
    reg         msg_done;
    reg         msg_start;
    reg [1:0]   msg_kind;
    reg [15:0]  crc_calc;

    // Status snapshot taken on 'S' so one line is internally consistent.
    reg [15:0]  st_win;
    reg         st_lock;
    reg         st_mel;
    reg         st_npu;
    reg         st_logits;

    // Combinational render helpers.
    reg [7:0]   tx_byte_c;
    reg [8:0]   pay_idx_c;
    reg [8:0]   pay_shift_c;
    reg [255:0] pay_beat_c;
    reg [8:0]   msg_last_c;
    reg [7:0]   status_char;

    wire [19:0] st_bcd;
    wire [31:0] rd_addr_c;

    // ------------------------------------------------------------------
    // Functions (declared before use)
    // ------------------------------------------------------------------
    // CRC-16/CCITT-FALSE single byte step, identical to weight_loader.v.
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

    // 16-bit binary to five packed BCD digits (double dabble); the pin
    // result holds d4 in [19:16] down to d0 in [3:0].  Only five digits of
    // range are needed because win_id is 16 bits (max 65535).
    function [19:0] bin_to_bcd;
        input [15:0] bin;
        reg [19:0] bcd;
        integer i;
        begin
            bcd = 20'd0;
            for (i = 15; i >= 0; i = i - 1) begin
                if (bcd[3:0]   >= 4'd5) bcd[3:0]   = bcd[3:0]   + 4'd3;
                if (bcd[7:4]   >= 4'd5) bcd[7:4]   = bcd[7:4]   + 4'd3;
                if (bcd[11:8]  >= 4'd5) bcd[11:8]  = bcd[11:8]  + 4'd3;
                if (bcd[15:12] >= 4'd5) bcd[15:12] = bcd[15:12] + 4'd3;
                if (bcd[19:16] >= 4'd5) bcd[19:16] = bcd[19:16] + 4'd3;
                bcd = {bcd[18:0], bin[i]};
            end
            bin_to_bcd = bcd;
        end
    endfunction

    // ASCII byte at one position of the 61-byte status line.  Index map:
    //   0..8   "DIAG win="        9..13  five decimal digits of st_win
    //   14..21 " locked="         22     locked digit
    //   23..32 " mel_done="       33     mel_done digit
    //   34..43 " npu_done="       44     npu_done digit
    //   45..58 " logits_valid="   59     logits_valid digit
    //   60     newline
    function [7:0] status_byte;
        input [8:0] idx;
        reg [7:0] b;
        begin
            b = 8'h20;
            if (idx < 9'd9) begin
                // "DIAG win="
                case (idx)
                    9'd0: b = 8'h44;   // 'D'
                    9'd1: b = 8'h49;   // 'I'
                    9'd2: b = 8'h41;   // 'A'
                    9'd3: b = 8'h47;   // 'G'
                    9'd4: b = 8'h20;   // ' '
                    9'd5: b = 8'h77;   // 'w'
                    9'd6: b = 8'h69;   // 'i'
                    9'd7: b = 8'h6E;   // 'n'
                    default: b = 8'h3D; // '='
                endcase
            end else if (idx < 9'd14) begin
                // five decimal digits, most significant first
                case (idx)
                    9'd9:  b = 8'h30 + {4'd0, st_bcd[19:16]};
                    9'd10: b = 8'h30 + {4'd0, st_bcd[15:12]};
                    9'd11: b = 8'h30 + {4'd0, st_bcd[11:8]};
                    9'd12: b = 8'h30 + {4'd0, st_bcd[7:4]};
                    default: b = 8'h30 + {4'd0, st_bcd[3:0]};
                endcase
            end else if (idx < 9'd22) begin
                // " locked="
                case (idx)
                    9'd14: b = 8'h20;   // ' '
                    9'd15: b = 8'h6C;   // 'l'
                    9'd16: b = 8'h6F;   // 'o'
                    9'd17: b = 8'h63;   // 'c'
                    9'd18: b = 8'h6B;   // 'k'
                    9'd19: b = 8'h65;   // 'e'
                    9'd20: b = 8'h64;   // 'd'
                    default: b = 8'h3D; // '='
                endcase
            end else if (idx == 9'd22) begin
                b = 8'h30 + {7'd0, st_lock};
            end else if (idx < 9'd33) begin
                // " mel_done="
                case (idx)
                    9'd23: b = 8'h20;   // ' '
                    9'd24: b = 8'h6D;   // 'm'
                    9'd25: b = 8'h65;   // 'e'
                    9'd26: b = 8'h6C;   // 'l'
                    9'd27: b = 8'h5F;   // '_'
                    9'd28: b = 8'h64;   // 'd'
                    9'd29: b = 8'h6F;   // 'o'
                    9'd30: b = 8'h6E;   // 'n'
                    9'd31: b = 8'h65;   // 'e'
                    default: b = 8'h3D; // '='
                endcase
            end else if (idx == 9'd33) begin
                b = 8'h30 + {7'd0, st_mel};
            end else if (idx < 9'd44) begin
                // " npu_done="
                case (idx)
                    9'd34: b = 8'h20;   // ' '
                    9'd35: b = 8'h6E;   // 'n'
                    9'd36: b = 8'h70;   // 'p'
                    9'd37: b = 8'h75;   // 'u'
                    9'd38: b = 8'h5F;   // '_'
                    9'd39: b = 8'h64;   // 'd'
                    9'd40: b = 8'h6F;   // 'o'
                    9'd41: b = 8'h6E;   // 'n'
                    9'd42: b = 8'h65;   // 'e'
                    default: b = 8'h3D; // '='
                endcase
            end else if (idx == 9'd44) begin
                b = 8'h30 + {7'd0, st_npu};
            end else if (idx < 9'd59) begin
                // " logits_valid="
                case (idx)
                    9'd45: b = 8'h20;   // ' '
                    9'd46: b = 8'h6C;   // 'l'
                    9'd47: b = 8'h6F;   // 'o'
                    9'd48: b = 8'h67;   // 'g'
                    9'd49: b = 8'h69;   // 'i'
                    9'd50: b = 8'h74;   // 't'
                    9'd51: b = 8'h73;   // 's'
                    9'd52: b = 8'h5F;   // '_'
                    9'd53: b = 8'h76;   // 'v'
                    9'd54: b = 8'h61;   // 'a'
                    9'd55: b = 8'h6C;   // 'l'
                    9'd56: b = 8'h69;   // 'i'
                    9'd57: b = 8'h64;   // 'd'
                    default: b = 8'h3D; // '='
                endcase
            end else if (idx == 9'd59) begin
                b = 8'h30 + {7'd0, st_logits};
            end else begin
                b = 8'h0A;              // 60: newline
            end
            status_byte = b;
        end
    endfunction

    // ------------------------------------------------------------------
    // Combinational field extraction
    // ------------------------------------------------------------------
    assign st_bcd = bin_to_bcd(st_win);

    // Frame base address: 'R' addr plus the 256 B frame offset.  The arbiter
    // requires 32 B alignment, the host is required to pass 256 B alignment.
    assign rd_addr_c = arg_addr + {12'd0, frame_idx[11:0], 8'd0};

    // Last byte position of the current message.
    always @* begin
        case (tx_kind)
            KIND_K:      msg_last_c = 9'd0;
            KIND_NAK:    msg_last_c = 9'd1;
            KIND_STATUS: msg_last_c = 9'd60;
            default:     msg_last_c = 9'd263;   // KIND_FRAME
        endcase
    end

    // Byte renderer for the message being shifted out.
    always @* begin
        pay_idx_c   = 9'd0;
        pay_shift_c = 9'd0;
        pay_beat_c  = 256'd0;
        status_char = 8'h20;
        tx_byte_c  = 8'h00;
        case (tx_kind)
            KIND_K: begin
                tx_byte_c = 8'h4B;              // 'K'
            end
            KIND_NAK: begin
                if (tx_pos == 9'd0) tx_byte_c = 8'h4E;             // 'N'
                else                tx_byte_c = 8'h30 + {5'd0, nak_code};
            end
            KIND_STATUS: begin
                status_char = status_byte(tx_pos);
                tx_byte_c   = status_char;
            end
            default: begin
                // KIND_FRAME: AA 55 seq[2] len[2] payload[256] crc[2]
                if (tx_pos == 9'd0) begin
                    tx_byte_c = 8'hAA;
                end else if (tx_pos == 9'd1) begin
                    tx_byte_c = 8'h55;
                end else if (tx_pos == 9'd2) begin
                    tx_byte_c = seq_tx[7:0];
                end else if (tx_pos == 9'd3) begin
                    tx_byte_c = seq_tx[15:8];
                end else if (tx_pos == 9'd4) begin
                    tx_byte_c = 8'h00;              // len = 256, low byte
                end else if (tx_pos == 9'd5) begin
                    tx_byte_c = 8'h01;              // len = 256, high byte
                end else if (tx_pos <= 9'd261) begin
                    pay_idx_c   = tx_pos - 9'd6;
                    pay_beat_c  = beat_buf[pay_idx_c[7:5]];
                    pay_shift_c = {pay_idx_c[4:0], 3'b000};
                    tx_byte_c   = pay_beat_c[pay_shift_c +: 8];
                end else if (tx_pos == 9'd262) begin
                    tx_byte_c = crc_calc[7:0];
                end else begin
                    tx_byte_c = crc_calc[15:8];
                end
            end
        endcase
    end

    // ------------------------------------------------------------------
    // Byte transmitter: one-shot request, accept detected on tx_ready while
    // tx_valid is high, then exactly one idle cycle before the next byte is
    // presented (absorbs the extra high cycle of uart_tx byte_wready).
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tx_active <= 1'b0;
            tx_kind   <= KIND_K;
            tx_pos    <= 9'd0;
            tx_valid  <= 1'b0;
            tx_data   <= 8'd0;
            crc_calc  <= 16'hFFFF;
            msg_done  <= 1'b0;
        end else begin
            msg_done <= 1'b0;
            if (msg_start) begin
                tx_active <= 1'b1;
                tx_kind   <= msg_kind;
                tx_pos    <= 9'd0;
                crc_calc  <= 16'hFFFF;
                tx_valid  <= 1'b0;      // first byte presented next cycle
            end else if (!tx_active) begin
                tx_valid <= 1'b0;
            end else if (tx_valid) begin
                if (tx_ready) begin
                    tx_valid <= 1'b0;
                    // CRC covers seq, len and payload only.
                    if ((tx_kind == KIND_FRAME) &&
                        (tx_pos >= 9'd2) && (tx_pos <= 9'd261))
                        crc_calc <= crc16_step(crc_calc, tx_data);
                    if (tx_pos == msg_last_c) begin
                        tx_active <= 1'b0;
                        msg_done  <= 1'b1;
                    end else begin
                        tx_pos <= tx_pos + 9'd1;
                    end
                end
            end else begin
                tx_data  <= tx_byte_c;
                tx_valid <= 1'b1;
            end
        end
    end

    // ------------------------------------------------------------------
    // Command parser and read-back sequencer
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= S_IDLE;
            arg_addr     <= 32'd0;
            arg_len      <= 16'd0;
            arg_idx      <= 3'd0;
            nak_code     <= 3'd0;
            frame_idx    <= 13'd0;
            frame_total  <= 13'd0;
            seq_tx       <= 16'd0;
            beat_cnt     <= 4'd0;
            done_seen    <= 1'b0;
            ack_cnt      <= 24'd0;
            msg_start    <= 1'b0;
            msg_kind     <= KIND_K;
            m3_cmd_valid <= 1'b0;
            m3_cmd       <= 37'd0;
            m3_rd_ready  <= 1'b0;
            diag_lock    <= 1'b0;
            st_win       <= 16'd0;
            st_lock      <= 1'b0;
            st_mel       <= 1'b0;
            st_npu       <= 1'b0;
            st_logits    <= 1'b0;
        end else begin
            msg_start <= 1'b0;

            case (state)
                S_IDLE: begin
                    if (rx_valid) begin
                        case (rx_data)
                            8'h4C: begin            // 'L'
                                diag_lock <= 1'b1;
                                msg_kind  <= KIND_K;
                                msg_start <= 1'b1;
                                state     <= S_TX;
                            end
                            8'h55: begin            // 'U'
                                diag_lock <= 1'b0;
                                msg_kind  <= KIND_K;
                                msg_start <= 1'b1;
                                state     <= S_TX;
                            end
                            8'h53: begin            // 'S'
                                st_win    <= win_id;
                                st_lock   <= diag_lock;
                                st_mel    <= mel_done;
                                st_npu    <= npu_done;
                                st_logits <= logits_valid;
                                msg_kind  <= KIND_STATUS;
                                msg_start <= 1'b1;
                                state     <= S_TX;
                            end
                            8'h47: begin            // 'G' full logits
                                // 8 x int32 fits exactly in beat_buf[0]; the
                                // rest of the 256-byte payload is zero.
                                beat_buf[0] <= logits_in;
                                beat_buf[1] <= 256'd0;
                                beat_buf[2] <= 256'd0;
                                beat_buf[3] <= 256'd0;
                                beat_buf[4] <= 256'd0;
                                beat_buf[5] <= 256'd0;
                                beat_buf[6] <= 256'd0;
                                beat_buf[7] <= 256'd0;
                                frame_total <= 16'd1;
                                frame_idx   <= 13'd0;
                                seq_tx      <= 16'd0;
                                msg_kind    <= KIND_FRAME;
                                msg_start   <= 1'b1;
                                state       <= S_TX;
                            end
                            8'h52: begin            // 'R'
                                arg_addr <= 32'd0;
                                arg_len  <= 16'd0;
                                arg_idx  <= 3'd0;
                                state    <= S_ARG;
                            end
                            default: begin          // illegal command
                                nak_code  <= 3'd2;
                                msg_kind  <= KIND_NAK;
                                msg_start <= 1'b1;
                                state     <= S_TX;
                            end
                        endcase
                    end
                end

                S_ARG: begin
                    if (rx_valid) begin
                        if (arg_idx < 3'd4) begin
                            arg_addr <= {rx_data, arg_addr[31:8]};
                            arg_idx  <= arg_idx + 3'd1;
                        end else if (arg_idx == 3'd4) begin
                            arg_len[7:0] <= rx_data;
                            arg_idx      <= 3'd5;
                        end else begin
                            if ({rx_data, arg_len[7:0]} == 16'd0) begin
                                nak_code <= 3'd3;       // len == 0
                                msg_kind <= KIND_NAK;
                                msg_start <= 1'b1;
                                state    <= S_TX;
                            end else if (arg_len[7:0] != 8'd0) begin
                                nak_code <= 3'd1;       // not a 256 B multiple
                                msg_kind <= KIND_NAK;
                                msg_start <= 1'b1;
                                state    <= S_TX;
                            end else begin
                                frame_total <= {5'd0, rx_data};
                                frame_idx   <= 13'd0;
                                seq_tx      <= 16'd0;
                                state       <= S_RD_SET;
                            end
                        end
                    end
                end

                S_RD_SET: begin
                    m3_cmd       <= {1'b0, rd_addr_c[27:0], 8'd7};
                    m3_cmd_valid <= 1'b1;
                    m3_rd_ready  <= 1'b1;
                    beat_cnt     <= 4'd0;
                    done_seen    <= 1'b0;
                    state        <= S_RD_BEAT;
                end

                S_RD_BEAT: begin
                    // The burst is complete once all eight beats have been
                    // popped.  cmd_valid is dropped on that same edge: the
                    // controller is already back in S_IDLE here (rlast is the
                    // eighth push), and a still-high request would be granted
                    // a second time for the same frame (the elastic read fifo
                    // is empty one cycle after the last pop).
                    if (m3_done) done_seen <= 1'b1;
                    if (m3_rd_valid) begin
                        beat_buf[beat_cnt[2:0]] <= m3_rd_data;
                        beat_cnt <= beat_cnt + 4'd1;
                        if (beat_cnt == 4'd7) begin
                            m3_cmd_valid <= 1'b0;
                            m3_rd_ready  <= 1'b0;
                            seq_tx       <= {3'd0, frame_idx};
                            msg_kind     <= KIND_FRAME;
                            msg_start    <= 1'b1;
                            state        <= S_TX;
                        end
                    end else if (done_seen) begin
                        // Short burst (controller watchdog abort): no frame
                        // is emitted for a partial read.
                        m3_cmd_valid <= 1'b0;
                        m3_rd_ready  <= 1'b0;
                        state        <= S_IDLE;
                    end
                end

                S_TX: begin
                    if (msg_done) begin
                        if (tx_kind == KIND_FRAME) begin
                            frame_idx <= frame_idx + 13'd1;
                            ack_cnt   <= 24'd0;
                            state     <= S_ACK;
                        end else begin
                            state <= S_IDLE;
                        end
                    end
                end

                S_ACK: begin
                    // One 'K' per frame; every other byte is ignored while
                    // the frame flow control window is open.
                    if (rx_valid && (rx_data == 8'h4B)) begin
                        ack_cnt <= 24'd0;
                        if (frame_idx == frame_total) state <= S_IDLE;
                        else                          state <= S_RD_SET;
                    end else if (ack_cnt == ACK_TO) begin
                        ack_cnt <= 24'd0;
                        if (frame_idx == frame_total) state <= S_IDLE;
                        else                          state <= S_RD_SET;
                    end else begin
                        ack_cnt <= ack_cnt + 24'd1;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule