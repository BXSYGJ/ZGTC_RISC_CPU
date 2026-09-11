`timescale 1ns/1ps
module btb_bounded64_tb;
    btb_tb #(.INDEX_BITS(6),.ADDRESS_BITS(16),.TEST_NAME("btb_bounded64")) test_instance();
endmodule
