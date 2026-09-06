`timescale 1ns/1ps
module rv32_board_top #(
    parameter integer CLOCK_HZ=27000000,
    parameter integer ENABLE_PREDICTOR=1,
    parameter integer LOAD_USE_BUBBLE=0,
    parameter integer FAST_ICACHE_HIT=0,
    parameter integer CACHE_SET_BITS=4,
    parameter integer ENABLE_CACHE=1,
    parameter integer UART_BAUD=115200,
    parameter INIT_FILE=""
) (
    input wire clk,
    input wire rst_n,
    input wire key,
    input wire uart_rx,
    output wire uart_tx,
    output wire [7:0] led
);
    reg [1:0] reset_pipe;
    wire [7:0] gpio_output;
    wire maintenance_fault;
    wire unused_trace_valid,unused_trap_valid;
    wire [31:0] unused_status,unused_pc,unused_instruction,unused_cause;
    wire [63:0] unused_cycles,unused_retired;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) reset_pipe<=0;
        else reset_pipe<={reset_pipe[0],1'b1};
    end
    assign led=maintenance_fault ? 8'he1 : gpio_output;
    rv32_soc #(.CLOCK_HZ(CLOCK_HZ),.INIT_FILE(INIT_FILE),.ENABLE_PREDICTOR(ENABLE_PREDICTOR),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.FAST_ICACHE_HIT(FAST_ICACHE_HIT),.CACHE_SET_BITS(CACHE_SET_BITS),.ENABLE_CACHE(ENABLE_CACHE),.BAUD(UART_BAUD)) soc(
        .clk(clk),.rst_n(reset_pipe[1]),.serial_rx(uart_rx),.serial_tx(uart_tx),.gpio_input({6'b0,uart_rx,~key}),.gpio_output(gpio_output),
        .status_code(unused_status),.maintenance_fault(maintenance_fault),.trace_valid(unused_trace_valid),.trace_pc(unused_pc),.trace_instruction(unused_instruction),
        .trap_valid(unused_trap_valid),.trap_cause(unused_cause),.cycle_count(unused_cycles),.retired_count(unused_retired)
    );
endmodule
