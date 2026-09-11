`timescale 1ns/1ps
module cache_rw_fast_tb;
    cache_tb #(.READONLY(0),.FAST_READ_HIT(1)) test();
endmodule
