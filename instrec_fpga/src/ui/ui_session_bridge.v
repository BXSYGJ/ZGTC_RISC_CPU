// ui_session_bridge: debounced keys and a frame-atomic CPU-owned view.
// Held payload cannot be written until the pixel domain acknowledges it.
module ui_session_bridge #(
    parameter CORE_HZ = 125000000
) (
    input wire core_clk, core_rst_n,
    input wire [3:0] keys_n,
    output reg [31:0] key_events,
    input wire write_en,
    input wire [8:0] write_addr,
    input wire [31:0] write_data,
    output wire busy,
    input wire pix_clk, pix_rst_n, frame_start,
    output reg [511:0] view_rows,
    output reg [63:0] view_probs,
    output reg [31:0] view_meta
);
    reg [3:0] key_meta, key_sync, stable, held_long;
    reg [31:0] debounce [0:3];
    reg [31:0] held [0:3];
    reg [607:0] payload;
    reg request, acknowledge;
    reg [1:0] ack_sync, req_sync;
    integer k;
    assign busy = request != ack_sync[1];
    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            key_meta <= 4'hf; key_sync <= 4'hf; stable <= 4'hf;
            held_long <= 0; key_events <= 0;
            for (k=0;k<4;k=k+1) begin debounce[k] <= 0; held[k] <= 0; end
        end else begin
            key_meta <= keys_n; key_sync <= key_meta;
            for (k=0;k<4;k=k+1) begin
                if (key_sync[k] == stable[k]) debounce[k] <= 0;
                else if (debounce[k] >= CORE_HZ/50-1) begin
                    stable[k] <= key_sync[k]; debounce[k] <= 0;
                    if (key_sync[k] && !held_long[k])
                        key_events[k*4 +: 4] <= key_events[k*4 +: 4] + 4'd1;
                end else debounce[k] <= debounce[k] + 1;
                if (stable[k]) begin held[k] <= 0; held_long[k] <= 0; end
                else if (!held_long[k]) begin
                    if (held[k] >= CORE_HZ*3/5-1) begin
                        held_long[k] <= 1;
                        key_events[16+k*4 +: 4] <= key_events[16+k*4 +: 4] + 4'd1;
                    end else held[k] <= held[k] + 1;
                end
            end
        end
    end
    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            payload <= 0; request <= 0; ack_sync <= 0;
        end else begin
            ack_sync <= {ack_sync[0],acknowledge};
            if (write_en && !busy) begin
                if (write_addr >= 9'h100 && write_addr < 9'h140)
                    payload[write_addr[5:2]*32 +: 32] <= write_data;
                case (write_addr)
                    9'h058: payload[607:576] <= write_data;
                    9'h05c: payload[543:512] <= write_data;
                    9'h060: payload[575:544] <= write_data;
                    9'h068: request <= ~request;
                    default: begin end
                endcase
            end
        end
    end
    always @(posedge pix_clk or negedge pix_rst_n) begin
        if (!pix_rst_n) begin
            req_sync <= 0; acknowledge <= 0;
            view_rows <= 0; view_probs <= 0; view_meta <= 0;
        end else begin
            req_sync <= {req_sync[0],request};
            if (frame_start && req_sync[1] != acknowledge) begin
                {view_meta,view_probs,view_rows} <= payload;
                acknowledge <= req_sync[1];
            end
        end
    end
endmodule
