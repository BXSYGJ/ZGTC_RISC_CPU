`timescale 1ns/1ps
`ifndef SYMPHONY_FONT_HEX
`define SYMPHONY_FONT_HEX "src/ui/symphony_font.hex"
`define SYMPHONY_GUIDE_HEX "src/ui/symphony_guide.hex"
`define SYMPHONY_LIBRARY_HEX "src/ui/symphony_library.hex"
`endif
module tb_symphony_integration;
    reg clk = 0;
    always #5 clk = !clk;
    reg rst_n = 0;
    reg key1_n = 1;
    reg result_update = 0;
    reg [2:0] result_class = 0;
    reg [63:0] percentages = 0;
    reg [10:0] pix_x = 0, pix_y = 0;
    reg pix_de = 0, pix_hs = 0, pix_vs = 0;
    wire [23:0] rgb;
    wire de_out, hs_out, vs_out, frame_start;
    wire page_library;
    wire [3:0] filter_class;
    wire [5:0] selected_index, rd_index;
    wire [6:0] item_count, history_count;
    wire [31:0] result_time_ms, result_sequence, dropped_results;
    wire selected_valid, selected_bookmark, rd_valid, rd_bookmark, rd_all;
    wire [2:0] selected_class, rd_class;
    wire [7:0] selected_confidence, rd_confidence;
    wire [31:0] selected_time_ms, selected_sequence, rd_time_ms, rd_sequence;
    wire [10:0] wave_address;
    wire [14:0] spectrum_address;
    symphony_state #(.PIXEL_HZ(10000), .DEBOUNCE_MS(3), .LONG_PRESS_MS(900), .DOUBLE_CLICK_MS(300)) control (
        .pix_clk(clk), .pix_rst_n(rst_n), .frame_start(frame_start), .key1_n(key1_n),
        .result_update(result_update), .result_class(result_class), .result_percentages(percentages),
        .rd_index(rd_index), .rd_all(rd_all), .page_library(page_library), .filter_class(filter_class),
        .selected_index(selected_index), .item_count(item_count), .history_count(history_count),
        .result_time_ms(result_time_ms), .result_sequence(result_sequence), .dropped_results(dropped_results),
        .selected_valid(selected_valid), .selected_class(selected_class), .selected_confidence(selected_confidence),
        .selected_time_ms(selected_time_ms), .selected_sequence(selected_sequence), .selected_bookmark(selected_bookmark),
        .rd_valid(rd_valid), .rd_class(rd_class), .rd_confidence(rd_confidence), .rd_time_ms(rd_time_ms),
        .rd_sequence(rd_sequence), .rd_bookmark(rd_bookmark)
    );
    symphony_renderer #(.SIMULATION(1), .FONT_HEX(`SYMPHONY_FONT_HEX),
        .GUIDE_HEX(`SYMPHONY_GUIDE_HEX), .LIBRARY_HEX(`SYMPHONY_LIBRARY_HEX)) display (
        .pix_clk(clk), .rst_pix_n(rst_n), .pix_x(pix_x), .pix_y(pix_y),
        .pix_de(pix_de), .pix_hs(pix_hs), .pix_vs(pix_vs),
        .wave_rd_addr(wave_address), .wave_min(16'd0), .wave_max(16'd0),
        .wave_valid(1'b0), .mute_flag_sync(1'b0), .spec_ram_addr(spectrum_address),
        .spec_ram_data(8'd0), .feature_ready(1'b1), .result_ready(history_count != 0),
        .class_idx({1'b0,result_class}), .pct0(percentages[7:0]), .pct1(percentages[15:8]),
        .pct2(percentages[23:16]), .pct3(percentages[31:24]), .pct4(percentages[39:32]),
        .pct5(percentages[47:40]), .pct6(percentages[55:48]), .pct7(percentages[63:56]),
        .page_library(page_library), .filter_class(filter_class), .selected_index(selected_index),
        .item_count(item_count), .history_count(history_count), .result_time_ms(result_time_ms),
        .result_sequence(result_sequence), .rd_index(rd_index), .rd_all(rd_all),
        .rd_valid(rd_valid), .rd_class(rd_class), .rd_confidence(rd_confidence),
        .rd_time_ms(rd_time_ms), .rd_sequence(rd_sequence), .rd_bookmark(rd_bookmark),
        .selected_valid(selected_valid), .selected_class(selected_class), .selected_confidence(selected_confidence),
        .selected_time_ms(selected_time_ms), .selected_sequence(selected_sequence), .selected_bookmark(selected_bookmark),
        .vsync_pulse(frame_start), .rgb(rgb), .de_out(de_out), .hs_out(hs_out), .vs_out(vs_out)
    );
    integer assertions = 0;
    integer sync_checks = 0;
    integer pixel_checks = 0;
    integer slot;
    reg probe_valid = 0;
    reg [23:0] probe_rgb = 0;
    reg [4:0] de_expected = 0, hs_expected = 0, vs_expected = 0, probe_expected = 0;
    reg [23:0] colors [0:4];
    reg [10:0] probes_x [0:4];
    reg [10:0] probes_y [0:4];
    task check;
        input condition;
        input [1023:0] description;
        begin
            assertions = assertions + 1;
            if (!condition) $fatal(1,"SYMPHONY_INTEGRATION_FAIL check=%0d %0s",assertions,description);
        end
    endtask
    // Independent video tags verify the full five-stage timing relationship.
    always @(posedge clk) begin
        if (!rst_n) begin
            de_expected <= 0; hs_expected <= 0; vs_expected <= 0; probe_expected <= 0;
            for (slot=0;slot<5;slot=slot+1) begin colors[slot]<=0;probes_x[slot]<=0;probes_y[slot]<=0;end
        end else begin
            de_expected <= {de_expected[3:0],pix_de};
            hs_expected <= {hs_expected[3:0],pix_hs};
            vs_expected <= {vs_expected[3:0],pix_vs};
            probe_expected <= {probe_expected[3:0],probe_valid};
            colors[0]<=probe_rgb;probes_x[0]<=pix_x;probes_y[0]<=pix_y;
            for (slot=1;slot<5;slot=slot+1) begin
                colors[slot]<=colors[slot-1];probes_x[slot]<=probes_x[slot-1];probes_y[slot]<=probes_y[slot-1];
            end
            #1;
            sync_checks = sync_checks + 3;
            if (de_out !== de_expected[4] || hs_out !== hs_expected[4] || vs_out !== vs_expected[4])
                $fatal(1,"SYMPHONY_INTEGRATION_SYNC_FAIL de=%b/%b hs=%b/%b vs=%b/%b",de_out,de_expected[4],hs_out,hs_expected[4],vs_out,vs_expected[4]);
            if (!de_out && rgb !== 0) $fatal(1,"SYMPHONY_INTEGRATION_BLANKING_FAIL rgb=%h",rgb);
            if (probe_expected[4]) begin
                pixel_checks = pixel_checks + 1;
                if (rgb !== colors[4]) $fatal(1,"SYMPHONY_INTEGRATION_PIXEL_FAIL x=%0d y=%0d expected=%h actual=%h",probes_x[4],probes_y[4],colors[4],rgb);
                $display("SYMPHONY_PIXEL x=%0d y=%0d rgb=%06h",probes_x[4],probes_y[4],rgb);
            end
        end
    end
    task wait_ms;
        input integer duration;
        begin repeat (duration*10) @(posedge clk); #1; end
    endtask
    task publish_frame;
        begin
            @(negedge clk);pix_de=0;pix_x=0;pix_y=0;pix_vs=1;
            @(negedge clk);pix_vs=0;
            repeat (75) @(posedge clk);#1;
        end
    endtask
    task emit;
        input [2:0] instrument;
        input [7:0] confidence;
        begin
            @(negedge clk);result_class=instrument;percentages=0;
            percentages[63:56]=4;percentages[instrument*8+:8]=confidence;result_update=1;
            @(negedge clk);result_update=0;
            publish_frame;
        end
    endtask
    task sample_pixel;
        input [10:0] x,y;
        input [23:0] expected;
        begin
            @(negedge clk);pix_x=x;pix_y=y;pix_de=1;probe_rgb=expected;probe_valid=1;
            @(negedge clk);probe_valid=0;pix_de=0;
            repeat (7) @(posedge clk);#1;
        end
    endtask
    task short_click;
        begin
            @(negedge clk);key1_n=0;wait_ms(30);
            @(negedge clk);key1_n=1;wait_ms(330);
            publish_frame;
        end
    endtask
    task double_click;
        begin
            @(negedge clk);key1_n=0;wait_ms(30);
            @(negedge clk);key1_n=1;wait_ms(30);
            @(negedge clk);key1_n=0;wait_ms(30);
            @(negedge clk);key1_n=1;wait_ms(350);
            publish_frame;
        end
    endtask
    task long_click;
        begin
            @(negedge clk);key1_n=0;wait_ms(1000);
            @(negedge clk);key1_n=1;wait_ms(350);
            publish_frame;
        end
    endtask
    initial begin
        repeat (5) @(posedge clk);
        @(negedge clk);rst_n=1;
        repeat (8) @(posedge clk);#1;
        sample_pixel(30,280,24'h36574a);
        sample_pixel(480,310,24'hffffff);
        emit(7,67);emit(0,35);emit(0,91);
        check(history_count==3&&result_sequence==3&&dropped_results==0,"three genuine events include consecutive same-class results");
        sample_pixel(1410,904,24'h75b79d);
        sample_pixel(1590,394,24'h75b79d);
        sample_pixel(1610,394,24'hecf0e5);
        sample_pixel(1798,394,24'hffffff);
        sample_pixel(1410,888,24'hffffff);
        double_click;
        check(!page_library&&filter_class==8,"guide double-click does not change page or class");
        sample_pixel(1410,888,24'h244a36);
        short_click;
        check(filter_class==0&&item_count==2,"KEY1 short-click filters two real class-zero results");
        sample_pixel(1798,394,24'he8f2e2);
        long_click;
        check(page_library&&selected_index==0&&selected_sequence==3,"KEY1 long-click enters library with filter and selection intact");
        sample_pixel(30,280,24'h18332e);
        sample_pixel(480,310,24'hdcebd8);
        sample_pixel(1800,470,24'he8f2e2);
        sample_pixel(1800,534,24'hffffff);
        sample_pixel(1812,480,24'h244a36);
        short_click;
        check(page_library&&selected_index==1&&selected_sequence==2&&selected_confidence==35,"KEY1 short-click selects older matching observation");
        sample_pixel(1800,470,24'hffffff);
        sample_pixel(1800,534,24'he8f2e2);
        sample_pixel(1812,544,24'he8f2e2);
        double_click;
        check(selected_index==1&&selected_sequence==2&&selected_bookmark,"KEY1 double-click bookmarks selected result without selecting next row");
        sample_pixel(1812,544,24'h244a36);
        double_click;
        check(selected_index==1&&!selected_bookmark,"second double-click removes selected bookmark");
        sample_pixel(1812,544,24'he8f2e2);
        long_click;
        check(!page_library&&filter_class==0,"KEY1 long-click returns to guide and retains filter");
        sample_pixel(30,280,24'h36574a);
        // Changes on consecutive pixel clocks catch off-by-one metadata/timing.
        @(negedge clk);pix_x=30;pix_y=280;pix_de=1;pix_hs=1;probe_valid=1;probe_rgb=24'h36574a;
        @(negedge clk);pix_x=300;pix_y=280;pix_de=1;pix_hs=0;probe_rgb=24'hf4f6ef;
        @(negedge clk);pix_x=30;pix_y=280;pix_de=1;pix_hs=1;probe_rgb=24'h36574a;
        @(negedge clk);pix_de=0;pix_hs=0;probe_valid=0;
        repeat (8) @(posedge clk);#1;
        check(pixel_checks==23,"all tagged native pixels traversed the renderer");
        $display("SYMPHONY_INTEGRATION_PASS assertions=%0d pixel_checks=%0d sync_checks=%0d latency=5 retained=%0d selected=%0d",assertions,pixel_checks,sync_checks,history_count,selected_index);
        $finish;
    end
    initial begin #100000000;$fatal(1,"SYMPHONY_INTEGRATION_TIMEOUT");end
endmodule
