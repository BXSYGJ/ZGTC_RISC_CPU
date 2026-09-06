`timescale 1ns/1ps
module muldiv_tb;
    reg clk=0,rst_n=0,cancel=0,req_valid=0,rsp_ready=0;
    always #5 clk=~clk;
    reg [2:0] req_operation=0;
    reg [31:0] req_operand_a=0,req_operand_b=0;
    wire req_ready,rsp_valid;
    wire [31:0] rsp_data;
    integer checks=0;
    reg [31:0] random_state=32'h20260906;
    reg [31:0] edges[0:7];
    rv32_muldiv dut(.*);
    function automatic [31:0] reference_result(input [2:0] operation,input [31:0] operand_a,input [31:0] operand_b);
        reg signed [63:0] signed_a,signed_b,signed_product;
        reg [63:0] unsigned_product;
        begin
            signed_a={{32{operand_a[31]}},operand_a};
            signed_b={{32{operand_b[31]}},operand_b};
            unsigned_product={32'b0,operand_a}*{32'b0,operand_b};
            case(operation)
                0: reference_result=unsigned_product[31:0];
                1: begin signed_product=signed_a*signed_b; reference_result=signed_product[63:32]; end
                2: begin signed_product=signed_a*$signed({32'b0,operand_b}); reference_result=signed_product[63:32]; end
                3: reference_result=unsigned_product[63:32];
                4: reference_result=operand_b==0 ? 32'hffffffff : 32'(signed_a/signed_b);
                5: reference_result=operand_b==0 ? 32'hffffffff : operand_a/operand_b;
                6: reference_result=operand_b==0 ? operand_a : 32'(signed_a%signed_b);
                7: reference_result=operand_b==0 ? operand_a : operand_a%operand_b;
            endcase
        end
    endfunction
    task automatic next_random(output [31:0] value);
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            value=random_state;
        end
    endtask
    task automatic run_case(input [2:0] operation,input [31:0] operand_a,input [31:0] operand_b,input integer hold_cycles);
        reg [31:0] expected;
        integer waited;
        begin
            expected=reference_result(operation,operand_a,operand_b);
            @(negedge clk);
            if(!req_ready || rsp_valid) $fatal(1,"Unit not idle before request");
            req_operation=operation; req_operand_a=operand_a; req_operand_b=operand_b; req_valid=1; rsp_ready=0;
            @(negedge clk); req_valid=0;
            req_operand_a=~operand_a; req_operand_b=~operand_b; req_operation=~operation;
            waited=0;
            while(!rsp_valid) begin
                if(req_ready) $fatal(1,"Unit accepts request while busy");
                @(negedge clk); waited=waited+1;
                if(waited>35) $fatal(1,"Muldiv response timeout");
            end
            if(operation<4) begin
                if(waited!=((operation==0 || operation==3) ? 0 : 1)) $fatal(1,"Product response latency mismatch op=%0d waited=%0d",operation,waited);
                checks=checks+1;
            end
            repeat(hold_cycles+1) begin
                if(!rsp_valid || req_ready || rsp_data!==expected)
                    $fatal(1,"Muldiv op=%0d a=%08x b=%08x expected=%08x actual=%08x",operation,operand_a,operand_b,expected,rsp_data);
                checks=checks+1;
                @(negedge clk);
            end
            rsp_ready=1;
            @(negedge clk); rsp_ready=0;
            if(rsp_valid || !req_ready) $fatal(1,"Duplicate response after consumption");
            checks=checks+1;
        end
    endtask
    task automatic canceled_case(input [2:0] operation,input integer delay_cycles,input bit use_reset);
        begin
            @(negedge clk); req_operation=operation; req_operand_a=32'h81234567; req_operand_b=32'h12345; req_valid=1;
            @(negedge clk); req_valid=0;
            repeat(delay_cycles) @(negedge clk);
            if(use_reset) rst_n=0; else cancel=1;
            #1;
            if(!use_reset && (rsp_valid || req_ready)) $fatal(1,"Cancel must suppress both handshakes immediately");
            @(negedge clk); rst_n=1; cancel=0;
            repeat(40) begin
                @(negedge clk);
                if(rsp_valid || !req_ready) $fatal(1,"Canceled operation leaked response");
                checks=checks+1;
            end
        end
    endtask
    initial begin : tests
        reg [31:0] random_a,random_b;
        edges[0]=0; edges[1]=1; edges[2]=32'hffffffff; edges[3]=32'h80000000;
        edges[4]=32'h7fffffff; edges[5]=32'hffff0000; edges[6]=32'h10001; edges[7]=2;
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
        for(integer operation=0;operation<8;operation=operation+1)
            for(integer first=0;first<8;first=first+1)
                for(integer second=0;second<8;second=second+1)
                    run_case(3'(operation),edges[first],edges[second],(first+second)%4);
        for(integer index=0;index<2048;index=index+1) begin
            next_random(random_a); next_random(random_b);
            run_case(3'(index%8),random_a,random_b,index%5);
        end
        for(integer operation=0;operation<8;operation=operation+1) begin
            canceled_case(3'(operation),0,0);
            canceled_case(3'(operation),1,0);
            canceled_case(3'(operation),35,0);
            canceled_case(3'(operation),10,1);
        end
        run_case(0,7,9,0);
        $display("PASS muldiv checks=%0d",checks);
        $finish;
    end
    initial begin #20000000; $fatal(1,"Muldiv test timeout"); end
endmodule
