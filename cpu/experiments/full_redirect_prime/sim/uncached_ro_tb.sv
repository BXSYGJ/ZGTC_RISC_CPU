`timescale 1ns/1ps
module uncached_ro_tb;
    uncached_tb #(.READONLY(1)) test_instance();
endmodule
