// -----------------------------------------------------------------------------
// uart_tx - 115200 8N1 transmitter (tasks.md T-M0-09 uart_debug group,
//           design.md Sec. 2.2.9 contract)
// -----------------------------------------------------------------------------
// Single-byte valid/ready handshake transmitter (chosen over a 16-byte
// FIFO for simplicity: the line-print use case is slow status text at
// ~12 lines/s max, and the consumer uart_debug already buffers whole
// lines, so a deep TX FIFO adds nothing).
//
// Baud divider (self-check):
//   BAUD_DIV = round(125e6 / 115200) = round(1085.07) = 1085
//   actual baud = 125e6 / 1085 = 115207.37 baud
//   error = +6.4e-5 = +0.0064% (64 ppm), far inside the 8N1 tolerance
//   (a receiver mid-bit sampler tolerates ~2-3% mismatch).
//   One bit = 1085 core_clk cycles = 8.68 us; one 10-bit frame = 86.8 us.
//
// Frame format (bit-level self-check table, LSB first):
//   bit_idx 0      : START = 0
//   bit_idx 1..8   : DATA[0] .. DATA[7] (LSB first)
//   bit_idx 9      : STOP = 1
//   line idles high after STOP; byte_wready re-asserts only after the
//   STOP bit completes (conservative; ~87 us per byte is plenty for
//   status-line printing).
//
// All logic runs in the core_clk (125 MHz) domain. The physical pin is
// driven by the registered output uart_txd (pin C24, LVCMOS33; pin
// constraint is the responsibility of T-M0-09 instrec_top.fdc).
// -----------------------------------------------------------------------------
module uart_tx #(
    // Baud divider: round(125e6/115200) = 1085 (+0.0064% baud error).
    parameter integer BAUD_DIV = 1085
) (
    input  wire       clk,           // core_clk 125 MHz
    input  wire       rst_n,         // core-domain reset, sync release
    input  wire [7:0] byte_wdata,    // byte to send
    input  wire       byte_wvalid,   // byte request
    output reg        byte_wready,   // handshake: byte accepted when high
    output reg        uart_txd       // serialized output pin (C24)
);

    // ------------------------------------------------------------------
    // Bit engine: one frame = 10 bit slots (start + 8 data + stop),
    // each slot lasting BAUD_DIV core_clk cycles.
    // ------------------------------------------------------------------
    localparam [3:0] BIT_START = 4'd0;
    localparam [3:0] BIT_STOP  = 4'd9;

    reg [3:0]  bit_idx;
    reg [10:0] div_cnt;
    reg [7:0]  tx_byte;
    reg        busy;

    // Combinational bit value for the current slot (start / data / stop).
    // Declared separately from the assign so lint tools read the
    // expression as an expression, not a name list.
    wire tx_bit;

    assign tx_bit = (bit_idx == BIT_START) ? 1'b0 :
                    (bit_idx == BIT_STOP)  ? 1'b1 :
                    tx_byte[bit_idx - 4'd1];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bit_idx     <= 4'd0;
            div_cnt     <= 11'd0;
            tx_byte     <= 8'd0;
            busy        <= 1'b0;
            byte_wready <= 1'b0;
            uart_txd    <= 1'b1;   // line idles high
        end else begin
            // Accept a new byte only when completely idle.  byte_wready is also
            // de-asserted for the cycle right after an accept: with a plain
            // ~busy it stayed high for one extra cycle (busy is updated by a
            // non-blocking assignment), which let uart_debug believe it could
            // hand over the next character and drop it.
            byte_wready <= ~busy & ~(byte_wvalid & byte_wready);

            if (!busy) begin
                if (byte_wvalid && byte_wready) begin
                    tx_byte <= byte_wdata;
                    bit_idx <= BIT_START;
                    div_cnt <= 11'd0;
                    busy    <= 1'b1;
                    // The line stays high this cycle; the busy branch
                    // drives the start bit from the next cycle for a
                    // full BAUD_DIV period, so the start bit is exactly
                    // BAUD_DIV cycles wide (see header timing table).
                end else begin
                    uart_txd <= 1'b1;   // idle line
                end
            end else begin
                uart_txd <= tx_bit;
                if (div_cnt == BAUD_DIV - 1) begin
                    div_cnt <= 11'd0;
                    if (bit_idx == BIT_STOP) begin
                        busy <= 1'b0;   // frame done, back to idle
                    end else begin
                        bit_idx <= bit_idx + 4'd1;
                    end
                end else begin
                    div_cnt <= div_cnt + 11'd1;
                end
            end
        end
    end

endmodule