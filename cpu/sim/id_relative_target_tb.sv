`timescale 1ns/1ps
module id_relative_target_tb;
    reg clk=0,rst_n=1,id_fire=0;
    reg [31:0] id_pc=0,id_instruction=0,effective_address=0;
    wire [31:0] parent_target,candidate_target,parent_indirect,candidate_indirect;
    wire [31:0] parent_pc,candidate_pc,parent_immediate,candidate_immediate;
    integer cycles=0,resets=0,sample_index,control_index,field_bit;
    reg [31:0] instruction_word,pc_word;
    relative_parent parent(.clk(clk),.rst_n(rst_n),.id_fire(id_fire),.id_pc(id_pc),.id_instruction(id_instruction),.effective_address(effective_address),.target(parent_target),.indirect_target(parent_indirect),.pc(parent_pc),.immediate(parent_immediate));
    relative_candidate candidate(.clk(clk),.rst_n(rst_n),.id_fire(id_fire),.id_pc(id_pc),.id_instruction(id_instruction),.effective_address(effective_address),.target(candidate_target),.indirect_target(candidate_indirect),.pc(candidate_pc),.immediate(candidate_immediate));
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
            if(parent_pc!==candidate_pc || parent_immediate!==candidate_immediate || parent_target!==candidate_target || parent_indirect!==candidate_indirect)
                $fatal(1,"FAIL id_relative_target cycle=%0d fire=%b pc=%h imm=%h target=%h/%h indirect=%h/%h",cycles,id_fire,parent_pc,parent_immediate,parent_target,candidate_target,parent_indirect,candidate_indirect);
        end
    endtask
    task automatic reset_state;
        begin
            clk=0; rst_n=0; #1; check_state;
            if(candidate_target!==32'b0) $fatal(1,"FAIL id_relative_target reset");
            rst_n=1; #1; resets=resets+1;
        end
    endtask
    task automatic tick(input [31:0] instruction,pc_value,input capture);
        begin
            clk=0; id_instruction=instruction; id_pc=pc_value; id_fire=capture;
            effective_address=$random;
            #1; check_state; clk=1; #1; check_state; clk=0;
            cycles=cycles+1;
        end
    endtask
    initial begin
        reset_state;
        for(sample_index=0;sample_index<8192;sample_index=sample_index+1) begin
            instruction_word=$random;
            case(sample_index%8)
                0: instruction_word[6:0]=7'h63;
                1: instruction_word[6:0]=7'h6f;
                2: begin instruction_word[6:0]=7'h67; instruction_word[14:12]=0; end
                3: instruction_word[6:0]=7'h17;
                4: instruction_word[6:0]=7'h37;
                5: instruction_word[6:0]=7'h03;
                6: instruction_word[6:0]=7'h23;
                default: instruction_word[6:0]=7'h13;
            endcase
            case(sample_index%4)
                0: pc_word=32'hfffffff0;
                1: pc_word=32'h0000ffff;
                2: pc_word=32'h7ffffffe;
                default: pc_word=$random;
            endcase
            tick(instruction_word,pc_word,1'b1);
            tick(~instruction_word,~pc_word,1'b0);
        end
        for(sample_index=0;sample_index<1024;sample_index=sample_index+1) begin
            if(sample_index%64==0) reset_state;
            instruction_word=$random; pc_word=$random;
            for(control_index=0;control_index<4;control_index=control_index+1)
                tick(instruction_word,pc_word,state_value(control_index));
            for(field_bit=0;field_bit<8;field_bit=field_bit+1) begin
                instruction_word[(sample_index+field_bit*3)%32]=state_value(sample_index>>(field_bit%5));
                pc_word[(sample_index+field_bit*5)%32]=state_value((sample_index+field_bit)>>(field_bit%5));
            end
            for(control_index=0;control_index<16;control_index=control_index+1)
                tick(instruction_word,pc_word,state_value(control_index));
        end
        if(cycles!=36864 || resets!=17) $fatal(1,"FAIL id_relative_target inventory");
        $display("PASS id_relative_target cycles=%0d resets=%0d",cycles,resets);
        $finish;
    end
endmodule
