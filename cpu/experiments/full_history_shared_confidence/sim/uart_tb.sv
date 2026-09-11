`timescale 1ns/1ps
module uart_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,tx_valid=0,rx_ready=1,loopback=1,manual_rx=1;
    reg [7:0] tx_data=0;
    wire serial_tx,tx_ready,tx_busy,rx_valid,framing_error,overrun_error;
    wire [7:0] rx_data;
    wire serial_rx=loopback ? serial_tx : manual_rx;
    integer checks=0,queued=0,transmitted=0,received=0,frame_errors=0,overruns=0;
    reg [7:0] expected[0:255];
    rv32_uart #(.CLOCK_HZ(3200),.BAUD(100)) uart(.*);
    task automatic check(input bit condition,input string label_text);
        begin checks=checks+1; if(!condition) $fatal(1,"FAIL UART %s rx=%02x",label_text,rx_data); end
    endtask
    task send_tx(input [7:0] value);
        begin
            @(negedge clk); expected[queued]=value; queued=queued+1; tx_data=value; tx_valid=1;
            @(posedge clk); while(!tx_ready) @(posedge clk);
            @(negedge clk); tx_valid=0;
        end
    endtask
    task send_rx(input [7:0] value,input integer bit_cycles,input bit good_stop);
        begin
            @(negedge clk); manual_rx=0;
            repeat(bit_cycles) @(negedge clk);
            for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin
                manual_rx=value[bit_index]; repeat(bit_cycles) @(negedge clk);
            end
            manual_rx=good_stop; repeat(bit_cycles) @(negedge clk);
            manual_rx=1; repeat(32) @(negedge clk);
        end
    endtask
    always @(posedge clk) begin
        if(rst_n) begin
            if(framing_error) frame_errors=frame_errors+1;
            if(overrun_error) overruns=overruns+1;
            if(loopback && rx_valid && rx_ready) begin
                check(received<queued && rx_data===expected[received],"loopback byte"); received=received+1;
            end
        end
    end
    initial begin : transmitter_monitor
        reg [7:0] observed;
        forever begin
            @(negedge serial_tx);
            if(rst_n) begin
                #160; check(serial_tx===0,"TX start midpoint");
                for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin #320; observed[bit_index]=serial_tx; end
                #320; check(serial_tx===1,"TX stop midpoint");
                check(transmitted<queued && observed===expected[transmitted],"TX 8N1 wire decoding");
                transmitted=transmitted+1;
            end
        end
    end
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
        for(integer value=0;value<256;value=value+1) send_tx(8'(value));
        wait(!tx_busy && received==256 && transmitted==256);
        @(negedge clk); loopback=0; rx_ready=0;
        send_rx(8'h55,32,1);
        check(rx_valid && rx_data==8'h55,"RX holds unread byte");
        send_rx(8'haa,32,1);
        check(rx_valid && rx_data==8'h55 && overruns==1,"overrun preserves unread byte");
        @(negedge clk); rx_ready=1;
        repeat(2) @(negedge clk); rx_ready=0;
        send_rx(8'h81,33,1);
        check(rx_valid && rx_data==8'h81,"slower incoming baud");
        @(negedge clk); rx_ready=1;
        repeat(2) @(negedge clk); rx_ready=0;
        send_rx(8'h7e,31,1);
        check(rx_valid && rx_data==8'h7e,"faster incoming baud");
        @(negedge clk); rx_ready=1;
        repeat(2) @(negedge clk); rx_ready=0;
        send_rx(8'h5a,32,0);
        check(!rx_valid && frame_errors==1,"bad stop discarded");
        @(negedge clk); manual_rx=0;
        repeat(2) @(negedge clk); manual_rx=1;
        repeat(64) @(negedge clk);
        check(!rx_valid && frame_errors==1,"false start ignored");
        $display("PASS uart checks=%0d tx=%0d rx=%0d framing=%0d overrun=%0d",checks,transmitted,received,frame_errors,overruns);
        $finish;
    end
    initial begin #2000000; $fatal(1,"UART watchdog expired"); end
endmodule
