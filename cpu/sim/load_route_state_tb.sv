`timescale 1ns/1ps
module load_route_state_tb;
    parameter integer FULL_SWEEP=1;
    typedef struct packed {
        logic uses_rs1,uses_rs2,writes_rd;
        logic [31:0] immediate;
        logic [3:0] alu_op;
        logic alu_immediate;
        logic is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
        logic is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    } decode_t;
    decode_t selected_decode;
    reg clk=0,rst_n=1;
    reg selected_ex_fire=0,selected_mem_fire=0,selected_flush=0;
    reg response_valid=0,response_error=0;
    reg [31:0] selected_instruction=0,selected_address=0,selected_result=32'h712345ab,response_data=0;
    reg [7:0] control_coverage=0;
    integer cases=0,state_checks=0,data_checks=0,tag_count;
    rv32_core core(.clk(clk),.rst_n(rst_n),
        .i_req_ready(1'b0),.i_rsp_valid(1'b0),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(1'b0),.d_rsp_valid(response_valid),.d_rsp_data(response_data),.d_rsp_error(response_error),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic verify_data;
        reg [31:0] shifted,expected;
        begin
            shifted=response_data>>{core.mem_address[1:0],3'b0};
            expected=core.mem_result;
            if(core.mem_load) begin
                case(core.mem_funct3)
                    0: expected={{24{shifted[7]}},shifted[7:0]};
                    1: expected={{16{shifted[15]}},shifted[15:0]};
                    2: expected=shifted;
                    4: expected={24'b0,shifted[7:0]};
                    5: expected={16'b0,shifted[15:0]};
                    default: expected=0;
                endcase
            end
            if(core.mem_value!==expected) $fatal(1,"FAIL load_route_state data case=%0d format=%0d offset=%0d value=%08x expected=%08x",cases,core.mem_funct3,core.mem_address[1:0],core.mem_value,expected);
            data_checks=data_checks+1;
        end
    endtask
    task automatic tick;
        begin
            #1; clk=1; #1;
            if(core.mem_load_route!==core.decode_load_route(core.mem_funct3,core.mem_address[1:0]))
                $fatal(1,"FAIL load_route_state metadata coherence case=%0d",cases);
            state_checks=state_checks+1;
            clk=0;
            for(integer pattern=0;pattern<36;pattern=pattern+1) begin
                if(pattern<32) response_data=32'b1<<pattern;
                else case(pattern)
                    32: response_data=0;
                    33: response_data=32'hffffffff;
                    34: response_data=32'h80ff7f01;
                    default: response_data=32'h55aa1234;
                endcase
                response_valid=pattern[0]; response_error=pattern[1];
                #1; verify_data();
            end
        end
    endtask
    initial begin
        selected_decode='0;
        force core.ex_fire=selected_ex_fire;
        force core.mem_fire=selected_mem_fire;
        force core.mem_flush=selected_flush;
        force core.id_fire=1'b0;
        force core.ex_instruction=selected_instruction;
        force core.ex_decode=selected_decode;
        force core.effective_address=selected_address;
        force core.execute_result=selected_result;
        #1; rst_n=0; #1;
        if(core.mem_load_route!==17'h00401) $fatal(1,"FAIL load_route_state reset");
        rst_n=1;
        tag_count=FULL_SWEEP!=0 ? 32 : 8;
        for(integer previous_tag=0;previous_tag<tag_count;previous_tag=previous_tag+1) begin
            for(integer next_tag=0;next_tag<32;next_tag=next_tag+1) begin
                for(integer controls=0;controls<8;controls=controls+1) begin
                    for(integer load_kind=0;load_kind<2;load_kind=load_kind+1) begin
                        selected_ex_fire=1; selected_mem_fire=0; selected_flush=0;
                        selected_instruction={17'b0,previous_tag[4:2],12'h003};
                        selected_address={30'b0,previous_tag[1:0]};
                        selected_decode='0; selected_decode.is_load=!load_kind[0];
                        tick();
                        selected_instruction={17'b0,next_tag[4:2],12'h003};
                        selected_address={30'b0,next_tag[1:0]};
                        selected_decode.is_load=load_kind[0];
                        selected_ex_fire=controls[0]; selected_mem_fire=controls[1]; selected_flush=controls[2];
                        selected_result=selected_result^32'h19ad03fe;
                        tick();
                        cases=cases+1; control_coverage=control_coverage | (8'b1<<controls);
                    end
                end
            end
        end
        if(cases!=(FULL_SWEEP!=0 ? 16384 : 4096) || state_checks!=cases*2 || data_checks!=cases*72 || control_coverage!==8'hff)
            $fatal(1,"FAIL load_route_state incomplete coverage");
        #1; rst_n=0; #1;
        if(core.mem_load_route!==17'h00401) $fatal(1,"FAIL load_route_state second reset");
        $display("PASS load_route_state cases=%0d state_checks=%0d data_checks=%0d controls=%02x",cases,state_checks,data_checks,control_coverage);
        $finish;
    end
endmodule
