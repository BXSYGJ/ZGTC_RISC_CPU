`timescale 1ns/1ps
module precompute_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,cancel=0,req_valid=0,req_precomputed=0,rsp_ready=0;
    reg [2:0] req_operation=0;
    reg [31:0] req_operand_a=0,req_operand_b=0;
    wire req_ready,rsp_valid;
    wire [31:0] rsp_data;
    rv32_muldiv #(.PRECOMPUTE(1)) dut(.*);
    integer trial,hold_cycle,checks=0;
    reg [31:0] expected;
    task automatic check(input condition);
        begin
            checks=checks+1;
            if(condition!==1'b1) $fatal(1,"FAIL precompute trial=%0d check=%0d",trial,checks);
        end
    endtask
    initial begin
        repeat(2) @(negedge clk);
        rst_n=1;
        for(trial=0;trial<2048;trial=trial+1) begin
            @(negedge clk);
            req_valid=0; req_precomputed=0; rsp_ready=0; cancel=0;
            req_operand_a=$random; req_operand_b=$random; req_operation=trial%4;
            expected=req_operand_a*req_operand_b;
            #1; check(req_ready && !rsp_valid);
            @(negedge clk);
            req_valid=1; req_precomputed=1; req_operation=0;
            req_operand_a=$random; req_operand_b=$random;
            rsp_ready=trial%2;
            cancel=trial%7==0;
            #1;
            if(cancel) check(!rsp_valid && !req_ready);
            else check(req_ready && rsp_valid && rsp_data===expected);
            @(negedge clk);
            req_valid=0; req_precomputed=0; cancel=0;
            if(trial%7!=0 && trial%2==0) begin
                for(hold_cycle=0;hold_cycle<3;hold_cycle=hold_cycle+1) begin
                    req_operand_a=$random; req_operand_b=$random;
                    #1; check(rsp_valid && !req_ready && rsp_data===expected);
                    @(negedge clk);
                end
                if(trial%5==0) begin
                    cancel=1; #1; check(!rsp_valid && !req_ready);
                end else rsp_ready=1;
                @(negedge clk);
                cancel=0; rsp_ready=0;
            end
            #1; check(!rsp_valid && req_ready);
        end
        $display("PASS precompute checks=%0d trials=%0d",checks,trial);
        $finish;
    end
    initial begin #1000000; $fatal(1,"watchdog"); end
endmodule

