`timescale 1ns/1ps
module cache_write_fast_tb;
    cache_tb #(.ADDRESS_BITS(10),.FAST_WRITE_HIT(1),.FAST_READ_HIT(0),.READ_OVERLAP(0),.READONLY(0),.TEST_NAME("cache_write_fast")) test_instance();
endmodule
