`timescale 1ns/1ps
module fetch_enable_tb #(parameter integer FETCH_OVERLAP=1);
    reg clk=0,rst_n=0;
    reg active=0,sent=0,pending=0,response=0,space=0,flush=0,barrier=0,ready=0;
    integer checks=0;
    rv32_core #(.ENABLE_M(1),.FETCH_OVERLAP(FETCH_OVERLAP),.LOAD_USE_BUBBLE(1)) candidate(
        .clk(clk),.rst_n(rst_n),.i_req_ready(ready),.i_rsp_valid(response),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    rv32_core_reference #(.ENABLE_M(1),.FETCH_OVERLAP(FETCH_OVERLAP),.LOAD_USE_BUBBLE(1)) reference(
        .clk(clk),.rst_n(rst_n),.i_req_ready(ready),.i_rsp_valid(response),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    wire original_prediction_write=reference.redirect_prediction_commit ||
        ((!reference.fetch_active || reference.fetch_complete) && !reference.frontend_flush && !reference.frontend_barrier);
    initial begin
        force candidate.fetch_active=active;
        force reference.fetch_active=active;
        force candidate.fetch_sent=sent;
        force reference.fetch_sent=sent;
        force candidate.fetch_redirect_pending=pending;
        force reference.fetch_redirect_pending=pending;
        force candidate.fetch_accept_space=space;
        force reference.fetch_accept_space=space;
        force candidate.frontend_flush=flush;
        force reference.frontend_flush=flush;
        force candidate.frontend_barrier=barrier;
        force reference.frontend_barrier=barrier;
        for(integer vector=0;vector<256;vector=vector+1) begin
            {active,sent,pending,response,space,flush,barrier,ready}=vector[7:0];
            #1;
            if(candidate.next_pc_write!==reference.next_pc_write)
                $fatal(1,"FAIL fetch_enable next_pc vector=%0d",vector);
            if((candidate.fetch_prediction_update && !candidate.frontend_flush)!==original_prediction_write)
                $fatal(1,"FAIL fetch_enable prediction vector=%0d",vector);
            checks=checks+2;
        end
        $display("PASS fetch_enable combinations=256 checks=%0d overlap=%0d",checks,FETCH_OVERLAP);
        $finish;
    end
endmodule
