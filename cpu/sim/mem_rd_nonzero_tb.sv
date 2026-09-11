`timescale 1ns/1ps
module mem_rd_nonzero_tb;
    reg clk=0,rst_n=1,ex_fire=0;
    reg [4:0] ex_rd=0;
    wire [4:0] parent_rd,candidate_rd;
    wire parent_nonzero,candidate_nonzero;
    integer pattern,bit_index,checks=0,resets=0;
    mem_rd_parent parent(clk,rst_n,ex_fire,ex_rd,parent_rd,parent_nonzero);
    mem_rd_candidate candidate(clk,rst_n,ex_fire,ex_rd,candidate_rd,candidate_nonzero);
    function automatic four_state(input integer value);
        case(value&3)
            0: four_state=1'b0;
            1: four_state=1'b1;
            2: four_state=1'bx;
            3: four_state=1'bz;
        endcase
    endfunction
    task check;
        begin
            if(candidate_rd!==parent_rd || candidate_nonzero!==parent_nonzero)
                $fatal(1,"FAIL mem_rd_nonzero input=%b fire=%b parent=%b/%b candidate=%b/%b",ex_rd,ex_fire,parent_rd,parent_nonzero,candidate_rd,candidate_nonzero);
        end
    endtask
    task tick;
        begin
            #1; clk=1; #1; check(); clk=0; #1; checks=checks+1;
        end
    endtask
    task reset_now;
        begin
            rst_n=0; #1; check(); rst_n=1; #1; resets=resets+1;
        end
    endtask
    initial begin
        reset_now();
        for(pattern=0;pattern<1024;pattern=pattern+1) begin
            for(bit_index=0;bit_index<5;bit_index=bit_index+1) ex_rd[bit_index]=four_state(pattern>>(bit_index*2));
            ex_fire=1; tick();
            ex_rd=~ex_rd; ex_fire=0; tick();
            ex_rd=pattern[4:0]; ex_fire=1'bx; tick();
            ex_rd=~pattern[4:0]; ex_fire=1'bz; tick();
            if(pattern%31==0) reset_now();
        end
        $display("PASS mem_rd_nonzero cycles=%0d resets=%0d four_state_destinations=1024",checks,resets);
        $finish;
    end
endmodule
