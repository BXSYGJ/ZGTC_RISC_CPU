`timescale 1ns/1ps
module cache_bounds_registered_tb;
    cache_bounds_tb #(.FAST_READ_HIT(0),.READ_OVERLAP(0),.TEST_NAME("cache_bounds_registered")) test();
endmodule
