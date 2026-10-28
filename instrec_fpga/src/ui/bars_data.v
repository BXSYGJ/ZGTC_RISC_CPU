// ---------------------------------------------------------------------------
// bars_data.v -- probability capture and CDC for the bar overlay (M3)
//
// The NPU emits eight percentage bytes as a stream (probs_valid, 0..7 per
// frame). They are latched in the core_clk domain, then transferred to the
// pixel domain with two flip-flop synchronizers per bit. The update rate is
// one window per 3 s, so a plain 2FF is adequate (a frame may briefly show
// a mixed old/new value, which is invisible at 0.33 Hz).
// ---------------------------------------------------------------------------

module bars_data (
    input  wire       core_clk,
    input  wire       core_rst_n,
    input  wire       probs_valid,
    input  wire [7:0] probs_pct,
    input  wire [3:0] probs_idx,

    input  wire       pix_clk,
    input  wire       pix_rst_n,
    output reg  [7:0] pct0,
    output reg  [7:0] pct1,
    output reg  [7:0] pct2,
    output reg  [7:0] pct3,
    output reg  [7:0] pct4,
    output reg  [7:0] pct5,
    output reg  [7:0] pct6,
    output reg  [7:0] pct7
);

    reg [7:0] lat [0:7];

    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            lat[0] <= 8'd0; lat[1] <= 8'd0;
            lat[2] <= 8'd0; lat[3] <= 8'd0;
            lat[4] <= 8'd0; lat[5] <= 8'd0;
            lat[6] <= 8'd0; lat[7] <= 8'd0;
        end else if (probs_valid && probs_idx < 4'd8) begin
            lat[probs_idx] <= probs_pct;
        end
    end

    // Two-flop synchronizers per byte.
    reg [7:0] s0 [0:7];
    reg [7:0] s1 [0:7];

    always @(posedge pix_clk or negedge pix_rst_n) begin
        if (!pix_rst_n) begin
            s0[0] <= 8'd0; s1[0] <= 8'd0;
            s0[1] <= 8'd0; s1[1] <= 8'd0;
            s0[2] <= 8'd0; s1[2] <= 8'd0;
            s0[3] <= 8'd0; s1[3] <= 8'd0;
            s0[4] <= 8'd0; s1[4] <= 8'd0;
            s0[5] <= 8'd0; s1[5] <= 8'd0;
            s0[6] <= 8'd0; s1[6] <= 8'd0;
            s0[7] <= 8'd0; s1[7] <= 8'd0;
        end else begin
            s0[0] <= lat[0]; s1[0] <= s0[0];
            s0[1] <= lat[1]; s1[1] <= s0[1];
            s0[2] <= lat[2]; s1[2] <= s0[2];
            s0[3] <= lat[3]; s1[3] <= s0[3];
            s0[4] <= lat[4]; s1[4] <= s0[4];
            s0[5] <= lat[5]; s1[5] <= s0[5];
            s0[6] <= lat[6]; s1[6] <= s0[6];
            s0[7] <= lat[7]; s1[7] <= s0[7];
        end
    end

    always @* begin
        pct0 = s1[0]; pct1 = s1[1]; pct2 = s1[2]; pct3 = s1[3];
        pct4 = s1[4]; pct5 = s1[5]; pct6 = s1[6]; pct7 = s1[7];
    end

endmodule