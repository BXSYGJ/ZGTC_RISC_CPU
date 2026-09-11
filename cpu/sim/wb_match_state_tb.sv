`timescale 1ns/1ps
module wb_match_state_tb;
    parameter integer FULL_SWEEP=1;
    reg clk=0,rst_n=1;
    reg selected_id_fire=0,selected_mem_fire=0,selected_mem_fault=0,selected_mem_writes=0,selected_flush=0;
    reg [4:0] selected_rd=0;
    reg [31:0] selected_instruction=32'h00000033;
    reg [31:0] control_coverage=0;
    integer cases=0,checks=0,nonzero_a=0,nonzero_b=0;
    integer register_count,register_edges[0:7];
    reg [4:0] source_a,source_b;
    rv32_core core(.clk(clk),.rst_n(rst_n),
        .i_req_ready(1'b0),.i_rsp_valid(1'b0),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic verify_state;
        begin
            if(core.ex_wb_match_a !== (core.wb_valid && core.wb_writes && core.wb_rd!=0 && core.ex_rs1==core.wb_rd))
                $fatal(1,"FAIL wb_match_state A case=%0d wb=%0d/%0d/%0d rs1=%0d",cases,core.wb_valid,core.wb_writes,core.wb_rd,core.ex_rs1);
            if(core.ex_wb_match_b !== (core.wb_valid && core.wb_writes && core.wb_rd!=0 && core.ex_rs2==core.wb_rd))
                $fatal(1,"FAIL wb_match_state B case=%0d wb=%0d/%0d/%0d rs2=%0d",cases,core.wb_valid,core.wb_writes,core.wb_rd,core.ex_rs2);
            if(core.ex_wb_match_a) nonzero_a=nonzero_a+1;
            if(core.ex_wb_match_b) nonzero_b=nonzero_b+1;
            checks=checks+2;
        end
    endtask
    task automatic tick;
        begin
            #1; clk=1; #1;
            verify_state();
            clk=0; #1;
        end
    endtask
    initial begin
        register_edges[0]=0; register_edges[1]=1; register_edges[2]=2; register_edges[3]=3;
        register_edges[4]=15; register_edges[5]=16; register_edges[6]=30; register_edges[7]=31;
        register_count=FULL_SWEEP!=0 ? 32 : 8;
        force core.id_fire=selected_id_fire;
        force core.mem_fire=selected_mem_fire;
        force core.mem_fault=selected_mem_fault;
        force core.mem_writes=selected_mem_writes;
        force core.mem_rd=selected_rd;
        force core.id_instruction=selected_instruction;
        force core.mem_flush=selected_flush;
        force core.ex_fire=1'b0;
        #1; rst_n=0; #1;
        if(core.ex_wb_match_a!==0 || core.ex_wb_match_b!==0) $fatal(1,"FAIL wb_match_state reset");
        rst_n=1;
        for(integer controls=0;controls<32;controls=controls+1) begin
            for(integer destination=0;destination<register_count;destination=destination+1) begin
                for(integer operand_a=0;operand_a<register_count;operand_a=operand_a+1) begin
                    for(integer operand_b=0;operand_b<register_count;operand_b=operand_b+1) begin
                        source_a=FULL_SWEEP!=0 ? operand_a[4:0] : register_edges[operand_a][4:0];
                        source_b=FULL_SWEEP!=0 ? operand_b[4:0] : register_edges[operand_b][4:0];
                        selected_rd=FULL_SWEEP!=0 ? destination[4:0] : register_edges[destination][4:0];
                        selected_id_fire=1; selected_mem_fire=0; selected_mem_fault=0; selected_flush=0;
                        selected_mem_writes=0;
                        selected_instruction={7'b0,source_b,source_a,3'b0,5'd3,7'h33};
                        tick();
                        selected_id_fire=controls[0]; selected_mem_fire=controls[1]; selected_mem_fault=controls[2];
                        selected_mem_writes=controls[3]; selected_flush=controls[4];
                        selected_instruction={7'b0,(source_b^5'h15),(source_a^5'h1f),3'b0,5'd3,7'h33};
                        tick();
                        cases=cases+1;
                        control_coverage=control_coverage | (32'b1 << controls);
                    end
                end
            end
        end
        if(cases!=(FULL_SWEEP!=0 ? 1048576 : 16384) || control_coverage!==32'hffffffff || nonzero_a==0 || nonzero_b==0)
            $fatal(1,"FAIL wb_match_state incomplete case coverage");
        #1; rst_n=0; #1;
        if(core.ex_wb_match_a!==0 || core.ex_wb_match_b!==0) $fatal(1,"FAIL wb_match_state second reset");
        $display("PASS wb_match_state cases=%0d checks=%0d match_a=%0d match_b=%0d controls=%08x",cases,checks,nonzero_a,nonzero_b,control_coverage);
        $finish;
    end
endmodule
