`timescale 1ns/1ps
module alu_carry_select_tb;
    reg [31:0] operand_a=0,operand_b=0;
    reg [3:0] operation=0;
    wire [31:0] result;
    reg [31:0] edges[0:15];
    integer checks=0;
    rv32_alu dut(.*);
    task automatic check_case(input [31:0] first,input [31:0] second,input bit subtract);
        reg [31:0] expected;
        begin
            operand_a=first; operand_b=second; operation=subtract ? 4'd1 : 4'd0;
            expected=subtract ? first-second : first+second;
            #1;
            if(result!==expected) $fatal(1,"FAIL carry_select op=%0d first=%08x second=%08x expected=%08x actual=%08x",operation,first,second,expected,result);
            checks=checks+1;
        end
    endtask
    initial begin
        edges[0]=0; edges[1]=1; edges[2]=32'h0000ffff; edges[3]=32'h00010000;
        edges[4]=32'h00010001; edges[5]=32'h0001ffff; edges[6]=32'hffff0000; edges[7]=32'hffffffff;
        edges[8]=32'h7fffffff; edges[9]=32'h80000000; edges[10]=32'h7fff0000; edges[11]=32'h8000ffff;
        edges[12]=32'h5555ffff; edges[13]=32'haaaa0000; edges[14]=32'h55550000; edges[15]=32'haaaaffff;
        for(integer first=0;first<16;first=first+1)
            for(integer second=0;second<16;second=second+1) begin
                check_case(edges[first],edges[second],0);
                check_case(edges[first],edges[second],1);
            end
        for(integer position=0;position<32;position=position+1) begin
            check_case((32'd1<<position)-1,1,0);
            check_case(32'd1<<position,1,1);
            check_case(0,32'd1<<position,1);
            check_case(32'hffffffff,32'd1<<position,0);
        end
        if(checks!=640) $fatal(1,"Incomplete carry/borrow boundary coverage");
        $display("PASS carry_select checks=%0d",checks);
        $finish;
    end
endmodule
