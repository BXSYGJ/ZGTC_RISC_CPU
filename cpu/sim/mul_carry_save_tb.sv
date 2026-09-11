`timescale 1ns/1ps
module mul_carry_save_tb;
    reg [31:0] partial_low_low=0,partial_high_high=0;
    reg signed [33:0] partial_low_high=0,partial_high_low=0;
    reg [31:0] edges[0:15];
    reg [31:0] random_state=32'h370952ac,operand_a,operand_b;
    integer checks=0;
    rv32_muldiv dut(.clk(1'b0),.rst_n(1'b0),.cancel(1'b0),.req_valid(1'b0),.rsp_ready(1'b0),
        .req_operation(3'b0),.req_operand_a(32'b0),.req_operand_b(32'b0));
    rv32_muldiv_reference reference(.clk(1'b0),.rst_n(1'b0),.cancel(1'b0),.req_valid(1'b0),.rsp_ready(1'b0),
        .req_operation(3'b0),.req_operand_a(32'b0),.req_operand_b(32'b0));
    task automatic verify_product(input [31:0] first,input [31:0] second,input [2:0] operation);
        reg signed [16:0] low_a,low_b,high_a,high_b;
        reg signed [63:0] wide_a,wide_b;
        reg [63:0] expected;
        begin
            low_a={1'b0,first[15:0]}; low_b={1'b0,second[15:0]};
            high_a={((operation==1 || operation==2) && first[31]),first[31:16]};
            high_b={(operation==1 && second[31]),second[31:16]};
            partial_low_low=first[15:0]*second[15:0];
            partial_low_high=low_a*high_b;
            partial_high_low=high_a*low_b;
            partial_high_high=high_a*high_b;
            wide_a=(operation==1 || operation==2) ? {{32{first[31]}},first} : {32'b0,first};
            wide_b=operation==1 ? {{32{second[31]}},second} : {32'b0,second};
            expected=wide_a*wide_b;
            #1;
            if(dut.product!==reference.product || dut.product!==expected)
                $fatal(1,"FAIL mul_carry_save operation=%0d first=%08x second=%08x expected=%016x actual=%016x",operation,first,second,expected,dut.product);
            checks=checks+1;
        end
    endtask
    task automatic random_word(output [31:0] value);
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            value=random_state;
        end
    endtask
    initial begin
        force dut.product_low_low=partial_low_low;
        force dut.product_high_high=partial_high_high;
        force dut.product_low_high=partial_low_high;
        force dut.product_high_low=partial_high_low;
        force reference.product_low_low=partial_low_low;
        force reference.product_high_high=partial_high_high;
        force reference.product_low_high=partial_low_high;
        force reference.product_high_low=partial_high_low;
        edges[0]=0; edges[1]=1; edges[2]=32'hffffffff; edges[3]=32'h80000000;
        edges[4]=32'h7fffffff; edges[5]=32'h0000ffff; edges[6]=32'h00010000; edges[7]=32'hffff0000;
        edges[8]=32'h00008000; edges[9]=32'h80000001; edges[10]=32'hffff8000; edges[11]=32'h7fff8000;
        edges[12]=32'h00007fff; edges[13]=32'hfffeffff; edges[14]=32'hffff0001; edges[15]=32'h00010001;
        for(integer first=0;first<16;first=first+1)
            for(integer second=0;second<16;second=second+1)
                for(integer operation=0;operation<4;operation=operation+1)
                    verify_product(edges[first],edges[second],operation[2:0]);
        for(integer sample=0;sample<65536;sample=sample+1) begin
            random_word(operand_a); random_word(operand_b);
            for(integer operation=0;operation<4;operation=operation+1)
                verify_product(operand_a,operand_b,operation[2:0]);
        end
        if(checks!=263168) $fatal(1,"FAIL mul_carry_save incomplete cases");
        $display("PASS mul_carry_save checks=%0d",checks);
        $finish;
    end
endmodule

