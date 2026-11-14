// -----------------------------------------------------------------------------
// uart_rx - 115200 8N1 receiver (tasks.md T-M0-09 uart_debug group,
//           design.md Sec. 2.2.9 contract)
// -----------------------------------------------------------------------------
// Reception strategy (chosen for robustness, documented per task note):
//   * two-stage synchronizer on the asynchronous input pin (REQ-AUD-007
//     style protection, 125 MHz domain);
//   * mid-bit sampling (not 16x oversampling): after the START falling
//     edge is seen, wait 1.5 bit periods and sample bit0 at its center,
//     then sample every 1 bit period. At 115200 baud a bit lasts 8.68 us
//     (1085 core_clk cycles), so glitches far shorter than a bit cannot
//     pass the half-bit start qualification;
//   * START re-validation: at the start-bit midpoint the line must still
//     be low, otherwise the detection is discarded as a glitch;
//   * STOP check: the stop bit is sampled at its midpoint; a low level
//     is a framing error and the byte is dropped (no byte_rvalid pulse),
//     the receiver returns to idle hunting for the next START edge.
//
// Baud divider (self-check, same math as uart_tx):
//   BAUD_DIV = round(125e6 / 115200) = 1085 -> +0.0064% (64 ppm) error.
//   Mid-bit sample positions: start-bit center at 0.5 x 1085 = 542.5
//   -> 543 cycles after the synced falling edge; bit0 is sampled one
//   bit period later, at 1.5 bits. Accumulated TX/RX divider mismatch over a
//   10-bit frame is 10 x 0.0064% = 0.064% of a bit period (5.6 ns),
//   negligible against the half-bit sampling margin (4.34 us).
//
// All logic runs in the core_clk (125 MHz) domain. The physical pin is
// uart_rxd (pin B24, LVCMOS33; pin constraint is the responsibility of
// T-M0-09 instrec_top.fdc).
// -----------------------------------------------------------------------------
module uart_rx #(
    // Baud divider: round(125e6/115200) = 1085 (+0.0064% baud error).
    parameter integer BAUD_DIV = 1085
) (
    input  wire       clk,           // core_clk 125 MHz
    input  wire       rst_n,         // core-domain reset, sync release
    input  wire       uart_rxd,      // asynchronous serial input pin (B24)
    output reg  [7:0] byte_rdata,    // received byte
    output reg        byte_rvalid    // one-cycle pulse per good byte
);

    // ------------------------------------------------------------------
    // Two-stage synchronizer for the asynchronous input.
    // ------------------------------------------------------------------
    reg rxd_meta;
    reg rxd_sync;
    reg rxd_prev;   // one-cycle delayed copy for edge detection

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rxd_meta <= 1'b1;   // line idles high
            rxd_sync <= 1'b1;
            rxd_prev <= 1'b1;
        end else begin
            rxd_meta <= uart_rxd;
            rxd_sync <= rxd_meta;
            rxd_prev <= rxd_sync;
        end
    end

    // Falling edge = START candidate.
    wire start_edge = rxd_prev & ~rxd_sync;

    // ------------------------------------------------------------------
    // Sampler: mid-bit positions relative to the synced START edge.
    //   start midpoint : 0.5 x BAUD_DIV = 542.5 -> 543 cycles
    //   each data bit  : 1 x BAUD_DIV  = 1085 cycles after previous sample
    // ------------------------------------------------------------------
    localparam integer START_MID = (BAUD_DIV + 1) / 2;

    reg [1:0]  state;
    reg [10:0] samp_cnt;
    reg [3:0]  bit_idx;      // 0..7 data bits, then stop check
    reg [7:0]  shifter;

    localparam [1:0] ST_IDLE  = 2'd0;
    localparam [1:0] ST_START = 2'd1;
    localparam [1:0] ST_DATA  = 2'd2;
    localparam [1:0] ST_STOP  = 2'd3;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= ST_IDLE;
            samp_cnt  <= 11'd0;
            bit_idx   <= 4'd0;
            shifter   <= 8'd0;
            byte_rdata  <= 8'd0;
            byte_rvalid <= 1'b0;
        end else begin
            byte_rvalid <= 1'b0;

            case (state)
                ST_IDLE: begin
                    if (start_edge) begin
                        samp_cnt <= 11'd0;
                        state    <= ST_START;
                    end
                end

                ST_START: begin
                    // Qualify the start bit at its midpoint.
                    if (samp_cnt == START_MID - 1) begin
                        samp_cnt <= 11'd0;
                        if (rxd_sync == 1'b0) begin
                            bit_idx <= 4'd0;
                            state   <= ST_DATA;
                        end else begin
                            state <= ST_IDLE;   // glitch, discard
                        end
                    end else begin
                        samp_cnt <= samp_cnt + 11'd1;
                    end
                end

                ST_DATA: begin
                    // Sample each data bit at its center, LSB first.
                    if (samp_cnt == BAUD_DIV - 1) begin
                        samp_cnt <= 11'd0;
                        shifter  <= {rxd_sync, shifter[7:1]};
                        if (bit_idx == 4'd7) begin
                            state <= ST_STOP;
                        end else begin
                            bit_idx <= bit_idx + 4'd1;
                        end
                    end else begin
                        samp_cnt <= samp_cnt + 11'd1;
                    end
                end

                ST_STOP: begin
                    // Sample the stop bit at its center.
                    if (samp_cnt == BAUD_DIV - 1) begin
                        if (rxd_sync == 1'b1) begin
                            byte_rdata  <= shifter;
                            byte_rvalid <= 1'b1;   // good frame
                        end
                        // else: framing error, byte dropped
                        state <= ST_IDLE;
                    end else begin
                        samp_cnt <= samp_cnt + 11'd1;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule
