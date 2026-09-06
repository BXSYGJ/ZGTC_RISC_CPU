`timescale 1ns/1ps
module decode_alu_tb;
    reg [31:0] instruction;
    wire [4:0] rs1,rs2,rd;
    wire uses_rs1,uses_rs2,writes_rd,alu_immediate;
    wire [31:0] immediate;
    wire [3:0] alu_op;
    wire is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
    wire is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    reg [31:0] operand_a,operand_b;
    reg [3:0] operation;
    wire [31:0] result;
    integer funct_index,upper_index,trial,op_index,checks;
    reg expected_illegal;
    reg [31:0] expected_result;
    reg [31:0] random_state;
    rv32_decode decoder (.*);
    rv32_alu alu (.*);
    task check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if (!condition) $fatal(1,"FAIL %s instruction=%08x",label_text,instruction);
        end
    endtask
    task next_random;
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
        end
    endtask
    initial begin
        checks=0; instruction=0; operand_a=0; operand_b=0; operation=0;
        random_state=32'h104729;
        for(upper_index=0;upper_index<128;upper_index=upper_index+1) begin
            for(funct_index=0;funct_index<8;funct_index=funct_index+1) begin
                instruction={upper_index[6:0],5'd2,5'd1,funct_index[2:0],5'd3,7'h33};
                expected_illegal=!(upper_index==0 || (upper_index==32 && (funct_index==0 || funct_index==5)));
                #1; check(illegal===expected_illegal,"OP legality");
                check(writes_rd===!expected_illegal,"OP side effect");
                instruction[6:0]=7'h13;
                expected_illegal=(funct_index==1 && upper_index!=0) ||
                    (funct_index==5 && upper_index!=0 && upper_index!=32);
                #1; check(illegal===expected_illegal,"OP-IMM legality");
            end
        end
        for(funct_index=0;funct_index<8;funct_index=funct_index+1) begin
            instruction={12'hffe,5'd7,funct_index[2:0],5'd5,7'h03};
            #1; check(illegal===(funct_index==3 || funct_index==6 || funct_index==7),"load widths");
            check(immediate===32'hfffffffe,"I immediate");
            instruction[6:0]=7'h23;
            #1; check(illegal===(funct_index>2),"store widths");
            check(!illegal || !is_store,"illegal store suppressed");
            instruction[6:0]=7'h63;
            #1; check(illegal===(funct_index==2 || funct_index==3),"branch conditions");
        end
        instruction=32'hfe208ee3; #1;
        check(immediate===32'hfffffffc && is_branch,"negative B immediate");
        instruction=32'hffdff0ef; #1;
        check(immediate===32'hfffffffc && is_jal,"negative J immediate");
        instruction=32'h800002b7; #1;
        check(immediate===32'h80000000 && is_lui,"U immediate");
        instruction=32'h00000073; #1; check(is_ecall && !illegal,"ecall");
        instruction=32'h00100073; #1; check(is_ebreak && !illegal,"ebreak");
        instruction=32'h30200073; #1; check(is_mret && !illegal,"mret");
        instruction=32'h10500073; #1; check(is_wfi && !illegal,"wfi");
        instruction=32'h00200073; #1; check(illegal,"unsupported privileged instruction");
        instruction=32'h00008073; #1; check(illegal,"reserved ecall rs1");
        instruction=32'h00000000; #1; check(illegal,"compressed not supported");
        instruction=32'h300fd073; #1; check(is_csr && !uses_rs1 && immediate==31,"CSR immediate");
        instruction=32'h30009073; #1; check(is_csr && uses_rs1,"CSR register");
        for(trial=0;trial<1000;trial=trial+1) begin
            next_random; operand_a=random_state;
            next_random; operand_b=random_state;
            for(op_index=0;op_index<10;op_index=op_index+1) begin
                operation=op_index[3:0];
                case(op_index)
                    0: expected_result=operand_a+operand_b;
                    1: expected_result=operand_a-operand_b;
                    2: expected_result=operand_a<<operand_b[4:0];
                    3: expected_result=($signed(operand_a)<$signed(operand_b)) ? 1 : 0;
                    4: expected_result=(operand_a<operand_b) ? 1 : 0;
                    5: expected_result=operand_a^operand_b;
                    6: expected_result=operand_a>>operand_b[4:0];
                    7: expected_result=$signed(operand_a)>>>operand_b[4:0];
                    8: expected_result=operand_a|operand_b;
                    9: expected_result=operand_a&operand_b;
                endcase
                #1; check(result===expected_result,"ALU randomized");
            end
        end
        $display("PASS decode_alu checks=%0d seed=104729",checks);
        $finish;
    end
endmodule
