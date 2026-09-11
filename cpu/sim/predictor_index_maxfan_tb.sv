`timescale 1ns/1ps
module predictor_index_maxfan_tb;
    reg clk=0,rst_n=1,invalidate=0,update_valid=0,update_taken=0,update_conditional=0;
    reg [31:0] fetch_pc=0,update_pc=0,update_target=0;
    wire parent_taken,candidate_taken,parent_hit,candidate_hit;
    wire [31:0] parent_target,candidate_target;
    integer sample_index,control_index,cycles=0,resets=0;
    predictor_parent #(.INDEX_BITS(8),.ADDRESS_BITS(16),.HISTORY_BITS(3)) parent(.clk(clk),.rst_n(rst_n),.invalidate(invalidate),.fetch_pc(fetch_pc),.predicted_taken(parent_taken),.predicted_target(parent_target),.prediction_hit(parent_hit),.update_valid(update_valid),.update_pc(update_pc),.update_target(update_target),.update_taken(update_taken),.update_conditional(update_conditional));
    rv32_btb #(.INDEX_BITS(8),.ADDRESS_BITS(16),.HISTORY_BITS(3)) candidate(.clk(clk),.rst_n(rst_n),.invalidate(invalidate),.fetch_pc(fetch_pc),.predicted_taken(candidate_taken),.predicted_target(candidate_target),.prediction_hit(candidate_hit),.update_valid(update_valid),.update_pc(update_pc),.update_target(update_target),.update_taken(update_taken),.update_conditional(update_conditional));
    function automatic state_value(input integer digit);
        case(digit&3)
            0: state_value=1'b0;
            1: state_value=1'b1;
            2: state_value=1'bx;
            default: state_value=1'bz;
        endcase
    endfunction
    task automatic check_outputs;
        begin
            if(parent_taken!==candidate_taken || parent_hit!==candidate_hit || parent_target!==candidate_target)
                $fatal(1,"FAIL predictor index pair cycle=%0d fetch=%h",cycles,fetch_pc);
        end
    endtask
    task automatic reset_state;
        begin
            clk=0; rst_n=0; #1; check_outputs; rst_n=1; #1; resets=resets+1;
        end
    endtask
    task automatic tick;
        begin
            clk=0; #1; check_outputs; clk=1; #1; check_outputs; clk=0; cycles=cycles+1;
        end
    endtask
    initial begin
        reset_state;
        for(sample_index=0;sample_index<16384;sample_index=sample_index+1) begin
            update_pc=($random&32'h0000fffc); update_target=($random&32'h0000fffc);
            fetch_pc=sample_index%2==0 ? update_pc : ($random&32'h0001ffff);
            update_valid=sample_index%7!=0; update_taken=sample_index[0]; update_conditional=sample_index%5!=0; invalidate=sample_index%113==0;
            tick;
        end
        for(sample_index=0;sample_index<1024;sample_index=sample_index+1) begin
            if(sample_index%64==0) reset_state;
            update_pc=($random&32'h0000fffc); update_target=($random&32'h0000fffc); fetch_pc=update_pc;
            fetch_pc[sample_index%32]=state_value(sample_index);
            update_taken=state_value(sample_index>>2); update_conditional=state_value(sample_index>>4);
            if(sample_index%3==0) update_pc[sample_index%32]=state_value(sample_index>>6);
            if(sample_index%5==0) update_target[sample_index%32]=state_value(sample_index>>8);
            for(control_index=0;control_index<16;control_index=control_index+1) begin
                invalidate=state_value(control_index); update_valid=state_value(control_index>>2); tick;
            end
        end
        if(cycles!=32768 || resets!=17) $fatal(1,"FAIL predictor index pair inventory");
        $display("PASS predictor index pair cycles=%0d resets=%0d",cycles,resets);
        $finish;
    end
endmodule
