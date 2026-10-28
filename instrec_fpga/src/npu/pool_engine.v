// ---------------------------------------------------------------------------
// pool_engine.v -- 2x2 stride-2 max pooling with floor semantics (T-M2-05)
//
// Bit truth: golden_pipeline.maxpool2x2_floor().
//   out_w = w_in >> 1, out_h = h_in >> 1; an odd last column/row is never
//   consumed (design.md 4.4, R-10). Max is channel-local.
//
// Geometry is a runtime input (cin / w_in / h_in), so one instance can serve
// every pooling stage of the InstRec stack: the layer sequencer runs exactly
// one layer at a time, so the four stages never overlap. The caller owns the
// capacity contract below.
//
// Input stream (from conv_engine egress):
//   one beat per cycle, order (row, grp, col, lane 0..15); one pixel carries
//   16 consecutive lanes. lane/col/grp/row are derived by counting.
//
// Output stream (to the next conv_engine ingress):
//   same (row, grp, col, lane) shape at half resolution. p_valid is high for
//   the 16 lanes of one pooled pixel, in lane order, one beat after the
//   second window column arrives.
//
// Storage: four synchronous line banks (row ping-pong x column parity),
// each cin*out_w bytes. Splitting even/odd columns lets the window read
// (c-1, c) of the previous row and (c-1) of the current row in the same
// cycle with one read port per bank, which is what a DRM primitive offers.
// The odd last column of an odd-width layer is never written or read.
// ---------------------------------------------------------------------------

