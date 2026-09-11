`timescale 1ns/1ps
module load_address_carry16_tb;
    typedef struct packed {
        logic uses_rs1,uses_rs2,writes_rd;
        logic [31:0] immediate;
        logic [3:0] alu_op;
        logic alu_immediate;
        logic is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
        logic is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    } decode_t;
    decode_t decode_value;
    reg [31:0] loaded_base=0,general_base=0,expected_address=0,instruction=0;
    reg [31:0] random_state=32'h7e153ac9,random_loaded,random_general,random_immediate;
    reg [31:0] edges[0:19],instructions[0:9];
    reg [16:0] expected_low;
    reg expected_misaligned;
    integer checks=0,carry_zero=0,carry_one=0,aligned=0,misaligned=0;
    rv32_core dut(.clk(1'b0),.rst_n(1'b0),
        .i_req_ready(1'b0),.i_rsp_valid(1'b0),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic draw_random(output reg [31:0] value);
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            value=random_state;
        end
    endtask
    task automatic check_case(input [31:0] first,input [31:0] second,input [31:0] immediate);
        reg [31:0] selected_base;
        begin
            loaded_base=first; general_base=second; decode_value.immediate=immediate;
            selected_base=decode_value.is_load ? first : second;
            expected_address=selected_base+immediate;
            expected_low={1'b0,selected_base[15:0]}+{1'b0,immediate[15:0]};
            expected_misaligned=(instruction[13:12]==1 && expected_address[0]) ||
                (instruction[13:12]==2 && expected_address[1:0]!=0);
            #1;
            if(dut.effective_address!==expected_address)
                $fatal(1,"FAIL load_address_carry16 address check=%0d load=%0d base=%08x immediate=%08x expected=%08x actual=%08x",checks,decode_value.is_load,selected_base,immediate,expected_address,dut.effective_address);
            if(dut.data_misaligned!==expected_misaligned || dut.d_req_address!=={expected_address[31:2],2'b0})
                $fatal(1,"FAIL load_address_carry16 alignment check=%0d",checks);
            if(expected_low[16]) carry_one=carry_one+1; else carry_zero=carry_zero+1;
            if(expected_misaligned) misaligned=misaligned+1; else aligned=aligned+1;
            checks=checks+1;
        end
    endtask
    initial begin
        force dut.ex_decode=decode_value; force dut.ex_instruction=instruction;
        force dut.branch_operand_a=loaded_base; force dut.forwarded_a=general_base;
        force dut.select_ex_data=1'b1;
        edges[0]=0; edges[1]=1; edges[2]=2; edges[3]=3; edges[4]=32'h0000ffff;
        edges[5]=32'h00010000; edges[6]=32'h00010001; edges[7]=32'h00007fff; edges[8]=32'h00008000;
        edges[9]=32'hffff0000; edges[10]=32'hffffffff; edges[11]=32'h7fffffff; edges[12]=32'h80000000;
        edges[13]=32'h0fffffff; edges[14]=32'h10000000; edges[15]=32'hefffffff; edges[16]=32'hf0000000;
        edges[17]=32'h55555555; edges[18]=32'haaaaaaaa; edges[19]=32'hfffff800;
        instructions[0]=32'h00000003; instructions[1]=32'h00001003; instructions[2]=32'h00002003;
        instructions[3]=32'h00004003; instructions[4]=32'h00005003; instructions[5]=32'h00000023;
        instructions[6]=32'h00001023; instructions[7]=32'h00002023; instructions[8]=32'h00000067; instructions[9]=32'h00000013;
        for(integer operation=0;operation<10;operation=operation+1) begin
            decode_value=0; decode_value.uses_rs1=1; decode_value.is_load=operation<5;
            decode_value.is_store=operation>=5 && operation<8; decode_value.is_jalr=operation==8;
            instruction=instructions[operation]; carry_zero=0; carry_one=0; aligned=0; misaligned=0;
            for(integer first=0;first<20;first=first+1)
                for(integer second=0;second<20;second=second+1) check_case(edges[first],~edges[first],edges[second]);
            for(integer position=0;position<32;position=position+1) begin
                check_case((32'd1<<position)-1,~((32'd1<<position)-1),1);
                check_case(32'hffffffff,0,32'd1<<position);
            end
            for(integer sample=0;sample<32768;sample=sample+1) begin
                draw_random(random_loaded); draw_random(random_general); draw_random(random_immediate);
                check_case(random_loaded,random_general,random_immediate);
            end
            if(carry_zero==0 || carry_one==0 || aligned==0 || (instruction[13:12]!=0 && misaligned==0))
                $fatal(1,"FAIL load_address_carry16 missing carry/alignment coverage operation=%0d",operation);
            $display("COVER load_address_carry16 operation=%0d carry_zero=%0d carry_one=%0d aligned=%0d misaligned=%0d",operation,carry_zero,carry_one,aligned,misaligned);
        end
        if(checks!=332320) $fatal(1,"FAIL load_address_carry16 incomplete case count");
        $display("PASS load_address_carry16 checks=%0d operations=10",checks);
        $finish;
    end
endmodule
