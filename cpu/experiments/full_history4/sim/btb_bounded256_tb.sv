`timescale 1ns/1ps
module btb_bounded256_tb;
    btb_tb #(.INDEX_BITS(8),.ADDRESS_BITS(16),.TEST_NAME("btb_bounded256")) test_instance();
endmodule
