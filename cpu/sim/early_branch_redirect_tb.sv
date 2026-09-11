`timescale 1ns/1ps
module early_branch_redirect_tb #(
    parameter integer FETCH_OVERLAP=1
);
    typedef struct packed {
        logic uses_rs1,uses_rs2,writes_rd;
        logic [31:0] immediate;
        logic [3:0] alu_op;
        logic alu_immediate;
        logic is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
        logic is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    } decode_t;
    reg clk=0,rst_n=1,response_valid=0,maintenance_ready=0;
    reg expected_early,expected_memory_flush,expected_frontend,expected_execute;
    reg [31:0] expected_next,expected_prediction,expected_redirect;
    integer checks=0,early_checks=0,older_priority=0,pending_drains=0;
    decode_t decoded;
    rv32_core #(.ENABLE_PREDICTOR(1),.ENABLE_M(1),.FETCH_OVERLAP(FETCH_OVERLAP),.EARLY_D_REQUEST(1),.LOAD_USE_BUBBLE(1)) dut(
        .clk(clk),.rst_n(rst_n),.i_req_ready(1'b1),.i_rsp_valid(response_valid),.i_rsp_data(32'h00000013),.i_rsp_error(1'b0),
        .d_req_ready(1'b1),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(maintenance_ready),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic run_case(input integer operation,input integer prediction_match,input integer exception_kind,input integer older,input integer fetch_mode);
        begin
            clk=0; rst_n=0; response_valid=0; maintenance_ready=0; #1;
            rst_n=1; #1;
            decoded=0;
            decoded.immediate=8;
            decoded.is_branch=operation<2;
            decoded.is_jal=operation==2;
            decoded.is_jalr=operation==3;
            decoded.uses_rs1=operation<2 || operation==3;
            decoded.uses_rs2=operation<2;
            decoded.writes_rd=operation==2 || operation==3;
            decoded.illegal=exception_kind==2;
            if(operation==3) decoded.immediate=0;
            dut.ex_decode=decoded; dut.ex_valid=1; dut.ex_pc=32'h100;
            dut.ex_instruction=operation<2 ? 32'h00208463 : operation==2 ? 32'h008000ef : operation==3 ? 32'h000080e7 : 32'h00000013;
            dut.ex_rd=1;
            dut.ex_operand_a=operation==3 ? 32'h108 : 1;
            dut.ex_operand_b=operation==1 ? 0 : 1;
            dut.ex_error=exception_kind==1;
            expected_next=(operation==1 || operation==4) ? 32'h104 : 32'h108;
            expected_prediction=prediction_match!=0 ? expected_next : 32'h200;
            dut.ex_prediction=expected_prediction;
            dut.mem_valid=older!=0; dut.mem_load=older==2; dut.mem_store=0;
            dut.mem_writes=0; dut.mem_exception=older==3; dut.mem_cause=32'd2;
            dut.mem_pc=32'h80; dut.mem_instruction=32'h00000013;
            dut.mem_next_pc=32'h84; dut.mem_prediction=older>=7 ? 32'h300 : 32'h84;
            dut.mem_early_redirect=older==8;
            dut.mem_mret=older==4; dut.mem_fence_i=older==5 || older==6;
            maintenance_ready=older==6;
            dut.mem_sent=older==2;
            dut.id_valid=1; dut.id_instruction=32'h00000013; dut.if_valid=1;
            dut.fetch_active=1; dut.fetch_sent=fetch_mode!=0; dut.fetch_discard=0;
            dut.fetch_address=32'h200; dut.next_pc=32'h204;
            response_valid=fetch_mode==2;
            expected_memory_flush=older==3 || older==4 || older==6 || older==7;
            expected_execute=older!=2 && older!=5 && !expected_memory_flush;
            expected_early=expected_execute && exception_kind==0 && operation!=4 && prediction_match==0;
            expected_frontend=expected_memory_flush || expected_early;
            #1;
            expected_redirect=expected_memory_flush ? (older==3 ? dut.trap_target : 32'h84) : expected_next;
            if(dut.mem_flush!==expected_memory_flush || dut.ex_fire!==expected_execute || dut.ex_redirect!==expected_early || dut.frontend_flush!==expected_frontend)
                $fatal(1,"FAIL early_redirect decision case=%0d operation=%0d match=%0d exception=%0d older=%0d fetch=%0d",checks,operation,prediction_match,exception_kind,older,fetch_mode);
            if(expected_frontend && (dut.id_fire || dut.if_fire || dut.fetch_overlap || dut.redirect_pc!==expected_redirect))
                $fatal(1,"FAIL early_redirect frontend gate case=%0d",checks);
            if(expected_frontend && fetch_mode!=0 && !dut.i_rsp_ready)
                $fatal(1,"FAIL early_redirect cannot drain response case=%0d",checks);
            if(expected_memory_flush) older_priority=older_priority+1;
            if(expected_early) begin
                clk=1; #1;
                if(!dut.mem_valid || !dut.mem_early_redirect || dut.mem_prediction!==expected_prediction || dut.mem_next_pc!==expected_next || dut.mem_exception)
                    $fatal(1,"FAIL early_redirect MEM capture case=%0d",checks);
                if(dut.next_pc!==expected_next || dut.if_valid || dut.id_valid || dut.ex_valid || dut.mem_flush)
                    $fatal(1,"FAIL early_redirect duplicate or younger state case=%0d",checks);
                if(fetch_mode!=2 && !dut.fetch_discard)
                    $fatal(1,"FAIL early_redirect missing pending discard case=%0d",checks);
                clk=0; response_valid=1; #1;
                if(fetch_mode!=2) begin
                    if(!dut.i_rsp_ready || !dut.fetch_discard)
                        $fatal(1,"FAIL early_redirect lost drain after redirect case=%0d",checks);
                    pending_drains=pending_drains+1;
                end
                clk=1; #1;
                if(!dut.trace_valid || dut.trace_pc!==32'h100 || dut.mem_flush)
                    $fatal(1,"FAIL early_redirect branch did not retire precisely case=%0d",checks);
                if(operation>=2 && (!dut.trace_write || dut.trace_data!==32'h104))
                    $fatal(1,"FAIL early_redirect link register case=%0d",checks);
                early_checks=early_checks+1;
            end
            checks=checks+1;
        end
    endtask
    initial begin
        for(integer operation=0;operation<5;operation=operation+1)
            for(integer prediction_match=0;prediction_match<2;prediction_match=prediction_match+1)
                for(integer exception_kind=0;exception_kind<3;exception_kind=exception_kind+1)
                    for(integer older=0;older<9;older=older+1)
                        for(integer fetch_mode=0;fetch_mode<3;fetch_mode=fetch_mode+1)
                            run_case(operation,prediction_match,exception_kind,older,fetch_mode);
        if(checks!=810 || early_checks!=36 || older_priority!=360 || pending_drains!=24)
            $fatal(1,"FAIL early_redirect coverage checks=%0d early=%0d older=%0d drains=%0d",checks,early_checks,older_priority,pending_drains);
        $display("PASS early_redirect checks=%0d early=%0d older_priority=%0d pending_drains=%0d overlap=%0d",checks,early_checks,older_priority,pending_drains,FETCH_OVERLAP);
        $finish;
    end
endmodule
