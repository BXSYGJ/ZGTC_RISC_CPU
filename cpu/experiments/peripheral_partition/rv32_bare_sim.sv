`timescale 1ns/1ps
module rv32_bare_sim #(
    parameter integer CLOCK_HZ=157500000,
    parameter INIT_FILE=""
)(
    input wire clk,
    input wire rst_n,
    input wire [13:0] read_word,
    output wire [31:0] memory_word,
    output wire trap_valid,
    output wire [31:0] trap_cause,
    output wire maintenance_fault,
    output wire mmio_request
);
    rv32_soc #(.DATA_OVERLAP(1),.BTB_INDEX_BITS(8),.EARLY_D_REQUEST(1),.ENABLE_M(1),.CLOCK_HZ(CLOCK_HZ),.ENABLE_PREDICTOR(1),.LOAD_USE_BUBBLE(1),.FETCH_OVERLAP(1),.FAST_DCACHE_WRITE(1),.FAST_DCACHE_READ(1),.FAST_ICACHE_HIT(1),.ICACHE_SET_BITS(9),.CACHE_SET_BITS(6),.ENABLE_CACHE(1),.INIT_FILE(INIT_FILE)) soc(
        .clk(clk),.rst_n(rst_n),.serial_rx(1'b1),.gpio_input(8'b0),
        .maintenance_fault(maintenance_fault),.trap_valid(trap_valid),.trap_cause(trap_cause)
    );
    assign memory_word=soc.memory_system.ram.memory[read_word];
    assign mmio_request=soc.mmio_req_valid;
endmodule
