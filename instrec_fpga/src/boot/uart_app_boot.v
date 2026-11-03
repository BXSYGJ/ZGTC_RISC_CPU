// -----------------------------------------------------------------------------
// File    : uart_app_boot.v
// Module  : uart_app_boot
// UART application loader: framed image download into a 4 KiB instruction
// RAM with per-frame CRC32, sequence checking and EXEC gating.
//
// Protocol v0 (frozen interface draft, work package "CPU boot / bus"):
//   frame = SOF0 0xA5, SOF1 0x5A, type, seq, len_lo, len_hi,
//           payload[len], crc32[4B little-endian over type..payload].
//   type 0x01 APP_CHUNK : payload <= 512 B, written to IRAM from the
//                         committed byte offset (starts at 0).
//   type 0x02 APP_EXEC  : payload 12 B = entry, total_len, image_crc32
//                         (all little-endian). Accepted only when
//                         total_len <= bytes_received, image_crc32 equals
//                         the CRC32 of the committed total_len bytes and
//                         entry < total_len with 2-bit alignment.
//   type 0x03 APP_ABORT : clears the session (write pointer, CRC state).
//   type 0x04 APP_RESET : same semantics as ABORT in v0.
//   ACK  : 'K' (0x4B) + seq.
//   NAK  : 'N' (0x4E) + seq + reason
//          1 = CRC error, 2 = sequence order, 3 = over capacity,
//          4 = not ready / busy / malformed frame.
//   seq must equal the expected value (strictly increasing from 0).
//   Replays of already accepted frames and skipped values are NAK 2. A
//   retransmission of a REJECTED frame keeps the expected seq (nothing
//   was committed) and is accepted when its CRC is good.
//
// IRAM: 4 KiB = 1024 x 32 b, byte lanes little-endian. Instruction fetch
// arbitration during download is left to the integration stage; this
// module only writes the IRAM and exposes a synchronous read port plus
// the app_ready / app_entry exec gates.
//
// Trial writes: payload bytes stream into the IRAM while the frame CRC
// is still being received. A rejected frame commits neither its byte
// count nor its image CRC, so a retransmission overwrites the very same
// offsets and the final image is exact.
//
// UART: 115200 8N1, BAUD_DIV = round(125 MHz / 115200) = 1085, same
// contract as src/ctrl/uart_rx.v and src/ctrl/uart_tx.v (reused here).
// -----------------------------------------------------------------------------

