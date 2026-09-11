`timescale 1ns/1ps
module cache_bounds_ro_tb;
    cache_bounds_tb #(.READ_ONLY(1),.TEST_NAME("cache_bounds_ro")) test();
endmodule
