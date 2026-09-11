`timescale 1ns/1ps
module btb_bounded128_tb;
    btb_tb #(.INDEX_BITS(7),.ADDRESS_BITS(16),.TEST_NAME("btb_bounded128")) test_instance();
endmodule
