`timescale 1ns/1ps
module loop_predictor_pending_tb;
    parameter integer INDEX_BITS=8,ADDRESS_BITS=16,HASH_INDEX=1;
    reg clk=0,rst_n=1,invalidate=0,update_valid=0,update_taken=0,update_conditional=0;
    reg [31:0] fetch_pc=0,update_pc=0,update_target=0;
    wire predicted_taken,prediction_hit;
    wire [31:0] predicted_target;
    integer source_file,fields,checks=0;
    reg expected_pre_hit,expected_pre_taken,expected_post_hit,expected_post_taken;
    reg [31:0] expected_pre_target,expected_post_target;
    string vectors;
    rv32_btb #(.INDEX_BITS(INDEX_BITS),.ADDRESS_BITS(ADDRESS_BITS),.HASH_INDEX(HASH_INDEX),.HISTORY_BITS(3),.COUNTER_BITS(2)) dut(.*);
    initial begin
        if(!$value$plusargs("vectors=%s",vectors)) $fatal(1,"Missing vectors");
        source_file=$fopen(vectors,"r");
        if(!source_file) $fatal(1,"Cannot open vectors");
        while(!$feof(source_file)) begin
            fields=$fscanf(source_file,"%h %h %h %h %h %h %h %h %h %h %h %h %h %h\n",rst_n,invalidate,fetch_pc,update_valid,update_pc,update_target,update_taken,update_conditional,expected_pre_hit,expected_pre_taken,expected_pre_target,expected_post_hit,expected_post_taken,expected_post_target);
            if(fields!=14) $fatal(1,"Malformed pending loop vector");
            #1;
            if(prediction_hit!==expected_pre_hit || predicted_taken!==expected_pre_taken || predicted_target!==expected_pre_target)
                $fatal(1,"FAIL pending_loop pre check=%0d pc=%08x hit=%b/%b taken=%b/%b target=%08x/%08x",checks,fetch_pc,prediction_hit,expected_pre_hit,predicted_taken,expected_pre_taken,predicted_target,expected_pre_target);
            clk=1; #1; update_valid=0; #1;
            if(prediction_hit!==expected_post_hit || predicted_taken!==expected_post_taken || predicted_target!==expected_post_target)
                $fatal(1,"FAIL pending_loop post check=%0d pc=%08x hit=%b/%b taken=%b/%b target=%08x/%08x",checks,fetch_pc,prediction_hit,expected_post_hit,predicted_taken,expected_post_taken,predicted_target,expected_post_target);
            clk=0; #1; checks=checks+1;
        end
        $fclose(source_file);
        if(checks<10000) $fatal(1,"Insufficient pending loop vectors");
        $display("PASS pending_loop vectors=%0d queries=%0d",checks,checks*2);
        $finish;
    end
endmodule
