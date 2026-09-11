`timescale 1ns/1ps
module forward_match_retime_tb;
    reg clk=0,rst_n=1,id_fire=0,ex_fire=0;
    reg [31:0] id_instruction=0;
    wire [31:0] parent_instruction,candidate_instruction;
    wire [4:0] parent_ex_rd,parent_mem_rd,candidate_ex_rd,candidate_mem_rd;
    wire parent_a,parent_b,candidate_a,candidate_b;
    integer cycles=0,resets=0;
    integer destination,source_index,sample_index,control_index,field_bit;
    reg [31:0] instruction_word;
    match_parent parent(.clk(clk),.rst_n(rst_n),.id_fire(id_fire),.ex_fire(ex_fire),.id_instruction(id_instruction),.ex_instruction(parent_instruction),.ex_rd(parent_ex_rd),.mem_rd(parent_mem_rd),.match_a(parent_a),.match_b(parent_b));
    match_candidate candidate(.clk(clk),.rst_n(rst_n),.id_fire(id_fire),.ex_fire(ex_fire),.id_instruction(id_instruction),.ex_instruction(candidate_instruction),.ex_rd(candidate_ex_rd),.mem_rd(candidate_mem_rd),.match_a(candidate_a),.match_b(candidate_b));
    function automatic state_value(input integer digit);
        case(digit&3)
            0: state_value=1'b0;
            1: state_value=1'b1;
            2: state_value=1'bx;
            default: state_value=1'bz;
        endcase
    endfunction
    task automatic check_state;
        begin
            if(parent_instruction!==candidate_instruction || parent_ex_rd!==candidate_ex_rd || parent_mem_rd!==candidate_mem_rd || parent_a!==candidate_a || parent_b!==candidate_b)
                $fatal(1,"FAIL forward_match cycle=%0d id=%b ex=%b instruction=%h rd=%b expected=%b/%b actual=%b/%b",cycles,id_fire,ex_fire,parent_instruction,parent_mem_rd,parent_a,parent_b,candidate_a,candidate_b);
        end
    endtask
    task automatic reset_state;
        begin
            clk=0; rst_n=0; #1; check_state;
            if(candidate_a!==1'b1 || candidate_b!==1'b1) $fatal(1,"FAIL forward_match reset equality");
            rst_n=1; #1; resets=resets+1;
        end
    endtask
    task automatic tick(input [31:0] instruction,input id_enable,ex_enable);
        begin
            clk=0; id_instruction=instruction; id_fire=id_enable; ex_fire=ex_enable;
            #1; clk=1; #1; check_state; clk=0;
            cycles=cycles+1;
        end
    endtask
    initial begin
        reset_state;
        for(destination=0;destination<32;destination=destination+1)
            for(source_index=0;source_index<32;source_index=source_index+1) begin
                instruction_word=0;
                instruction_word[19:15]=source_index[4:0];
                instruction_word[24:20]=~source_index[4:0];
                instruction_word[11:7]=destination[4:0];
                tick(instruction_word,1'b1,1'b0);
                instruction_word[11:7]=destination[4:0]^5'd1;
                tick(instruction_word,1'b1,1'b1);
                instruction_word[11:7]=destination[4:0];
                tick(instruction_word,1'b1,1'b0);
                tick(instruction_word,1'b0,1'b1);
            end
        for(sample_index=0;sample_index<1024;sample_index=sample_index+1) begin
            if(sample_index>0 && sample_index%127==0) reset_state;
            instruction_word=0;
            for(field_bit=0;field_bit<5;field_bit=field_bit+1) begin
                instruction_word[15+field_bit]=state_value(sample_index>>(2*field_bit));
                instruction_word[20+field_bit]=state_value(((sample_index+37)&1023)>>(2*field_bit));
                instruction_word[7+field_bit]=state_value(((sample_index*29+53)&1023)>>(2*field_bit));
            end
            for(control_index=0;control_index<16;control_index=control_index+1)
                tick(instruction_word,state_value(control_index),state_value(control_index>>2));
        end
        if(cycles!=20480 || resets!=9) $fatal(1,"FAIL forward_match case inventory");
        $display("PASS forward_match cycles=%0d resets=%0d binary_cycles=4096 four_state_cycles=16384",cycles,resets);
        $finish;
    end
endmodule
