`timescale 1ns/1ps
module raw_pair_retime_redirect_tb #(
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
    reg clk=0,rst_n=1,response_valid=0,maintenance_ready=0,data_response_valid=0;
    reg [31:0] data_response_data=0;
    reg expected_early,expected_memory_flush,expected_frontend,expected_execute;
    reg [31:0] expected_next,expected_prediction,expected_redirect;
    integer checks=0,early_checks=0,older_priority=0,pending_drains=0,fallback_checks=0,condition_checks=0,independence_checks=0;
    reg [31:0] edges[0:7];
    decode_t decoded;
    rv32_core #(.ENABLE_PREDICTOR(1),.ENABLE_M(1),.FETCH_OVERLAP(FETCH_OVERLAP),.EARLY_D_REQUEST(1),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE)) dut(
        .clk(clk),.rst_n(rst_n),.i_req_ready(1'b1),.i_rsp_valid(response_valid),.i_rsp_data(32'h00000013),.i_rsp_error(1'b0),
        .d_req_ready(1'b1),.d_rsp_valid(data_response_valid),.d_rsp_data(data_response_data),.d_rsp_error(1'b0),
        .maintenance_ready(maintenance_ready),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic sync_wb_comparisons;
        integer byte_index;
        begin
            for(byte_index=0;byte_index<4;byte_index=byte_index+1) begin
                dut.wb_a_byte_equal[byte_index]=dut.ex_operand_a[byte_index*8+:8]==dut.wb_data[byte_index*8+:8];
                dut.wb_a_byte_less[byte_index]=dut.ex_operand_a[byte_index*8+:8]<dut.wb_data[byte_index*8+:8];
                dut.wb_b_byte_equal[byte_index]=dut.wb_data[byte_index*8+:8]==dut.ex_operand_b[byte_index*8+:8];
                dut.wb_b_byte_less[byte_index]=dut.wb_data[byte_index*8+:8]<dut.ex_operand_b[byte_index*8+:8];
            end
        end
    endtask
    task automatic run_case(input integer operation,input integer prediction_match,input integer exception_kind,input integer older,input integer fetch_mode);
        begin
            clk=0; rst_n=0; response_valid=0; maintenance_ready=0; data_response_valid=0; data_response_data=0; #1;
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
            dut.ex_decode=decoded; dut.ex_valid=1; dut.ex_pc=32'h100; dut.ex_relative_target=dut.ex_pc+dut.ex_decode.immediate;
            dut.ex_instruction=operation<2 ? 32'h00208463 : operation==2 ? 32'h008000ef : operation==3 ? 32'h000080e7 : 32'h00000013; dut.mem_match_a=(dut.ex_instruction[19:15]==dut.mem_rd); dut.mem_match_b=(dut.ex_instruction[24:20]==dut.mem_rd);
            dut.ex_rd=1;
            dut.ex_operand_a=operation==3 ? 32'h108 : 1; dut.raw_pair_relation=dut.operand_relation(dut.ex_operand_a,dut.ex_operand_b); sync_wb_comparisons;
            dut.ex_operand_b=operation==1 ? 0 : 1; dut.raw_pair_relation=dut.operand_relation(dut.ex_operand_a,dut.ex_operand_b); sync_wb_comparisons;
            dut.ex_error=exception_kind==1;
            expected_next=(operation==1 || operation==4) ? 32'h104 : 32'h108;
            expected_prediction=prediction_match!=0 ? expected_next : 32'h200;
            dut.ex_prediction=expected_prediction;
            dut.mem_valid=older!=0; dut.mem_load=older==2 || older>=9; dut.mem_store=0;
            dut.mem_writes=older>=9; dut.mem_rd=older==9 ? 1 : older==11 ? 2 : 7; dut.mem_rd_nonzero=dut.mem_rd!=0; dut.mem_match_a=(dut.ex_instruction[19:15]==dut.mem_rd); dut.mem_match_b=(dut.ex_instruction[24:20]==dut.mem_rd);
            dut.mem_exception=older==3; dut.mem_cause=32'd2;
            dut.mem_load_route=dut.decode_load_route(3'd2,2'd0);
            data_response_valid=older>=9;
            data_response_data=operation==3 ? 32'h108 : operation==1 && older==11 ? 0 : 1;
            dut.mem_pc=32'h80; dut.mem_instruction=32'h00000013;
            dut.mem_next_pc=32'h84; dut.mem_prediction=(older==7 || older==8) ? 32'h300 : 32'h84;
            dut.mem_early_redirect=older==8;
            dut.mem_mret=older==4; dut.mem_fence_i=older==5 || older==6;
            maintenance_ready=older==6;
            dut.mem_sent=older==2 || older>=9;
            dut.id_valid=1; dut.id_instruction=32'h00000013; dut.if_valid=1;
            dut.fetch_active=1; dut.fetch_sent=fetch_mode!=0; dut.fetch_discard=0;
            dut.fetch_address=32'h200; dut.next_pc=32'h204;
            response_valid=fetch_mode==2;
            expected_memory_flush=older==3 || older==4 || older==6 || older==7;
            expected_execute=older!=2 && older!=5 && !expected_memory_flush && !(LOAD_USE_BUBBLE!=0 && operation==3 && older==9);
            expected_early=expected_execute && exception_kind==0 && operation<3 && prediction_match==0 && !(operation<2 && (older==9 || older==11));
            expected_frontend=expected_memory_flush || expected_early;
            #1;
            expected_redirect=expected_memory_flush ? (older==3 ? dut.trap_target : 32'h84) : expected_next;
            if(dut.mem_flush!==expected_memory_flush || dut.ex_fire!==expected_execute || dut.ex_redirect!==expected_early || dut.frontend_flush!==expected_frontend)
                $fatal(1,"FAIL early_direct_redirect decision case=%0d operation=%0d match=%0d exception=%0d older=%0d fetch=%0d",checks,operation,prediction_match,exception_kind,older,fetch_mode);
            if(expected_frontend && (dut.id_fire || dut.if_fire || dut.fetch_overlap || dut.redirect_pc!==expected_redirect))
                $fatal(1,"FAIL early_direct_redirect frontend gate case=%0d",checks);
            if(expected_frontend && fetch_mode!=0 && !dut.i_rsp_ready)
                $fatal(1,"FAIL early_direct_redirect cannot drain response case=%0d",checks);
            if(expected_early && (dut.early_next!==dut.actual_next || dut.execute_exception || dut.early_load_dependency))
                $fatal(1,"FAIL early_direct_redirect canonical agreement case=%0d",checks);
            if(expected_memory_flush) older_priority=older_priority+1;
            if(expected_early) begin
                clk=1; #1;
                if(!dut.mem_valid || !dut.mem_early_redirect || dut.mem_prediction!==expected_prediction || dut.mem_next_pc!==expected_next || dut.mem_exception)
                    $fatal(1,"FAIL early_direct_redirect MEM capture case=%0d",checks);
                if(dut.next_pc!==expected_next || dut.if_valid || dut.id_valid || dut.ex_valid || dut.mem_flush)
                    $fatal(1,"FAIL early_direct_redirect duplicate or younger state case=%0d",checks);
                if(fetch_mode!=2 && !dut.fetch_discard)
                    $fatal(1,"FAIL early_direct_redirect missing pending discard case=%0d",checks);
                clk=0; response_valid=1; #1;
                if(fetch_mode!=2) begin
                    if(!dut.i_rsp_ready || !dut.fetch_discard)
                        $fatal(1,"FAIL early_direct_redirect lost drain after redirect case=%0d",checks);
                    pending_drains=pending_drains+1;
                end
                clk=1; #1;
                if(!dut.trace_valid || dut.trace_pc!==32'h100 || dut.mem_flush)
                    $fatal(1,"FAIL early_direct_redirect branch did not retire precisely case=%0d",checks);
                if(operation>=2 && (!dut.trace_write || dut.trace_data!==32'h104))
                    $fatal(1,"FAIL early_direct_redirect link register case=%0d",checks);
                early_checks=early_checks+1;
            end else if(expected_execute && exception_kind==0 && prediction_match==0) begin
                clk=1; #1;
                if(!dut.mem_valid || dut.mem_early_redirect || !dut.mem_flush || dut.mem_next_pc!==expected_next || dut.mem_prediction!==expected_prediction)
                    $fatal(1,"FAIL early_direct_redirect MEM fallback capture case=%0d",checks);
                clk=0; response_valid=1; #1;
                if(dut.ex_fire || !dut.frontend_flush || dut.redirect_pc!==expected_next)
                    $fatal(1,"FAIL early_direct_redirect MEM fallback priority case=%0d",checks);
                clk=1; #1;
                if(dut.next_pc!==expected_next || dut.if_valid || dut.id_valid || dut.ex_valid || !dut.trace_valid || dut.trace_pc!==32'h100)
                    $fatal(1,"FAIL early_direct_redirect MEM fallback retirement case=%0d",checks);
                if(operation==3 && (!dut.trace_write || dut.trace_data!==32'h104))
                    $fatal(1,"FAIL early_direct_redirect JALR fallback link case=%0d",checks);
                fallback_checks=fallback_checks+1;
            end
            checks=checks+1;
        end
    endtask
    task automatic run_condition_case(input integer function_code,input [31:0] first,input [31:0] second,input integer unaligned);
        reg taken;
        reg [31:0] expected;
        begin
            clk=0; rst_n=0; response_valid=0; data_response_valid=0; #1; rst_n=1; #1;
            decoded=0; decoded.is_branch=1; decoded.uses_rs1=1; decoded.uses_rs2=1;
            decoded.immediate=unaligned!=0 ? 10 : 8;
            dut.ex_decode=decoded; dut.ex_valid=1; dut.ex_pc=32'h100; dut.ex_relative_target=dut.ex_pc+dut.ex_decode.immediate;
            dut.ex_instruction=32'h00208063 | (function_code<<12); dut.mem_match_a=(dut.ex_instruction[19:15]==dut.mem_rd); dut.mem_match_b=(dut.ex_instruction[24:20]==dut.mem_rd);
            dut.ex_prediction=32'h200; dut.ex_operand_a=first; dut.ex_operand_b=second; dut.raw_pair_relation=dut.operand_relation(dut.ex_operand_a,dut.ex_operand_b); sync_wb_comparisons;
            case(function_code)
                0: taken=first==second;
                1: taken=first!=second;
                4: taken=$signed(first)<$signed(second);
                5: taken=$signed(first)>=$signed(second);
                6: taken=first<second;
                7: taken=first>=second;
                default: taken=0;
            endcase
            expected=taken ? 32'h100+decoded.immediate : 32'h104;
            #1;
            if(dut.early_taken!==taken || dut.early_next!==expected || dut.actual_next!==expected || dut.early_exception!==(taken && unaligned!=0) || dut.ex_redirect!==( !(taken && unaligned!=0)))
                $fatal(1,"FAIL early_direct_redirect condition function=%0d first=%08x second=%08x unaligned=%0d",function_code,first,second,unaligned);
            condition_checks=condition_checks+1;
        end
    endtask
    task automatic run_data_independence;
        reg [31:0] expected_actual;
        begin
            clk=0; rst_n=0; response_valid=0; data_response_valid=0; #1; rst_n=1; #1;
            decoded=0; decoded.is_branch=1; decoded.uses_rs1=1; decoded.uses_rs2=1; decoded.immediate=8;
            dut.ex_decode=decoded; dut.ex_valid=1; dut.ex_pc=32'h100; dut.ex_instruction=32'h00208463; dut.mem_match_a=(dut.ex_instruction[19:15]==dut.mem_rd); dut.mem_match_b=(dut.ex_instruction[24:20]==dut.mem_rd); dut.ex_relative_target=dut.ex_pc+dut.ex_decode.immediate;
            dut.ex_prediction=32'h200; dut.ex_operand_a=0; dut.ex_operand_b=1; dut.raw_pair_relation=dut.operand_relation(dut.ex_operand_a,dut.ex_operand_b); sync_wb_comparisons;
            dut.mem_valid=1; dut.mem_load=1; dut.mem_writes=1; dut.mem_rd=1; dut.mem_rd_nonzero=dut.mem_rd!=0; dut.mem_match_a=(dut.ex_instruction[19:15]==dut.mem_rd); dut.mem_match_b=(dut.ex_instruction[24:20]==dut.mem_rd); dut.mem_sent=1;
            dut.mem_next_pc=32'h84; dut.mem_prediction=32'h84;
            dut.mem_load_route=dut.decode_load_route(3'd2,2'd0); data_response_valid=1;
            for(integer sample=0;sample<8;sample=sample+1) begin
                data_response_data=edges[sample]; expected_actual=data_response_data==1 ? 32'h108 : 32'h104; #1;
                if(!dut.ex_fire || !dut.early_load_dependency || dut.early_operand_a!==0 || dut.early_taken || dut.early_next!==32'h104 || dut.ex_redirect || dut.actual_next!==expected_actual)
                    $fatal(1,"FAIL early_direct_redirect returned-data isolation sample=%0d",sample);
                independence_checks=independence_checks+1;
            end
        end
    endtask
    initial begin
        for(integer operation=0;operation<5;operation=operation+1)
            for(integer prediction_match=0;prediction_match<2;prediction_match=prediction_match+1)
                for(integer exception_kind=0;exception_kind<3;exception_kind=exception_kind+1)
                    for(integer older=0;older<12;older=older+1)
                        for(integer fetch_mode=0;fetch_mode<3;fetch_mode=fetch_mode+1)
                            run_case(operation,prediction_match,exception_kind,older,fetch_mode);
        if(checks!=1080 || early_checks!=42 || older_priority!=360 || pending_drains!=28 || fallback_checks!=(LOAD_USE_BUBBLE!=0 ? 45 : 48))
            $fatal(1,"FAIL early_direct_redirect coverage checks=%0d early=%0d older=%0d drains=%0d",checks,early_checks,older_priority,pending_drains);
        edges[0]=0; edges[1]=1; edges[2]=32'hffffffff; edges[3]=32'h7fffffff;
        edges[4]=32'h80000000; edges[5]=32'h0000ffff; edges[6]=32'hffff0000; edges[7]=32'h55555555;
        for(integer function_code=0;function_code<8;function_code=function_code+1)
            if(function_code!=2 && function_code!=3)
                for(integer first=0;first<8;first=first+1)
                    for(integer second=0;second<8;second=second+1)
                        for(integer unaligned=0;unaligned<2;unaligned=unaligned+1) run_condition_case(function_code,edges[first],edges[second],unaligned);
        run_data_independence();
        if(condition_checks!=768 || independence_checks!=8) $fatal(1,"FAIL early_direct_redirect added coverage");
        $display("PASS early_direct_redirect checks=%0d early=%0d older_priority=%0d pending_drains=%0d fallback=%0d conditions=%0d independent=%0d overlap=%0d bubble=%0d",checks,early_checks,older_priority,pending_drains,fallback_checks,condition_checks,independence_checks,FETCH_OVERLAP,LOAD_USE_BUBBLE);
        $finish;
    end
endmodule
