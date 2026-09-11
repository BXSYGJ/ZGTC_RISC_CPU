`timescale 1ns/1ps
module cache_bounded_rw_tb;
    cache_tb #(.ADDRESS_BITS(10),.FAST_READ_HIT(1),.READ_OVERLAP(1),.TEST_NAME("cache_bounded_rw")) test();
endmodule
