`timescale 1ns/1ps
module shared_relation_tb;
    reg clk=0,rst_n=0;
    reg ex_valid=0,id_fire=0,mem_fire=0,mem_fault=0;
    reg [31:0] forwarded_a=0,forwarded_b=0,id_operand_a=0,id_operand_b=0,wb_data=0,mem_value=0;
    wire [31:0] reference_a,reference_b,candidate_a,candidate_b;
    wire [2:0] reference_relation,candidate_relation;
    integer cycle_index,random_seed=32'h34ed8291,reset_count=0;
    integer both_fire=0,id_only=0,ex_only=0,hold_count=0,unknown_count=0;
    always #5 clk=~clk;
    reference reference_dut(.clk(clk),.rst_n(rst_n),.ex_valid(ex_valid),.id_fire(id_fire),.mem_fire(mem_fire),.mem_fault(mem_fault),
        .forwarded_a(forwarded_a),.forwarded_b(forwarded_b),.id_operand_a(id_operand_a),.id_operand_b(id_operand_b),.wb_data(wb_data),.mem_value(mem_value),
        .ex_operand_a(reference_a),.ex_operand_b(reference_b),.raw_pair_relation(reference_relation));
    candidate candidate_dut(.clk(clk),.rst_n(rst_n),.ex_valid(ex_valid),.id_fire(id_fire),.mem_fire(mem_fire),.mem_fault(mem_fault),
        .forwarded_a(forwarded_a),.forwarded_b(forwarded_b),.id_operand_a(id_operand_a),.id_operand_b(id_operand_b),.wb_data(wb_data),.mem_value(mem_value),
        .ex_operand_a(candidate_a),.ex_operand_b(candidate_b),.raw_pair_relation(candidate_relation));
    function automatic control_value(input integer choice);
        case(choice & 3)
            0: control_value=0;
            1: control_value=1;
            2: control_value=1'bx;
            3: control_value=1'bz;
        endcase
    endfunction
    task check;
        begin
            if({reference_a,reference_b,reference_relation} !== {candidate_a,candidate_b,candidate_relation})
                $fatal(1,"RELATION_MISMATCH cycle=%0d reference=%b candidate=%b",cycle_index,reference_relation,candidate_relation);
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0; #1; check();
        for(cycle_index=0;cycle_index<32768;cycle_index=cycle_index+1) begin
            @(negedge clk);
            rst_n=(cycle_index%2048)!=0;
            if(!rst_n) reset_count=reset_count+1;
            ex_valid=control_value(cycle_index);
            id_fire=control_value(cycle_index>>2);
            mem_fire=control_value(cycle_index>>4);
            mem_fault=control_value(cycle_index>>6);
            forwarded_a=$random(random_seed); forwarded_b=$random(random_seed);
            id_operand_a=$random(random_seed); id_operand_b=$random(random_seed);
            wb_data=$random(random_seed); mem_value=$random(random_seed);
            case((cycle_index>>4)%8)
                0: begin forwarded_b=forwarded_a; id_operand_b=id_operand_a; end
                1: begin forwarded_a=32'h80000000; forwarded_b=32'h7fffffff; id_operand_a=0; id_operand_b=32'hffffffff; end
                2: begin forwarded_a[7:0]=8'hxx; id_operand_b[31]=1'bx; end
                3: begin forwarded_b[23:16]=8'hzz; id_operand_a[15:8]=8'hxx; end
                4: begin forwarded_a[31:24]=8'hfe; forwarded_b[31:24]=0; forwarded_a[7:0]=8'hxx; id_operand_a=0; id_operand_b=1; end
                5: begin forwarded_a=0; forwarded_b=32'hzzzzzzzz; id_operand_a=32'hxxxxxxxx; id_operand_b=0; end
                default: begin end
            endcase
            if(ex_valid===1'b1 && id_fire===1'b1) both_fire=both_fire+1;
            else if(ex_valid===1'b0 && id_fire===1'b1) id_only=id_only+1;
            else if(ex_valid===1'b1 && id_fire===1'b0) ex_only=ex_only+1;
            else if(ex_valid===1'b0 && id_fire===1'b0) hold_count=hold_count+1;
            else unknown_count=unknown_count+1;
            @(posedge clk); #1; check();
        end
        if(both_fire==0 || id_only==0 || ex_only==0 || hold_count==0 || unknown_count==0 || reset_count!=16)
            $fatal(1,"Coverage incomplete");
        $display("PASS shared_relation cycles=%0d resets=%0d both=%0d id=%0d ex=%0d hold=%0d unknown=%0d",cycle_index,reset_count,both_fire,id_only,ex_only,hold_count,unknown_count);
        $finish;
    end
endmodule
