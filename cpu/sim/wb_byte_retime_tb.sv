`timescale 1ns/1ps
module wb_byte_retime_tb;
    reg clk=0,rst_n=1,ex_valid=0,id_fire=0,trace_write=0,mem_fire=0,mem_fault=0;
    reg [4:0] wb_rd=0,id_rs1=0,id_rs2=0;
    reg [31:0] register_a=0,register_b=0,mem_value=0,forwarded_a=0,forwarded_b=0;
    wire [31:0] parent_a,parent_b,parent_wb,candidate_a,candidate_b,candidate_wb;
    wire [2:0] parent_relation,candidate_relation,parent_wb_a,parent_wb_b,candidate_wb_a,candidate_wb_b;
    integer cycles=0,resets=0,sample_index,control_index,field_bit;
    wb_byte_parent parent(.clk(clk),.rst_n(rst_n),.ex_valid(ex_valid),.id_fire(id_fire),.trace_write(trace_write),.mem_fire(mem_fire),.mem_fault(mem_fault),.wb_rd(wb_rd),.id_rs1(id_rs1),.id_rs2(id_rs2),.register_a(register_a),.register_b(register_b),.mem_value(mem_value),.wb_data(parent_wb),.forwarded_a(forwarded_a),.forwarded_b(forwarded_b),.ex_operand_a(parent_a),.ex_operand_b(parent_b),.relation(parent_relation),.wb_a_relation(parent_wb_a),.wb_b_relation(parent_wb_b));
    wb_byte_candidate candidate(.clk(clk),.rst_n(rst_n),.ex_valid(ex_valid),.id_fire(id_fire),.trace_write(trace_write),.mem_fire(mem_fire),.mem_fault(mem_fault),.wb_rd(wb_rd),.id_rs1(id_rs1),.id_rs2(id_rs2),.register_a(register_a),.register_b(register_b),.mem_value(mem_value),.wb_data(candidate_wb),.forwarded_a(forwarded_a),.forwarded_b(forwarded_b),.ex_operand_a(candidate_a),.ex_operand_b(candidate_b),.relation(candidate_relation),.wb_a_relation(candidate_wb_a),.wb_b_relation(candidate_wb_b));
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
            if(parent_a!==candidate_a || parent_b!==candidate_b || parent_wb!==candidate_wb || parent_relation!==candidate_relation || parent_wb_a!==candidate_wb_a || parent_wb_b!==candidate_wb_b)
                $fatal(1,"FAIL wb_byte_retime cycle=%0d controls=%b%b%b%b operands=%h/%h wb=%h expected=%b/%b actual=%b/%b",cycles,id_fire,ex_valid,mem_fire,mem_fault,parent_a,parent_b,parent_wb,parent_wb_a,parent_wb_b,candidate_wb_a,candidate_wb_b);
        end
    endtask
    task automatic reset_state;
        begin
            clk=0; rst_n=0; #1; check_state;
            if(candidate_wb_a!==3'b100 || candidate_wb_b!==3'b100) $fatal(1,"FAIL wb_byte_retime reset");
            rst_n=1; #1; resets=resets+1;
        end
    endtask
    task automatic tick(input id_capture,operand_refresh,wb_capture,wb_fault);
        begin
            clk=0; id_fire=id_capture; ex_valid=operand_refresh; mem_fire=wb_capture; mem_fault=wb_fault;
            mem_value=mem_value^32'h01020408;
            #1; check_state; clk=1; #1; check_state; clk=0;
            cycles=cycles+1;
        end
    endtask
    initial begin
        reset_state;
        for(sample_index=0;sample_index<1024;sample_index=sample_index+1) begin
            register_a=$random; register_b=$random; mem_value=$random;
            forwarded_a=$random; forwarded_b=$random;
            wb_rd=sample_index[4:0]; id_rs1=sample_index[5:1]; id_rs2=sample_index[6:2];
            trace_write=sample_index[0];
            case(sample_index%8)
                0: begin register_b=mem_value; register_a=mem_value; end
                1: begin forwarded_b=mem_value; forwarded_a=mem_value; end
                2: begin register_a=32'h80000000; mem_value=32'h7fffffff; end
                3: begin forwarded_a=0; mem_value=32'hffffffff; end
                4: begin register_b=32'h80000000; mem_value=32'h7fffffff; end
                default: begin end
            endcase
            for(control_index=0;control_index<16;control_index=control_index+1)
                tick(control_index[0],control_index[1],control_index[2],control_index[3]);
        end
        for(sample_index=0;sample_index<256;sample_index=sample_index+1) begin
            if(sample_index%8==0) reset_state;
            register_a=$random; register_b=$random; mem_value=$random;
            forwarded_a=$random; forwarded_b=$random;
            wb_rd=sample_index[4:0]; id_rs1=sample_index[4:0]; id_rs2=~sample_index[4:0];
            trace_write=state_value(sample_index);
            for(field_bit=0;field_bit<4;field_bit=field_bit+1) begin
                register_a[(sample_index+field_bit*5)%32]=state_value(sample_index>>field_bit);
                register_b[(sample_index+field_bit*7)%32]=state_value((sample_index+1)>>field_bit);
                forwarded_a[(sample_index+field_bit*3)%32]=state_value((sample_index+2)>>field_bit);
                forwarded_b[(sample_index+field_bit*9)%32]=state_value((sample_index+3)>>field_bit);
                mem_value[(sample_index+field_bit*11)%32]=state_value((sample_index+7)>>field_bit);
            end
            id_rs2[sample_index%5]=state_value(sample_index>>2);
            for(control_index=0;control_index<256;control_index=control_index+1)
                tick(state_value(control_index),state_value(control_index>>2),state_value(control_index>>4),state_value(control_index>>6));
        end
        if(cycles!=81920 || resets!=33) $fatal(1,"FAIL wb_byte_retime inventory");
        $display("PASS wb_byte_retime cycles=%0d resets=%0d",cycles,resets);
        $finish;
    end
endmodule
