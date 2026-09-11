`timescale 1ns/1ps
module address_partition_tb;
    parameter integer SPLIT_BITS=16;
    localparam [31:0] BOUNDARY_MASK=(32'd1<<SPLIT_BITS)-1;
    reg [31:0] random_first=0;
    typedef struct packed {
        logic uses_rs1,uses_rs2,writes_rd;
        logic [31:0] immediate;
        logic [3:0] alu_op;
        logic alu_immediate;
        logic is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
        logic is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    } decode_t;
    decode_t decode_value;
    reg [31:0] operand_a=0;
    reg [31:0] edges[0:15];
    reg [31:0] random_state=32'h516ad930;
    reg [31:0] instruction=32'h00002003;
    integer checks=0;
    rv32_core dut(.clk(1'b0),.rst_n(1'b0),.i_req_ready(1'b0),.i_rsp_valid(1'b0),
        .i_rsp_data(32'b0),.i_rsp_error(1'b0),.d_req_ready(1'b0),.d_rsp_valid(1'b0),
        .d_rsp_data(32'b0),.d_rsp_error(1'b0),.maintenance_ready(1'b0),.timer_value(64'b0),
        .irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic check_case(input [31:0] first,input [31:0] second);
        reg [31:0] expected;
        begin
            operand_a=first; decode_value='0; decode_value.immediate=second;
            decode_value.is_jalr=1'b1; expected=first+second;
            instruction=32'h00002003;
            #1;
            if(dut.effective_address!==expected || dut.data_misaligned!==(expected[1:0]!=0))
                $fatal(1,"FAIL address_partition first=%08x immediate=%08x expected=%08x actual=%08x",first,second,expected,dut.effective_address);
            if(dut.branch_target!==(expected & 32'hfffffffe)) $fatal(1,"FAIL address_partition JALR target");
            instruction=32'h00001003;
            #1;
            if(dut.data_misaligned!==expected[0]) $fatal(1,"FAIL address_partition halfword alignment");
            instruction=32'h00000003;
            #1;
            if(dut.data_misaligned!==1'b0) $fatal(1,"FAIL address_partition byte alignment");
            checks=checks+1;
        end
    endtask
    initial begin
        force dut.forwarded_a=operand_a;
        force dut.ex_decode=decode_value;
        force dut.ex_instruction=instruction;
        edges[0]=0; edges[1]=1; edges[2]=32'h0000ffff; edges[3]=32'h00010000;
        edges[4]=32'h00010001; edges[5]=32'h0001ffff; edges[6]=32'hffff0000; edges[7]=32'hffffffff;
        edges[8]=32'h7fffffff; edges[9]=32'h80000000; edges[10]=32'h7fff0000; edges[11]=32'h8000ffff;
        edges[12]=32'h000007ff; edges[13]=32'hfffff800; edges[14]=32'h5555ffff; edges[15]=32'haaaa0000;
        for(integer first=0;first<16;first=first+1)
            for(integer second=0;second<16;second=second+1) check_case(edges[first],edges[second]);
        for(integer position=0;position<32;position=position+1) begin
            check_case((32'd1<<position)-1,1);
            check_case(32'hffffffff,32'd1<<position);
        end
        for(integer index=0;index<10000;index=index+1) begin
            random_state=random_state ^ (random_state<<13);
            random_state=random_state ^ (random_state>>17);
            random_state=random_state ^ (random_state<<5);
            check_case(random_state,{20'hfffff,random_state[11:0]});
            check_case(random_state,{20'b0,random_state[27:16]});
        end
        for(integer edge_index=0;edge_index<16;edge_index=edge_index+1) begin
            check_case((edges[edge_index] & ~BOUNDARY_MASK) | BOUNDARY_MASK,1);
            check_case(edges[edge_index] & ~BOUNDARY_MASK,BOUNDARY_MASK);
            check_case((edges[edge_index] & ~BOUNDARY_MASK) | BOUNDARY_MASK,32'hffffffff);
            check_case((edges[edge_index] & ~BOUNDARY_MASK) | 1,~BOUNDARY_MASK);
        end
        for(integer index=0;index<10000;index=index+1) begin
            random_state=random_state ^ (random_state<<13);
            random_state=random_state ^ (random_state>>17);
            random_state=random_state ^ (random_state<<5);
            random_first=random_state;
            random_state=random_state ^ (random_state<<13);
            random_state=random_state ^ (random_state>>17);
            random_state=random_state ^ (random_state<<5);
            check_case(random_first,random_state);
        end
        if(checks!=30384) $fatal(1,"Incomplete address carry coverage");
        $display("PASS address_partition checks=%0d",checks);
        $finish;
    end
endmodule
