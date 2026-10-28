// ---------------------------------------------------------------------------
// npu_top.v -- InstRec INT8 NPU top level (T-M2-06 integration skeleton)
//
// Chain: conv1 -> pool1 -> conv2 -> pool2 -> conv3 -> pool3 -> conv4 ->
//        pool4 -> gap -> fc1 -> fc2 -> softmax.
//
// Fully wired here: activation stream between stages, layer sequencer,
// GAP result capture, FC input replay, fc2 -> softmax logits bus.
//
// Deliberately left as tie-offs (single remaining producer):
//   * the 48-beat group contract (16 bias / 16 M / 16 shift) for
//     conv_engine, and the per-channel M/shift contract for fc_engine;
//   * wdma currently streams weight taps only, so all contract inputs are
//     tied to zero. The sequencer/topology is final; only the contract
//     loader remains.
//
// Budget: 200 ms at 125 MHz = 25,000,000 cycles; timeout_flag latches at
// 2x that (REQ-REL-002).
// ---------------------------------------------------------------------------

module npu_top (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        start,
    output reg         busy,
    output reg         done,
    output reg  [31:0] npu_cycles,
    output reg         timeout_flag,

    // Mel feature read port: address now, data next cycle (mel_engine's
    // bank is a 1-cycle synchronous read).
    output wire [14:0] feat_rd_addr,
    input  wire [7:0]  feat_rd_data,
    output wire        feat_rd_en,

    output wire        rd_cmd_valid,
    output wire [36:0] rd_cmd,
    input  wire        rd_ready,
    input  wire [255:0] rd_data,
    input  wire        rd_valid,
    input  wire        rd_done,

    output wire        probs_valid,
    output wire [7:0]  probs_pct,
    output wire [3:0]  probs_idx,
    output wire [3:0]  top1
);

    localparam [31:0] TIMEOUT_CYCLES = 32'd50_000_000;

    localparam [3:0] L_CONV1 = 4'd0;
    localparam [3:0] L_POOL1 = 4'd1;
    localparam [3:0] L_CONV2 = 4'd2;
    localparam [3:0] L_POOL2 = 4'd3;
    localparam [3:0] L_CONV3 = 4'd4;
    localparam [3:0] L_POOL3 = 4'd5;
    localparam [3:0] L_CONV4 = 4'd6;
    localparam [3:0] L_POOL4 = 4'd7;
    localparam [3:0] L_GAP   = 4'd8;
    localparam [3:0] L_FC1   = 4'd9;
    localparam [3:0] L_FC2   = 4'd10;
    localparam [3:0] L_SM    = 4'd11;

    reg [3:0] layer;
    reg [1:0] settle;
    reg       layer_pulse;

    wire conv1_start = (layer == L_CONV1) && layer_pulse;
    wire pool1_start = (layer == L_POOL1) && layer_pulse;
    wire conv2_start = (layer == L_CONV2) && layer_pulse;
    wire pool2_start = (layer == L_POOL2) && layer_pulse;
    wire conv3_start = (layer == L_CONV3) && layer_pulse;
    wire pool3_start = (layer == L_POOL3) && layer_pulse;
    wire conv4_start = (layer == L_CONV4) && layer_pulse;
    wire pool4_start = (layer == L_POOL4) && layer_pulse;
    wire gap_start   = (layer == L_GAP)   && layer_pulse;
    wire fc1_start   = (layer == L_FC1)   && layer_pulse;
    wire fc2_start   = (layer == L_FC2)   && layer_pulse;

    wire conv1_done, pool1_done, conv2_done, pool2_done;
    wire conv3_done, pool3_done, conv4_done, pool4_done;
    wire gap_done, fc1_done, fc2_done, sm_done;

    wire       c1_v; wire [7:0] c1_d;
    wire       p1_v; wire [7:0] p1_d;
    wire       c2_v; wire [7:0] c2_d;
    wire       p2_v; wire [7:0] p2_d;
    wire       c3_v; wire [7:0] c3_d;
    wire       p3_v; wire [7:0] p3_d;
    wire       c4_v; wire [7:0] c4_d;
    wire       p4_v; wire [7:0] p4_d;

    wire        w_valid;
    wire [127:0] w_data;
    wire        grp_start;
    wire        wdma_done;
    wire        wl_b_valid, wl_m_valid, wl_s_valid;
    wire signed [31:0] wl_bias, wl_m;
    wire [6:0]  wl_shift;

    // Only the conv instance owning the current layer may consume the
    // 48-beat contract; all four share the same data bus.
    wire cb1 = wl_b_valid && (layer == L_CONV1);
    wire cm1 = wl_m_valid && (layer == L_CONV1);
    wire cs1 = wl_s_valid && (layer == L_CONV1);
    wire cb2 = wl_b_valid && (layer == L_CONV2);
    wire cm2 = wl_m_valid && (layer == L_CONV2);
    wire cs2 = wl_s_valid && (layer == L_CONV2);
    wire cb3 = wl_b_valid && (layer == L_CONV3);
    wire cm3 = wl_m_valid && (layer == L_CONV3);
    wire cs3 = wl_s_valid && (layer == L_CONV3);
    wire cb4 = wl_b_valid && (layer == L_CONV4);
    wire cm4 = wl_m_valid && (layer == L_CONV4);
    wire cs4 = wl_s_valid && (layer == L_CONV4);
    wire fb1 = wl_b_valid && (layer == L_FC1);
    wire fm1 = wl_m_valid && (layer == L_FC1);
    wire fs1 = wl_s_valid && (layer == L_FC1);
    wire fb2 = wl_b_valid && (layer == L_FC2);
    wire fm2 = wl_m_valid && (layer == L_FC2);
    wire fs2 = wl_s_valid && (layer == L_FC2);
    wire        wdma_busy;
    wire [3:0]  conv_wready;
    wire [3:0]  conv_grpadv;
    wire [15:0] gap_unused_rdata;

    wdma u_wdma (
        .clk          (clk),
        .rst_n        (rst_n),
        .start        (layer_pulse && (layer <= L_FC2)),
        .layer_id     (layer),
        .rd_cmd_valid (rd_cmd_valid),
        .rd_cmd       (rd_cmd),
        .rd_ready     (rd_ready),
        .rd_data      (rd_data),
        .rd_valid     (rd_valid),
        .rd_done      (rd_done),
        .w_valid      (w_valid),
        .w_data       (w_data),
        .w_ready      (1'b1),
        .grp_start    (grp_start),
        .b_valid      (wl_b_valid), .bias_s32 (wl_bias),
        .m_valid      (wl_m_valid), .m_s32    (wl_m),
        .s_valid      (wl_s_valid), .shift    (wl_shift),
        .busy         (wdma_busy),
        .done         (wdma_done)
    );

    // Feature replay: 64x258 uint8 stream read from mel_engine.
    reg [14:0] feat_addr;
    reg        feat_run, feat_dv;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            feat_addr <= 15'd0;
            feat_run  <= 1'b0;
            feat_dv   <= 1'b0;
        end else if (conv1_start) begin
            feat_addr <= 15'd0;
            feat_run  <= 1'b1;
            feat_dv   <= 1'b0;
        end else if (feat_run) begin
            feat_dv <= 1'b1;
            if (feat_addr == 15'd16511) feat_run <= 1'b0;
            else                        feat_addr <= feat_addr + 15'd1;
        end else begin
            feat_dv <= 1'b0;
        end
    end
    assign feat_rd_addr = feat_addr;
    assign feat_rd_en   = feat_run;

    conv_engine #(.CIN(1), .COUT(48), .H_IN(64), .W_IN(258)) u_conv1 (
        .clk(clk), .rst_n(rst_n),
        .cfg_valid(1'b0), .cfg_zp_in(8'd49), .cfg_zp_out(8'd0),
        .layer_start(conv1_start), .layer_done(conv1_done),
        .x_valid(feat_dv), .x_u8(feat_rd_data),
        .grp_start(grp_start),
        .bias_valid(cb1), .bias_s32(wl_bias),
        .mult_valid(cm1), .m_s32(wl_m),
        .shft_valid(cs1), .shift(wl_shift),
        .w_valid(w_valid), .w_data(w_data), .w_ready(conv_wready[0]),
        .y_valid(c1_v), .y_u8(c1_d), .grp_advance(conv_grpadv[0])
    );

    pool_engine #(.CIN(48), .W_IN(258), .H_IN(64)) u_pool1 (
        .clk(clk), .rst_n(rst_n), .layer_start(pool1_start),
        .y_valid(c1_v), .y_u8(c1_d),
        .p_valid(p1_v), .p_u8(p1_d), .p_last(pool1_done)
    );

    conv_engine #(.CIN(48), .COUT(96), .H_IN(32), .W_IN(129)) u_conv2 (
        .clk(clk), .rst_n(rst_n),
        .cfg_valid(1'b0), .cfg_zp_in(8'd0), .cfg_zp_out(8'd0),
        .layer_start(conv2_start), .layer_done(conv2_done),
        .x_valid(p1_v), .x_u8(p1_d),
        .grp_start(grp_start),
        .bias_valid(cb2), .bias_s32(wl_bias),
        .mult_valid(cm2), .m_s32(wl_m),
        .shft_valid(cs2), .shift(wl_shift),
        .w_valid(w_valid), .w_data(w_data), .w_ready(conv_wready[1]),
        .y_valid(c2_v), .y_u8(c2_d), .grp_advance(conv_grpadv[1])
    );

    pool_engine #(.CIN(96), .W_IN(129), .H_IN(32)) u_pool2 (
        .clk(clk), .rst_n(rst_n), .layer_start(pool2_start),
        .y_valid(c2_v), .y_u8(c2_d),
        .p_valid(p2_v), .p_u8(p2_d), .p_last(pool2_done)
    );

    conv_engine #(.CIN(96), .COUT(192), .H_IN(16), .W_IN(64)) u_conv3 (
        .clk(clk), .rst_n(rst_n),
        .cfg_valid(1'b0), .cfg_zp_in(8'd0), .cfg_zp_out(8'd0),
        .layer_start(conv3_start), .layer_done(conv3_done),
        .x_valid(p2_v), .x_u8(p2_d),
        .grp_start(grp_start),
        .bias_valid(cb3), .bias_s32(wl_bias),
        .mult_valid(cm3), .m_s32(wl_m),
        .shft_valid(cs3), .shift(wl_shift),
        .w_valid(w_valid), .w_data(w_data), .w_ready(conv_wready[2]),
        .y_valid(c3_v), .y_u8(c3_d), .grp_advance(conv_grpadv[2])
    );

    pool_engine #(.CIN(192), .W_IN(64), .H_IN(16)) u_pool3 (
        .clk(clk), .rst_n(rst_n), .layer_start(pool3_start),
        .y_valid(c3_v), .y_u8(c3_d),
        .p_valid(p3_v), .p_u8(p3_d), .p_last(pool3_done)
    );

    conv_engine #(.CIN(192), .COUT(256), .H_IN(8), .W_IN(32)) u_conv4 (
        .clk(clk), .rst_n(rst_n),
        .cfg_valid(1'b0), .cfg_zp_in(8'd0), .cfg_zp_out(8'd0),
        .layer_start(conv4_start), .layer_done(conv4_done),
        .x_valid(p3_v), .x_u8(p3_d),
        .grp_start(grp_start),
        .bias_valid(cb4), .bias_s32(wl_bias),
        .mult_valid(cm4), .m_s32(wl_m),
        .shft_valid(cs4), .shift(wl_shift),
        .w_valid(w_valid), .w_data(w_data), .w_ready(conv_wready[3]),
        .y_valid(c4_v), .y_u8(c4_d), .grp_advance(conv_grpadv[3])
    );

    pool_engine #(.CIN(256), .W_IN(32), .H_IN(8)) u_pool4 (
        .clk(clk), .rst_n(rst_n), .layer_start(pool4_start),
        .y_valid(c4_v), .y_u8(c4_d),
        .p_valid(p4_v), .p_u8(p4_d), .p_last(pool4_done)
    );

    wire        gap_we;
    wire [7:0]  gap_waddr;
    wire [15:0] gap_wdata;

    gap_unit #(.CIN(256), .H_IN(4), .W_IN(16)) u_gap (
        .clk(clk), .rst_n(rst_n), .layer_start(gap_start),
        .y_valid(p4_v), .y_u8(p4_d),
        .g_raddr(8'd0), .g_rdata(gap_unused_rdata),
        .gap_done(gap_done),
        .gap_waddr(gap_waddr), .gap_we(gap_we), .gap_wdata(gap_wdata)
    );

    // Capture GAP results, then replay them into fc1 (256 beats).
    reg [15:0] gap_buf [0:255];
    always @(posedge clk) begin
        if (gap_we) gap_buf[gap_waddr] <= gap_wdata;
    end

    reg [7:0] fc_x_cnt;
    reg       fc_x_run;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fc_x_cnt <= 8'd0;
            fc_x_run <= 1'b0;
        end else if (fc1_start) begin
            fc_x_cnt <= 8'd0;
            fc_x_run <= 1'b1;
        end else if (fc_x_run) begin
            if (fc_x_cnt == 8'd255) fc_x_run <= 1'b0;
            else                    fc_x_cnt <= fc_x_cnt + 8'd1;
        end
    end

    wire        fc1_x_valid = fc_x_run;
    wire [15:0] fc1_x_s16   = gap_buf[fc_x_cnt];

    wire       fc1_y_valid;
    wire [7:0] fc1_y;
    wire       fc2_y_valid;
    wire [7:0] fc2_y;

    fc_engine #(.CIN(256), .COUT(128), .ZP_IN(8'd0), .ZP_OUT(8'd0)) u_fc1 (
        .clk(clk), .rst_n(rst_n), .layer_start(fc1_start),
        .x_valid(fc1_x_valid), .x_s16(fc1_x_s16),
        .w_valid(w_valid), .w_data(w_data), .w_ready(conv_wready[0]),
        .b_valid(fb1), .bias_s32(wl_bias), .m_valid(fm1), .m_s32(wl_m),
        .s_valid(fs1), .shift(wl_shift),
        .y_valid(fc1_y_valid), .y_u8(fc1_y), .done(fc1_done)
    );

    fc_engine #(.CIN(128), .COUT(16), .ZP_IN(8'd0), .ZP_OUT(8'd57)) u_fc2 (
        .clk(clk), .rst_n(rst_n), .layer_start(fc2_start),
        .x_valid(fc1_y_valid), .x_s16({8'd0, fc1_y}),
        .w_valid(w_valid), .w_data(w_data), .w_ready(conv_wready[1]),
        .b_valid(fb2), .bias_s32(wl_bias), .m_valid(fm2), .m_s32(wl_m),
        .s_valid(fs2), .shift(wl_shift),
        .y_valid(fc2_y_valid), .y_u8(fc2_y), .done(fc2_done)
    );

    // fc2 produces 16 lanes (8 real + 8 padding); softmax consumes 8.
    reg [255:0] logits_bus;
    reg [3:0]   fc2_lane;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            logits_bus <= 256'd0;
            fc2_lane   <= 4'd0;
        end else if (fc2_start) begin
            fc2_lane   <= 4'd0;
        end else if (fc2_y_valid && fc2_lane < 4'd8) begin
            logits_bus[fc2_lane*32 +: 32] <=
                $signed({24'd0, fc2_y}) - 32'sd57;
            fc2_lane <= fc2_lane + 4'd1;
        end
    end

    reg sm_start;
    wire [15:0] sm_q16;
    wire [7:0]  sm_pct;
    wire [3:0]  sm_idx;

    softmax_top u_softmax (
        .clk(clk), .rst_n(rst_n), .start(sm_start),
        .logits(logits_bus),
        .out_valid(probs_valid), .out_q16(sm_q16),
        .out_pct(sm_pct), .out_idx(sm_idx),
        .top1_idx(top1), .done(sm_done)
    );

    assign probs_pct = sm_pct;
    assign probs_idx = sm_idx;

    wire layer_finished =
        (layer == L_CONV1) ? conv1_done :
        (layer == L_POOL1) ? pool1_done :
        (layer == L_CONV2) ? conv2_done :
        (layer == L_POOL2) ? pool2_done :
        (layer == L_CONV3) ? conv3_done :
        (layer == L_POOL3) ? pool3_done :
        (layer == L_CONV4) ? conv4_done :
        (layer == L_POOL4) ? pool4_done :
        (layer == L_GAP)   ? gap_done  :
        (layer == L_FC1)   ? fc1_done  :
        (layer == L_FC2)   ? fc2_done  : 1'b0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy         <= 1'b0;
            done         <= 1'b0;
            npu_cycles   <= 32'd0;
            timeout_flag <= 1'b0;
            layer        <= L_CONV1;
            settle       <= 2'd0;
            layer_pulse  <= 1'b0;
            sm_start     <= 1'b0;
        end else begin
            layer_pulse <= 1'b0;
            sm_start    <= 1'b0;
            done        <= 1'b0;

            if (timeout_flag == 1'b0 && npu_cycles >= TIMEOUT_CYCLES)
                timeout_flag <= 1'b1;

            if (!busy) begin
                if (start) begin
                    busy       <= 1'b1;
                    layer      <= L_CONV1;
                    npu_cycles <= 32'd0;
                    settle     <= 2'd0;
                    layer_pulse<= 1'b1;
                end
            end else begin
                npu_cycles <= npu_cycles + 32'd1;

                if (settle != 2'd0) begin
                    settle <= settle - 2'd1;
                    if (settle == 2'd1) layer_pulse <= 1'b1;
                end else if (layer_finished) begin
                    if (layer == L_FC2) begin
                        sm_start <= 1'b1;
                        layer    <= L_SM;
                        settle   <= 2'd1;
                    end else if (layer == L_SM) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                    end else begin
                        layer  <= layer + 4'd1;
                        settle <= 2'd1;
                    end
                end
            end
        end
    end

endmodule