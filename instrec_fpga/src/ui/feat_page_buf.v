// ---------------------------------------------------------------------------
// feat_page_buf.v -- double-buffered Mel feature page (M3)
//
// 258 x 64 uint8, two pages. The core domain writes the latest window into
// one page while the pixel domain reads the other; `page_sel` flips at the
// window boundary so the display never tears mid-frame.
//
// Ports are deliberately simple so the copy engine and the spectrum shader
// can be built independently:
//   core side : wr_en / wr_addr / wr_data, wr_page (page being written)
//   pix side  : rd_addr, rd_data (1-cycle synchronous), rd_page
// ---------------------------------------------------------------------------

module feat_page_buf (
    input  wire        core_clk,
    input  wire        core_rst_n,
    input  wire        wr_en,
    input  wire [14:0] wr_addr,
    input  wire [7:0]  wr_data,
    input  wire        wr_page,      // 0 = page0 being filled, 1 = page1

    input  wire        pix_clk,
    input  wire        pix_rst_n,
    input  wire [14:0] rd_addr,
    output reg  [7:0]  rd_data
);

    localparam DEPTH = 16512;   // 258 * 64

    reg [7:0] page0 [0:DEPTH-1];
    reg [7:0] page1 [0:DEPTH-1];

    // Write side (core domain); wr_page is owned by the copy engine.
    always @(posedge core_clk) begin
        if (wr_en) begin
            if (wr_page) page1[wr_addr] <= wr_data;
            else         page0[wr_addr] <= wr_data;
        end
    end

    // Read side (pixel domain): read the opposite page.
    always @(posedge pix_clk or negedge pix_rst_n) begin
        if (!pix_rst_n) rd_data <= 8'd0;
        else if (wr_page) rd_data <= page0[rd_addr];
        else              rd_data <= page1[rd_addr];
    end

endmodule