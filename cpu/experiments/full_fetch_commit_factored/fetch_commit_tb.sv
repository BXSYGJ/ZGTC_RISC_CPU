`timescale 1ns/1ps
module fetch_commit_tb #(
    parameter integer FETCH_OVERLAP=1,
    parameter integer PREDICTOR=1
);
    reg clk=0,rst_n=1;
    reg request_ready=0,response_valid=0,response_error=0;
    reg flush=0,barrier=0,prediction_taken=0,accept_space=1;
    reg [31:0] redirect=0,random_state=32'h13579bdf;
    reg outstanding=0,pending_error=0;
    reg accept_request,consume_response;
    integer remaining=0,checks=0,extra_payload=0,flushes=0,barriers=0,held=0,overlaps=0;
    wire [31:0] synthetic_target=reference.next_pc+32'h80;
    rv32_core_reference #(.RESET_VECTOR(0),.ENABLE_PREDICTOR(PREDICTOR),.ENABLE_M(1),.FETCH_OVERLAP(FETCH_OVERLAP),.EARLY_D_REQUEST(1),.LOAD_USE_BUBBLE(1)) reference(
        .clk(clk),.rst_n(rst_n),.i_req_ready(request_ready),.i_rsp_valid(response_valid),.i_rsp_data(32'h00000013),.i_rsp_error(response_error),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    rv32_core #(.RESET_VECTOR(0),.ENABLE_PREDICTOR(PREDICTOR),.ENABLE_M(1),.FETCH_OVERLAP(FETCH_OVERLAP),.EARLY_D_REQUEST(1),.LOAD_USE_BUBBLE(1)) candidate(
        .clk(clk),.rst_n(rst_n),.i_req_ready(request_ready),.i_rsp_valid(response_valid),.i_rsp_data(32'h00000013),.i_rsp_error(response_error),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));

    task automatic check(input logic condition,input string message);
        begin
            checks=checks+1;
            if(condition!==1'b1) $fatal(1,"FAIL fetch_commit check=%0d %s",checks,message);
        end
    endtask

    task automatic compare_state;
        begin
            check({reference.fetch_active,reference.fetch_sent,reference.fetch_discard,reference.fetch_redirect_pending}===
                {candidate.fetch_active,candidate.fetch_sent,candidate.fetch_discard,candidate.fetch_redirect_pending},"fetch control differs");
            check(reference.next_pc===candidate.next_pc && reference.fetch_address===candidate.fetch_address,"fetch address differs");
            check({reference.if_valid,reference.id_valid,reference.ex_valid,reference.mem_valid,reference.wb_valid}===
                {candidate.if_valid,candidate.id_valid,candidate.ex_valid,candidate.mem_valid,candidate.wb_valid},"pipeline valid differs");
            if(reference.if_valid)
                check({reference.if_pc,reference.if_instruction,reference.if_prediction,reference.if_error}===
                    {candidate.if_pc,candidate.if_instruction,candidate.if_prediction,candidate.if_error},"live IF metadata differs");
            if(reference.id_valid)
                check({reference.id_pc,reference.id_instruction,reference.id_prediction,reference.id_error}===
                    {candidate.id_pc,candidate.id_instruction,candidate.id_prediction,candidate.id_error},"live ID metadata differs");
            if(reference.ex_valid)
                check({reference.ex_pc,reference.ex_instruction,reference.ex_prediction,reference.ex_error}===
                    {candidate.ex_pc,candidate.ex_instruction,candidate.ex_prediction,candidate.ex_error},"live EX metadata differs");
            if(reference.mem_valid)
                check({reference.mem_pc,reference.mem_instruction,reference.mem_prediction,reference.mem_exception}===
                    {candidate.mem_pc,candidate.mem_instruction,candidate.mem_prediction,candidate.mem_exception},"live MEM metadata differs");
            if(reference.trace_valid)
                check({reference.trace_write,reference.trace_pc,reference.trace_instruction,reference.trace_rd,reference.trace_data}===
                    {candidate.trace_write,candidate.trace_pc,candidate.trace_instruction,candidate.trace_rd,candidate.trace_data},"retirement differs");
            if(candidate.fetch_redirect_pending)
                check(candidate.fetch_active && !candidate.fetch_sent && !candidate.fetch_discard,"pending invariant");
            check(reference.fetch_prediction===candidate.fetch_prediction,"prediction payload differs");
            if(reference.fetch_prediction!==candidate.fetch_prediction) extra_payload=extra_payload+1;
        end
    endtask

    initial begin
        force reference.frontend_flush=flush;
        force candidate.frontend_flush=flush;
        force reference.fetch_accept_space=accept_space;
        force candidate.fetch_accept_space=accept_space;
        force reference.frontend_barrier=barrier;
        force candidate.frontend_barrier=barrier;
        force reference.redirect_pc=redirect;
        force candidate.redirect_pc=redirect;
        force reference.prediction_hit=1'b1;
        force candidate.prediction_hit=1'b1;
        force reference.predicted_taken=prediction_taken;
        force candidate.predicted_taken=prediction_taken;
        force reference.predicted_target=synthetic_target;
        force candidate.predicted_target=synthetic_target;
        rst_n=0; #1; rst_n=1; #1;
        for(integer cycle=0;cycle<6000;cycle=cycle+1) begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            request_ready=|random_state[2:0];
            prediction_taken=random_state[3];
            accept_space=|random_state[18:16];
            flush=random_state[7:4]==4'b0000;
            barrier=random_state[11:8]==4'b0000;
            redirect={16'h0000,random_state[25:12],2'b00};
            response_valid=outstanding && remaining==0;
            response_error=pending_error;
            #1;
            check(reference.i_req_valid===candidate.i_req_valid && reference.i_rsp_ready===candidate.i_rsp_ready,"bus handshake differs");
            if(reference.i_req_valid) check(reference.i_req_address===candidate.i_req_address,"request address differs");
            accept_request=reference.i_req_valid && request_ready;
            consume_response=response_valid && reference.i_rsp_ready;
            check(!accept_request || !outstanding || consume_response,"multiple outstanding requests");
            if(flush) flushes=flushes+1;
            if(barrier) barriers=barriers+1;
            if(response_valid && !reference.i_rsp_ready) held=held+1;
            if(accept_request && consume_response) overlaps=overlaps+1;
            clk=1; #1; compare_state(); clk=0; #1;
            if(consume_response) outstanding=0;
            if(outstanding && remaining>0) remaining=remaining-1;
            if(accept_request) begin
                outstanding=1;
                remaining={29'b0,random_state[14:12]};
                pending_error=random_state[19:16]==0;
            end
        end
        check(extra_payload==0 && flushes>0 && barriers>0 && held>0,"missing exact payload, flush or backpressure coverage");
        if(FETCH_OVERLAP!=0) check(overlaps>0,"missing overlap coverage");
        $display("PASS fetch_commit checks=%0d extra=%0d flush=%0d barrier=%0d held=%0d overlap=%0d mode=%0d predictor=%0d",checks,extra_payload,flushes,barriers,held,overlaps,FETCH_OVERLAP,PREDICTOR);
        $finish;
    end
endmodule
