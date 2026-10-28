// ---------------------------------------------------------------------------
// feat_copy_engine.v -- copy one Mel window into the display page (M3)
//
// Reads 16512 bytes (258 x 64) from mel_engine's feature port and writes
// them into feat_page_buf. mel returns data one cycle after the address, so
// the copy keeps a 1-beat pipeline: present addr N, write the data of N-1.
// At the end the destination page flips.
//
// The mel feature port is shared with the NPU; the caller gates this engine
// with npu_feat_rd_en (NPU priority). start only when the NPU is idle.
// ---------------------------------------------------------------------------

module feat_copy_engine (
    input  wire        core_clk,
    input  wire        core_rst_n,

    input  wire        start,
    input  wire        busy_in,

    output reg  [14:0] src_addr,
    output reg         src_en,
    input  wire [7:0]  src_data,

    output reg  [14:0] dst_addr,
    output reg  [7:0]  dst_data,
    output reg         dst_we,
    output reg         dst_page,

    output reg         done
);

    localparam DEPTH = 16512;

    reg [14:0] idx;
    reg [14:0] idx_q;
    reg        run;
    reg        fin;       // last byte written; flip page on the next beat

    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            idx      <= 15'd0;
            idx_q    <= 15'd0;
            run      <= 1'b0;
            fin      <= 1'b0;
            src_addr <= 15'd0;
            src_en   <= 1'b0;
            dst_addr <= 15'd0;
            dst_data <= 8'd0;
            dst_we   <= 1'b0;
            dst_page <= 1'b0;
            done     <= 1'b0;
        end else begin
            src_en <= 1'b0;
            dst_we <= 1'b0;
            done   <= 1'b0;

            if (!run) begin
                if (start && !busy_in) begin
                    run      <= 1'b1;
                    idx      <= 15'd0;
                    idx_q    <= 15'd0;
                    src_addr <= 15'd0;
                    src_en   <= 1'b1;
                end
            end else if (!busy_in) begin
                idx_q <= idx;
                if (idx != 15'd0) begin
                    dst_addr <= idx_q;
                    dst_data <= src_data;
                    dst_we   <= 1'b1;
                end

                if (idx == DEPTH) begin
                    // The final byte is written on THIS beat; flip the page
                    // one beat later so it lands in the completed page.
                    fin    <= 1'b1;
                    src_en <= 1'b0;
                end else begin
                    idx      <= idx + 15'd1;
                    src_addr <= idx + 15'd1;
                    src_en   <= ((idx + 15'd1) < DEPTH);
                end

                if (fin && idx == DEPTH) begin
                    run      <= 1'b0;
                    fin      <= 1'b0;
                    dst_page <= ~dst_page;
                    done     <= 1'b1;
                end
            end
        end
    end

endmodule
