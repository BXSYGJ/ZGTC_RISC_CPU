`timescale 1ns/1ps
module return_metadata_tb;
    parameter integer INDEX_BITS=4;
    parameter integer HISTORY_BITS=3;
    parameter integer STACK_DEPTH=1;
    localparam integer ENTRIES=1<<INDEX_BITS;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,invalidate=0,update_valid=0,update_taken=0,update_conditional=0,update_return=0;
    reg stack_push=0,stack_pop=0;
    reg [31:0] fetch_pc=0,update_pc=0,update_target=0,stack_push_address=0;
    wire candidate_taken,reference_taken,candidate_hit,reference_hit;
    wire [31:0] candidate_target,reference_target;
    reg [31:0] random_state=32'he315790b;
    integer cycle_index,entry_index,checks=0,conditional_checks=0,return_checks=0,unconditional_checks=0;
    rv32_btb #(.INDEX_BITS(INDEX_BITS),.HISTORY_BITS(HISTORY_BITS),.RETURN_STACK_DEPTH(STACK_DEPTH)) candidate (
        .clk(clk),.rst_n(rst_n),.invalidate(invalidate),.fetch_pc(fetch_pc),
        .predicted_taken(candidate_taken),.predicted_target(candidate_target),.prediction_hit(candidate_hit),
        .update_valid(update_valid),.update_pc(update_pc),.update_target(update_target),.update_taken(update_taken),
        .update_conditional(update_conditional),.update_return(update_return),
        .stack_push(stack_push),.stack_pop(stack_pop),.stack_push_address(stack_push_address)
    );
    rv32_btb_reference #(.INDEX_BITS(INDEX_BITS),.HISTORY_BITS(HISTORY_BITS),.RETURN_STACK_DEPTH(STACK_DEPTH)) reference (
        .clk(clk),.rst_n(rst_n),.invalidate(invalidate),.fetch_pc(fetch_pc),
        .predicted_taken(reference_taken),.predicted_target(reference_target),.prediction_hit(reference_hit),
        .update_valid(update_valid),.update_pc(update_pc),.update_target(update_target),.update_taken(update_taken),
        .update_conditional(update_conditional),.update_return(update_return),
        .stack_push(stack_push),.stack_pop(stack_pop),.stack_push_address(stack_push_address)
    );
    task random_next;
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
        end
    endtask
    task compare_outputs;
        begin
            if({candidate_hit,candidate_taken,candidate_target}!=={reference_hit,reference_taken,reference_target})
                $fatal(1,"FAIL metadata output cycle=%0d",cycle_index);
            checks=checks+1;
            if(candidate_hit && !reference.conditional[reference.fetch_index] && reference.return_entry[reference.fetch_index] && reference.stack_available)
                return_checks=return_checks+1;
        end
    endtask
    initial begin
        #11; rst_n=1;
        for(cycle_index=0;cycle_index<12000;cycle_index=cycle_index+1) begin
            @(negedge clk);
            random_next();
            rst_n=cycle_index!=4000 && cycle_index!=8000;
            invalidate=random_state[6:0]==0;
            update_valid=random_state[0] || random_state[1];
            update_conditional=random_state[2];
            update_return=random_state[3];
            update_taken=random_state[4];
            stack_push=random_state[5];
            stack_pop=random_state[6];
            random_next();
            update_pc={18'd0,random_state[11:0],2'b00};
            update_target={18'd0,random_state[23:12],2'b00};
            random_next();
            stack_push_address={random_state[31:2],2'b00};
            fetch_pc={18'd0,random_state[11:0],2'b00};
            if(cycle_index%4==0) fetch_pc=update_pc;
            if(cycle_index%8<4) begin
                update_pc=32'h80;
                fetch_pc=update_pc;
                update_valid=1;
                update_conditional=cycle_index%8==2;
                update_return=cycle_index%8==1;
            end
            if(cycle_index%31==0) update_pc=update_pc|32'd2;
            if(cycle_index%37==0) fetch_pc=fetch_pc|32'd2;
            #1; compare_outputs();
            @(posedge clk); #1; compare_outputs();
            if(candidate.valid!==reference.valid) $fatal(1,"FAIL metadata valid");
            for(entry_index=0;entry_index<ENTRIES;entry_index=entry_index+1) begin
                if(reference.valid[entry_index]) begin
                    if(candidate.tags[entry_index]!==reference.tags[entry_index] || candidate.targets[entry_index]!==reference.targets[entry_index] || candidate.conditional[entry_index]!==reference.conditional[entry_index])
                        $fatal(1,"FAIL metadata entry");
                    if(reference.conditional[entry_index]) begin
                        if(candidate.history[entry_index]!==reference.history[entry_index]) $fatal(1,"FAIL metadata conditional history");
                        conditional_checks=conditional_checks+1;
                    end else begin
                        if(candidate.history[entry_index][0]!==reference.return_entry[entry_index] || (candidate.history[entry_index]>>1)!==0)
                            $fatal(1,"FAIL metadata return encoding");
                        unconditional_checks=unconditional_checks+1;
                    end
                end
            end
        end
        if(checks!=24000 || conditional_checks==0 || unconditional_checks==0 || (STACK_DEPTH>0 && return_checks==0))
            $fatal(1,"FAIL metadata insufficient coverage");
        $display("PASS metadata index=%0d history=%0d depth=%0d outputs=%0d conditional=%0d unconditional=%0d returns=%0d",INDEX_BITS,HISTORY_BITS,STACK_DEPTH,checks,conditional_checks,unconditional_checks,return_checks);
        $finish;
    end
endmodule
