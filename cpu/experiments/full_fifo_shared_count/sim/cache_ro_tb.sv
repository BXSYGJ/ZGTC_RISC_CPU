`timescale 1ns/1ps
module cache_ro_tb;
    cache_tb #(.READONLY(1)) test();
endmodule
