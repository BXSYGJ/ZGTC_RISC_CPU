`timescale 1ns/1ps
module fetch_address_select_tb;
    parameter integer PREDICTOR=1;
    parameter integer OVERLAP=1;
    parameter integer RETIMED=1;
    reg clk=0,rst_n=0;
    reg active_value=0,sent_value=0,if_valid_value=0,if_fire_value=0;
    reg discard_value=0,flush_value=0,barrier_value=0,response_value=0,ready_value=0;
    reg [31:0] next_value=0,address_value=0,random_state=32'h592bacd7;
    reg [31:0] edges[0:15];
    wire request_valid,response_ready;
    wire [31:0] request_address;
    integer checks=0,valid_checks=0,stalled_checks=0,overlap_checks=0,idle_differences=0;
    rv32_core #(.ENABLE_PREDICTOR(PREDICTOR),.FETCH_OVERLAP(OVERLAP)) dut(
        .clk(clk),.rst_n(rst_n),.i_req_valid(request_valid),.i_req_ready(ready_value),
        .i_req_address(request_address),.i_rsp_valid(response_value),.i_rsp_ready(response_ready),
        .i_rsp_data(32'b0),.i_rsp_error(1'b0),.d_req_ready(1'b0),.d_rsp_valid(1'b0),
        .d_rsp_data(32'b0),.d_rsp_error(1'b0),.maintenance_ready(1'b0),.timer_value(64'b0),
        .irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic check_case(input [31:0] saved_pc,input [31:0] prospective_pc,input integer mode);
        reg expected_response_ready,expected_overlap,expected_request_valid;
        reg [31:0] expected_address;
        begin
            {ready_value,response_value,barrier_value,flush_value,discard_value,
                if_fire_value,if_valid_value,sent_value,active_value}=mode[8:0];
            address_value=saved_pc; next_value=prospective_pc;
            expected_response_ready=active_value && sent_value &&
                (!if_valid_value || if_fire_value || discard_value || flush_value || barrier_value);
            expected_overlap=OVERLAP!=0 && response_value && expected_response_ready && !flush_value && !barrier_value;
            expected_request_valid=active_value && (!sent_value || expected_overlap);
            expected_address=expected_overlap ? prospective_pc : saved_pc;
            #1;
            if({request_valid,response_ready}!=={expected_request_valid,expected_response_ready})
                $fatal(1,"FAIL fetch_address_select control mode=%0d",mode);
            if(expected_request_valid) begin
                if(request_address!==expected_address)
                    $fatal(1,"FAIL fetch_address_select valid payload mode=%0d expected=%08x actual=%08x",mode,expected_address,request_address);
                if(dut.fetch_overlap!==sent_value)
                    $fatal(1,"FAIL fetch_address_select selector implication");
                valid_checks=valid_checks+1;
                if(!ready_value) stalled_checks=stalled_checks+1;
                if(expected_overlap) overlap_checks=overlap_checks+1;
            end else if(request_address!==expected_address) idle_differences=idle_differences+1;
            checks=checks+1;
        end
    endtask
    initial begin
        force dut.fetch_active=active_value;
        force dut.fetch_sent=sent_value;
        force dut.if_valid=if_valid_value;
        force dut.if_fire=if_fire_value;
        force dut.fetch_discard=discard_value;
        force dut.mem_flush=flush_value;
        force dut.frontend_barrier=barrier_value;
        force dut.next_pc=next_value;
        force dut.fetch_address=address_value;
        #1; rst_n=1; #1; rst_n=0; #1; rst_n=1;
        edges[0]=0; edges[1]=1; edges[2]=2; edges[3]=3;
        edges[4]=32'hffffffff; edges[5]=32'hfffffffc; edges[6]=32'hfffffffd; edges[7]=32'hfffffffe;
        edges[8]=32'h000003ff; edges[9]=32'h0003ffff; edges[10]=32'h03ffffff; edges[11]=32'h7fffffff;
        edges[12]=32'h80000000; edges[13]=32'hffff0001; edges[14]=32'h55555555; edges[15]=32'haaaaaaaa;
        for(integer edge_index=0;edge_index<16;edge_index=edge_index+1)
            for(integer mode=0;mode<512;mode=mode+1) check_case(edges[edge_index],~edges[edge_index],mode);
        for(integer position=0;position<32;position=position+1)
            for(integer mode=0;mode<512;mode=mode+1) begin
                check_case(32'd1<<position,~(32'd1<<position),mode);
                check_case(~(32'd1<<position),32'd1<<position,mode);
            end
        for(integer sample=0;sample<2048;sample=sample+1) begin
            random_state=random_state ^ (random_state<<13);
            random_state=random_state ^ (random_state>>17);
            random_state=random_state ^ (random_state<<5);
            check_case(random_state,random_state ^ 32'h93bc507f,sample%512);
        end
        if(checks!=43008 || valid_checks==0 || stalled_checks==0 || (OVERLAP!=0 && overlap_checks==0))
            $fatal(1,"FAIL fetch_address_select missing coverage");
        if((RETIMED!=0 && idle_differences==0) || (RETIMED==0 && idle_differences!=0))
            $fatal(1,"FAIL fetch_address_select idle payload boundary");
        $display("PASS fetch_address_select checks=%0d valid=%0d stalled=%0d overlap=%0d idle_differences=%0d predictor=%0d enabled=%0d retimed=%0d",
            checks,valid_checks,stalled_checks,overlap_checks,idle_differences,PREDICTOR,OVERLAP,RETIMED);
        $finish;
    end
endmodule
