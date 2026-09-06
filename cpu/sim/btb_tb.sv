`timescale 1ns/1ps
module btb_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,invalidate=0,update_valid=0,update_taken=0,update_conditional=1;
    reg [31:0] fetch_pc=0,update_pc=0,update_target=0;
    wire predicted_taken,prediction_hit;
    wire [31:0] predicted_target;
    integer checks=0;
    rv32_btb #(.INDEX_BITS(2)) predictor(.*);
    task check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if (!condition) $fatal(1,"FAIL BTB %s",label_text);
        end
    endtask
    task train(input bit taken);
        begin
            @(negedge clk); update_valid=1; update_taken=taken;
            @(posedge clk); #1;
            @(negedge clk); update_valid=0;
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        @(negedge clk); rst_n=1; #1;
        check(!prediction_hit && !predicted_taken && predicted_target==4,"cold miss");
        update_pc=0; update_target=128;
        train(1); #1; check(prediction_hit && predicted_taken && predicted_target==128,"allocate weak taken");
        train(1); train(1); train(0); #1;
        check(predicted_taken,"saturates strongly taken");
        train(0); #1; check(!predicted_taken,"transition not taken");
        train(0); train(0); train(1); #1;
        check(!predicted_taken,"saturates strongly not taken");
        train(1); #1; check(predicted_taken,"relearn taken");
        fetch_pc=16; #1; check(!prediction_hit,"tag prevents alias hit");
        update_pc=16; update_target=256; train(0); #1;
        check(prediction_hit && !predicted_taken && predicted_target==256,"alias replacement initializes counter");
        fetch_pc=0; #1; check(!prediction_hit,"old tag evicted");
        fetch_pc=16; update_conditional=0; train(1); #1;
        check(predicted_taken,"unconditional jump");
        update_target=258; train(1); #1;
        check(predicted_target==256,"misaligned target ignored");
        fetch_pc=17; #1; check(!prediction_hit,"misaligned fetch ignored");
        fetch_pc=16;
        @(negedge clk); invalidate=1; update_valid=1; update_target=512;
        @(posedge clk); #1; check(!prediction_hit,"invalidation overrides update");
        @(negedge clk); invalidate=0; update_valid=0;
        #1; check(!predicted_taken,"invalidated prediction disabled");
        $display("PASS btb checks=%0d",checks);
        $finish;
    end
    initial begin
        #10000; $fatal(1,"BTB watchdog timeout");
    end
endmodule
