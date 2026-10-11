`timescale 1ns/1ps
module rv32_board_top #(
    parameter integer ENABLE_M=0,
    parameter integer CLOCK_HZ=27000000,
    parameter integer ENABLE_PREDICTOR=1,
    parameter integer LOAD_USE_BUBBLE=0,
    parameter integer FAST_ICACHE_HIT=0,
    parameter integer FAST_DCACHE_READ=0,
    parameter integer FAST_DCACHE_WRITE=0,
    parameter integer FETCH_OVERLAP=0,
    parameter integer DATA_OVERLAP=0,
    parameter integer EARLY_D_REQUEST=0,
    parameter integer BTB_INDEX_BITS=4,
    parameter integer ICACHE_SET_BITS=0,
    parameter integer CACHE_SET_BITS=4,
    parameter integer CACHE_ADDRESS_BITS=16,
    parameter integer ENABLE_CACHE=1,
    parameter integer UART_BAUD=115200,
    parameter INIT_FILE=""
) (
    input wire clk,
    input wire rst_n,
    input wire key,
    input wire uart_rx,
    output wire uart_tx,
    input wire spi_miso,
    output wire spi_cs,
    output wire spi_sck,
    output wire spi_mosi,
    output wire [7:0] led,
    // ---- DDR3 physical side (differential ref clock + pads) ----
    input  wire ref_clk_p,
    input  wire ref_clk_n,
    output wire [14:0] mem_a,
    output wire [2:0]  mem_ba,
    output wire        mem_ck,
    output wire        mem_ck_n,
    output wire        mem_cke,
    output wire        mem_cs_n,
    output wire        mem_ras_n,
    output wire        mem_cas_n,
    output wire        mem_we_n,
    output wire        mem_odt,
    output wire        mem_rst_n,
    inout  wire [31:0] mem_dq,
    inout  wire [3:0]  mem_dqs,
    inout  wire [3:0]  mem_dqs_n,
    output wire [3:0]  mem_dm
);
    reg [1:0] reset_pipe;
    wire [7:0] gpio_output;
    wire maintenance_fault;
    wire unused_trace_valid,unused_trap_valid;
    wire [31:0] unused_status,unused_pc,unused_instruction,unused_cause;
    wire [63:0] unused_cycles,unused_retired;
    // DDR3 backend: burst-bus slave <-> AXI bridge <-> DDR3 IP wrapper
    wire ddr_cmd_valid,ddr_cmd_ready,ddr_cmd_write,ddr_w_valid,ddr_w_ready,ddr_w_last;
    wire ddr_b_valid,ddr_b_ready,ddr_b_error,ddr_r_valid,ddr_r_ready,ddr_r_last,ddr_r_error;
    wire [31:0] ddr_cmd_address,ddr_w_data,ddr_r_data;
    wire [7:0] ddr_cmd_length;
    wire core_clk,core_clk_rst_n,ddr_init_done,ddr_pll_lock;
    // AXI (core_clk domain)
    wire axiw_awvalid,axiw_awready,axiw_wvalid,axiw_wready,axiw_wusero_last;
    wire [27:0] axiw_awaddr;
    wire [3:0]  axiw_awuser_id,axiw_awlen,axiw_wusero_id;
    wire [255:0] axiw_wdata;
    wire [31:0] axiw_wstrb;
    wire axir_arvalid,axir_arready,axir_rvalid,axir_rlast;
    wire [27:0] axir_araddr;
    wire [3:0]  axir_aruser_id,axir_arlen,axir_rid;
    wire [255:0] axir_rdata;
    wire axiw_awuser_ap,axir_aruser_ap;
    // DDR debug bus
    wire [3:0] ddr_dbg_state;
    wire ddr_dbg_arvalid, ddr_dbg_arready, ddr_dbg_rvalid;
    wire ddr_dbg_to_err;
    wire [2:0] ddr_dbg_to_state;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) reset_pipe<=0;
        else reset_pipe<={reset_pipe[0],1'b1};
    end
    assign led=maintenance_fault ? 8'he1 : gpio_output;
    rv32_soc #(.DATA_OVERLAP(DATA_OVERLAP),.BTB_INDEX_BITS(BTB_INDEX_BITS),.EARLY_D_REQUEST(EARLY_D_REQUEST),.ENABLE_M(ENABLE_M),.CLOCK_HZ(CLOCK_HZ),.INIT_FILE(INIT_FILE),.ENABLE_PREDICTOR(ENABLE_PREDICTOR),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.FETCH_OVERLAP(FETCH_OVERLAP),.FAST_DCACHE_WRITE(FAST_DCACHE_WRITE),.FAST_DCACHE_READ(FAST_DCACHE_READ),.FAST_ICACHE_HIT(FAST_ICACHE_HIT),.ICACHE_SET_BITS(ICACHE_SET_BITS),.CACHE_SET_BITS(CACHE_SET_BITS),.ENABLE_CACHE(ENABLE_CACHE),.CACHE_ADDRESS_BITS(CACHE_ADDRESS_BITS),.BAUD(UART_BAUD)) soc(
        .clk(clk),.rst_n(reset_pipe[1]),.serial_rx(uart_rx),.serial_tx(uart_tx),.spi_miso(spi_miso),.spi_cs(spi_cs),.spi_sck(spi_sck),.spi_mosi(spi_mosi),        .gpio_input({ddr_dbg_to_err,ddr_dbg_to_state[2:0],ddr_init_done,ddr_pll_lock,uart_rx,~key}),.gpio_output(gpio_output),
        .status_code(unused_status),.maintenance_fault(maintenance_fault),.trace_valid(unused_trace_valid),.trace_pc(unused_pc),.trace_instruction(unused_instruction),
        .trap_valid(unused_trap_valid),.trap_cause(unused_cause),.cycle_count(unused_cycles),.retired_count(unused_retired),
        .ddr_cmd_valid(ddr_cmd_valid),.ddr_cmd_ready(ddr_cmd_ready),.ddr_cmd_write(ddr_cmd_write),
        .ddr_cmd_address(ddr_cmd_address),.ddr_cmd_length(ddr_cmd_length),
        .ddr_w_valid(ddr_w_valid),.ddr_w_ready(ddr_w_ready),.ddr_w_data(ddr_w_data),.ddr_w_last(ddr_w_last),
        .ddr_b_valid(ddr_b_valid),.ddr_b_ready(ddr_b_ready),.ddr_b_error(ddr_b_error),
        .ddr_r_valid(ddr_r_valid),.ddr_r_ready(ddr_r_ready),.ddr_r_data(ddr_r_data),.ddr_r_last(ddr_r_last),.ddr_r_error(ddr_r_error)
    );
    rv32_burst_ddr3 ddr3_bridge(
        .clk(clk),.rst_n(reset_pipe[1]),
        .cmd_valid(ddr_cmd_valid),.cmd_ready(ddr_cmd_ready),.cmd_write(ddr_cmd_write),
        .cmd_address(ddr_cmd_address),.cmd_length(ddr_cmd_length),
        .w_valid(ddr_w_valid),.w_ready(ddr_w_ready),.w_data(ddr_w_data),.w_last(ddr_w_last),
        .b_valid(ddr_b_valid),.b_ready(ddr_b_ready),.b_error(ddr_b_error),
        .r_valid(ddr_r_valid),.r_ready(ddr_r_ready),.r_data(ddr_r_data),.r_last(ddr_r_last),.r_error(ddr_r_error),
        .ddr_clk(core_clk),.ddr_rst_n(core_clk_rst_n),.ddr_init_done(ddr_init_done),
        .axiw_awaddr(axiw_awaddr),.axiw_awuser_ap(axiw_awuser_ap),.axiw_awuser_id(axiw_awuser_id),.axiw_awlen(axiw_awlen),
        .axiw_awvalid(axiw_awvalid),.axiw_awready(axiw_awready),
        .axiw_wdata(axiw_wdata),.axiw_wstrb(axiw_wstrb),.axiw_wvalid(axiw_wvalid),.axiw_wready(axiw_wready),
        .axiw_wusero_id(axiw_wusero_id),.axiw_wusero_last(axiw_wusero_last),
        .axir_araddr(axir_araddr),.axir_aruser_ap(axir_aruser_ap),.axir_aruser_id(axir_aruser_id),.axir_arlen(axir_arlen),
        .axir_arvalid(axir_arvalid),.axir_arready(axir_arready),
        .axir_rdata(axir_rdata),.axir_rid(axir_rid),.axir_rlast(axir_rlast),.axir_rvalid(axir_rvalid),
        .dbg_ddr_state(ddr_dbg_state),.dbg_arvalid(ddr_dbg_arvalid),.dbg_arready(ddr_dbg_arready),.dbg_rvalid(ddr_dbg_rvalid),
        .dbg_to_err(ddr_dbg_to_err),.dbg_to_state(ddr_dbg_to_state)
    );
    rv32_ddr3_ip_wrapper ddr3_wrapper(
        .ref_clk_p(ref_clk_p),.ref_clk_n(ref_clk_n),
        .resetn(rst_n),
        .core_clk(core_clk),.core_clk_rst_n(core_clk_rst_n),.ddr_init_done(ddr_init_done),.pll_lock(ddr_pll_lock),
        .axiw_awaddr(axiw_awaddr),.axiw_awuser_ap(axiw_awuser_ap),.axiw_awuser_id(axiw_awuser_id),.axiw_awlen(axiw_awlen),
        .axiw_awvalid(axiw_awvalid),.axiw_awready(axiw_awready),
        .axiw_wdata(axiw_wdata),.axiw_wstrb(axiw_wstrb),.axiw_wvalid(axiw_wvalid),.axiw_wready(axiw_wready),
        .axiw_wusero_id(axiw_wusero_id),.axiw_wusero_last(axiw_wusero_last),
        .axir_araddr(axir_araddr),.axir_aruser_ap(axir_aruser_ap),.axir_aruser_id(axir_aruser_id),.axir_arlen(axir_arlen),
        .axir_arvalid(axir_arvalid),.axir_arready(axir_arready),
        .axir_rdata(axir_rdata),.axir_rid(axir_rid),.axir_rlast(axir_rlast),.axir_rvalid(axir_rvalid),
        .mem_cs_n(mem_cs_n),.mem_rst_n(mem_rst_n),.mem_ck(mem_ck),.mem_ck_n(mem_ck_n),.mem_cke(mem_cke),
        .mem_ras_n(mem_ras_n),.mem_cas_n(mem_cas_n),.mem_we_n(mem_we_n),.mem_odt(mem_odt),
        .mem_a(mem_a),.mem_ba(mem_ba),
        .mem_dqs(mem_dqs),.mem_dqs_n(mem_dqs_n),.mem_dq(mem_dq),.mem_dm(mem_dm)
    );
endmodule
