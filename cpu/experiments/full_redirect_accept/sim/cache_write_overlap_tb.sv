`timescale 1ns/1ps
module cache_write_overlap_tb;
    cache_tb #(.ADDRESS_BITS(10),.FAST_WRITE_HIT(1),.FAST_READ_HIT(1),.READ_OVERLAP(1),.READONLY(0),.TEST_NAME("cache_write_overlap")) test_instance();
endmodule
