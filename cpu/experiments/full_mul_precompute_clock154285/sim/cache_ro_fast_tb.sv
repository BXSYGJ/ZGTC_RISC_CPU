`timescale 1ns/1ps
module cache_ro_fast_tb;
    cache_tb #(.READONLY(1),.FAST_READ_HIT(1)) test();
endmodule
