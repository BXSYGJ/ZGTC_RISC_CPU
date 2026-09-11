`timescale 1ns/1ps
module btb_local_history_tb;
    parameter integer INDEX_BITS=8,ADDRESS_BITS=16,HASH_INDEX=1;
    reg clk=0,rst_n=0,invalidate=0,update_valid=0,update_taken=0,update_conditional=0;
    reg [31:0] fetch_pc=0,update_pc=0,update_target=0;
    wire predicted_taken,prediction_hit;
    wire [31:0] predicted_target;
    integer source_file,fields,checks=0;
    reg expected_hit,expected_taken;
    reg [31:0] expected_target;
    string vectors;
    rv32_btb #(.INDEX_BITS(INDEX_BITS),.ADDRESS_BITS(ADDRESS_BITS),.HASH_INDEX(HASH_INDEX)) dut(.*);
    initial begin
        if(!$value$plusargs("vectors=%s",vectors)) $fatal(1,"Missing vectors");
        source_file=$fopen(vectors,"r");
        if(!source_file) $fatal(1,"Cannot open vectors");
        while(!$feof(source_file)) begin
            fields=$fscanf(source_file,"%h %h %h %h %h %h %h %h %h %h %h\n",rst_n,invalidate,fetch_pc,update_valid,update_pc,update_target,update_taken,update_conditional,expected_hit,expected_taken,expected_target);
            if(fields!=11) $fatal(1,"Malformed local history vector");
            #1; clk=1; #1; clk=0; #1;
            if(prediction_hit!==expected_hit || predicted_taken!==expected_taken || predicted_target!==expected_target)
                $fatal(1,"FAIL local_history check=%0d pc=%08x hit=%b/%b taken=%b/%b target=%08x/%08x",checks,fetch_pc,prediction_hit,expected_hit,predicted_taken,expected_taken,predicted_target,expected_target);
            checks=checks+1;
        end
        $fclose(source_file);
        if(checks<2000) $fatal(1,"Insufficient local history vectors");
        $display("PASS local_history vectors=%0d",checks);
        $finish;
    end
endmodule
