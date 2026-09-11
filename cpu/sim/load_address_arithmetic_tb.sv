`timescale 1ns/1ps
module load_address_arithmetic_tb;
    typedef struct packed {
        logic uses_rs1,uses_rs2,writes_rd;
        logic [31:0] immediate;
        logic [3:0] alu_op;
        logic alu_immediate;
        logic is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
        logic is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    } decode_t;
    decode_t decode_value;
    reg [31:0] base_value=0,expected_address=0,random_state=32'h6a52ce17;
    reg [31:0] edges[0:7];
    integer checks=0;
    rv32_core dut(.clk(1'b0),.rst_n(1'b0),
        .i_req_ready(1'b0),.i_rsp_valid(1'b0),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    initial begin
        force dut.ex_decode=decode_value;
        force dut.branch_operand_a=base_value;
        decode_value=0; decode_value.is_load=1; decode_value.uses_rs1=1;
        edges[0]=0; edges[1]=32'hffffffff; edges[2]=32'h80000000; edges[3]=32'h7fffffff;
        edges[4]=32'h00000fff; edges[5]=32'hfffff000; edges[6]=32'h00000800; edges[7]=32'hfffff800;
        for(integer immediate_index=0;immediate_index<4096;immediate_index=immediate_index+1) begin
            decode_value.immediate={{20{immediate_index[11]}},immediate_index[11:0]};
            for(integer sample_index=0;sample_index<1032;sample_index=sample_index+1) begin
                if(sample_index<8) base_value=edges[sample_index];
                else begin
                    random_state=random_state^(random_state<<13);
                    random_state=random_state^(random_state>>17);
                    random_state=random_state^(random_state<<5);
                    base_value=random_state;
                end
                expected_address=base_value+decode_value.immediate;
                #1;
                if(dut.effective_address!==expected_address)
                    $fatal(1,"FAIL load_address_arithmetic check=%0d base=%08x immediate=%08x expected=%08x actual=%08x",checks,base_value,decode_value.immediate,expected_address,dut.effective_address);
                checks=checks+1;
            end
        end
        if(checks!=4227072) $fatal(1,"FAIL load_address_arithmetic incomplete case count");
        $display("PASS load_address_arithmetic checks=%0d signed_immediates=4096",checks);
        $finish;
    end
endmodule
