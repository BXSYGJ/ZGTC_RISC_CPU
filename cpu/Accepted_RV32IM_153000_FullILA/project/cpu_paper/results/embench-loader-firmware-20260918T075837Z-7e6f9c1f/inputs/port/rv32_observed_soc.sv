`timescale 1ns/1ps
// Simulation-only observer. The instantiated reference RTL is unchanged.
module rv32_observed_soc #(
    parameter integer ENABLE_M=1, ENABLE_PREDICTOR=1, LOAD_USE_BUBBLE=1,
    parameter integer FAST_ICACHE_HIT=1, FAST_DCACHE_READ=1, FAST_DCACHE_WRITE=1,
    parameter integer FETCH_OVERLAP=1, DATA_OVERLAP=1, EARLY_D_REQUEST=1,
    parameter integer BTB_INDEX_BITS=8, ICACHE_SET_BITS=9, CACHE_SET_BITS=6,
    parameter integer ENABLE_CACHE=1, MEMORY_ADDRESS_BITS=14,
    parameter integer CLOCK_HZ=3200, BAUD=100,
    parameter INIT_FILE="firmware.hex"
) (
    input wire clk, rst_n, serial_rx,
    input wire [7:0] gpio_input,
    output wire serial_tx,
    output wire [7:0] gpio_output,
    output wire [31:0] status_code, trace_pc, trace_instruction, trap_cause,
    output wire maintenance_fault, trace_valid, trap_valid,
    output wire [63:0] cycle_count, retired_count,
    output wire [31:0] snapshot_sequence,
    output wire [63:0] snapshot_cycles, snapshot_retired,
    output wire retire_event, wb_write,
    output wire [4:0] wb_rd,
    output wire [31:0] wb_data,
    output wire redirect_event, redirect_eligible, fetch_request_stall, fetch_response_wait, frontend_barrier,
    output wire [2:0] redirect_kind
);
    rv32_soc #(
        .ENABLE_M(ENABLE_M),.ENABLE_PREDICTOR(ENABLE_PREDICTOR),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),
        .FAST_ICACHE_HIT(FAST_ICACHE_HIT),.FAST_DCACHE_READ(FAST_DCACHE_READ),.FAST_DCACHE_WRITE(FAST_DCACHE_WRITE),
        .FETCH_OVERLAP(FETCH_OVERLAP),.DATA_OVERLAP(DATA_OVERLAP),.EARLY_D_REQUEST(EARLY_D_REQUEST),
        .BTB_INDEX_BITS(BTB_INDEX_BITS),.ICACHE_SET_BITS(ICACHE_SET_BITS),.CACHE_SET_BITS(CACHE_SET_BITS),
        .ENABLE_CACHE(ENABLE_CACHE),.MEMORY_ADDRESS_BITS(MEMORY_ADDRESS_BITS),
        .CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD),.INIT_FILE(INIT_FILE)
    ) soc(
        .clk(clk),.rst_n(rst_n),.serial_rx(serial_rx),.gpio_input(gpio_input),.serial_tx(serial_tx),.gpio_output(gpio_output),
        .status_code(status_code),.trace_pc(trace_pc),.trace_instruction(trace_instruction),.trap_cause(trap_cause),
        .maintenance_fault(maintenance_fault),.trace_valid(trace_valid),.trap_valid(trap_valid),
        .cycle_count(cycle_count),.retired_count(retired_count)
    );
    assign snapshot_sequence=soc.peripherals.snapshot_sequence;
    assign snapshot_cycles=soc.peripherals.performance_snapshot[63:0];
    assign snapshot_retired=soc.peripherals.performance_snapshot[127:64];
    assign retire_event=soc.core.wb_valid && !soc.core.wb_counter_write;
    assign wb_write=soc.core.trace_write;
    assign wb_rd=soc.core.trace_rd;
    assign wb_data=soc.core.trace_data;
    wire [6:0] redirect_opcode=soc.core.mem_flush ? soc.core.mem_instruction[6:0] : soc.core.ex_instruction[6:0];
    assign redirect_event=soc.core.frontend_flush;
    assign frontend_barrier=soc.core.frontend_barrier;
    assign redirect_eligible=redirect_event && !frontend_barrier && (!soc.core.fetch_active || soc.core.fetch_complete);
    // Categories are resolved frontend flushes, not all retired branches.
    assign redirect_kind=(soc.core.mem_flush && soc.core.mem_fault) ? 3'd3 :
        (soc.core.mem_flush && soc.core.mem_mret) ? 3'd4 :
        (soc.core.mem_flush && soc.core.mem_fence_i) ? 3'd5 :
        redirect_opcode==7'h63 ? 3'd0 : redirect_opcode==7'h6f ? 3'd1 : redirect_opcode==7'h67 ? 3'd2 : 3'd6;
    assign fetch_request_stall=soc.i_req_valid && !soc.i_req_ready;
    assign fetch_response_wait=soc.core.fetch_active && soc.core.fetch_sent && !soc.i_rsp_valid;
endmodule
