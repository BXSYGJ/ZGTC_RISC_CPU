`timescale 1ns/1ps
module forward_select_maxfan_tb;
    reg [7:0] controls;
    reg [4:0] ex_rs1,ex_rs2,mem_rd,wb_rd;
    reg [31:0] ex_operand_a,ex_operand_b,mem_result,mem_value,wb_data;

    wire [31:0] parent_a[0:1],parent_b[0:1],candidate_a[0:1],candidate_b[0:1];
    integer iteration,lane,checks=0;
    genvar bubble;
    generate for(bubble=0;bubble<2;bubble=bubble+1) begin: configurations
        forward_parent #(.LOAD_USE_BUBBLE(bubble)) parent(
            controls,ex_rs1,ex_rs2,mem_rd,wb_rd,ex_operand_a,ex_operand_b,mem_result,mem_value,wb_data,parent_a[bubble],parent_b[bubble]);
        forward_candidate #(.LOAD_USE_BUBBLE(bubble)) candidate(
            controls,ex_rs1,ex_rs2,mem_rd,wb_rd,ex_operand_a,ex_operand_b,mem_result,mem_value,wb_data,candidate_a[bubble],candidate_b[bubble]);
    end endgenerate
    function automatic state_bit(input integer value);
        case(value & 3)
            0: state_bit=1'b0;
            1: state_bit=1'b1;
            2: state_bit=1'bx;
            3: state_bit=1'bz;
        endcase
    endfunction
    task check;
        begin
            #1;
            for(integer mode=0;mode<2;mode=mode+1) begin
                if(candidate_a[mode]!==parent_a[mode] || candidate_b[mode]!==parent_b[mode])
                    $fatal(1,"FAIL forward_select mode=%0d controls=%b rs1=%b rs2=%b mem=%b wb=%b",mode,controls,ex_rs1,ex_rs2,mem_rd,wb_rd);
                checks=checks+1;
            end
        end
    endtask
    initial begin
        ex_operand_a=32'h13579bdf; ex_operand_b=32'h2468ace0;
        mem_result=32'hz0xx1122; mem_value=32'h33zz44xx; wb_data=32'habcdef01;
        for(iteration=0;iteration<65536;iteration=iteration+1) begin
            for(lane=0;lane<8;lane=lane+1) controls[lane]=state_bit(iteration>>(2*lane));
            ex_rs1=5'd7; ex_rs2=5'd7; mem_rd=5'd7; wb_rd=5'd7; check();
        end
        for(iteration=0;iteration<16384;iteration=iteration+1) begin
            controls=iteration[7:0];
            mem_rd=iteration[12:8]; wb_rd=iteration[13:9];
            ex_rs1=iteration[1] ? mem_rd : wb_rd;
            ex_rs2=iteration[2] ? mem_rd : wb_rd;
            if(iteration[3]) ex_rs1[2]=state_bit(iteration>>4);
            if(iteration[6]) ex_rs2[4]=state_bit(iteration>>7);
            if(iteration[8]) mem_rd[1]=state_bit(iteration>>9);
            if(iteration[11]) wb_rd[3]=state_bit(iteration>>12);
            check();
        end
        controls=8'hbf;
        for(iteration=0;iteration<32;iteration=iteration+1) begin
            ex_rs1=iteration; ex_rs2=iteration; mem_rd=iteration; wb_rd=iteration; check();
        end
        controls=8'haf;
        for(iteration=0;iteration<1024;iteration=iteration+1) begin
            mem_rd=iteration[4:0]; wb_rd=iteration[9:5];
            ex_rs1=mem_rd; ex_rs2=wb_rd; check();
            ex_rs1=wb_rd; ex_rs2=mem_rd; check();
        end
        $display("PASS forward_select checks=%0d",checks);
        $finish;
    end
endmodule
