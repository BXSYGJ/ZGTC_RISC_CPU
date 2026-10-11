`timescale 1ns/1ps

module blink_top_tb;

    localparam integer TEST_COUNT_MAX = 4;

    reg        clk;
    reg        rst_n;
    reg        key;
    wire [7:0] led;
    reg  [7:0] expected_led;
    integer    step;

    blink_top #(
        .COUNT_MAX(TEST_COUNT_MAX)
    ) dut (
        .clk  (clk),
        .rst_n(rst_n),
        .key  (key),
        .led  (led)
    );

    initial begin
        clk = 1'b0;
        forever #10 clk = ~clk;
    end

    initial begin
        rst_n        = 1'b0;
        key           = 1'b1;
        expected_led = 8'b0000_0001;

        repeat (3) @(posedge clk);
        #1;
        if (led !== expected_led)
            $fatal(1, "Reset failed: led=%b expected=%b", led, expected_led);

        rst_n = 1'b1;
        for (step = 0; step < 8; step = step + 1) begin
            repeat (TEST_COUNT_MAX) @(posedge clk);
            #1;
            expected_led = {expected_led[6:0], expected_led[7]};
            if (led !== expected_led)
                $fatal(1, "Left rotation failed at step %0d", step);
        end

        key = 1'b0;
        for (step = 0; step < 8; step = step + 1) begin
            repeat (TEST_COUNT_MAX) @(posedge clk);
            #1;
            expected_led = {expected_led[0], expected_led[7:1]};
            if (led !== expected_led)
                $fatal(1, "Right rotation failed at step %0d", step);
        end

        $display("PASS: reset and both LED rotation directions verified");
        $finish;
    end

endmodule
