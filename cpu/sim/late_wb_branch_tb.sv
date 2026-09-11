`timescale 1ns/1ps
module late_wb_branch_tb;
    reg mem_valid=0,mem_writes=0,mem_load=0,mem_exception=0,trace_write=0,uses_rs1=0,uses_rs2=0;
    reg [4:0] ex_rs1=0,ex_rs2=0,mem_rd=0,wb_rd=0;
    reg [31:0] ex_operand_a=0,ex_operand_b=0,mem_result=0,wb_data=0;
    wire [31:0] early_operand_a,early_operand_b;
    wire early_equal,early_unsigned_less,early_signed_less;
    integer checks=0;
    reg [31:0] random_state=32'h458ddf17;
    early_compare_probe dut(.*);
    function automatic [31:0] corner(input integer index);
        begin
            case(index)
                0: corner=0; 1: corner=32'hffffffff; 2: corner=32'h80000000; 3: corner=32'h7fffffff;
                4: corner=1; 5: corner=32'hff; 6: corner=32'h100; 7: corner=32'hffff;
                8: corner=32'h10000; 9: corner=32'hffffff; 10: corner=32'h1000000; 11: corner=32'hfffffffe;
                12: corner=32'h55aa55aa; 13: corner=32'haa55aa55; 14: corner=32'h80000001; default: corner=32'h7ffffffe;
            endcase
        end
    endfunction
    function automatic [31:0] next_random(input [31:0] value);
        reg [31:0] shifted;
        begin shifted=value^(value<<13); shifted=shifted^(shifted>>17); next_random=shifted^(shifted<<5); end
    endfunction
    task automatic check_result;
        reg [31:0] expected_a,expected_b;
        begin
            expected_a=ex_operand_a; expected_b=ex_operand_b;
            if(trace_write && ex_rs1==wb_rd) expected_a=wb_data;
            if(trace_write && ex_rs2==wb_rd) expected_b=wb_data;
            if(mem_valid && mem_writes && !mem_load && mem_rd!=0 && !mem_exception) begin
                if(ex_rs1==mem_rd) expected_a=mem_result;
                if(ex_rs2==mem_rd) expected_b=mem_result;
            end
            if(ex_rs1==0 || !uses_rs1) expected_a=0;
            if(ex_rs2==0 || !uses_rs2) expected_b=0;
            #1;
            if(early_operand_a!==expected_a || early_operand_b!==expected_b ||
               early_equal!==(expected_a==expected_b) || early_unsigned_less!==(expected_a<expected_b) ||
               early_signed_less!==($signed(expected_a)<$signed(expected_b)))
                $fatal(1,"FAIL late_wb_branch check=%0d first=%08x second=%08x rs=%0d/%0d mem=%0d wb=%0d",checks,expected_a,expected_b,ex_rs1,ex_rs2,mem_rd,wb_rd);
            checks=checks+1;
        end
    endtask
    initial begin
        for(integer pattern=0;pattern<16;pattern=pattern+1) begin
            ex_operand_a=corner(pattern); ex_operand_b=corner((pattern+3)%16);
            mem_result=corner((pattern+5)%16); wb_data=corner((pattern+11)%16);
            for(integer registers=0;registers<256;registers=registers+1) begin
                ex_rs1={3'b0,registers[1:0]}; ex_rs2={3'b0,registers[3:2]};
                mem_rd={3'b0,registers[5:4]}; wb_rd={3'b0,registers[7:6]};
                for(integer control=0;control<128;control=control+1) begin
                    uses_rs1=control[0]; uses_rs2=control[1]; trace_write=control[2] && wb_rd!=0;
                    mem_valid=control[3]; mem_writes=control[4]; mem_load=control[5]; mem_exception=control[6];
                    check_result();
                end
            end
        end
        for(integer sample=0;sample<65536;sample=sample+1) begin
            random_state=next_random(random_state); ex_operand_a=random_state;
            random_state=next_random(random_state); ex_operand_b=sample[2:0]==0 ? ex_operand_a : random_state;
            random_state=next_random(random_state); mem_result=random_state;
            random_state=next_random(random_state); wb_data=sample[1:0]==0 ? mem_result : random_state;
            random_state=next_random(random_state);
            ex_rs1=random_state[4:0]; ex_rs2=random_state[9:5]; mem_rd=random_state[14:10]; wb_rd=random_state[19:15];
            uses_rs1=random_state[20]; uses_rs2=random_state[21]; trace_write=random_state[22] && wb_rd!=0;
            mem_valid=random_state[23]; mem_writes=random_state[24]; mem_load=random_state[25]; mem_exception=random_state[26];
            check_result();
        end
        if(checks!=589824) $fatal(1,"FAIL late_wb_branch incomplete checks=%0d",checks);
        $display("PASS late_wb_branch checks=%0d selectors=524288 random=65536",checks);
        $finish;
    end
endmodule
