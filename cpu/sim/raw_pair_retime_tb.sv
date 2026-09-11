`timescale 1ns/1ps
module raw_pair_retime_tb;
    reg clk=0,rst_n=1,ex_valid=0,id_fire=0,trace_write=0;
    reg [4:0] wb_rd=0,id_rs1=0,id_rs2=0;
    reg [31:0] register_a=0,register_b=0,wb_data=0,forwarded_a=0,forwarded_b=0;
    wire [31:0] parent_a,parent_b,candidate_a,candidate_b;
    wire [2:0] parent_relation,candidate_relation;
    integer cycles=0,resets=0,sample_index,control_index,field_bit;
    raw_pair_parent parent(.clk(clk),.rst_n(rst_n),.ex_valid(ex_valid),.id_fire(id_fire),.trace_write(trace_write),.wb_rd(wb_rd),.id_rs1(id_rs1),.id_rs2(id_rs2),.register_a(register_a),.register_b(register_b),.wb_data(wb_data),.forwarded_a(forwarded_a),.forwarded_b(forwarded_b),.ex_operand_a(parent_a),.ex_operand_b(parent_b),.relation(parent_relation));
    raw_pair_candidate candidate(.clk(clk),.rst_n(rst_n),.ex_valid(ex_valid),.id_fire(id_fire),.trace_write(trace_write),.wb_rd(wb_rd),.id_rs1(id_rs1),.id_rs2(id_rs2),.register_a(register_a),.register_b(register_b),.wb_data(wb_data),.forwarded_a(forwarded_a),.forwarded_b(forwarded_b),.ex_operand_a(candidate_a),.ex_operand_b(candidate_b),.relation(candidate_relation));
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
            if(parent_a!==candidate_a || parent_b!==candidate_b || parent_relation!==candidate_relation)
                $fatal(1,"FAIL raw_pair_retime cycle=%0d id=%b valid=%b operands=%h/%h expected=%b actual=%b",cycles,id_fire,ex_valid,parent_a,parent_b,parent_relation,candidate_relation);
        end
    endtask
    task automatic reset_state;
        begin
            clk=0; rst_n=0; #1; check_state;
            if(candidate_relation!==3'b100) $fatal(1,"FAIL raw_pair_retime reset");
            rst_n=1; #1; resets=resets+1;
        end
    endtask
    task automatic tick(input id_capture,operand_refresh);
        begin
            clk=0; id_fire=id_capture; ex_valid=operand_refresh;
            #1; check_state; clk=1; #1; check_state; clk=0;
            cycles=cycles+1;
        end
    endtask
    initial begin
        reset_state;
        for(sample_index=0;sample_index<4096;sample_index=sample_index+1) begin
            register_a=$random; register_b=$random; wb_data=$random;
            forwarded_a=$random; forwarded_b=$random;
            wb_rd=sample_index[4:0]; id_rs1=sample_index[5:1]; id_rs2=sample_index[6:2];
            trace_write=sample_index[0];
            case(sample_index%8)
                0: register_b=register_a;
                1: forwarded_b=forwarded_a;
                2: begin register_a=32'h80000000; register_b=32'h7fffffff; end
                3: begin forwarded_a=0; forwarded_b=32'hffffffff; end
                default: begin end
            endcase
            for(control_index=0;control_index<4;control_index=control_index+1)
                tick(control_index[0],control_index[1]);
        end
        for(sample_index=0;sample_index<1024;sample_index=sample_index+1) begin
            if(sample_index%64==0) reset_state;
            register_a=$random; register_b=$random; wb_data=$random;
            forwarded_a=$random; forwarded_b=$random;
            wb_rd=sample_index[4:0]; id_rs1=sample_index[4:0]; id_rs2=~sample_index[4:0];
            trace_write=state_value(sample_index);
            for(field_bit=0;field_bit<4;field_bit=field_bit+1) begin
                register_a[(sample_index+field_bit*5)%32]=state_value(sample_index>>field_bit);
                register_b[(sample_index+field_bit*7)%32]=state_value((sample_index+1)>>field_bit);
                forwarded_a[(sample_index+field_bit*3)%32]=state_value((sample_index+2)>>field_bit);
                forwarded_b[(sample_index+field_bit*9)%32]=state_value((sample_index+3)>>field_bit);
                wb_data[(sample_index+field_bit*11)%32]=state_value((sample_index+7)>>field_bit);
            end
            id_rs2[sample_index%5]=state_value(sample_index>>2);
            for(control_index=0;control_index<16;control_index=control_index+1)
                tick(state_value(control_index),state_value(control_index>>2));
        end
        if(cycles!=32768 || resets!=17) $fatal(1,"FAIL raw_pair_retime inventory");
        $display("PASS raw_pair_retime cycles=%0d resets=%0d",cycles,resets);
        $finish;
    end
endmodule
