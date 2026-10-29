// -----------------------------------------------------------------------------
// uart_debug - line-oriented debug printer, M0 base version
//              (tasks.md T-M0-09 uart_debug group, design.md Sec. 2.2.9,
//              REQ-MNT-001 subset: BOOT/PLL/DDROK/ERR line types)
// -----------------------------------------------------------------------------
// This is the ASCII line-printing base ONLY. The KEY1-triggered binary
// layer-export protocol of design.md Sec. 9.2 is an M2 extension
// (T-M2-07) and is intentionally NOT implemented here. Likewise UART
// command parsing for weight loading (T-M2-01) is out of scope; received
// bytes are only counted (rx_byte_cnt).
//
// Architecture (all logic in the core_clk 125 MHz domain):
//
//   dbg_line_* ----> [128-byte line RAM] --\
//                                           +--> [tx engine] --> byte_* --> uart_tx
//   dbg_line_id/arg/fire -> [line ROM req] -/
//
//   uart_rx --> byte_rdata/rvalid --> rx_byte_cnt (loop counter only)
//
// Interface contracts:
//
// 1) Custom text line channel (byte-wise, external modules write a full
//    ASCII line, typically sys_ctrl / self_test):
//      dbg_line_wdata  [7:0]  byte to append to the current line
//      dbg_line_wvalid        byte strobe
//      dbg_line_wready        1 = byte accepted this cycle
//    A line is committed when a '\n' (0x0A) byte is accepted or when the
//    128-byte buffer fills; the engine then drains the buffer through
//    uart_tx and holds dbg_line_wready low until the line is out. The
//    upstream must honor the ready/valid handshake; bytes pushed while
//    ready=0 are dropped.
//
// 2) Predefined status line channel (ROM lines, M0 minimal set):
//      dbg_line_id   [2:0]  0 "INSTREC BOOT\n"    1 "PLL LOCK ERR\n"
//                           2 "DDR3 SELFTEST...\n" 3 "DDROK\n"
//                           4 "DDR3 ERR @" <hex32> "\n"  (uses dbg_line_arg)
//                           5 "RUN\n"
//      dbg_line_arg [31:0]  hex argument, only used by line 4
//      dbg_line_fire        one-cycle request strobe
//      dbg_busy             1 = engine busy (line out or buffered lines
//                           pending); a fire while busy is DROPPED, the
//                           caller (slow sys_ctrl state machine) is
//                           expected to check dbg_busy first
//    Lines are emitted at 115200 8N1 via the byte channel below; the
//    hex32 formatter renders 8 uppercase nibbles ("%08X" semantics).
//
// 3) Byte channel to the physical transmitter (uart_tx module instance
//    lives in the top level, see design.md Sec. 2.1 file plan):
//      tx_byte_data / tx_byte_valid / tx_byte_ready
//
// Physical pins (uart_tx C24 / uart_rx B24, LVCMOS33) are wired at the
// top level; pin constraints are the responsibility of T-M0-09
// (instrec_top.fdc).
// -----------------------------------------------------------------------------
module uart_debug (
    input  wire        clk,            // core_clk 125 MHz
    input  wire        rst_n,          // core-domain reset, sync release
    // byte channel to uart_tx
    output reg  [7:0]  tx_byte_data,
    output reg         tx_byte_valid,
    input  wire        tx_byte_ready,
    // byte channel from uart_rx
    input  wire [7:0]  rx_byte_data,
    input  wire        rx_byte_valid,
    // custom text line channel
    input  wire [7:0]  dbg_line_wdata,
    input  wire        dbg_line_wvalid,
    output wire        dbg_line_wready,
    // predefined status line channel
    input  wire [2:0]  dbg_line_id,
    input  wire [31:0] dbg_line_arg,
    input  wire        dbg_line_fire,
    output wire        dbg_busy,
    // status
    output reg  [15:0] rx_byte_cnt     // received-byte counter (M0: count
                                       // only; KEY/UART command parsing is
                                       // an M2 extension, T-M2-01/07)
);

    // ------------------------------------------------------------------
    // Predefined ASCII line ROM (M0 minimal set, 6 lines).
    // Each localparam is a plain string; rom_char() indexes it. Line 4
    // is split: 10-byte prefix "DDR3 ERR @" + 8 hex nibbles of
    // dbg_line_arg + "\n" (the "\n" is appended by the hex path).
    // ------------------------------------------------------------------
    localparam LINE_BOOT    = "INSTREC BOOT\n";     // id 0, 13 bytes
    localparam LINE_PLLERR  = "PLL LOCK ERR\n";     // id 1, 13 bytes
    localparam LINE_DDRTEST = "DDR3 SELFTEST...\n"; // id 2, 17 bytes
    localparam LINE_DDROK   = "DDROK\n";            // id 3,  6 bytes
    localparam LINE_DDRERR  = "DDR3 ERR @";         // id 4, 10-byte prefix
    localparam LINE_RUN     = "RUN\n";              // id 5,  4 bytes

    localparam integer LINE_MAX = 24;   // slot width, longest line is 16

    // Line length (total bytes to emit, line 4 counts only the prefix;
    // the hex digits and newline are appended by the hex path).
    localparam [4:0] LINE_LEN_BOOT    = 5'd13;
    localparam [4:0] LINE_LEN_PLLERR  = 5'd13;
    localparam [4:0] LINE_LEN_DDRTEST = 5'd17;
    localparam [4:0] LINE_LEN_DDROK   = 5'd6;
    localparam [4:0] LINE_LEN_DDRERR  = 5'd10;
    localparam [4:0] LINE_LEN_RUN     = 5'd4;

    localparam [2:0] LINE_ID_DDRERR = 3'd4;

    // ROM lookup: character idx of line id. Strings are zero-extended
    // into a LINE_MAX-wide word. Measured on PDS 2022.2: the string is
    // right-aligned (first character in the LOW byte), so char idx selects
    // idx*8 +: 8. The earlier left-aligned assumption returned zero bytes
    // for the leading characters (observed on the board as 00 00 ...).
    function [7:0] rom_char;
        input [2:0] id;
        input [4:0] idx;
        begin
            rom_char = 8'h20;   // space default
            case (id)
                3'd0: begin
                    case (idx)
                        5'd0: rom_char = 8'h49;
                        5'd1: rom_char = 8'h4e;
                        5'd2: rom_char = 8'h53;
                        5'd3: rom_char = 8'h54;
                        5'd4: rom_char = 8'h52;
                        5'd5: rom_char = 8'h45;
                        5'd6: rom_char = 8'h43;
                        5'd7: rom_char = 8'h20;
                        5'd8: rom_char = 8'h42;
                        5'd9: rom_char = 8'h4f;
                        5'd10: rom_char = 8'h4f;
                        5'd11: rom_char = 8'h54;
                        5'd12: rom_char = 8'h0a;
                        default: rom_char = 8'h20;
                    endcase
                end
                3'd1: begin
                    case (idx)
                        5'd0: rom_char = 8'h50;
                        5'd1: rom_char = 8'h4c;
                        5'd2: rom_char = 8'h4c;
                        5'd3: rom_char = 8'h20;
                        5'd4: rom_char = 8'h4c;
                        5'd5: rom_char = 8'h4f;
                        5'd6: rom_char = 8'h43;
                        5'd7: rom_char = 8'h4b;
                        5'd8: rom_char = 8'h20;
                        5'd9: rom_char = 8'h45;
                        5'd10: rom_char = 8'h52;
                        5'd11: rom_char = 8'h52;
                        5'd12: rom_char = 8'h0a;
                        default: rom_char = 8'h20;
                    endcase
                end
                3'd2: begin
                    case (idx)
                        5'd0: rom_char = 8'h44;
                        5'd1: rom_char = 8'h44;
                        5'd2: rom_char = 8'h52;
                        5'd3: rom_char = 8'h33;
                        5'd4: rom_char = 8'h20;
                        5'd5: rom_char = 8'h53;
                        5'd6: rom_char = 8'h45;
                        5'd7: rom_char = 8'h4c;
                        5'd8: rom_char = 8'h46;
                        5'd9: rom_char = 8'h54;
                        5'd10: rom_char = 8'h45;
                        5'd11: rom_char = 8'h53;
                        5'd12: rom_char = 8'h54;
                        5'd13: rom_char = 8'h2e;
                        5'd14: rom_char = 8'h2e;
                        5'd15: rom_char = 8'h2e;
                        5'd16: rom_char = 8'h0a;
                        default: rom_char = 8'h20;
                    endcase
                end
                3'd3: begin
                    case (idx)
                        5'd0: rom_char = 8'h44;
                        5'd1: rom_char = 8'h44;
                        5'd2: rom_char = 8'h52;
                        5'd3: rom_char = 8'h4f;
                        5'd4: rom_char = 8'h4b;
                        5'd5: rom_char = 8'h0a;
                        default: rom_char = 8'h20;
                    endcase
                end
                3'd4: begin
                    case (idx)
                        5'd0: rom_char = 8'h44;
                        5'd1: rom_char = 8'h44;
                        5'd2: rom_char = 8'h52;
                        5'd3: rom_char = 8'h33;
                        5'd4: rom_char = 8'h20;
                        5'd5: rom_char = 8'h45;
                        5'd6: rom_char = 8'h52;
                        5'd7: rom_char = 8'h52;
                        5'd8: rom_char = 8'h20;
                        5'd9: rom_char = 8'h40;
                        default: rom_char = 8'h20;
                    endcase
                end
                3'd5: begin
                    case (idx)
                        5'd0: rom_char = 8'h52;
                        5'd1: rom_char = 8'h55;
                        5'd2: rom_char = 8'h4e;
                        5'd3: rom_char = 8'h0a;
                        default: rom_char = 8'h20;
                    endcase
                end
                default: rom_char = 8'h20;
            endcase
        end
    endfunction

    function [4:0] rom_len;
        input [2:0] id;
        begin
            case (id)
                3'd0:    rom_len = LINE_LEN_BOOT;
                3'd1:    rom_len = LINE_LEN_PLLERR;
                3'd2:    rom_len = LINE_LEN_DDRTEST;
                3'd3:    rom_len = LINE_LEN_DDROK;
                3'd4:    rom_len = LINE_LEN_DDRERR;
                default: rom_len = LINE_LEN_RUN;
            endcase
        end
    endfunction

    // Uppercase hex digit ASCII for a 4-bit nibble ("%08X" semantics).
    function [7:0] hex_ascii;
        input [3:0] nib;
        begin
            hex_ascii = (nib >= 4'hA) ? (8'h41 + {4'd0, nib - 4'hA})
                                      : (8'h30 + {4'd0, nib});
        end
    endfunction

    // ------------------------------------------------------------------
    // 128-byte line RAM for the custom text channel.
    // ------------------------------------------------------------------
    reg [7:0] line_ram [0:127];
    reg [6:0] wr_cnt;        // bytes buffered in the current line
    reg       ram_pending;   // a complete line waits for draining
    reg [6:0] ram_len;       // length of the pending line (1..128)
    reg [6:0] ram_rd_idx;    // drain read index

    // Accept bytes only while the engine is fully idle (no pending line,
    // no line being drained, no ROM request in flight or buffered).
    assign dbg_line_wready = ~ram_pending & ~rom_pending & (state == ST_IDLE);

    // ------------------------------------------------------------------
    // ROM request latching (fire while a request is already buffered is
    // dropped; the caller checks dbg_busy).
    // ------------------------------------------------------------------
    reg       rom_pending;
    reg [2:0] rom_id;
    reg [31:0] rom_arg;

    assign dbg_busy = ram_pending | rom_pending | (state != ST_IDLE) |
                      (wr_cnt != 7'd0);

    // ------------------------------------------------------------------
    // TX engine: arbitrates between the RAM line and the ROM line
    // (RAM line has priority; both are slow status texts).
    // ------------------------------------------------------------------
    localparam [2:0] ST_IDLE = 3'd0;
    localparam [2:0] ST_RAM  = 3'd1;
    localparam [2:0] ST_ROM  = 3'd2;
    localparam [2:0] ST_HEX  = 3'd3;
    localparam [2:0] ST_EOL  = 3'd4;

    reg [2:0]  state;
    reg [4:0]  rom_idx;      // character index within the ROM line
    reg [3:0]  hex_left;     // nibbles still to emit (8 -> 0)
    reg [31:0] hex_shf;      // shifting hex argument

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_cnt      <= 7'd0;
            ram_pending <= 1'b0;
            ram_len     <= 7'd0;
            ram_rd_idx  <= 7'd0;
            rom_pending <= 1'b0;
            rom_id      <= 3'd0;
            rom_arg     <= 32'd0;
            state       <= ST_IDLE;
            rom_idx     <= 5'd0;
            hex_left    <= 4'd0;
            hex_shf     <= 32'd0;
            tx_byte_data  <= 8'd0;
            tx_byte_valid <= 1'b0;
            rx_byte_cnt   <= 16'd0;
        end else begin
            // tx_byte_valid is a LEVEL handshake, not a strobe: it is cleared
            // only when uart_tx asserts byte_wready. The old strobe advanced
            // rom_idx one cycle before uart_tx sampled the byte, so uart_tx
            // dropped every 2nd/3rd character (board printed 'ITCO' for
            // 'INSTREC BOOT', i.e. idx 0,3,6,9).

            // -------- RX side: loop counter only (M0) --------
            if (rx_byte_valid) begin
                rx_byte_cnt <= rx_byte_cnt + 16'd1;
            end

            // -------- custom line capture --------
            if (dbg_line_wready && dbg_line_wvalid) begin
                line_ram[wr_cnt[6:0]] <= dbg_line_wdata;
                if (dbg_line_wdata == 8'h0A || wr_cnt == 7'd127) begin
                    // Line complete: '\n' seen or buffer full.
                    ram_len     <= (wr_cnt == 7'd127) ? 7'd128
                                                      : wr_cnt + 7'd1;
                    ram_pending <= 1'b1;
                    wr_cnt      <= 7'd0;
                end else begin
                    wr_cnt <= wr_cnt + 7'd1;
                end
            end

            // -------- ROM request latching --------
            if (dbg_line_fire && !rom_pending && !ram_pending &&
                (state == ST_IDLE)) begin
                rom_pending <= 1'b1;
                rom_id      <= dbg_line_id;
                rom_arg     <= dbg_line_arg;
            end

            // -------- TX engine --------
            case (state)
                ST_IDLE: begin
                    if (ram_pending) begin
                        ram_rd_idx <= 7'd0;
                        state      <= ST_RAM;
                    end else if (rom_pending) begin
                        rom_idx <= 5'd0;
                        hex_shf <= rom_arg;
                        state   <= ST_ROM;
                    end
                end

                ST_RAM: begin
                    // Load one byte, then hold it until uart_tx accepts it.
                    if (!tx_byte_valid) begin
                        tx_byte_data  <= line_ram[ram_rd_idx];
                        tx_byte_valid <= 1'b1;
                    end else if (tx_byte_ready) begin
                        tx_byte_valid <= 1'b0;
                        if (ram_rd_idx == ram_len - 7'd1) begin
                            state       <= ST_IDLE;
                            ram_pending <= 1'b0;
                        end else begin
                            ram_rd_idx <= ram_rd_idx + 7'd1;
                        end
                    end
                end

                ST_ROM: begin
                    // Emit ROM characters; the parameterized line (id 4)
                    // diverts to the hex path after its prefix. Index and
                    // state advance only on the actual handshake.
                    if (!tx_byte_valid) begin
                        tx_byte_data  <= rom_char(rom_id, rom_idx);
                        tx_byte_valid <= 1'b1;
                    end else if (tx_byte_ready) begin
                        tx_byte_valid <= 1'b0;
                        if (rom_id == LINE_ID_DDRERR &&
                            rom_idx == LINE_LEN_DDRERR - 5'd1) begin
                            hex_left <= 4'd8;
                            state    <= ST_HEX;
                        end else if (rom_idx == rom_len(rom_id) - 5'd1) begin
                            // Plain line already carries its terminating LF.
                            state       <= ST_IDLE;
                            rom_pending <= 1'b0;
                        end else begin
                            rom_idx <= rom_idx + 5'd1;
                        end
                    end
                end

                ST_HEX: begin
                    // Emit 8 uppercase hex digits, MSB nibble first.
                    if (!tx_byte_valid) begin
                        tx_byte_data  <= hex_ascii(hex_shf[31:28]);
                        tx_byte_valid <= 1'b1;
                    end else if (tx_byte_ready) begin
                        tx_byte_valid <= 1'b0;
                        hex_shf       <= {hex_shf[27:0], 4'd0};
                        if (hex_left == 4'd1) begin
                            state <= ST_EOL;
                        end else begin
                            hex_left <= hex_left - 4'd1;
                        end
                    end
                end

                ST_EOL: begin
                    // Terminate the parameterized line.
                    if (!tx_byte_valid) begin
                        tx_byte_data  <= 8'h0A;
                        tx_byte_valid <= 1'b1;
                    end else if (tx_byte_ready) begin
                        tx_byte_valid <= 1'b0;
                        state         <= ST_IDLE;
                        rom_pending   <= 1'b0;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule