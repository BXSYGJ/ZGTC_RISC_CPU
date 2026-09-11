`timescale 1ns/1ps
module wb_rd_nonzero_tb;
    reg clk=0,rst_n=1,mem_fire=0,mem_fault=0;
    reg [4:0] mem_rd=0;
    wire [4:0] parent_rd,candidate_rd;
    wire parent_nonzero,candidate_nonzero;
    integer pattern,bit_index,control_code,checks=0,resets=0;
    wb_rd_parent parent(clk,rst_n,mem_fire,mem_fault,mem_rd,parent_rd,parent_nonzero);
    wb_rd_candidate candidate(clk,rst_n,mem_fire,mem_fault,mem_rd,candidate_rd,candidate_nonzero);
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
                $fatal(1,"FAIL wb_rd_nonzero input=%b fire=%b parent=%b/%b candidate=%b/%b",mem_rd,mem_fire,parent_rd,parent_nonzero,candidate_rd,candidate_nonzero);
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
            for(bit_index=0;bit_index<5;bit_index=bit_index+1) mem_rd[bit_index]=four_state(pattern>>(bit_index*2));
            mem_fire=1; mem_fault=0; tick();
            for(control_code=0;control_code<16;control_code=control_code+1) begin
                for(bit_index=0;bit_index<5;bit_index=bit_index+1) mem_rd[bit_index]=four_state((pattern>>(bit_index*2))^(control_code^(control_code>>2)));
                mem_fire=four_state(control_code); mem_fault=four_state(control_code>>2); tick();
            end
            if(pattern%31==0) reset_now();
        end
        $display("PASS wb_rd_nonzero cycles=%0d resets=%0d four_state_destinations=1024 four_state_controls=16",checks,resets);
        $finish;
    end
endmodule
