// dashboard_renderer: labeled instrument recognition dashboard.
// Fixed 1080p dashboard. Graphics and text share a four-clock video latency.
// External waveform/feature memories have a one-clock read latency.
module dashboard_renderer #(parameter SIMULATION = 0) (
    input wire pix_clk, rst_pix_n,
    input wire [10:0] pix_x, pix_y,
    input wire pix_de, pix_hs, pix_vs,
    output wire [10:0] wave_rd_addr,
    input wire [15:0] wave_min, wave_max,
    input wire wave_valid, mute_flag_sync,
    input wire feature_ready, result_ready,
    input wire [3:0] class_idx,
    input wire [7:0] pct0, pct1, pct2, pct3, pct4, pct5, pct6, pct7,
    input wire [511:0] history_boundaries,
    input wire [3:0] history_count,
    output wire vsync_pulse,
    output reg [23:0] rgb,
    output wire de_out, hs_out, vs_out
);
    wire in_wave = pix_x >= 128 && pix_x < 1152 && pix_y >= 288 && pix_y < 448;
    wire in_hist = pix_x >= 128 && pix_x < 1152 && pix_y >= 688 && pix_y < 888;
    wire [10:0] dx = pix_x - 11'd128;
    wire [14:0] wave_product = ({4'd0,dx} << 4) - {4'd0,dx};
    assign wave_rd_addr = in_wave ? wave_product[13:3] : 11'd0;
    wire [63:0] percentages = {pct7,pct6,pct5,pct4,pct3,pct2,pct1,pct0};
    wire [2:0] hist_col = (pix_x - 11'd128) >> 7;
    wire [63:0] hist_vector = history_boundaries[hist_col * 64 +: 64];
    function [23:0] class_color;
        input [2:0] category;
        begin
            case (category)
                0: class_color = 24'h75b79d;
                1: class_color = 24'hb393c8;
                2: class_color = 24'hd9a0b5;
                3: class_color = 24'h87b7c8;
                4: class_color = 24'he0bc73;
                5: class_color = 24'hbdaf76;
                6: class_color = 24'hd99572;
                default: class_color = 24'h9aaad1;
            endcase
        end
    endfunction
    wire [23:0] text_rgb;
    wire text_on;
    dashboard_text #(.SIMULATION(SIMULATION)) u_text (
        .pix_clk(pix_clk), .rst_pix_n(rst_pix_n), .pix_x(pix_x), .pix_y(pix_y),
        .pix_de(pix_de), .wave_valid(wave_valid), .feature_ready(feature_ready),
        .result_ready(result_ready), .class_idx(class_idx), .percentages(percentages),
        .rgb(text_rgb), .text_on(text_on)
    );
    reg [10:0] x_s1, y_s1;
    reg wave_s1, hist_s1, wave_ready_s1, result_s1, mute_s1;
    reg [3:0] class_s1;
    reg [63:0] percentages_s1;
    reg [63:0] hist_vector_s1;
    reg hist_valid_s1;
    reg [2:0] hist_col_s1;
    reg [23:0] graph_s2, graph_s3, graph_color;
    reg [3:0] de_pipe, hs_pipe, vs_pipe;
    reg vs_d;
    reg [3:0] bar_row;
    reg [7:0] bar_pct;
    reg [10:0] bar_width;
    reg [6:0] pos_amp, neg_amp;
    reg [15:0] neg_magnitude;
    integer stack_lane;
    reg [8:0] stack_bottom, stack_top;
    reg [7:0] stack_position;
    reg [2:0] legend_class;
    // Wave-band pipeline: register the amplitude extraction (which runs a
    // 16-bit complement carry chain off the wave_min DRM read) one beat,
    // and shift the wave coordinates to match, so the whole wave graphic is
    // drawn from registered values and the wave_min->compare path is split.
    reg [6:0] pos_amp_r, neg_amp_r;
    reg [10:0] x_s2, y_s2;
    reg wave_s2, wave_ready_s2, mute_s2;
    always @* begin
        graph_color = 24'h0b1020;
        if ((x_s1 >= 64 && x_s1 < 1184 && ((y_s1 >= 160 && y_s1 < 512) || (y_s1 >= 544 && y_s1 < 1008))) ||
            (x_s1 >= 1216 && x_s1 < 1856 && y_s1 >= 160 && y_s1 < 1008))
            graph_color = 24'h121c2d;
        if (((x_s1 == 64 || x_s1 == 1183) && ((y_s1 >= 160 && y_s1 < 512) || (y_s1 >= 544 && y_s1 < 1008))) ||
            ((y_s1 == 160 || y_s1 == 511 || y_s1 == 544 || y_s1 == 1007) && x_s1 >= 64 && x_s1 < 1184) ||
            ((x_s1 == 1216 || x_s1 == 1855) && y_s1 >= 160 && y_s1 < 1008) ||
            ((y_s1 == 160 || y_s1 == 1007) && x_s1 >= 1216 && x_s1 < 1856))
            graph_color = 24'h27364c;
        if (y_s1 == 143 && x_s1 >= 64 && x_s1 < 1856) graph_color = 24'h27364c;
        pos_amp = wave_max[15] ? 7'd0 : {1'b0,wave_max[14:9]};
        neg_magnitude = (~wave_min) + 16'd1;
        neg_amp = wave_min[15] ? neg_magnitude[15:9] : 7'd0;
        if (neg_amp > 64) neg_amp = 64;
        if (wave_s2) begin
            graph_color = 24'h0d1726;
            if (x_s2[7:0] == 128 || y_s2 == 304 || y_s2 == 368 || y_s2 == 432) graph_color = 24'h27364c;
            if (wave_ready_s2 && y_s2 >= (11'd368 - {4'd0,pos_amp_r}) && y_s2 <= (11'd368 + {4'd0,neg_amp_r}))
                graph_color = mute_s2 ? 24'h9aabc0 : 24'h36d6c5;
        end
        stack_bottom = 0;
        stack_top = 0;
        stack_position = (11'd887 - y_s1) >> 1;
        if (hist_s1) begin
            graph_color = 24'h0d1726;
            if (y_s1 == 688 || y_s1 == 788 || y_s1 == 887)
                graph_color = 24'h27364c;
            // One inference per column, all eight classes share its height.
            for (stack_lane = 0; stack_lane < 8; stack_lane = stack_lane + 1) begin
                stack_top = {1'b0,hist_vector_s1[stack_lane*8 +: 8]};
                if (hist_valid_s1 && x_s1[6:0] >= 16 && x_s1[6:0] < 112 &&
                    stack_position >= stack_bottom && stack_position < stack_top)
                    graph_color = class_color(stack_lane[2:0]);
                stack_bottom = stack_top;
            end
        end
        legend_class = ((x_s1 - 11'd128) >> 8) + (y_s1 >= 960 ? 3'd4 : 3'd0);
        if (x_s1 >= 128 && x_s1 < 912 && x_s1[7:0] >= 128 && x_s1[7:0] < 144 &&
            ((y_s1 >= 936 && y_s1 < 952) || (y_s1 >= 968 && y_s1 < 984)))
            graph_color = class_color(legend_class);
        bar_row = (y_s1 - 11'd448) >> 6;
        bar_pct = 0;
        if (bar_row < 8) bar_pct = percentages_s1[bar_row*8 +: 8];
        if (bar_pct > 100) bar_pct = 100;
        bar_width = {1'b0,bar_pct,2'b00};
        if (x_s1 >= 1280 && x_s1 < 1680 && y_s1 >= 480 && y_s1 < 940 && y_s1[5:0] >= 32 && y_s1[5:0] < 44 && bar_row < 8) begin
            graph_color = 24'h27364c;
            if (result_s1 && x_s1 - 1280 < bar_width)
                graph_color = bar_row == class_s1 ? 24'h36d6c5 : 24'h547d9d;
        end

    end
    always @(posedge pix_clk) begin
        x_s1 <= pix_x; y_s1 <= pix_y;
        wave_s1 <= in_wave; hist_s1 <= in_hist;
        wave_ready_s1 <= wave_valid;
        result_s1 <= result_ready && class_idx < 8;
        mute_s1 <= mute_flag_sync;
        class_s1 <= class_idx; percentages_s1 <= percentages;
        hist_vector_s1 <= hist_vector; hist_col_s1 <= hist_col;
        hist_valid_s1 <= history_count != 0 && {1'b0,hist_col} >= (4'd8 - history_count);
        pos_amp_r <= pos_amp;
        neg_amp_r <= neg_amp;
        x_s2 <= x_s1;
        y_s2 <= y_s1;
        wave_s2 <= wave_s1;
        wave_ready_s2 <= wave_ready_s1;
        mute_s2 <= mute_s1;
        graph_s2 <= graph_color;
        graph_s3 <= graph_s2;
        rgb <= de_pipe[2] ? (text_on ? text_rgb : graph_s3) : 24'd0;
        de_pipe <= {de_pipe[2:0],pix_de};
        hs_pipe <= {hs_pipe[2:0],pix_hs};
        vs_pipe <= {vs_pipe[2:0],pix_vs};
        vs_d <= pix_vs;
        if (!rst_pix_n) begin
            de_pipe <= 0; hs_pipe <= 0; vs_pipe <= 0; vs_d <= 0; rgb <= 0;
        end
    end
    assign de_out = de_pipe[3];
    assign hs_out = hs_pipe[3];
    assign vs_out = vs_pipe[3];
    assign vsync_pulse = pix_vs && !vs_d;
endmodule
