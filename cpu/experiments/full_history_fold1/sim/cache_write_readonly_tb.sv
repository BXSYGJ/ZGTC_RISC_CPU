`timescale 1ns/1ps
module cache_write_readonly_tb;
    cache_tb #(.ADDRESS_BITS(10),.FAST_WRITE_HIT(1),.FAST_READ_HIT(1),.READ_OVERLAP(1),.READONLY(1),.TEST_NAME("cache_write_readonly")) test_instance();
endmodule
