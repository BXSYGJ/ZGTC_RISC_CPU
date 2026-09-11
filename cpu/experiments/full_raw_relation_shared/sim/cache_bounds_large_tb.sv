`timescale 1ns/1ps
module cache_bounds_large_tb;
    cache_bounds_tb #(.ADDRESS_BITS(16),.SET_BITS(6),.TEST_NAME("cache_bounds_large")) test();
endmodule
