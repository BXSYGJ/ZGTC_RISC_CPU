`timescale 1ns/1ps
module peripherals_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,req_valid=0,req_write=0,rsp_ready=0;
    reg [31:0] req_address=0,req_data=0;
    reg [3:0] req_strobe=0;
    wire req_ready,rsp_valid,rsp_error,serial_tx,irq_external,irq_software,irq_timer;
    wire [31:0] rsp_data,status_code;
    wire [63:0] timer_value;
    wire [7:0] gpio_output;
    reg [7:0] gpio_input=0;
    reg [287:0] performance_values=0;
    reg [31:0] performance_config=32'h0e020401;
    reg loopback=1,manual_rx=1;
    wire serial_rx=loopback ? serial_tx : manual_rx;
    integer checks=0,request_waits=0;
    reg [31:0] read_value,deadline;
    rv32_peripherals #(.CLOCK_HZ(3200),.BAUD(100)) peripherals(.*);
    task check(input bit condition,input string label_text);
        begin checks=checks+1; if(!condition) $fatal(1,"FAIL peripherals %s address=%08x data=%08x",label_text,req_address,read_value); end
    endtask
    task access(input bit writing,input [31:0] address,input [31:0] value,input [3:0] strobe,input bit expected_error,output [31:0] result);
        reg [31:0] held;
        begin
            @(negedge clk); req_valid=1; req_write=writing; req_address=address; req_data=value; req_strobe=strobe;
            @(posedge clk); while(!req_ready) begin request_waits=request_waits+1; @(posedge clk); end
            @(negedge clk); req_valid=0;
            @(posedge clk); while(!rsp_valid) @(posedge clk);
            check(rsp_error===expected_error,"MMIO error response");
            held=rsp_data; result=rsp_data;
            repeat(3) begin @(posedge clk); check(rsp_valid && rsp_data===held && rsp_error===expected_error && !req_ready,"response stable and single outstanding"); end
            @(negedge clk); rsp_ready=1;
            @(posedge clk);
            @(negedge clk); rsp_ready=0;
        end
    endtask
    task write_reg(input [31:0] address,input [31:0] value,input [3:0] strobe);
        begin access(1,address,value,strobe,0,read_value); end
    endtask
    task read_reg(input [31:0] address,input [31:0] expected);
        begin access(0,address,0,0,0,read_value); check(read_value===expected,"register value"); end
    endtask
    task send_rx(input [7:0] value,input bit good_stop);
        begin
            @(negedge clk); manual_rx=0; repeat(32) @(negedge clk);
            for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin manual_rx=value[bit_index]; repeat(32) @(negedge clk); end
            manual_rx=good_stop; repeat(32) @(negedge clk);
            manual_rx=1; repeat(32) @(negedge clk);
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
        read_reg(32'h10000004,32'h00010000);
        read_reg(32'h10000400,0);
        read_reg(32'h10000404,32'h0e020401);
        for(integer word_index=0;word_index<9;word_index=word_index+1) begin
            read_reg(32'h10000410+4*word_index,0);
            performance_values[word_index*32+:32]=32'ha0000000+word_index;
        end
        write_reg(32'h10000400,1,2);
        write_reg(32'h10000400,0,1);
        read_reg(32'h10000400,0);
        write_reg(32'h10000400,1,1);
        read_reg(32'h10000400,1);
        performance_values=0;
        for(integer word_index=0;word_index<9;word_index=word_index+1) begin
            read_reg(32'h10000410+4*word_index,32'ha0000000+word_index);
            access(1,32'h10000410+4*word_index,32'hffffffff,15,1,read_value);
            read_reg(32'h10000410+4*word_index,32'ha0000000+word_index);
        end
        access(1,32'h10000404,0,15,1,read_value);
        access(1,32'h10000401,1,1,1,read_value);
        access(0,32'h10000434,0,0,1,read_value);
        read_reg(32'h10000400,1);
        write_reg(32'h10000400,1,1);
        read_reg(32'h10000400,2);
        for(integer word_index=0;word_index<9;word_index=word_index+1) read_reg(32'h10000410+4*word_index,0);
        write_reg(32'h10000000,32'h11223344,15);
        write_reg(32'h10000000,32'haabbccdd,5);
        read_reg(32'h10000000,32'h11bb33dd);
        check(status_code==32'h11bb33dd,"status output");
        write_reg(32'h10000200,32'haa,1); check(gpio_output==8'haa,"GPIO output");
        write_reg(32'h10000200,0,2); check(gpio_output==8'haa,"GPIO byte enable");
        gpio_input=1; repeat(5) @(negedge clk);
        read_reg(32'h10000204,1); read_reg(32'h1000020c,1); check(!irq_external,"GPIO interrupt initially masked");
        write_reg(32'h10000208,1,1); check(irq_external,"GPIO pending enables IRQ");
        write_reg(32'h1000020c,1,1); check(!irq_external,"GPIO W1C clear");
        gpio_input=3; repeat(5) @(negedge clk); read_reg(32'h1000020c,2);
        check(!irq_external,"second GPIO event masked");
        write_reg(32'h10000208,3,1); check(irq_external,"second GPIO event unmasked");
        write_reg(32'h1000020c,2,1); check(!irq_external,"second GPIO event cleared");
        access(1,32'h10000204,0,15,1,read_value);
        access(1,32'h10000201,0,15,1,read_value); check(gpio_output==8'haa,"faulting GPIO write has no effect");
        access(0,32'h10000500,0,0,1,read_value);
        write_reg(32'h10000310,1,1); check(irq_software,"software IRQ set");
        write_reg(32'h10000310,0,2); check(irq_software,"software IRQ byte enable");
        write_reg(32'h10000310,0,1); check(!irq_software,"software IRQ clear");
        write_reg(32'h10000304,32'h12345678,15);
        write_reg(32'h10000300,32'hfffffffd,15);
        repeat(16) @(negedge clk); read_reg(32'h10000304,32'h12345679);
        write_reg(32'h1000030c,32'hffffffff,15);
        write_reg(32'h10000304,0,15); write_reg(32'h10000300,0,15);
        deadline=timer_value[31:0]+100;
        write_reg(32'h10000308,deadline,15); write_reg(32'h1000030c,0,15);
        check(!irq_timer,"timer compare in future");
        repeat(110) @(negedge clk); check(irq_timer,"timer compare fires");
        write_reg(32'h1000030c,32'hffffffff,15); check(!irq_timer,"timer compare rearmed");
        read_reg(32'h10000100,32'hffffffff);
        write_reg(32'h10000108,1,1);
        for(integer byte_index=0;byte_index<20;byte_index=byte_index+1) write_reg(32'h10000100,32'h80+32'(byte_index),1);
        check(request_waits>0,"TX FIFO full stalls request");
        for(integer byte_index=0;byte_index<20;byte_index=byte_index+1) begin
            access(0,32'h10000104,0,0,0,read_value);
            while(!read_value[2]) access(0,32'h10000104,0,0,0,read_value);
            check(irq_external,"RX data IRQ");
            read_reg(32'h10000100,32'h80+32'(byte_index));
        end
        repeat(40) @(negedge clk); check(!irq_external,"RX IRQ drains");
        read_reg(32'h10000100,32'hffffffff);
        write_reg(32'h10000100,32'hff,0); repeat(400) @(negedge clk);
        read_reg(32'h10000100,32'hffffffff);
        write_reg(32'h10000108,2,1); check(irq_external,"TX empty interrupt");
        write_reg(32'h10000108,0,1); check(!irq_external,"UART interrupt disable");
        loopback=0;
        for(integer byte_index=0;byte_index<18;byte_index=byte_index+1) send_rx(8'(byte_index),1);
        read_reg(32'h1000010c,2);
        access(0,32'h10000104,0,0,0,read_value); check(read_value[3] && read_value[5],"RX full and sticky overrun status");
        write_reg(32'h1000010c,2,1); read_reg(32'h1000010c,0);
        for(integer byte_index=0;byte_index<17;byte_index=byte_index+1) read_reg(32'h10000100,32'(byte_index));
        read_reg(32'h10000100,32'hffffffff);
        send_rx(8'h55,0); read_reg(32'h1000010c,1);
        write_reg(32'h1000010c,1,2); read_reg(32'h1000010c,1);
        write_reg(32'h1000010c,1,1); read_reg(32'h1000010c,0);
        $display("PASS peripherals checks=%0d request_waits=%0d",checks,request_waits);
        $finish;
    end
    initial begin #3000000; $fatal(1,"Peripheral watchdog expired"); end
endmodule
