`timescale 1ns/1ps
module fetch_space_reduce_tb #(parameter integer LOAD_USE_BUBBLE=1,FETCH_OVERLAP=1);
    reg mem_load,mem_store,mem_exception,mem_valid,mem_sent,mem_fence_i,maintenance_ready,d_rsp_valid,d_rsp_error,mem_mret,mem_early_redirect;
    reg interrupt_pending,ex_is_csr,ex_is_mret,ex_is_branch,ex_is_jal,ex_is_load,uses_rs1,uses_rs2;
    reg ex_valid,mem_writes,wb_valid,muldiv_valid,id_valid,if_valid,ex_error,ex_illegal,early_taken;
    reg [31:0] mem_next_pc,mem_prediction,ex_instruction,ex_pc,ex_prediction,early_next,early_target;
    reg [4:0] mem_rd;
    reg [16:0] mem_load_route;
    reg fetch_active,fetch_sent,fetch_discard,i_rsp_valid,i_req_ready;
    wire [22:0] original_witness,candidate_witness;
    integer checks=0;
    reg [63:0] random_state=64'h428195d1e367ba09;
    original_control #(.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.FETCH_OVERLAP(FETCH_OVERLAP)) original_dut(.witness(original_witness),.*);
    candidate_control #(.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.FETCH_OVERLAP(FETCH_OVERLAP)) candidate_dut(.witness(candidate_witness),.*);
    function automatic [63:0] next_random(input [63:0] value);
        reg [63:0] shifted;
        begin shifted=value^(value<<13); shifted=shifted^(shifted>>7); next_random=shifted^(shifted<<17); end
    endfunction
    task automatic configure(input [31:0] pattern,input integer variant);
        begin
            {ex_error,muldiv_valid,mem_early_redirect,mem_mret,maintenance_ready,mem_fence_i,d_rsp_error,d_rsp_valid,mem_sent,mem_exception,mem_store,mem_load,interrupt_pending,if_valid,id_valid,ex_valid,wb_valid,mem_valid}=pattern[17:0];
            {fetch_active,fetch_sent,fetch_discard,i_rsp_valid,i_req_ready}={pattern[7],pattern[11],pattern[15],pattern[3],pattern[17]};
            uses_rs1=!variant[2]; uses_rs2=!variant[3]; mem_writes=!variant[1] || pattern[16];
            ex_is_csr=variant[1:0]==1; ex_is_mret=variant[2:0]==5; ex_is_branch=variant[1:0]==2; ex_is_jal=variant[2:0]==6; ex_is_load=variant[1:0]==3;
            ex_illegal=variant[0] && pattern[20]; early_taken=variant[1] || pattern[21];
            ex_instruction=variant[1:0]==3 ? 32'h02000033 : 32'h00000013;
            ex_instruction[19:15]=pattern[4:0]; ex_instruction[24:20]=pattern[9:5]; ex_instruction[14:12]=pattern[22:20];
            mem_rd=pattern[14:10]; mem_load_route=pattern[16] ? 17'd512 : 17'd1;
            ex_pc=32'h100+{30'b0,pattern[19:18]};
            ex_prediction=32'h200; early_next=pattern[15] ? 32'h200 : 32'h104; early_target=32'h108+{30'b0,pattern[23:22]};
            mem_prediction=32'h80; mem_next_pc=pattern[17] ? 32'h80 : 32'h84;
        end
    endtask
    task automatic check_outputs;
        begin
            #1;
            if(original_witness!==candidate_witness) $fatal(1,"FAIL fetch_space_reduce check=%0d old=%h new=%h irq=%b older=%b/%b",checks,original_witness,candidate_witness,interrupt_pending,mem_valid,wb_valid);
            if(interrupt_pending) begin
                if(candidate_dut.ex_fire!==(ex_valid && !mem_valid && !wb_valid) || candidate_dut.ex_redirect!==0)
                    $fatal(1,"FAIL fetch_space_reduce interrupt issue contract check=%0d",checks);
                if(candidate_dut.id_fire!==(id_valid && !candidate_dut.mem_flush && !candidate_dut.frontend_barrier && (!ex_valid || (!mem_valid && !wb_valid))))
                    $fatal(1,"FAIL fetch_space_reduce interrupt decode contract check=%0d",checks);
            end
            checks=checks+1;
        end
    endtask
    initial begin
        for(integer variant=0;variant<4;variant=variant+1) begin
            for(integer pattern=0;pattern<262144;pattern=pattern+1) begin
                configure(pattern,variant);
                check_outputs();
            end
        end
        for(integer sample=0;sample<65536;sample=sample+1) begin
            random_state=next_random(random_state);
            configure(random_state[31:0],{28'b0,random_state[35:32]});
            check_outputs();
        end
        if(checks!=1114112) $fatal(1,"FAIL fetch_space_reduce incomplete coverage");
        $display("PASS fetch_space_reduce checks=%0d bubble=%0d overlap=%0d",checks,LOAD_USE_BUBBLE,FETCH_OVERLAP);
        $finish;
    end
endmodule
