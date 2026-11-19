`timescale 1ns/1ps
module tb_history_tracker;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst = 0, update = 0, clear_n = 1;
    reg [63:0] probabilities = 0;
    wire [511:0] history;
    wire [3:0] count;
    history_tracker #(.PIXEL_HZ(1000), .DEBOUNCE_MS(20)) dut (
        .pix_clk(clk), .pix_rst_n(rst), .frame_update(update),
        .frame_boundaries(probabilities), .clear_n(clear_n),
        .history_boundaries(history), .history_count(count)
    );
    initial begin
        repeat (3) @(negedge clk);
        rst = 1;
        for (integer n=1; n<=10; n=n+1) begin
            @(negedge clk); probabilities=n; update=1;
            @(negedge clk); update=0;
            if (history[511:448] != n || count != (n < 8 ? n : 8))
                $fatal(1,"Latest result/count mismatch");
        end
        for (integer slot=0; slot<8; slot=slot+1)
            if (history[slot*64 +: 64] != slot+3)
                $fatal(1,"Ninth result must evict oldest");
        repeat (100) @(negedge clk);
        if (count != 8 || history[511:448] != 10) $fatal(1,"History changed without inference");
        clear_n=0; repeat (5) @(negedge clk); clear_n=1;
        repeat (30) @(negedge clk);
        if (count != 8) $fatal(1,"Short key bounce cleared history");
        clear_n=0; repeat (30) @(negedge clk);
        if (count != 0 || history != 0) $fatal(1,"KEY2 did not clear all history");
        $display("RESULT: PASS history_tracker eviction, idle, key bounce and clear");
        $finish;
    end
endmodule
