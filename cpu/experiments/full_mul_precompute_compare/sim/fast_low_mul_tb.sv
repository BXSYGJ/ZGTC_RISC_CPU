`timescale 1ns/1ps
module fast_low_mul_tb;
    reg clk=0,rst_n=0,cancel=0,req_valid=0,rsp_ready=0;
    always #5 clk=~clk;
    reg [2:0] req_operation=0;
    reg [31:0] req_operand_a=0,req_operand_b=0;
    wire req_ready,rsp_valid;
    wire [31:0] rsp_data;
    reg [31:0] random_state=32'h92603031;
    integer checks=0;
    rv32_muldiv #(.FAST_LOW_MUL(1)) dut(.*);
    task automatic next_random(output [31:0] value);
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            value=random_state;
        end
    endtask
    task automatic immediate_case(input [31:0] operand_a,input [31:0] operand_b,input bit hold_response);
        reg [63:0] expected;
        begin
            expected={32'b0,operand_a}*{32'b0,operand_b};
            req_valid=1; rsp_ready=!hold_response; req_operation=0;
            req_operand_a=operand_a; req_operand_b=operand_b;
            #1;
            if(!req_ready || !rsp_valid || rsp_data!==expected[31:0])
                $fatal(1,"Immediate low product mismatch a=%08x b=%08x",operand_a,operand_b);
            checks=checks+1;
            @(negedge clk);
            req_valid=0; req_operand_a=~operand_a; req_operand_b=~operand_b; req_operation=7;
            #1;
            if(hold_response) begin
                repeat(3) begin
                    if(req_ready || !rsp_valid || rsp_data!==expected[31:0])
                        $fatal(1,"Held low product changed");
                    checks=checks+1;
                    @(negedge clk);
                end
                rsp_ready=1;
                @(negedge clk);
            end
            #1;
            if(!req_ready || rsp_valid) $fatal(1,"Consumed low product duplicated");
            checks=checks+1;
        end
    endtask
    initial begin : tests
        reg [31:0] operand_a,operand_b;
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
        immediate_case(32'hffffffff,32'hffffffff,0);
        immediate_case(32'h80000000,32'hffffffff,1);
        for(integer index=0;index<2048;index=index+1) begin
            next_random(operand_a); next_random(operand_b);
            immediate_case(operand_a,operand_b,index%4==0);
        end
        req_operation=0; req_operand_a=7; req_operand_b=9; req_valid=1; rsp_ready=1; cancel=1;
        #1;
        if(req_ready || rsp_valid) $fatal(1,"Immediate cancellation leaked handshake");
        @(negedge clk); cancel=0; req_valid=0;
        #1;
        if(!req_ready || rsp_valid) $fatal(1,"Canceled low product persisted");
        immediate_case(5,7,0);
        $display("PASS fast_low_mul checks=%0d",checks);
        $finish;
    end
    initial begin #1000000; $fatal(1,"Fast low product timeout"); end
endmodule
