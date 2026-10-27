// ---------------------------------------------------------------------------
// pool_engine.v -- 2x2 stride-2 max pooling with floor semantics (T-M2-05)
//
// Bit truth: golden_pipeline.maxpool2x2_floor().
//   out_w = W_IN >> 1, out_h = H_IN >> 1; an odd last column/row is never
//   consumed (design.md 4.4, R-10). Max is channel-local.
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
// each CIN*OUT_W bytes. Splitting even/odd columns lets the window read
// (c-1, c) of the previous row and (c-1) of the current row in the same
// cycle with one read port per bank, which is what a DRM primitive offers.
// The odd last column of an odd-width layer is never written or read.
// ---------------------------------------------------------------------------

module pool_engine #(
    parameter CIN  = 48,
    parameter W_IN = 258,
    parameter H_IN = 64
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       layer_start,

    input  wire       y_valid,
    input  wire [7:0] y_u8,

    output reg        p_valid,
    output reg  [7:0] p_u8,
    output reg        p_last
);

    localparam OUT_W    = W_IN >> 1;
    localparam OUT_H    = H_IN >> 1;
    localparam BANK_LEN = CIN * OUT_W;
    localparam [7:0] GRP_LAST = (CIN / 16) - 1;
    localparam [15:0] COL_LAST = (OUT_W << 1) - 1;
    localparam [15:0] ROW_LAST = (OUT_H << 1) - 1;

    reg [7:0] ev0 [0:BANK_LEN-1];
    reg [7:0] od0 [0:BANK_LEN-1];
    reg [7:0] ev1 [0:BANK_LEN-1];
    reg [7:0] od1 [0:BANK_LEN-1];

    reg [3:0]  lane_cnt;
    reg [15:0] col_cnt;
    reg [7:0]  grp_cnt;
    reg [15:0] row_cnt;

    wire [15:0] ch        = {8'd0, grp_cnt} * 16 + {12'd0, lane_cnt};
    wire [15:0] col_half  = col_cnt >> 1;
    wire [15:0] wr_idx    = ch * OUT_W + col_half;
    wire [15:0] rd_idx    = wr_idx;

    wire row_hi = row_cnt[0];
    wire col_hi = col_cnt[0];

    // write the incoming pixel (only the columns kept by floor pooling)
    always @(posedge clk) begin
        if (y_valid && col_cnt <= COL_LAST) begin
            if (!row_hi) begin
                if (!col_hi) ev0[wr_idx] <= y_u8;
                else         od0[wr_idx] <= y_u8;
            end else begin
                if (!col_hi) ev1[wr_idx] <= y_u8;
                else         od1[wr_idx] <= y_u8;
            end
        end
    end

    // Synchronous window read (DRM has a 1-cycle read latency):
    // stage 1 registers the address, stage 2 captures the data, and the
    // y/valid/last flags are delayed two beats to stay aligned.
    reg [15:0] rd_idx_q;
    reg        rd_row_hi_q;
    reg [7:0]  y_d1, y_d2;
    reg        fire_d1, fire_d2;
    reg        last_d1, last_d2;

    reg [7:0]  prev_even_q, prev_odd_q, cur_even_q;

    wire fire_c = y_valid && row_hi && col_hi && (col_cnt <= COL_LAST);
    wire last_c = fire_c && (row_cnt == ROW_LAST) && (grp_cnt == GRP_LAST) &&
                  (col_cnt == COL_LAST) && (lane_cnt == 4'd15);

    always @(posedge clk) begin
        rd_idx_q    <= rd_idx;
        rd_row_hi_q <= row_hi;
        y_d1        <= y_u8;
        y_d2        <= y_d1;
        fire_d1     <= fire_c;
        fire_d2     <= fire_d1;
        last_d1     <= last_c;
        last_d2     <= last_d1;
    end

    always @(posedge clk) begin
        if (!rd_row_hi_q) begin
            prev_even_q <= ev1[rd_idx_q];
            prev_odd_q  <= od1[rd_idx_q];
            cur_even_q  <= ev0[rd_idx_q];
        end else begin
            prev_even_q <= ev0[rd_idx_q];
            prev_odd_q  <= od0[rd_idx_q];
            cur_even_q  <= ev1[rd_idx_q];
        end
    end

    wire [7:0] m_prev = (prev_even_q > prev_odd_q) ? prev_even_q : prev_odd_q;
    wire [7:0] m_cur  = (cur_even_q  > y_d2)       ? cur_even_q  : y_d2;
    wire [7:0] p_max  = (m_prev      > m_cur)      ? m_prev      : m_cur;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lane_cnt <= 4'd0;
            col_cnt  <= 16'd0;
            grp_cnt  <= 8'd0;
            row_cnt  <= 16'd0;
            p_valid  <= 1'b0;
            p_u8     <= 8'd0;
            p_last   <= 1'b0;
        end else if (layer_start) begin
            lane_cnt <= 4'd0;
            col_cnt  <= 16'd0;
            grp_cnt  <= 8'd0;
            row_cnt  <= 16'd0;
            p_valid  <= 1'b0;
            p_last   <= 1'b0;
        end else begin
            p_valid <= fire_d2;
            if (fire_d2) p_u8 <= p_max;
            if (last_d2) p_last <= 1'b1;

            if (y_valid) begin
                if (lane_cnt == 4'd15) begin
                    lane_cnt <= 4'd0;
                    if (col_cnt == W_IN - 1) begin
                        col_cnt <= 16'd0;
                        if (grp_cnt == GRP_LAST) begin
                            grp_cnt <= 8'd0;
                            row_cnt <= row_cnt + 16'd1;
                        end else begin
                            grp_cnt <= grp_cnt + 8'd1;
                        end
                    end else begin
                        col_cnt <= col_cnt + 16'd1;
                    end
                end else begin
                    lane_cnt <= lane_cnt + 4'd1;
                end
            end
        end
    end

endmodule