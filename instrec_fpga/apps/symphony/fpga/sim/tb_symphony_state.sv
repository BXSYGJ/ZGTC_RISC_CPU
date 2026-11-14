`timescale 1ns/1ps
module tb_symphony_state;
    reg clk = 0;
    always #5 clk = !clk;
    reg rst_n = 0;
    reg frame_start = 0;
    reg key1_n = 1;
    reg result_update = 0;
    reg [2:0] result_class = 0;
    reg [63:0] result_percentages = 0;
    reg [5:0] rd_index = 0;
    reg rd_all = 1;
    wire page_library;
    wire [3:0] filter_class;
    wire [5:0] selected_index;
    wire [6:0] item_count, history_count;
    wire [31:0] result_time_ms, result_sequence, dropped_results;
    wire selected_valid, selected_bookmark, rd_valid, rd_bookmark;
    wire [2:0] selected_class, rd_class;
    wire [7:0] selected_confidence, rd_confidence;
    wire [31:0] selected_time_ms, selected_sequence, rd_time_ms, rd_sequence;
    // Accelerate only the ms divider. Gesture durations remain actual 900/300ms.
    symphony_state #(.PIXEL_HZ(10000), .HISTORY_DEPTH(64), .DEBOUNCE_MS(3),
                     .LONG_PRESS_MS(900), .DOUBLE_CLICK_MS(300)) dut (
        .pix_clk(clk), .pix_rst_n(rst_n), .frame_start(frame_start), .key1_n(key1_n),
        .result_update(result_update), .result_class(result_class), .result_percentages(result_percentages),
        .rd_index(rd_index), .rd_all(rd_all), .page_library(page_library), .filter_class(filter_class),
        .selected_index(selected_index), .item_count(item_count), .history_count(history_count),
        .result_time_ms(result_time_ms), .result_sequence(result_sequence), .dropped_results(dropped_results),
        .selected_valid(selected_valid), .selected_class(selected_class), .selected_confidence(selected_confidence),
        .selected_time_ms(selected_time_ms), .selected_sequence(selected_sequence), .selected_bookmark(selected_bookmark),
        .rd_valid(rd_valid), .rd_class(rd_class), .rd_confidence(rd_confidence), .rd_time_ms(rd_time_ms),
        .rd_sequence(rd_sequence), .rd_bookmark(rd_bookmark)
    );
    integer checks = 0;
    integer cycles = 0;
    integer observed = 0;
    integer expected_times [0:100];
    integer i;
    integer expected_sequence;
    integer baseline_ms;
    always @(posedge clk) begin
        if (!rst_n) cycles <= 0;
        else cycles <= cycles + 1;
    end
    task check;
        input condition;
        input [1023:0] message;
        begin
            checks = checks + 1;
            if (!condition) $fatal(1, "SYMPHONY_STATE_FAIL check=%0d %0s", checks, message);
        end
    endtask
    task wait_ms;
        input integer duration;
        begin repeat (duration * 10) @(posedge clk); #1; end
    endtask
    task publish_frame;
        begin
            @(negedge clk); frame_start = 1;
            @(negedge clk); frame_start = 0;
            repeat (70) @(posedge clk);
            #1;
        end
    endtask
    task emit;
        input [2:0] instrument;
        input [7:0] confidence;
        begin
            @(negedge clk);
            result_class = instrument;
            result_percentages = 64'h0102030405060708;
            result_percentages[instrument * 8 +: 8] = confidence;
            result_update = 1;
            @(posedge clk);
            observed = observed + 1;
            expected_times[observed] = (cycles + 1) / 10;
            @(negedge clk);
            result_update = 0;
            result_class = 7;
            result_percentages = 0;
        end
    endtask
    task read_row;
        input integer index;
        input all_rows;
        begin
            @(negedge clk); rd_index = index; rd_all = all_rows;
            @(posedge clk); #1;
        end
    endtask
    task short_click;
        begin
            @(negedge clk); key1_n = 0; wait_ms(30);
            @(negedge clk); key1_n = 1; wait_ms(330);
            publish_frame;
        end
    endtask
    task double_click;
        begin
            @(negedge clk); key1_n = 0; wait_ms(30);
            @(negedge clk); key1_n = 1; wait_ms(30);
            @(negedge clk); key1_n = 0; wait_ms(30);
            @(negedge clk); key1_n = 1; wait_ms(350);
            publish_frame;
        end
    endtask
    initial begin
        repeat (4) @(posedge clk);
        @(negedge clk); rst_n = 1;
        repeat (2) @(posedge clk); #1;
        check(history_count == 0 && item_count == 0 && filter_class == 8 && !page_library, "reset state");
        read_row(0, 1); check(!rd_valid, "unwritten RAM is invalid");
        baseline_ms = dut.uptime_ms;
        wait_ms(5); check(dut.uptime_ms == baseline_ms + 5, "divider advances one millisecond per ten configured clocks");

        emit(3, 91);
        check(history_count == 0 && result_sequence == 0, "result waits for frame boundary");
        publish_frame;
        check(history_count == 1 && item_count == 1 && result_sequence == 1, "first result committed once");
        read_row(0, 1);
        check(rd_valid && rd_class == 3 && rd_confidence == 91 && rd_sequence == 1, "winner percentage indexed by actual top1 and captured immutably");
        check(rd_time_ms == expected_times[1] && result_time_ms == expected_times[1], "timestamp is real notification arrival, not later frame commit");
        emit(3, 12); publish_frame;
        check(history_count == 2 && result_sequence == 2, "consecutive identical classifications are distinct records");
        read_row(0, 1); check(rd_sequence == 2 && rd_class == 3 && rd_confidence == 12, "newest-first second observation");
        read_row(1, 1); check(rd_sequence == 1 && rd_confidence == 91, "older observation payload retained");
        check(selected_valid && selected_sequence == 2, "selected cache follows newest row");

        @(negedge clk); result_class = 3; result_percentages = 0; result_percentages[31:24] = 66; result_update = 1;
        @(posedge clk); observed = observed + 1; expected_times[observed] = (cycles + 1) / 10;
        repeat (5) @(negedge clk);
        result_update = 0;
        publish_frame;
        check(history_count == 3 && result_sequence == 3, "held notification does not create duplicate records");

        for (i = 0; i < 4; i = i + 1) emit(i, 41+i);
        emit(6, 99);
        check(history_count == 3 && dropped_results == 1, "four-entry pending queue bounds bursts and reports overflow");
        for (i = 0; i < 4; i = i + 1) publish_frame;
        check(history_count == 7 && result_sequence == 7 && dut.pending_count == 0, "pending observations drain in capture order");
        read_row(0, 1); check(rd_class == 3 && rd_confidence == 44 && rd_sequence == 7, "latest queued payload remains coherent");

        repeat (6) begin
            @(negedge clk); key1_n = 0; wait_ms(1);
            @(negedge clk); key1_n = 1; wait_ms(1);
        end
        wait_ms(350); publish_frame;
        check(filter_class == 8 && !page_library, "contact bounce produces no gesture");
        @(negedge clk); key1_n = 0; wait_ms(30);
        @(negedge clk); key1_n = 1; wait_ms(30);
        publish_frame;
        check(filter_class == 8, "single click waits for double-click decision");
        wait_ms(310); publish_frame;
        check(filter_class == 0 && item_count == 1, "guide short click cycles filter and matches actual classes");
        read_row(0, 0); check(rd_valid && rd_class == 0 && rd_sequence == 4, "filtered synchronous read returns matching observation");
        double_click;
        check(filter_class == 0 && !page_library, "double click does not leak a short or long action");
        read_row(0, 1); check(rd_bookmark && rd_sequence == 7, "guide double click bookmarks most recent result");
        double_click;
        read_row(0, 1); check(rd_bookmark, "guide add-bookmark gesture is idempotent");

        repeat (4) short_click;
        check(filter_class == 4 && item_count == 0 && !selected_valid, "empty class filter exposes no stale row");
        read_row(0, 0); check(!rd_valid, "empty filter read invalid");
        repeat (4) short_click;
        check(filter_class == 8 && item_count == 7, "class filter wraps through all eight classes to ALL");
        repeat (4) short_click;
        check(filter_class == 3 && item_count == 4, "same-class result history survives class filtering");
        @(negedge clk); key1_n = 0; wait_ms(1000); publish_frame;
        check(page_library && selected_index == 0 && selected_sequence == 7, "900ms long press enters library");
        wait_ms(1000); publish_frame;
        check(page_library, "held long press fires once");
        @(negedge clk); key1_n = 1; wait_ms(350); publish_frame;
        check(page_library && selected_index == 0, "long release creates no short action");
        short_click;
        check(selected_index == 1 && selected_valid && selected_sequence == 3, "library short click selects next filtered result");
        double_click;
        check(selected_index == 1 && selected_bookmark && selected_sequence == 3, "library double click toggles selected bookmark without changing selection");
        double_click;
        check(!selected_bookmark && selected_index == 1, "library double click removes selected bookmark");

        for (i = 0; i < 70; i = i + 1) begin emit(i % 8, i + 21); publish_frame; end
        check(history_count == 64 && result_sequence == 78 && dropped_results == 1, "ring overwrites oldest observation at fixed depth without hiding dropped sequence");
        check(item_count == 8 && selected_valid && selected_sequence == 68, "filtered index and selected cache survive ring wrap");
        for (i = 0; i < 64; i = i + 1) begin
            read_row(i, 1);
            expected_sequence = 78 - i;
            check(rd_valid && rd_sequence == expected_sequence, "all-history sequence order remains correct across ring wrap");
            check(rd_class == (expected_sequence-9)%8 && rd_confidence == expected_sequence-9+21, "ring row class and true winner probability belong to its sequence");
            check(rd_time_ms == expected_times[expected_sequence] && !rd_bookmark, "ring row preserves arrival time and clears overwritten bookmark");
        end
        for (i = 0; i < 8; i = i + 1) begin
            read_row(i, 0);
            check(rd_valid && rd_class == 3 && rd_sequence == 76 - 8*i, "filtered rank lookup matches wrapped physical rows");
        end
        read_row(8, 0); check(!rd_valid, "read above filtered count invalid");
        $display("SYMPHONY_STATE_PASS checks=%0d observed=%0d retained=%0d last_sequence=%0d dropped=%0d filter_count=%0d divider_hz=10000 long_ms=900 double_ms=300", checks, observed, history_count, result_sequence, dropped_results, item_count);
        $finish;
    end
    initial begin
        #100000000;
        $fatal(1, "SYMPHONY_STATE_TIMEOUT");
    end
endmodule
