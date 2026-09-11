`timescale 1ns/1ps
module pll_tb;
    parameter integer CLOCK_HZ=54000000;
    reg reference_clk=0,reset=0;
    wire cpu_clk,locked;
    always #(500000000.0/27000000.0) reference_clk=~reference_clk;
    rv32_pll #(.CLOCK_HZ(CLOCK_HZ)) dut(.*);
    initial begin : measure
        realtime first_edge,last_edge,expected_span,error_span;
        #1; reset=1;
        #200; reset=0;
        wait(locked===1);
        repeat(10) @(posedge cpu_clk);
        first_edge=$realtime;
        repeat(200) @(posedge cpu_clk);
        last_edge=$realtime;
        expected_span=200000000000.0/CLOCK_HZ;
        error_span=last_edge-first_edge-expected_span;
        if(error_span<0) error_span=-error_span;
        if(error_span>expected_span*0.0002) $fatal(1,"PLL frequency mismatch %0d span=%f",CLOCK_HZ,last_edge-first_edge);
        reset=1;
        #200;
        if(locked!==0) $fatal(1,"PLL reset did not clear lock");
        reset=0;
        wait(locked===1);
        repeat(20) @(posedge cpu_clk);
        $display("PASS PLL clock_hz=%0d span_ns=%f reset_relock=1",CLOCK_HZ,last_edge-first_edge);
        $finish;
    end
    initial begin #1000000; $fatal(1,"PLL lock timeout"); end
endmodule
