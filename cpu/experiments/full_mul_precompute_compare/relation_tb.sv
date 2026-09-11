`timescale 1ns/1ps
module relation_tb;
    reg clk=0,rst_n=0,ex_valid=0,id_fire=0,mem_fire=0,mem_fault=0;
    always #5 clk=~clk;
    reg [31:0] ex_operand_a=0,ex_operand_b=0,forwarded_a=0,forwarded_b=0;
    reg [31:0] id_operand_a=0,id_operand_b=0,wb_data=0,mem_value=0;
    wire [15:0] reference_result,candidate_result;
    baseline reference_unit(.result(reference_result),.*);
    candidate candidate_unit(.result(candidate_result),.*);
    integer trial;
    initial begin
        for(trial=0;trial<32768;trial=trial+1) begin
            @(negedge clk);
            rst_n=trial%1024!=0;
            {ex_valid,id_fire,mem_fire,mem_fault}=$random;
            ex_operand_a=$random; ex_operand_b=$random; forwarded_a=$random; forwarded_b=$random;
            id_operand_a=$random; id_operand_b=$random; wb_data=$random; mem_value=$random;
            if(trial%3==0) begin id_operand_a=wb_data; forwarded_b=mem_value; end
            if(trial%5==0) begin ex_operand_a=32'hffffffff; id_operand_b=0; end
            if(trial%8==0) id_fire=1'bx;
            if(trial%8==1) ex_valid=1'bz;
            if(trial%8==2) mem_fire=1'bx;
            if(trial%8==3) mem_fault=1'bz;
            if(trial%11==0) begin id_operand_a[15:8]=8'hxx; mem_value[31:24]=8'hzz; end
            @(posedge clk); #1;
            if(reference_result!==candidate_result) $fatal(1,"FAIL relation trial=%0d expected=%04x actual=%04x",trial,reference_result,candidate_result);
        end
        $display("PASS WB relation checks=%0d",trial); $finish;
    end
endmodule

