`timescale 1ns/1ps
module load_use_address_bypass_tb;
    parameter integer LOAD_USE_BUBBLE=0;
    typedef struct packed {
        logic uses_rs1,uses_rs2,writes_rd;
        logic [31:0] immediate;
        logic [3:0] alu_op;
        logic alu_immediate;
        logic is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
        logic is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    } decode_t;
    decode_t decode_value;
    reg [31:0] instruction=0,operand_a=0,operand_b=0,memory_result=0,writeback_data=0,response_data=0;
    reg [31:0] memory_address=0,random_state=32'h2741ad69;
    reg [31:0] edges[0:7];
    reg [4:0] memory_rd=0,writeback_rd=0;
    reg [2:0] memory_funct3=0;
    reg memory_valid=0,memory_writes=0,memory_exception=0,memory_load=0;
    reg writeback_valid=0,writeback_writes=0,response_valid=0,response_error=0;
    integer checks=0;
    rv32_core #(.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE)) dut(.clk(1'b0),.rst_n(1'b0),
        .i_req_ready(1'b0),.i_rsp_valid(1'b0),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(1'b0),.d_rsp_valid(response_valid),.d_rsp_data(response_data),.d_rsp_error(response_error),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic verify_case;
        reg [31:0] shifted,expected_memory,expected_a,expected_b,selected_memory,branch_a,branch_b,expected_address;
        reg expected_taken,expected_wait;
        begin
            shifted=response_data >> {memory_address[1:0],3'b0};
            expected_memory=memory_result;
            if(memory_load) begin
                case(memory_funct3)
                    0: expected_memory={{24{shifted[7]}},shifted[7:0]};
                    1: expected_memory={{16{shifted[15]}},shifted[15:0]};
                    2: expected_memory=shifted;
                    4: expected_memory={24'b0,shifted[7:0]};
                    5: expected_memory={16'b0,shifted[15:0]};
                    default: expected_memory=0;
                endcase
            end
            selected_memory=LOAD_USE_BUBBLE!=0 ? memory_result : expected_memory;
            expected_a=operand_a; expected_b=operand_b;
            if(writeback_valid && writeback_writes && writeback_rd!=0) begin
                if(instruction[19:15]==writeback_rd) expected_a=writeback_data;
                if(instruction[24:20]==writeback_rd) expected_b=writeback_data;
            end
            if(memory_valid && memory_writes && memory_rd!=0 && !memory_exception && (!memory_load || LOAD_USE_BUBBLE==0)) begin
                if(instruction[19:15]==memory_rd) expected_a=selected_memory;
                if(instruction[24:20]==memory_rd) expected_b=selected_memory;
            end
            if(instruction[19:15]==0 || !decode_value.uses_rs1) expected_a=0;
            if(instruction[24:20]==0 || !decode_value.uses_rs2) expected_b=0;
            #1;
            if(dut.mem_value!==expected_memory || dut.forwarded_a!==expected_a || dut.forwarded_b!==expected_b)
                $fatal(1,"FAIL load_use_address_bypass check=%0d bubble=%0d expected=%08x/%08x actual=%08x/%08x",checks,LOAD_USE_BUBBLE,
                    expected_a,expected_b,dut.forwarded_a,dut.forwarded_b);
            branch_a=expected_a; branch_b=expected_b;
            if(LOAD_USE_BUBBLE!=0 && memory_valid && memory_writes && memory_rd!=0 && !memory_exception && memory_load) begin
                if(decode_value.uses_rs1 && instruction[19:15]==memory_rd) branch_a=expected_memory;
                if(decode_value.uses_rs2 && instruction[24:20]==memory_rd) branch_b=expected_memory;
            end
            for(integer branch_mode=0;branch_mode<2;branch_mode=branch_mode+1) begin
                decode_value.is_branch=branch_mode!=0;
                for(integer condition=0;condition<8;condition=condition+1) begin
                    instruction[14:12]=condition[2:0];
                    expected_wait=LOAD_USE_BUBBLE!=0 && !(branch_mode!=0 && condition<2) && memory_valid && memory_load && memory_writes && memory_rd!=0 &&
                        ((decode_value.uses_rs1 && instruction[19:15]==memory_rd) || (decode_value.uses_rs2 && instruction[24:20]==memory_rd));
                    case(condition)
                        0: expected_taken=branch_a==branch_b;
                        1: expected_taken=branch_a!=branch_b;
                        4: expected_taken=$signed(expected_a)<$signed(expected_b);
                        5: expected_taken=$signed(expected_a)>=$signed(expected_b);
                        6: expected_taken=expected_a<expected_b;
                        7: expected_taken=expected_a>=expected_b;
                        default: expected_taken=0;
                    endcase
                    if(branch_mode==0) expected_taken=0;
                    #1;
                    if(dut.branch_operand_a!==branch_a || dut.branch_operand_b!==branch_b || dut.branch_taken!==expected_taken || dut.load_use_wait!==expected_wait)
                        $fatal(1,"FAIL load_use_address_bypass branch check=%0d mode=%0d condition=%0d",checks,branch_mode,condition);
                    if(dut.forwarded_a!==expected_a || dut.forwarded_b!==expected_b)
                        $fatal(1,"FAIL load_use_address_bypass branch path contaminated ALU operands");
                    checks=checks+1;
                end
            end
            decode_value.is_branch=0;
            for(integer access_mode=0;access_mode<4;access_mode=access_mode+1) begin
                decode_value.is_load=access_mode==1;
                decode_value.is_store=access_mode==2;
                decode_value.is_jalr=access_mode==3;
                for(integer displacement=0;displacement<6;displacement=displacement+1) begin
                    case(displacement)
                        0: decode_value.immediate=0;
                        1: decode_value.immediate=1;
                        2: decode_value.immediate=4;
                        3: decode_value.immediate=32'hffffffff;
                        4: decode_value.immediate=32'hfffff800;
                        5: decode_value.immediate=2047;
                    endcase
                    expected_address=(access_mode==1 ? branch_a : expected_a)+decode_value.immediate;
                    expected_wait=LOAD_USE_BUBBLE!=0 && !(access_mode==1) && memory_valid && memory_load && memory_writes && memory_rd!=0 &&
                        ((decode_value.uses_rs1 && instruction[19:15]==memory_rd) || (decode_value.uses_rs2 && instruction[24:20]==memory_rd));
                    #1;
                    if(dut.effective_address!==expected_address || dut.load_use_wait!==expected_wait)
                        $fatal(1,"FAIL load_use_address_bypass address check=%0d mode=%0d displacement=%0d",checks,access_mode,displacement);
                    if(dut.forwarded_a!==expected_a || dut.forwarded_b!==expected_b)
                        $fatal(1,"FAIL load_use_address_bypass address path contaminated generic operands");
                    checks=checks+1;
                end
            end
            decode_value.is_load=0; decode_value.is_store=0; decode_value.is_jalr=0; decode_value.immediate=0;
        end
    endtask
    initial begin
        force dut.ex_decode=decode_value;
        force dut.ex_instruction=instruction;
        force dut.ex_operand_a=operand_a;
        force dut.ex_operand_b=operand_b;
        force dut.mem_valid=memory_valid;
        force dut.mem_writes=memory_writes;
        force dut.mem_exception=memory_exception;
        force dut.mem_load=memory_load;
        force dut.mem_rd=memory_rd;
        force dut.mem_funct3=memory_funct3;
        force dut.mem_address=memory_address;
        force dut.mem_result=memory_result;
        force dut.wb_valid=writeback_valid;
        force dut.wb_writes=writeback_writes;
        force dut.wb_rd=writeback_rd;
        force dut.wb_data=writeback_data;
        decode_value='0;
        for(integer controls=0;controls<256;controls=controls+1) begin
            memory_valid=controls[0]; memory_writes=controls[1]; memory_exception=controls[2]; memory_load=controls[3];
            writeback_valid=controls[4]; writeback_writes=controls[5];
            decode_value.uses_rs1=controls[6]; decode_value.uses_rs2=controls[7];
            for(integer relationship=0;relationship<8;relationship=relationship+1) begin
                instruction=0; instruction[19:15]=1; instruction[24:20]=2;
                case(relationship)
                    0: begin instruction=0; writeback_rd=0; memory_rd=0; end
                    1: begin writeback_rd=1; memory_rd=1; end
                    2: begin writeback_rd=2; memory_rd=2; end
                    3: begin writeback_rd=1; memory_rd=2; end
                    4: begin writeback_rd=2; memory_rd=1; end
                    5: begin writeback_rd=3; memory_rd=4; end
                    6: begin instruction[19:15]=31; instruction[24:20]=31; writeback_rd=31; memory_rd=31; end
                    7: begin instruction[19:15]=5; instruction[24:20]=5; writeback_rd=5; memory_rd=0; end
                endcase
                for(integer operation=0;operation<8;operation=operation+1) begin
                    memory_funct3=operation[2:0];
                    for(integer offset=0;offset<4;offset=offset+1) begin
                        memory_address=32'(offset);
                        random_state=random_state^(random_state<<13);
                        random_state=random_state^(random_state>>17);
                        random_state=random_state^(random_state<<5);
                        operand_a=random_state; operand_b=~random_state;
                        writeback_data=random_state^32'h1639e5ac; memory_result=random_state^32'hb469d215;
                        response_data={random_state[15:0],random_state[31:16]};
                        response_valid=random_state[2]; response_error=random_state[3];
                        verify_case();
                    end
                end
            end
        end
        edges[0]=0; edges[1]=32'hffffffff; edges[2]=32'h80008080; edges[3]=32'h7fff7f7f;
        edges[4]=32'h01020304; edges[5]=32'h80818283; edges[6]=32'ha55aa55a; edges[7]=32'h5aa55aa5;
        memory_valid=1; memory_writes=1; memory_exception=0; memory_load=1;
        writeback_valid=1; writeback_writes=1; writeback_rd=1; memory_rd=1;
        decode_value.uses_rs1=1; decode_value.uses_rs2=1;
        instruction[19:15]=1; instruction[24:20]=1;
        for(integer edge_index=0;edge_index<8;edge_index=edge_index+1)
            for(integer operation=0;operation<8;operation=operation+1)
                for(integer offset=0;offset<4;offset=offset+1) begin
                    response_data=edges[edge_index]; memory_funct3=operation[2:0]; memory_address=32'(offset);
                    verify_case();
                end
        if(checks!=2631680) $fatal(1,"FAIL load_use_address_bypass incomplete case count");
        $display("PASS load_use_address_bypass checks=%0d bubble=%0d",checks,LOAD_USE_BUBBLE);
        $finish;
    end
endmodule
