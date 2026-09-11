`timescale 1ns/1ps
module memory_overlap_registered_tb;
    memory_overlap_tb #(.FAST_DCACHE_READ(0),.TEST_NAME("memory_overlap_registered")) test();
endmodule