module pool_engine (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        layer_start,

    // Runtime layer geometry. The arrays below are sized for the deepest
    // stack layer (conv1, cin*out_w = 48*129 = 6192), so the caller must
    // keep cin*out_w <= 2*SEG (8192) and cin a multiple of 16.
    input  wire [15:0] cin,
    input  wire [15:0] w_in,
    input  wire [15:0] h_in,

    input  wire        y_valid,
    input  wire [7:0]  y_u8,

    output reg         p_valid,
    output reg  [7:0]  p_u8,
    output reg         p_last
);

    // Block RAM is limited to 4096 words at 8-bit width, while a bank is
    // cin*out_w (up to 6192 bytes). Split each bank into low/high halves and
    // select by address bit 12; otherwise PDS falls back to distributed RAM
    // (ram64x1d) and placement fails.
    localparam SEG = 4096;
    (* syn_ramstyle = "block_ram" *) reg [7:0] ev0_lo [0:SEG-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] ev0_hi [0:SEG-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] od0_lo [0:SEG-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] od0_hi [0:SEG-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] ev1_lo [0:SEG-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] ev1_hi [0:SEG-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] od1_lo [0:SEG-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] od1_hi [0:SEG-1];

    reg [3:0]  lane_cnt;
    reg [15:0] col_cnt;
    reg [7:0]  grp_cnt;
    reg [15:0] row_cnt;

    // Runtime geometry (floor pooling drops an odd last column or row).
    wire [15:0] out_w    = w_in >> 1;                  // pooled columns
    wire [15:0] out_h    = h_in >> 1;                  // pooled rows
    wire [15:0] col_last = (out_w << 1) - 16'd1;       // last consumed column
    wire [15:0] row_last = (out_h << 1) - 16'd1;       // last consumed row
    wire [15:0] col_all  = w_in - 16'd1;               // last column of a row
    wire [15:0] grp_last = (cin >> 4) - 16'd1;         // last 16-channel group

    // Bank index = ch * out_w + col_half, with ch = grp*16 + lane. It is
    // accumulated (+out_w per lane step) instead of multiplying at runtime;
    // grp_base holds grp*16*out_w so that a column wrap can resume the scan
    // without a multiplier.
    reg [15:0] idx;
    reg [15:0] grp_base;
    wire [15:0] grp_step = out_w << 4;                 // 16 channels * out_w

    wire row_hi = row_cnt[0];
    wire col_hi = col_cnt[0];

    // write the incoming pixel (only the columns kept by floor pooling)
    wire        wr_hi  = idx[12];
    wire [11:0] wr_off = idx[11:0];

    always @(posedge clk) begin
        if (y_valid && col_cnt <= col_last) begin
            if (!row_hi) begin
                if (!col_hi) begin
                    if (!wr_hi) ev0_lo[wr_off] <= y_u8;
                    else        ev0_hi[wr_off] <= y_u8;
                end else begin
                    if (!wr_hi) od0_lo[wr_off] <= y_u8;
                    else        od0_hi[wr_off] <= y_u8;
                end
            end else begin
                if (!col_hi) begin
                    if (!wr_hi) ev1_lo[wr_off] <= y_u8;
                    else        ev1_hi[wr_off] <= y_u8;
                end else begin
                    if (!wr_hi) od1_lo[wr_off] <= y_u8;
                    else        od1_hi[wr_off] <= y_u8;
                end
            end
        end
    end

    always @(posedge clk) begin
        if (y_valid && !col_hi && (col_cnt <= col_last)) cur_prev[lane_cnt] <= y_u8;
    end

    // Synchronous window read (DRM has a 1-cycle read latency):
    // stage 1 registers the address, stage 2 captures the data, and the
    // y/valid/last flags are delayed two beats to stay aligned.
    reg [15:0] rd_idx_q;
    reg        rd_row_hi_q;
    reg [7:0]  y_d1, y_d2;
    reg        fire_d1, fire_d2;
    reg        last_d1, last_d2;
    reg [3:0]  lane_d1, lane_d2;

    reg [7:0]  prev_even_q, prev_odd_q;
    // Current row's (c-1) value per lane, latched on the even column. This
    // removes the second read port on ev0/ev1, which otherwise makes PDS
    // replicate the bank into distributed RAM.
    reg [7:0]  cur_prev [0:15];

    wire fire_c = y_valid && row_hi && col_hi && (col_cnt <= col_last);
    wire last_c = fire_c && (row_cnt == row_last) && (grp_cnt == grp_last[7:0]) &&
                  (col_cnt == col_last) && (lane_cnt == 4'd15);

    always @(posedge clk) begin
        rd_idx_q    <= idx;
        rd_row_hi_q <= row_hi;
        y_d1        <= y_u8;
        y_d2        <= y_d1;
        lane_d1     <= lane_cnt;
        lane_d2     <= lane_d1;
        fire_d1     <= fire_c;
        fire_d2     <= fire_d1;
        last_d1     <= last_c;
        last_d2     <= last_d1;
    end

    wire        rd_hi  = rd_idx_q[12];
    wire [11:0] rd_off = rd_idx_q[11:0];

    always @(posedge clk) begin
        if (!rd_row_hi_q) begin
            prev_even_q <= rd_hi ? ev1_hi[rd_off] : ev1_lo[rd_off];
            prev_odd_q  <= rd_hi ? od1_hi[rd_off] : od1_lo[rd_off];
        end else begin
            prev_even_q <= rd_hi ? ev0_hi[rd_off] : ev0_lo[rd_off];
            prev_odd_q  <= rd_hi ? od0_hi[rd_off] : od0_lo[rd_off];
        end
    end

    wire [7:0] cur_even_d = cur_prev[lane_d2];
    wire [7:0] m_prev = (prev_even_q > prev_odd_q) ? prev_even_q : prev_odd_q;
    wire [7:0] m_cur  = (cur_even_d  > y_d2)       ? cur_even_d  : y_d2;
    wire [7:0] p_max  = (m_prev      > m_cur)      ? m_prev      : m_cur;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lane_cnt <= 4'd0;
            col_cnt  <= 16'd0;
            grp_cnt  <= 8'd0;
            row_cnt  <= 16'd0;
            idx      <= 16'd0;
            grp_base <= 16'd0;
            p_valid  <= 1'b0;
            p_u8     <= 8'd0;
            p_last   <= 1'b0;
        end else if (layer_start) begin
            lane_cnt <= 4'd0;
            col_cnt  <= 16'd0;
            grp_cnt  <= 8'd0;
            row_cnt  <= 16'd0;
            idx      <= 16'd0;
            grp_base <= 16'd0;
            p_valid  <= 1'b0;
            p_last   <= 1'b0;
        end else begin
            p_valid <= fire_d2;
            if (fire_d2) p_u8 <= p_max;
            if (last_d2) p_last <= 1'b1;

            if (y_valid) begin
                if (lane_cnt == 4'd15) begin
                    lane_cnt <= 4'd0;
                    if (col_cnt == col_all) begin
                        col_cnt <= 16'd0;
                        if (grp_cnt == grp_last[7:0]) begin
                            grp_cnt  <= 8'd0;
                            row_cnt  <= row_cnt + 16'd1;
                            idx      <= 16'd0;
                            grp_base <= 16'd0;
                        end else begin
                            grp_cnt  <= grp_cnt + 8'd1;
                            grp_base <= grp_base + grp_step;
                            idx      <= grp_base + grp_step;
                        end
                    end else begin
                        col_cnt <= col_cnt + 16'd1;
                        idx     <= grp_base + ((col_cnt + 16'd1) >> 1);
                    end
                end else begin
                    lane_cnt <= lane_cnt + 4'd1;
                    idx      <= idx + out_w;
                end
            end
        end
    end

endmodule