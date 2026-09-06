`timescale 1ns/1ps
module btb_bounds_tb;
    parameter integer ADDRESS_BITS=16;
    parameter integer INDEX_BITS=6;
    parameter TEST_NAME="btb_bounds";
    localparam [31:0] LIMIT=32'd1<<ADDRESS_BITS;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,invalidate=0,update_valid=0,update_taken=1,update_conditional=0;
    reg [31:0] fetch_pc=0,update_pc=0,update_target=4;
    wire predicted_taken,prediction_hit;
    wire [31:0] predicted_target;
    integer checks=0;
    rv32_btb #(.INDEX_BITS(INDEX_BITS),.ADDRESS_BITS(ADDRESS_BITS)) predictor(.*);
    task automatic check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL btb_bounds %s",label_text);
        end
    endtask
    task automatic train(input [31:0] pc_value,input [31:0] target_value);
        begin
            @(negedge clk); update_valid=1; update_pc=pc_value; update_target=target_value;
            @(posedge clk); #1;
            @(negedge clk); update_valid=0;
        end
    endtask
    task automatic expect_hit(input [31:0] pc_value,input [31:0] target_value,input string label_text);
        begin
            fetch_pc=pc_value; #1;
            check(prediction_hit && predicted_taken && predicted_target==target_value,label_text);
        end
    endtask
    task automatic expect_miss(input [31:0] pc_value,input string label_text);
        begin
            fetch_pc=pc_value; #1;
            check(!prediction_hit && !predicted_taken && predicted_target==pc_value+32'd4,label_text);
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        @(negedge clk); rst_n=1;
        check($bits(predictor.tags[0])==ADDRESS_BITS-INDEX_BITS-2,"bounded PC tag width");
        check($bits(predictor.targets[0])==ADDRESS_BITS-2,"aligned target storage width");
        expect_miss(0,"cold miss");
        train(0,4); train(LIMIT-4,LIMIT-8);
        expect_hit(0,4,"first PC retained");
        expect_hit(LIMIT-4,LIMIT-8,"last aligned target reconstructed");
        for(integer bit_index=ADDRESS_BITS;bit_index<32;bit_index=bit_index+1) begin
            expect_miss(32'd1<<bit_index,"high fetch PC does not alias");
            train(32'd1<<bit_index,128);
            expect_hit(0,4,"high update PC does not replace entry");
            train(0,(32'd1<<bit_index)|32'd8);
            expect_hit(0,4,"high update target does not replace entry");
            train((32'd1<<bit_index)|(LIMIT-4),LIMIT-16);
            expect_hit(LIMIT-4,LIMIT-8,"high update PC preserves boundary entry");
        end
        for(integer bit_index=2;bit_index<ADDRESS_BITS;bit_index=bit_index+1) begin
            train(0,32'd1<<bit_index);
            expect_hit(0,32'd1<<bit_index,"every target address bit retained");
        end
        train(0,0); expect_hit(0,0,"zero target retained");
        train(0,LIMIT-4); expect_hit(0,LIMIT-4,"highest target retained");
        for(integer offset=1;offset<4;offset=offset+1) begin
            train(32'(offset),4);
            expect_hit(0,LIMIT-4,"misaligned update PC ignored");
            train(0,32'(offset));
            expect_hit(0,LIMIT-4,"misaligned update target ignored");
            expect_miss(32'(offset),"misaligned fetch PC ignored");
        end
        expect_miss(32'hfffffffc,"full-width sequential target wraps");
        @(negedge clk); invalidate=1; update_valid=1; update_pc=0; update_target=16;
        @(posedge clk); #1;
        expect_miss(0,"invalidation wins over valid update");
        expect_miss(LIMIT-4,"invalidation clears final entry");
        @(negedge clk); invalidate=0; update_valid=0;
        for(integer entry_index=0;entry_index<(1<<INDEX_BITS);entry_index=entry_index+1)
            train(32'(entry_index)<<2,LIMIT-4-(32'(entry_index)<<2));
        for(integer entry_index=0;entry_index<(1<<INDEX_BITS);entry_index=entry_index+1)
            expect_hit(32'(entry_index)<<2,LIMIT-4-(32'(entry_index)<<2),"all bounded entries retained");
        train(32'd1<<(INDEX_BITS+2),64);
        expect_miss(0,"in-range tag alias replaces old PC");
        expect_hit(32'd1<<(INDEX_BITS+2),64,"in-range tag alias stores new PC");
        @(negedge clk); rst_n=0;
        #1; expect_miss(32'd1<<(INDEX_BITS+2),"reset clears retained entry");
        $display("PASS %s checks=%0d address_bits=%0d index_bits=%0d",TEST_NAME,checks,ADDRESS_BITS,INDEX_BITS);
        $finish;
    end
    initial begin
        #100000; $fatal(1,"BTB bounds watchdog timeout");
    end
endmodule
