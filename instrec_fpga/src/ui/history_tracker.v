// history_tracker: last eight cumulative class boundaries, oldest to newest.
// Animation updates never enter this buffer. KEY2 clears only history.
module history_tracker #(
    parameter PIXEL_HZ = 148500000,
    parameter DEBOUNCE_MS = 20
) (
    input wire pix_clk, pix_rst_n,
    input wire frame_update,
    input wire [63:0] frame_boundaries,
    input wire clear_n,
    output reg [511:0] history_boundaries,
    output reg [3:0] history_count
);
    localparam DEBOUNCE_CYCLES = (PIXEL_HZ / 1000) * DEBOUNCE_MS;
    reg clear_meta, clear_sync, clear_stable, clear_prev;
    reg [31:0] clear_debounce;
    wire clear_event = clear_prev && !clear_stable;
    always @(posedge pix_clk or negedge pix_rst_n) begin
        if (!pix_rst_n) begin
            clear_meta <= 1'b1;
            clear_sync <= 1'b1;
            clear_stable <= 1'b1;
            clear_prev <= 1'b1;
            clear_debounce <= 32'd0;
            history_boundaries <= 512'd0;
            history_count <= 4'd0;
        end else begin
            clear_meta <= clear_n;
            clear_sync <= clear_meta;
            clear_prev <= clear_stable;
            if (clear_sync == clear_stable) clear_debounce <= 32'd0;
            else if (clear_debounce >= DEBOUNCE_CYCLES - 1) begin
                clear_stable <= clear_sync;
                clear_debounce <= 32'd0;
            end else clear_debounce <= clear_debounce + 32'd1;
            if (clear_event) begin
                history_boundaries <= 512'd0;
                history_count <= 4'd0;
            end else if (frame_update) begin
                history_boundaries <= {frame_boundaries, history_boundaries[511:64]};
                if (history_count < 8) history_count <= history_count + 4'd1;
            end
        end
    end
endmodule
