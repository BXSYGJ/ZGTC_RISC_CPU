`timescale 1ns/1ps
module redirect_prime_tb #(
    parameter integer FETCH_OVERLAP=1,
    parameter integer PREDICTOR=1
);
    reg clk=0,rst_n=1;
    reg request_ready=0,response_valid=0,response_error=0;
    reg flush=0,barrier=0,prediction_taken=0;
    reg [31:0] redirect=0;
    wire [31:0] synthetic_target=dut.next_pc+32'h80;
    integer checks=0,cases=0;
    rv32_core #(.RESET_VECTOR(0),.ENABLE_PREDICTOR(PREDICTOR),.ENABLE_M(1),.FETCH_OVERLAP(FETCH_OVERLAP),.EARLY_D_REQUEST(1),.LOAD_USE_BUBBLE(1)) dut(
        .clk(clk),.rst_n(rst_n),.i_req_ready(request_ready),.i_rsp_valid(response_valid),.i_rsp_data(32'h00000013),.i_rsp_error(response_error),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));

    function [31:0] prediction(input [31:0] address);
        prediction=(PREDICTOR!=0 && prediction_taken) ? address+32'h80 : address+32'd4;
    endfunction

    task automatic check(input logic condition,input string message);
        begin
            checks=checks+1;
            if(condition!==1'b1) $fatal(1,"FAIL redirect_prime case=%0d check=%0d %s",cases,checks,message);
        end
    endtask

    task automatic step;
        begin
            #1; clk=1; #1; clk=0; #1;
            if(dut.fetch_redirect_pending)
                check(dut.fetch_active && !dut.fetch_sent && !dut.fetch_discard,"pending prediction invariant");
        end
    endtask

    task automatic reset_core;
        begin
            clk=0; flush=0; barrier=0; request_ready=0; response_valid=0; response_error=0; prediction_taken=0;
            rst_n=0; #1; rst_n=1; #1;
            dut.next_pc=32'h900;
            cases=cases+1;
        end
    endtask

    task automatic check_primed(input [31:0] address);
        begin
            flush=0; response_valid=0; #1;
            check(dut.fetch_active && !dut.fetch_sent && !dut.fetch_discard && dut.fetch_redirect_pending,"slot not primed");
            check(dut.fetch_address===address && dut.next_pc===address,"redirect address not retained");
            check(dut.i_req_valid && dut.i_req_address===address && !dut.i_rsp_ready,"primed request or response gate");
        end
    endtask

    task automatic accept_primed(input [31:0] address,input integer early_response,input integer error);
        reg [31:0] expected;
        begin
            expected=prediction(address);
            request_ready=1; response_valid=early_response; response_error=error; #1;
            check(dut.i_req_valid && dut.i_req_address===address && !dut.i_rsp_ready,"preaccept protocol");
            step();
            check(!dut.fetch_redirect_pending && dut.fetch_sent,"prediction not committed with request");
            check(dut.fetch_prediction===expected && dut.next_pc===expected,"prediction used stale PC or advanced twice");
            check(!dut.if_valid,"accepted response before prediction metadata");
            request_ready=0; response_valid=1; #1;
            check(dut.i_rsp_ready,"held response was not accepted");
            step();
            check(dut.if_valid && dut.if_pc===address && dut.if_prediction===expected && dut.if_error===error[0],"target response metadata");
            response_valid=0; #1;
        end
    endtask

    task automatic prime_idle(input integer delay,input integer taken,input integer early_response,input integer error);
        begin
            reset_core(); prediction_taken=taken;
            flush=1; redirect=32'h100; step(); check_primed(32'h100);
            for(integer count=0;count<delay;count=count+1) begin
                step();
                check(dut.i_req_valid && dut.i_req_address===32'h100 && dut.next_pc===32'h100 && dut.fetch_redirect_pending,"backpressured request changed");
            end
            accept_primed(32'h100,early_response,error);
        end
    endtask

    task automatic drain_old(input integer sent,input integer accept_on_flush,input integer complete_on_flush);
        begin
            reset_core(); prediction_taken=1;
            dut.fetch_active=1; dut.fetch_sent=sent; dut.fetch_discard=0; dut.fetch_address=32'h800; dut.fetch_prediction=32'h804;
            request_ready=accept_on_flush; response_valid=complete_on_flush; response_error=1;
            flush=1; redirect=32'h200; step();
            if(complete_on_flush!=0) begin
                request_ready=0; check_primed(32'h200); accept_primed(32'h200,1,0);
            end else begin
                flush=0; response_valid=0; #1;
                check(dut.fetch_active && dut.fetch_discard && !dut.fetch_redirect_pending && dut.fetch_address===32'h800,"outstanding request overwritten");
                check(dut.next_pc===32'h200,"lost redirect while draining");
                if(!dut.fetch_sent) begin
                    request_ready=0; step();
                    check(dut.i_req_valid && dut.i_req_address===32'h800,"unaccepted request not held");
                    request_ready=1; step();
                    check(dut.fetch_sent && dut.next_pc===32'h200,"drain acceptance changed redirect PC");
                end
                request_ready=0; response_valid=1; step(); response_valid=0; #1;
                check(!dut.if_valid && !dut.fetch_discard && dut.fetch_address===32'h200,"stale response leaked or target skipped");
                check(dut.fetch_prediction===prediction(32'h200) && dut.next_pc===prediction(32'h200),"normal prediction after drain");
            end
        end
    endtask

    task automatic repeat_redirect(input integer accept_on_second);
        begin
            reset_core(); prediction_taken=1;
            flush=1; redirect=32'h300; step(); check_primed(32'h300);
            flush=1; redirect=32'h500; request_ready=accept_on_second; step(); flush=0; #1;
            check(!dut.fetch_redirect_pending && dut.fetch_discard && dut.fetch_address===32'h300,"repeat redirect retained stale pending state");
            check(dut.next_pc===32'h500,"repeat redirect target priority");
            if(!dut.fetch_sent) begin
                request_ready=1; step();
                check(dut.next_pc===32'h500,"stale deferred prediction skipped newer target");
            end
            request_ready=0; response_valid=1; response_error=1; step(); response_valid=0; #1;
            check(!dut.if_valid && dut.fetch_address===32'h500 && !dut.fetch_discard,"repeat redirect drain failure");
            check(dut.fetch_prediction===prediction(32'h500) && dut.next_pc===prediction(32'h500),"repeat redirect prediction failure");
        end
    endtask

    task automatic fence_pending(input integer accept_during_barrier);
        begin
            reset_core(); prediction_taken=1;
            flush=1; redirect=32'h400; step(); check_primed(32'h400);
            barrier=1; request_ready=accept_during_barrier; step();
            check(!dut.fetch_redirect_pending && dut.fetch_discard && dut.next_pc===32'h400,"barrier did not cancel deferred prediction");
            if(!dut.fetch_sent) begin request_ready=1; step(); end
            request_ready=0; response_valid=1; step(); response_valid=0; #1;
            check(!dut.fetch_active && !dut.if_valid && dut.next_pc===32'h400,"barrier response was not drained");
            flush=1; redirect=32'h600; step();
            check(!dut.fetch_active && !dut.fetch_redirect_pending && dut.next_pc===32'h600,"FENCE.I redirect was primed before barrier release");
            flush=0; barrier=0; step();
            check(dut.fetch_address===32'h600 && dut.fetch_prediction===prediction(32'h600),"FENCE.I recovery target");
        end
    endtask

    initial begin
        force dut.frontend_flush=flush;
        force dut.frontend_barrier=barrier;
        force dut.redirect_pc=redirect;
        force dut.prediction_hit=1'b1;
        force dut.predicted_taken=prediction_taken;
        force dut.predicted_target=synthetic_target;
        for(integer delay=0;delay<3;delay=delay+1)
            for(integer taken=0;taken<2;taken=taken+1)
                for(integer early_response=0;early_response<2;early_response=early_response+1)
                    for(integer error=0;error<2;error=error+1)
                        prime_idle(delay==2 ? 7 : delay,taken,early_response,error);
        for(integer sent=0;sent<2;sent=sent+1)
            for(integer accepted=0;accepted<2;accepted=accepted+1)
                for(integer complete=0;complete<=sent;complete=complete+1)
                    drain_old(sent,accepted,complete);
        repeat_redirect(0); repeat_redirect(1);
        fence_pending(0); fence_pending(1);
        reset_core(); flush=1; redirect=32'h700; step(); check_primed(32'h700);
        rst_n=0; #1;
        check(!dut.fetch_redirect_pending && !dut.fetch_active && !dut.fetch_sent && dut.next_pc===0,"reset retained primed state");
        $display("PASS redirect_prime cases=%0d checks=%0d overlap=%0d predictor=%0d",cases,checks,FETCH_OVERLAP,PREDICTOR);
        $finish;
    end
endmodule