module uart_app_boot #(
    // Baud divider: round(125e6/115200) = 1085 (+0.0064% baud error).
    parameter integer BAUD_DIV = 1085
) (
    input  wire        clk,            // core_clk 125 MHz
    input  wire        rst_n,          // core-domain reset, sync release
    input  wire        uart_rxd,       // asynchronous serial input pin
    output wire        uart_txd,       // serialized reply output pin

    // 4 KiB IRAM read port (word addressed, synchronous 1-cycle read)
    input  wire [9:0]  iram_raddr,
    output reg  [31:0] iram_rdata,

    // exec gate
    output reg         app_ready,      // EXEC frame fully validated
    output reg  [31:0] app_entry,      // latched entry point

    // status / error registers
    output reg         busy,           // outside ST_IDLE
    output reg  [3:0]  status_state,   // FSM state code
    output reg  [15:0] bytes_received, // committed image bytes
    output reg  [7:0]  last_error,     // 0 none, 1..4 = NAK reason
    output reg  [7:0]  last_nak_seq    // seq of the last NAK
);

    // ------------------------------------------------------------------
    // FSM states
    // ------------------------------------------------------------------
    localparam [3:0] ST_IDLE  = 4'd0;
    localparam [3:0] ST_SOF1  = 4'd1;
    localparam [3:0] ST_TYPE  = 4'd2;
    localparam [3:0] ST_SEQ   = 4'd3;
    localparam [3:0] ST_LEN0  = 4'd4;
    localparam [3:0] ST_LEN1  = 4'd5;
    localparam [3:0] ST_PAY   = 4'd6;
    localparam [3:0] ST_CRC0  = 4'd7;
    localparam [3:0] ST_CRC1  = 4'd8;
    localparam [3:0] ST_CRC2  = 4'd9;
    localparam [3:0] ST_CRC3  = 4'd10;
    localparam [3:0] ST_CHECK = 4'd11;
    localparam [3:0] ST_REPLY = 4'd12;

    localparam [31:0] CRC32_INIT = 32'hFFFFFFFF;
    localparam [31:0] CRC32_POLY = 32'hEDB88320;

    // ------------------------------------------------------------------
    // Reused UART byte engines
    // ------------------------------------------------------------------
    wire [7:0] rx_data;
    wire       rx_valid;
    reg        tx_valid_r;
    reg  [7:0] tx_data_r;
    wire       tx_ready_r;

    uart_rx #(.BAUD_DIV(BAUD_DIV)) u_uart_rx (
        .clk(clk), .rst_n(rst_n), .uart_rxd(uart_rxd),
        .byte_rdata(rx_data), .byte_rvalid(rx_valid));

    uart_tx #(.BAUD_DIV(BAUD_DIV)) u_uart_tx (
        .clk(clk), .rst_n(rst_n), .byte_wdata(tx_data_r),
        .byte_wvalid(tx_valid_r), .byte_wready(tx_ready_r),
        .uart_txd(uart_txd));

    // ------------------------------------------------------------------
    // CRC-32 (IEEE 802.3 reflected) single byte step. Running registers
    // hold the raw state; results compare after the final xor.
    // ------------------------------------------------------------------
    function [31:0] crc32_step;
        input [31:0] crc;
        input [7:0]  b;
        reg [31:0] c;
        integer i;
        begin
            c = crc ^ {24'd0, b};
            for (i = 0; i < 8; i = i + 1) begin
                if (c[0]) c = {1'b0, c[31:1]} ^ CRC32_POLY;
                else      c = {1'b0, c[31:1]};
            end
            crc32_step = c;
        end
    endfunction

    // ------------------------------------------------------------------
    // Registers
    // ------------------------------------------------------------------
    reg [3:0]  state;
    reg [7:0]  type_rx;
    reg [7:0]  seq_rx;
    reg [15:0] len_rx;
    reg [15:0] pay_idx;
    reg [31:0] crc_rx;        // received frame CRC32
    reg [31:0] crc_frame;     // running frame CRC over type..payload
    reg [31:0] crc_try;       // running image CRC incl. the open frame
    reg [31:0] crc_image;     // committed image CRC state
    reg [31:0] entry_rx;      // EXEC payload: entry point
    reg [31:0] total_rx;      // EXEC payload: total_len
    reg [31:0] imgcrc_rx;     // EXEC payload: image_crc32
    reg [7:0]  exp_seq;       // next expected seq
    reg        ovf_flag;      // capacity / oversize violation
    reg        bad_flag;      // malformed frame (unknown type, bad len)
    reg [7:0]  reply_buf [0:2];
    reg [1:0]  reply_len;
    reg [1:0]  reply_pos;
    reg        tx_pend;
    reg        tx_saw_low;

    // ------------------------------------------------------------------
    // IRAM: 1024 x 32 b, byte lane little-endian (byte 0 -> bits 7:0)
    // ------------------------------------------------------------------
    reg [31:0] iram [0:1023];

    always @(posedge clk) begin
        iram_rdata <= iram[iram_raddr];
    end

    // ------------------------------------------------------------------
    // Combinational helpers
    // ------------------------------------------------------------------
    wire [15:0] len_hi_c  = {rx_data, len_rx[7:0]};
    wire [16:0] ovf_hi_c  = {1'b0, bytes_received} + {1'b0, len_hi_c};
    wire [15:0] wbyte_c   = bytes_received + pay_idx;
    wire        crc_ok_c  = (crc_rx == (crc_frame ^ CRC32_INIT));
    wire        chunk_wen = (type_rx == 8'h01) && !ovf_flag && !bad_flag;

    // ------------------------------------------------------------------
    // Reply helpers (single-cycle strobe + full ready low/high handshake
    // with uart_tx; see the weight_loader S_TX comment for why the extra
    // registered-ready cycle must not be counted as a delivered byte).
    // ------------------------------------------------------------------
    task nak_reply;
        input [7:0] reason;
        begin
            reply_buf[0] <= 8'h4E;      // 'N'
            reply_buf[1] <= seq_rx;
            reply_buf[2] <= reason;
            reply_len    <= 2'd3;
            reply_pos    <= 2'd0;
            last_error   <= reason;
            last_nak_seq <= seq_rx;
            state        <= ST_REPLY;
        end
    endtask

    task ack_reply;
        begin
            reply_buf[0] <= 8'h4B;      // 'K'
            reply_buf[1] <= seq_rx;
            reply_len    <= 2'd2;
            reply_pos    <= 2'd0;
            last_error   <= 8'd0;
            state        <= ST_REPLY;
        end
    endtask

    // ------------------------------------------------------------------
    // Frame receiver FSM
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= ST_IDLE;
            type_rx       <= 8'd0;
            seq_rx        <= 8'd0;
            len_rx        <= 16'd0;
            pay_idx       <= 16'd0;
            crc_rx        <= 32'd0;
            crc_frame     <= CRC32_INIT;
            crc_try       <= CRC32_INIT;
            crc_image     <= CRC32_INIT;
            entry_rx      <= 32'd0;
            total_rx      <= 32'd0;
            imgcrc_rx     <= 32'd0;
            exp_seq       <= 8'd0;
            ovf_flag      <= 1'b0;
            bad_flag      <= 1'b0;
            reply_len     <= 2'd0;
            reply_pos     <= 2'd0;
            tx_valid_r    <= 1'b0;
            tx_data_r     <= 8'd0;
            tx_pend       <= 1'b0;
            tx_saw_low    <= 1'b0;
            app_ready     <= 1'b0;
            app_entry     <= 32'd0;
            busy          <= 1'b0;
            status_state  <= ST_IDLE;
            bytes_received <= 16'd0;
            last_error    <= 8'd0;
            last_nak_seq  <= 8'd0;
        end else begin
            tx_valid_r <= 1'b0;
            busy       <= (state != ST_IDLE);
            status_state <= state;

            case (state)
                // ---- hunt for SOF0 ------------------------------------
                ST_IDLE: begin
                    if (rx_valid && rx_data == 8'hA5) begin
                        state     <= ST_SOF1;
                        crc_frame <= CRC32_INIT;
                        crc_try   <= crc_image;
                        pay_idx   <= 16'd0;
                        ovf_flag  <= 1'b0;
                        bad_flag  <= 1'b0;
                    end
                end

                // ---- SOF1 (A5 stays, resync candidate) ----------------
                ST_SOF1: begin
                    if (rx_valid) begin
                        if (rx_data == 8'h5A)      state <= ST_TYPE;
                        else if (rx_data != 8'hA5) state <= ST_IDLE;
                    end
                end

                // ---- type (CRC starts here) ---------------------------
                ST_TYPE: begin
                    if (rx_valid) begin
                        type_rx   <= rx_data;
                        crc_frame <= crc32_step(crc_frame, rx_data);
                        bad_flag  <= !(rx_data == 8'h01 || rx_data == 8'h02 ||
                                       rx_data == 8'h03 || rx_data == 8'h04);
                        state     <= ST_SEQ;
                    end
                end

                // ---- seq ----------------------------------------------
                ST_SEQ: begin
                    if (rx_valid) begin
                        seq_rx    <= rx_data;
                        crc_frame <= crc32_step(crc_frame, rx_data);
                        state     <= ST_LEN0;
                    end
                end

                // ---- len low ------------------------------------------
                ST_LEN0: begin
                    if (rx_valid) begin
                        len_rx    <= {8'd0, rx_data};
                        crc_frame <= crc32_step(crc_frame, rx_data);
                        state     <= ST_LEN1;
                    end
                end

                // ---- len high: capacity / shape checks ----------------
                ST_LEN1: begin
                    if (rx_valid) begin
                        len_rx    <= len_hi_c;
                        crc_frame <= crc32_step(crc_frame, rx_data);
                        bad_flag  <= bad_flag ||
                                     (type_rx == 8'h02 && len_hi_c != 16'd12);
                        ovf_flag  <= (type_rx == 8'h01) &&
                                     ((len_hi_c > 16'd512) ||
                                      (ovf_hi_c > 17'd4096));
                        if (len_hi_c == 16'd0) state <= ST_CRC0;
                        else                   state <= ST_PAY;
                    end
                end

                // ---- payload (trial write + CRC feeding) --------------
                ST_PAY: begin
                    if (rx_valid) begin
                        crc_frame <= crc32_step(crc_frame, rx_data);
                        pay_idx   <= pay_idx + 16'd1;

                        if (chunk_wen) begin
                            iram[wbyte_c[11:2]][(wbyte_c[1:0] * 8) +: 8] <= rx_data;
                            crc_try <= crc32_step(crc_try, rx_data);
                        end

                        if (type_rx == 8'h02 && !bad_flag) begin
                            case (pay_idx[3:0])
                                4'd0:  entry_rx[7:0]   <= rx_data;
                                4'd1:  entry_rx[15:8]  <= rx_data;
                                4'd2:  entry_rx[23:16] <= rx_data;
                                4'd3:  entry_rx[31:24] <= rx_data;
                                4'd4:  total_rx[7:0]   <= rx_data;
                                4'd5:  total_rx[15:8]  <= rx_data;
                                4'd6:  total_rx[23:16] <= rx_data;
                                4'd7:  total_rx[31:24] <= rx_data;
                                4'd8:  imgcrc_rx[7:0]  <= rx_data;
                                4'd9:  imgcrc_rx[15:8] <= rx_data;
                                4'd10: imgcrc_rx[23:16] <= rx_data;
                                4'd11: imgcrc_rx[31:24] <= rx_data;
                                default: ;
                            endcase
                        end

                        if (pay_idx + 16'd1 == len_rx) state <= ST_CRC0;
                    end
                end

                // ---- frame CRC32, little-endian -----------------------
                ST_CRC0: begin
                    if (rx_valid) begin
                        crc_rx[7:0] <= rx_data;
                        state       <= ST_CRC1;
                    end
                end
                ST_CRC1: begin
                    if (rx_valid) begin
                        crc_rx[15:8] <= rx_data;
                        state        <= ST_CRC2;
                    end
                end
                ST_CRC2: begin
                    if (rx_valid) begin
                        crc_rx[23:16] <= rx_data;
                        state         <= ST_CRC3;
                    end
                end
                ST_CRC3: begin
                    if (rx_valid) begin
                        crc_rx[31:24] <= rx_data;
                        state         <= ST_CHECK;
                    end
                end

                // ---- decide and reply ----------------------------------
                ST_CHECK: begin
                    if (!crc_ok_c) begin
                        nak_reply(8'd1);
                    end else if (seq_rx != exp_seq) begin
                        nak_reply(8'd2);
                    end else if (app_ready &&
                                 (type_rx == 8'h01 || type_rx == 8'h02)) begin
                        // session closed by a previous EXEC
                        nak_reply(8'd4);
                    end else if (bad_flag) begin
                        nak_reply(8'd4);
                    end else begin
                        case (type_rx)
                            8'h01: begin
                                if (ovf_flag) begin
                                    nak_reply(8'd3);
                                end else begin
                                    bytes_received <= bytes_received + len_rx;
                                    crc_image      <= crc_try;
                                    exp_seq        <= exp_seq + 8'd1;
                                    ack_reply;
                                end
                            end
                            8'h02: begin
                                if (total_rx > 32'd4096 ||
                                    total_rx > {16'd0, bytes_received}) begin
                                    nak_reply(8'd3);
                                end else if (entry_rx >= total_rx ||
                                             entry_rx[1:0] != 2'b00) begin
                                    nak_reply(8'd4);
                                end else if (imgcrc_rx !=
                                            (crc_image ^ CRC32_INIT)) begin
                                    nak_reply(8'd1);
                                end else begin
                                    app_ready <= 1'b1;
                                    app_entry <= entry_rx;
                                    exp_seq   <= exp_seq + 8'd1;
                                    ack_reply;
                                end
                            end
                            8'h03, 8'h04: begin
                                // ABORT / RESET: clear the whole session
                                bytes_received <= 16'd0;
                                crc_image      <= CRC32_INIT;
                                crc_try        <= CRC32_INIT;
                                exp_seq        <= 8'd0;
                                app_ready      <= 1'b0;
                                app_entry      <= 32'd0;
                                ack_reply;
                            end
                            default: begin
                                nak_reply(8'd4);
                            end
                        endcase
                    end
                end

                // ---- shift the reply out over uart_tx ------------------
                ST_REPLY: begin
                    if (!tx_pend) begin
                        if (tx_ready_r) begin
                            tx_data_r  <= reply_buf[reply_pos];
                            tx_valid_r <= 1'b1;
                            tx_pend    <= 1'b1;
                            tx_saw_low <= 1'b0;
                        end
                    end else if (!tx_ready_r) begin
                        tx_saw_low <= 1'b1;
                    end else if (tx_saw_low) begin
                        tx_pend    <= 1'b0;
                        tx_saw_low <= 1'b0;
                        if (reply_pos + 2'd1 == reply_len) begin
                            state <= ST_IDLE;
                        end else begin
                            reply_pos <= reply_pos + 2'd1;
                        end
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule
