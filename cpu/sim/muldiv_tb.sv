`timescale 1ns/1ps
module muldiv_tb;
    parameter integer CHECK_IDLE_CLEAR=0;
    parameter integer CHECK_IDLE_CAPTURE=0;
    parameter integer CHECK_IDLE_RESPONSE=0;
    reg clk=0,rst_n=0,cancel=0,req_valid=0,rsp_ready=0;
    always #5 clk=~clk;
    reg [2:0] req_operation=0;
    reg [31:0] req_operand_a=0,req_operand_b=0;
    wire req_ready,rsp_valid;
    wire [31:0] rsp_data;
    integer checks=0;
    integer idle_clear_checks=0,nonzero_idle_clears=0,idle_without_request=0;
    integer idle_capture_checks=0,capture_without_request=0,divisor_hold_checks=0;
    reg [36:0] captured_static_payload;
    reg [31:0] captured_quotient;
    reg capture_was_idle;
    reg [31:0] random_state=32'h20260906;
    reg [31:0] edges[0:7];
    rv32_muldiv dut(.*);
    always @(posedge clk) begin
        if(CHECK_IDLE_CAPTURE!=0 && rst_n && !cancel) begin
            capture_was_idle=dut.state==dut.IDLE;
            if(capture_was_idle) begin
                captured_static_payload={req_operation,
                    ((!req_operation[0] && req_operand_b[31]) ? ~req_operand_b+32'd1 : req_operand_b),
                    (!req_operation[0] && (req_operand_a[31]^req_operand_b[31])),
                    (!req_operation[0] && req_operand_a[31])};
                captured_quotient=(!req_operation[0] && req_operand_a[31]) ? ~req_operand_a+32'd1 : req_operand_a;
                if(!req_valid) capture_without_request=capture_without_request+1;
            end else captured_static_payload={dut.operation,dut.divisor,dut.quotient_negative,dut.remainder_negative};
            #1;
            if(capture_was_idle) begin
                if({dut.operation,dut.divisor,dut.quotient_negative,dut.remainder_negative}!==captured_static_payload ||
                   dut.quotient!==captured_quotient || dut.remainder!==0 || dut.division_step!==0)
                    $fatal(1,"Idle divider operand capture must be independent of request qualification");
                idle_capture_checks=idle_capture_checks+1;
            end else begin
                if({dut.operation,dut.divisor,dut.quotient_negative,dut.remainder_negative}!==captured_static_payload)
                    $fatal(1,"Busy divider operands must not follow changing request inputs");
                divisor_hold_checks=divisor_hold_checks+1;
            end
        end
    end
    always @(posedge clk) begin
        if(CHECK_IDLE_CLEAR!=0 && rst_n && !cancel && dut.state==dut.IDLE) begin
            if(dut.remainder!=0) nonzero_idle_clears=nonzero_idle_clears+1;
            if(!req_valid) idle_without_request=idle_without_request+1;
            #1;
            if(dut.remainder!==0) $fatal(1,"Idle remainder clear must not depend on request qualification");
            idle_clear_checks=idle_clear_checks+1;
        end
    end
    integer idle_response_checks=0,idle_response_without_request=0;
    reg [31:0] idle_response_expected;
    always @(posedge clk) begin
        if(CHECK_IDLE_RESPONSE!=0 && rst_n && !cancel && dut.state==dut.IDLE) begin
            idle_response_expected=req_operation[1] ? req_operand_a : 32'hffffffff;
            if(!req_valid) idle_response_without_request=idle_response_without_request+1;
            #1;
            if(dut.response_data!==idle_response_expected)
                $fatal(1,"Idle exceptional response payload must not depend on request qualification");
            idle_response_checks=idle_response_checks+1;
        end
    end
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
            else if(waited!=(operand_b==0 ? 0 : 33)) $fatal(1,"Division response latency mismatch op=%0d waited=%0d",operation,waited);
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
        if(CHECK_IDLE_CAPTURE!=0) begin
            if(idle_capture_checks==0 || capture_without_request==0 || divisor_hold_checks==0) $fatal(1,"Missing divider operand capture coverage");
            $display("IDLE_CAPTURE samples=%0d without_request=%0d held=%0d",idle_capture_checks,capture_without_request,divisor_hold_checks);
        end
        if(CHECK_IDLE_CLEAR!=0) begin
            if(idle_clear_checks==0 || nonzero_idle_clears==0 || idle_without_request==0) $fatal(1,"Missing idle remainder clear coverage");
            $display("IDLE_CLEAR checks=%0d nonzero=%0d without_request=%0d",idle_clear_checks,nonzero_idle_clears,idle_without_request);
        end
        if(CHECK_IDLE_RESPONSE!=0) begin
            if(idle_response_checks==0 || idle_response_without_request==0) $fatal(1,"Missing idle response capture coverage");
            $display("IDLE_RESPONSE samples=%0d without_request=%0d",idle_response_checks,idle_response_without_request);
        end
        $display("PASS muldiv checks=%0d",checks);
        $finish;
    end
    initial begin #20000000; $fatal(1,"Muldiv test timeout"); end
endmodule
