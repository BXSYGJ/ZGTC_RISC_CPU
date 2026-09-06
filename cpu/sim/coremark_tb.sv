`timescale 1ns/1ps
module coremark_tb;
    parameter integer ENABLE_PREDICTOR=1;
    parameter integer LOAD_USE_BUBBLE=0;
    parameter integer FAST_ICACHE_HIT=0;
    parameter integer CACHE_SET_BITS=4;
    parameter integer ENABLE_CACHE=1;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,serial_rx=1;
    reg [7:0] gpio_input=0;
    wire serial_tx,maintenance_fault,trace_valid,trap_valid;
    wire [7:0] gpio_output;
    wire [31:0] status_code,trace_pc,trace_instruction,trap_cause;
    wire [63:0] cycle_count,retired_count;
    integer cycles=0,uart_file;
    string firmware,uart_path;
    rv32_soc #(.CLOCK_HZ(3200),.BAUD(100),.ENABLE_PREDICTOR(ENABLE_PREDICTOR),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.FAST_ICACHE_HIT(FAST_ICACHE_HIT),.CACHE_SET_BITS(CACHE_SET_BITS),.ENABLE_CACHE(ENABLE_CACHE)) soc(.*);
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware");
        if(!$value$plusargs("uart=%s",uart_path)) $fatal(1,"Missing UART log");
        uart_file=$fopen(uart_path,"w");
        if(!uart_file) $fatal(1,"Cannot open UART log");
        #1; rst_n=1; $readmemh(firmware,soc.memory_system.ram.memory);
        #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
        wait(status_code==32'hc0100000);
        @(negedge clk); serial_rx=0; repeat(32) @(negedge clk);
        for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin
            serial_rx=(8'h47 >> bit_index)&1; repeat(32) @(negedge clk);
        end
        serial_rx=1;
    end
    initial begin : uart_monitor
        reg [7:0] observed;
        forever begin
            @(negedge serial_tx);
            if(rst_n) begin
                #160; if(serial_tx!==0) $fatal(1,"UART start");
                for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin #320; observed[bit_index]=serial_tx; end
                #320; if(serial_tx!==1) $fatal(1,"UART stop");
                $fwrite(uart_file,"%c",observed);
                $write("%c",observed);
            end
        end
    end
    always @(negedge clk) if(rst_n) begin
        cycles=cycles+1;
        if(trap_valid||maintenance_fault) $fatal(1,"CoreMark trap PC=%08x cause=%08x",trace_pc,trap_cause);
        if(status_code==32'hc0100001) begin
            $fclose(uart_file);
            $display("PASS CoreMark simulation finished cycles=%0d retired=%0d",cycles,retired_count);
            $finish;
        end
        if(cycles>50000000) $fatal(1,"CoreMark simulation timeout PC=%08x",trace_pc);
    end
endmodule
