// history_tracker: cumulative per-class inference histogram with a clear key.
//
// Lives entirely in the pixel domain.  On every frame_update pulse (one per
// fresh inference result, produced by bars_data at a frame boundary) it bumps
// the counter for the winning class and latches the arrival time.  KEY2 clears
// the whole histogram.  Counters are 8-bit (saturate at 255), so the renderer
// can map them straight onto an 8-bar chart without any extra scaling stage.
//
// Deliberately tiny: 8 x 8-bit counters + a millisecond uptime counter + a
// 2-stage sync / 20 ms debounce on the clear key.
module history_tracker #(
    parameter PIXEL_HZ     = 148500000,
    parameter DEBOUNCE_MS  = 20
) (
    input  wire        pix_clk,
    input  wire        pix_rst_n,
    input  wire        frame_update,     // 1-cycle pulse: new inference result
    input  wire [3:0]  frame_class,      // winning class 0..7
    input  wire        clear_n,          // KEY2, active low
    output reg  [7:0]  hist0, hist1, hist2, hist3,
    output reg  [7:0]  hist4, hist5, hist6, hist7,
    output reg  [31:0] last_time_ms      // arrival uptime of the latest result
);
    localparam [31:0] MS_CYCLES = PIXEL_HZ / 1000;      // 148500 @ 148.5 MHz
    localparam [31:0] DEBOUNCE_LIMIT = MS_CYCLES * DEBOUNCE_MS / 1000;

    reg [31:0] ms_divider;
    reg [31:0] uptime_ms;
    wire       ms_tick = (ms_divider == MS_CYCLES - 1);

    reg        clear_meta, clear_sync, clear_stable;
    reg [31:0] clear_debounce;
    reg        clear_prev;
    wire       clear_event = clear_prev && !clear_stable;   // press edge (1->0)

    reg [7:0]  count [0:7];
    integer    i;

    always @(posedge pix_clk or negedge pix_rst_n) begin
        if (!pix_rst_n) begin
            ms_divider  <= 0;
            uptime_ms   <= 0;
            clear_meta  <= 1'b1;
            clear_sync  <= 1'b1;
            clear_stable<= 1'b1;
            clear_debounce <= 0;
            clear_prev  <= 1'b1;
            last_time_ms<= 0;
            for (i = 0; i < 8; i = i + 1) count[i] <= 8'd0;
        end else begin
            // Millisecond uptime counter.
            if (ms_tick) begin
                ms_divider <= 0;
                if (uptime_ms != 32'hffffffff) uptime_ms <= uptime_ms + 1;
            end else begin
                ms_divider <= ms_divider + 1;
            end

            // KEY2 clear: 2-stage sync + 20 ms debounce, then a press edge.
            clear_meta <= clear_n;
            clear_sync <= clear_meta;
            if (clear_sync == clear_stable) begin
                clear_debounce <= 0;
            end else if (clear_debounce >= DEBOUNCE_LIMIT - 1) begin
                clear_debounce <= 0;
                clear_stable   <= clear_sync;
            end else begin
                clear_debounce <= clear_debounce + 1;
            end
            clear_prev <= clear_stable;

            if (clear_event) begin
                for (i = 0; i < 8; i = i + 1) count[i] <= 8'd0;
                last_time_ms <= 0;
            end else if (frame_update && frame_class < 4'd8) begin
                count[frame_class] <= (count[frame_class] == 8'hff)
                                      ? 8'hff : count[frame_class] + 8'd1;
                last_time_ms <= uptime_ms;
            end
        end
    end

    always @* begin
        hist0 = count[0]; hist1 = count[1]; hist2 = count[2]; hist3 = count[3];
        hist4 = count[4]; hist5 = count[5]; hist6 = count[6]; hist7 = count[7];
    end
endmodule
