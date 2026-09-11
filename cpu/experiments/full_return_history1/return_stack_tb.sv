`timescale 1ns/1ps
module return_stack_tb;
    parameter integer DEPTH=2;
    reg clk=0;
    reg rst_n,invalidate,update_valid,update_taken,update_conditional,update_return,stack_push,stack_pop;
    reg [31:0] fetch_pc,update_pc,update_target;
    wire predicted_taken,prediction_hit;
    wire [31:0] predicted_target;
    wire reference_taken,reference_hit;
    wire [31:0] reference_target;
    reg expected_hit;
    reg [31:0] expected_target;
    integer descriptor,fields,checks=0;
    reg [4095:0] vector_path;
    rv32_btb #(.INDEX_BITS(8),.ADDRESS_BITS(16),.RETURN_STACK_DEPTH(DEPTH)) dut (
        .clk(clk),.rst_n(rst_n),.invalidate(invalidate),.fetch_pc(fetch_pc),
        .predicted_taken(predicted_taken),.predicted_target(predicted_target),.prediction_hit(prediction_hit),
        .update_valid(update_valid),.update_pc(update_pc),.update_target(update_target),
        .update_taken(update_taken),.update_conditional(update_conditional),.update_return(update_return),
        .stack_push(stack_push),.stack_pop(stack_pop),.stack_push_address(update_pc+32'd4)
    );
    rv32_btb_reference #(.INDEX_BITS(8),.ADDRESS_BITS(16)) reference_predictor (
        .clk(clk),.rst_n(rst_n),.invalidate(invalidate),.fetch_pc(fetch_pc),
        .predicted_taken(reference_taken),.predicted_target(reference_target),.prediction_hit(reference_hit),
        .update_valid(update_valid),.update_pc(update_pc),.update_target(update_target),
        .update_taken(update_taken),.update_conditional(update_conditional)
    );
    initial begin
        if (!$value$plusargs("vectors=%s",vector_path)) $fatal(1,"Missing vectors");
        descriptor=$fopen(vector_path,"r");
        if (!descriptor) $fatal(1,"Cannot open vectors");
        while (!$feof(descriptor)) begin
            fields=$fscanf(descriptor,"%h %h %h %h %h %h %h %h %h %h %h %h %h %h\n",
                rst_n,invalidate,fetch_pc,update_valid,update_pc,update_target,update_taken,update_conditional,
                update_return,stack_push,stack_pop,expected_hit,expected_target,checks);
            if (fields==14) begin
                #5; clk=1; #5;
                if (prediction_hit!==expected_hit || predicted_target!==expected_target ||
                    prediction_hit!==reference_hit || predicted_taken!==reference_taken)
                    $fatal(1,"FAIL return_stack vector=%0d hit=%b/%b target=%h/%h",checks,prediction_hit,expected_hit,predicted_target,expected_target);
                if (DEPTH==0 && predicted_target!==reference_target)
                    $fatal(1,"FAIL return_stack disabled differs");
                clk=0;
            end else if (fields!=-1) $fatal(1,"Malformed vectors");
        end
        $display("PASS return_stack depth=%0d vectors=%0d",DEPTH,checks+1);
        $finish;
    end
endmodule
