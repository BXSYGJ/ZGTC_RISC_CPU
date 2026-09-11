`timescale 1ns/1ps
module uart_timer_only_tb;
    reg clk=0;
    always #50 clk=~clk;
    reg rst_n=0;
    reg req_valid=0, req_write=0, rsp_ready=1, serial_rx=1;
    reg [31:0] req_address=0, req_data=0;
    reg [3:0] req_strobe=4'hf;
    reg [7:0] gpio_input=0;
    reg [287:0] performance_values=288'habcdef1234567890;
    wire req_ready, rsp_valid, rsp_error, serial_tx, irq_external, irq_software, irq_timer;
    wire ref_ready, ref_valid, ref_error, ref_tx, ref_external, ref_software, ref_timer;
    wire [31:0] rsp_data, status_code, ref_data, ref_status;
    wire [63:0] timer_value, ref_time;
    wire [7:0] gpio_output, ref_gpio;
    integer checks=0;
    rv32_peripherals #(.CLOCK_HZ(10000000),.BAUD(1000000)) candidate(
        .clk(clk),.rst_n(rst_n),.performance_values(performance_values),.performance_config(32'h0e8e96fd),
        .req_valid(req_valid),.req_ready(req_ready),.req_address(req_address),.req_write(req_write),.req_data(req_data),.req_strobe(req_strobe),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_data(rsp_data),.rsp_error(rsp_error),
        .serial_rx(serial_rx),.serial_tx(serial_tx),.gpio_input(gpio_input),.gpio_output(gpio_output),
        .irq_external(irq_external),.irq_software(irq_software),.irq_timer(irq_timer),.timer_value(timer_value),.status_code(status_code)
    );
    reference_peripherals #(.CLOCK_HZ(10000000),.BAUD(1000000)) reference_device(
        .clk(clk),.rst_n(rst_n),.performance_values(performance_values),.performance_config(32'h0e8e96fd),
        .req_valid(req_valid),.req_ready(ref_ready),.req_address(req_address),.req_write(req_write),.req_data(req_data),.req_strobe(req_strobe),
        .rsp_valid(ref_valid),.rsp_ready(rsp_ready),.rsp_data(ref_data),.rsp_error(ref_error),
        .serial_rx(serial_rx),.serial_tx(ref_tx),.gpio_input(gpio_input),.gpio_output(ref_gpio),
        .irq_external(ref_external),.irq_software(ref_software),.irq_timer(ref_timer),.timer_value(ref_time),.status_code(ref_status)
    );
    always @(negedge clk) if(rst_n) begin
        if(serial_tx !== ref_tx || timer_value !== ref_time || irq_timer !== ref_timer || irq_software !== ref_software)
            $fatal(1,"Preserved service behavior differs");
        if(gpio_output !== 8'b0) $fatal(1,"Removed GPIO output became active");
    end
    task automatic access(input [31:0] address, input bit write_access, input [31:0] data,
                          input [3:0] strobes, input bit expected_error, input bit compare_reference);
        reg [31:0] held_data;
        begin
            @(negedge clk);
            if(!req_ready || !ref_ready) $fatal(1,"Request handshake mismatch");
            req_valid=1; req_address=address; req_write=write_access; req_data=data; req_strobe=strobes; rsp_ready=0;
            @(negedge clk);
            req_valid=0;
            if(!rsp_valid || rsp_error !== expected_error) $fatal(1,"Response/error mismatch address=%h",address);
            if(compare_reference && {rsp_valid,rsp_error,rsp_data,irq_external} !== {ref_valid,ref_error,ref_data,ref_external})
                $fatal(1,"Preserved MMIO differs address=%h",address);
            held_data=rsp_data;
            repeat(3) begin
                @(negedge clk);
                if(req_ready || !rsp_valid || rsp_data !== held_data || rsp_error !== expected_error)
                    $fatal(1,"Backpressured response changed");
            end
            rsp_ready=1;
            @(negedge clk);
            checks=checks+1;
        end
    endtask
    task automatic receive_byte(input [7:0] value);
        integer bit_index;
        begin
            @(negedge clk); serial_rx=0; repeat(10) @(negedge clk);
            for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin
                serial_rx=value[bit_index]; repeat(10) @(negedge clk);
            end
            serial_rx=1; repeat(20) @(negedge clk);
        end
    endtask
    integer offset;
    initial begin
        repeat(4) @(negedge clk); rst_n=1;
        access(32'h10000000,1,32'h12345678,4'hf,0,1);
        access(32'h10000000,1,32'habcd0000,4'hc,0,1);
        access(32'h10000000,0,0,4'hf,0,1);
        access(32'h10000004,0,0,4'hf,0,1);
        access(32'h10000108,1,1,4'hf,0,1);
        receive_byte(8'h55);
        if(!irq_external || !ref_external) $fatal(1,"UART RX interrupt missing");
        access(32'h10000104,0,0,4'hf,0,1);
        access(32'h10000100,0,0,4'hf,0,1);
        access(32'h10000100,1,32'h55,4'hf,0,1);
        access(32'h10000100,1,32'haa,4'hf,0,1);
        access(32'h1000010c,1,3,4'hf,0,1);
        access(32'h10000400,1,1,4'hf,0,1);
        for(offset=4;offset<=48;offset=offset+4) access(32'h10000400+offset,0,0,4'hf,(offset==8 || offset==12),1);
        access(32'h10000308,1,100,4'hf,0,1);
        access(32'h1000030c,1,0,4'hf,0,1);
        access(32'h10000300,0,0,4'hf,0,1);
        access(32'h10000310,1,1,4'hf,0,1);
        access(32'h10000310,1,0,4'hf,0,1);
        access(32'h10000108,1,0,4'hf,0,1);
        access(32'h10000101,0,0,4'hf,1,1);
        access(32'h10000ffc,0,0,4'hf,1,1);
        for(offset=0;offset<16;offset=offset+4) begin
            access(32'h10000200+offset,1,32'hff,4'hf,1,0);
            access(32'h10000200+offset,0,0,4'hf,1,0);
        end
        gpio_input=8'hff;
        repeat(12) begin
            @(negedge clk);
            if(irq_external) $fatal(1,"Removed GPIO raised an interrupt while high");
        end
        gpio_input=0; repeat(12) @(negedge clk);
        if(irq_external) $fatal(1,"Removed GPIO raised an interrupt");
        repeat(250) @(negedge clk);
        $display("PASS uart_timer_only checks=%0d UART waveform/RX IRQ/timer/snapshot/backpressure GPIO removal",checks);
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"Peripheral test watchdog");
    end
endmodule
