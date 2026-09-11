`timescale 1ns/1ps
module next_pc_enable_reduce_tb #(parameter integer ENABLE_PREDICTOR=1);
    reg clk=0,rst_n=0;
    reg fetch_active,fetch_sent,fetch_discard,if_valid,id_valid,ex_valid,ex_fire,i_rsp_valid;
    reg frontend_flush,frontend_barrier,prediction_hit,predicted_taken;
    reg [31:0] predicted_target,redirect_pc;
    wire [31:0] original_pc,candidate_pc;
    reg [31:0] expected_pc=32'hfffffffc;
    reg [63:0] random_state=64'hd590c31ba612784f;
    integer checks=0,resets=0;
    original_control #(.ENABLE_PREDICTOR(ENABLE_PREDICTOR)) original_dut(.next_pc(original_pc),.*);
    candidate_control #(.ENABLE_PREDICTOR(ENABLE_PREDICTOR)) candidate_dut(.next_pc(candidate_pc),.*);
    function automatic [63:0] next_random(input [63:0] value);
        reg [63:0] shifted;
        begin shifted=value^(value<<13); shifted=shifted^(shifted>>7); next_random=shifted^(shifted<<17); end
    endfunction
    task automatic configure(input [31:0] pattern);
        begin
            {fetch_active,fetch_sent,fetch_discard,if_valid,id_valid,ex_valid,ex_fire,i_rsp_valid,frontend_flush,frontend_barrier,prediction_hit,predicted_taken}=pattern[11:0];
            predicted_target={pattern[15:0],pattern[31:16]};
            redirect_pc=pattern^32'h93a54c16;
        end
    endtask
    task automatic check_cycle;
        reg capacity;
        begin
            #1;
            capacity=!if_valid || !id_valid || !ex_valid || ex_fire || fetch_discard;
            if(frontend_flush) expected_pc=redirect_pc;
            else if(!frontend_barrier && (!fetch_active || (i_rsp_valid && fetch_active && fetch_sent && capacity)))
                expected_pc=(ENABLE_PREDICTOR!=0 && prediction_hit && predicted_taken) ? predicted_target : expected_pc+32'd4;
            clk=1;
            #1;
            if(original_pc!==candidate_pc || candidate_pc!==expected_pc)
                $fatal(1,"FAIL next_pc_enable_reduce check=%0d old=%h new=%h expected=%h",checks,original_pc,candidate_pc,expected_pc);
            clk=0;
            #1;
            checks=checks+1;
        end
    endtask
    task automatic check_reset;
        begin
            rst_n=0;
            expected_pc=32'hfffffffc;
            #1;
            if(original_pc!==expected_pc || candidate_pc!==expected_pc) $fatal(1,"FAIL next_pc_enable_reduce reset");
            rst_n=1;
            #1;
            resets=resets+1;
        end
    endtask
    initial begin
        configure(0);
        #1;
        rst_n=1;
        check_reset();
        for(integer pattern=0;pattern<4096;pattern=pattern+1) begin
            configure(pattern);
            check_cycle();
        end
        for(integer sample=0;sample<65536;sample=sample+1) begin
            random_state=next_random(random_state);
            configure(random_state[31:0]);
            if(sample%1024==0) check_reset();
            check_cycle();
        end
        if(checks!=69632 || resets!=65) $fatal(1,"FAIL next_pc_enable_reduce incomplete coverage");
        $display("PASS next_pc_enable_reduce checks=%0d resets=%0d predictor=%0d",checks,resets,ENABLE_PREDICTOR);
        $finish;
    end
endmodule
