`timescale 1ns/1ps
module mem_nonzero_fault_tb #(
    parameter integer FETCH_OVERLAP=1,
    parameter integer LOAD_USE_BUBBLE=1
);
    typedef struct packed {
        logic uses_rs1,uses_rs2,writes_rd;
        logic [31:0] immediate;
        logic [3:0] alu_op;
        logic alu_immediate;
        logic is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
        logic is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    } decode_t;
    reg clk=0,rst_n=1,response_valid=0,data_valid=0,data_error=0;
    reg [31:0] expected_target;
    integer checks=0;
    decode_t decoded;
    rv32_core #(.ENABLE_PREDICTOR(1),.ENABLE_M(1),.FETCH_OVERLAP(FETCH_OVERLAP),.EARLY_D_REQUEST(1),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE)) dut(
        .clk(clk),.rst_n(rst_n),.i_req_ready(1'b1),.i_rsp_valid(response_valid),.i_rsp_data(32'h00000013),.i_rsp_error(1'b0),
        .d_req_ready(1'b1),.d_rsp_valid(data_valid),.d_rsp_data(32'h12345678),.d_rsp_error(data_error),
        .maintenance_ready(1'b1),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic run_fault(input integer store_operation,input integer fetch_mode);
        begin
            clk=0; rst_n=0; response_valid=0; data_valid=0; data_error=0; #1; rst_n=1; #1;
            decoded=0; decoded.is_jal=1; decoded.immediate=8; decoded.writes_rd=1;
            dut.ex_decode=decoded; dut.ex_valid=1; dut.ex_pc=32'h100; dut.ex_instruction=32'h008000ef;
            dut.ex_rd=1; dut.ex_prediction=32'h200;
            dut.mem_valid=1; dut.mem_load=store_operation==0; dut.mem_store=store_operation!=0;
            dut.mem_writes=store_operation==0; dut.mem_rd=7; dut.mem_rd_nonzero=dut.mem_rd!=0; dut.mem_exception=0; dut.mem_sent=1;
            dut.mem_pc=32'h80; dut.mem_instruction=store_operation!=0 ? 32'h00102023 : 32'h00002383;
            dut.mem_next_pc=32'h84; dut.mem_prediction=32'h84; dut.mem_early_redirect=0;
            dut.mem_load_route=dut.decode_load_route(3'd2,2'd0);
            dut.id_valid=1; dut.id_instruction=32'h00000013; dut.if_valid=1;
            dut.fetch_active=1; dut.fetch_sent=fetch_mode!=0; dut.fetch_discard=0;
            dut.fetch_address=32'h200; dut.next_pc=32'h204;
            data_valid=1; data_error=1; response_valid=fetch_mode==2; #1;
            expected_target=dut.trap_target;
            if(!dut.mem_fault || !dut.mem_flush || !dut.frontend_flush || dut.ex_fire || dut.ex_redirect || dut.id_fire || dut.if_fire || dut.fetch_overlap)
                $fatal(1,"FAIL early_direct_fault older priority store=%0d fetch=%0d",store_operation,fetch_mode);
            if(!dut.trap_valid || dut.trap_pc!==32'h80 || dut.trap_cause!==(store_operation!=0 ? 32'd7 : 32'd5) || dut.redirect_pc!==expected_target)
                $fatal(1,"FAIL early_direct_fault trap identity store=%0d fetch=%0d",store_operation,fetch_mode);
            if(fetch_mode!=0 && !dut.i_rsp_ready)
                $fatal(1,"FAIL early_direct_fault pending response blocked");
            clk=1; #1;
            if(dut.next_pc!==expected_target || dut.mem_valid || dut.ex_valid || dut.id_valid || dut.if_valid || dut.wb_valid || dut.trace_valid)
                $fatal(1,"FAIL early_direct_fault fault retirement or younger capture");
            if(fetch_mode!=2 && !dut.fetch_discard)
                $fatal(1,"FAIL early_direct_fault pending discard lost");
            checks=checks+1;
        end
    endtask
    initial begin
        for(integer store_operation=0;store_operation<2;store_operation=store_operation+1)
            for(integer fetch_mode=0;fetch_mode<3;fetch_mode=fetch_mode+1) run_fault(store_operation,fetch_mode);
        if(checks!=6) $fatal(1,"FAIL early_direct_fault coverage");
        $display("PASS early_direct_fault checks=6 overlap=%0d bubble=%0d",FETCH_OVERLAP,LOAD_USE_BUBBLE);
        $finish;
    end
endmodule
