module control_decode_tb;
    reg [31:0] instruction;
    wire branch,jal,jalr,load,store,fence_i,csr,mret;
    wire branch_m,jal_m,jalr_m,load_m,store_m,fence_i_m,csr_m,mret_m;
    wire [5:0] classes={branch|jal|jalr,load,store,fence_i,csr,mret};
    wire [5:0] classes_m={branch_m|jal_m|jalr_m,load_m,store_m,fence_i_m,csr_m,mret_m};
    integer opcode_index,funct3_index,funct7_index,operand_index,checks=0;
    reg [31:0] random_state=32'h17c0ab39;
    rv32_decode #(.ENABLE_M(0)) original(.instruction(instruction),.is_branch(branch),.is_jal(jal),.is_jalr(jalr),.is_load(load),.is_store(store),.is_fence_i(fence_i),.is_csr(csr),.is_mret(mret));
    rv32_decode #(.ENABLE_M(1)) extended(.instruction(instruction),.is_branch(branch_m),.is_jal(jal_m),.is_jalr(jalr_m),.is_load(load_m),.is_store(store_m),.is_fence_i(fence_i_m),.is_csr(csr_m),.is_mret(mret_m));
    task check_classes;
        begin
            #1;
            if((classes & (classes-6'b000001)) !== 6'b0 || (classes_m & (classes_m-6'b000001)) !== 6'b0)
                $fatal(1,"non-exclusive classes instruction=%08x",instruction);
            checks=checks+2;
        end
    endtask
    initial begin
        for(opcode_index=0;opcode_index<128;opcode_index=opcode_index+1)
            for(funct3_index=0;funct3_index<8;funct3_index=funct3_index+1)
                for(funct7_index=0;funct7_index<128;funct7_index=funct7_index+1)
                    for(operand_index=0;operand_index<4;operand_index=operand_index+1) begin
                        instruction=(funct7_index<<25)|(funct3_index<<12)|opcode_index;
                        case(operand_index)
                            1:instruction=instruction|32'h01ff8f80;
                            2:instruction=instruction|32'h01550500;
                            3:instruction=instruction|32'h00aa8a80;
                        endcase
                        check_classes();
                    end
        instruction=32'h30200073; check_classes();
        if(!mret || !mret_m) $fatal(1,"MRET not exercised");
        instruction=32'h0000100f; check_classes();
        if(!fence_i || !fence_i_m) $fatal(1,"FENCE.I not exercised");
        for(operand_index=0;operand_index<65536;operand_index=operand_index+1) begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            instruction=random_state; check_classes();
        end
        $display("PASS decoder classes checks=%0d",checks); $finish;
    end
endmodule
