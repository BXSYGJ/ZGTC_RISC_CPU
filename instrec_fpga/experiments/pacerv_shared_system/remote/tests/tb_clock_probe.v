`timescale 1ns/1ps
module GTP_INBUFDS(output O,input I,IB);
    assign O=I;
endmodule
module GTP_CLKBUFG(output CLKOUT,input CLKIN);
    assign CLKOUT=CLKIN;
endmodule
module tb_clock_probe;
    reg clk27=0, ref_clk=0, resetn=0;
    always #18.519 clk27=~clk27;
    always #4 ref_clk=~ref_clk;
    wire tx;
    pg200_clock_probe #(.MEASURE_TICKS(27000),.PRINT_TICKS(60000),.UART_DIV(4)) dut (
        .board_clk27(clk27),.ref_clk_p(ref_clk),.ref_clk_n(!ref_clk),.resetn(resetn),.uart_tx(tx));
    reg [7:0] expected[0:127];
    reg [7:0] value;
    integer accepted=0,received=0,b;
    always @(posedge clk27) if(dut.sending && dut.byte_ready && !dut.tx_accept_hold) begin
        expected[accepted]=dut.byte_data;
        accepted=accepted+1;
    end
    initial begin
        #100; resetn=1;
        #10000000; $fatal(1,"Clock probe timeout");
    end
    initial forever begin
        @(negedge tx);
        #(37.038*6);
        for(b=0;b<8;b=b+1) begin
            value[b]=tx;
            #(37.038*4);
        end
        if(tx!==1 || value!==expected[received])
            $fatal(1,"Clock-probe UART mismatch index=%0d got=%h expected=%h",received,value,expected[received]);
        $write("%c",value);
        received=received+1;
        if(received==26) begin
            if(dut.frame_edges<975 || dut.frame_edges>978)
                $fatal(1,"Clock-probe transition count=%0d",dut.frame_edges);
            $display("CLOCK_PROBE_SIM PASS bytes=26 ref_transitions=%0d",dut.frame_edges);
            $finish;
        end
    end
endmodule
