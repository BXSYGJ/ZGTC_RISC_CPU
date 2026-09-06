`timescale 1ns/1ps
module isa_tb;
    parameter integer PREDICTOR=1;
    parameter integer LOAD_USE_BUBBLE=0;
    parameter integer FAST_ICACHE_HIT=0;
    parameter integer CACHE_SETS=4;
    parameter integer ENABLE_CACHE=1;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0;
    wire i_req_valid,i_req_ready,i_rsp_valid,i_rsp_ready,i_rsp_error;
    wire d_req_valid,d_req_ready,d_req_write,d_rsp_valid,d_rsp_ready,d_rsp_error;
    wire [31:0] i_req_address,i_rsp_data,d_req_address,d_req_data,d_rsp_data;
    wire [3:0] d_req_strobe;
    wire maintenance_valid,maintenance_ready,memory_maintenance_ready,memory_maintenance_error;
    reg final_flush=0;
    wire mmio_req_valid,mmio_req_write,mmio_rsp_ready;
    wire [31:0] mmio_req_address,mmio_req_data;
    wire [3:0] mmio_req_strobe;
    wire mmio_req_ready;
    reg mmio_rsp_valid=0;
    wire [31:0] i_hit_count,i_miss_count,d_hit_count,d_miss_count,d_writeback_count;
    reg [63:0] timer_value=0;
    wire irq_external=0,irq_software=0,irq_timer=0;
    wire trace_valid,trace_write,trap_valid;
    wire [31:0] trace_pc,trace_instruction,trace_data,trap_pc,trap_cause,trap_value;
    wire [4:0] trace_rd,pipeline_valid;
    wire [63:0] cycle_count,retired_count;
    reg passed=0;
    integer cycles=0,success_wait=0,trace_file;
    string firmware,trace_path,memory_path,test_name;
    assign maintenance_ready=memory_maintenance_ready && !final_flush;
    assign mmio_req_ready=!mmio_rsp_valid;
    rv32_core #(.ENABLE_PREDICTOR(PREDICTOR),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE)) core(.*);
    rv32_memory_system #(.MEMORY_ADDRESS_BITS(14),.CACHE_SET_BITS(CACHE_SETS),.ENABLE_CACHE(ENABLE_CACHE),.FAST_ICACHE_HIT(FAST_ICACHE_HIT)) memory_system(
        .clk(clk),.rst_n(rst_n),
        .i_req_valid(i_req_valid),.i_req_ready(i_req_ready),.i_req_address(i_req_address),
        .i_rsp_valid(i_rsp_valid),.i_rsp_ready(i_rsp_ready),.i_rsp_data(i_rsp_data),.i_rsp_error(i_rsp_error),
        .d_req_valid(d_req_valid),.d_req_ready(d_req_ready),.d_req_address(d_req_address),.d_req_write(d_req_write),
        .d_req_data(d_req_data),.d_req_strobe(d_req_strobe),.d_rsp_valid(d_rsp_valid),.d_rsp_ready(d_rsp_ready),.d_rsp_data(d_rsp_data),.d_rsp_error(d_rsp_error),
        .maintenance_valid(maintenance_valid || final_flush),.maintenance_ready(memory_maintenance_ready),.maintenance_error(memory_maintenance_error),
        .mmio_req_valid(mmio_req_valid),.mmio_req_ready(mmio_req_ready),.mmio_req_address(mmio_req_address),.mmio_req_write(mmio_req_write),
        .mmio_req_data(mmio_req_data),.mmio_req_strobe(mmio_req_strobe),.mmio_rsp_valid(mmio_rsp_valid),.mmio_rsp_ready(mmio_rsp_ready),.mmio_rsp_data(32'b0),.mmio_rsp_error(1'b0),
        .i_hit_count(i_hit_count),.i_miss_count(i_miss_count),.d_hit_count(d_hit_count),.d_miss_count(d_miss_count),.d_writeback_count(d_writeback_count)
    );
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware");
        if(!$value$plusargs("trace=%s",trace_path)) $fatal(1,"Missing trace");
        if(!$value$plusargs("memory_out=%s",memory_path)) $fatal(1,"Missing memory output");
        if(!$value$plusargs("name=%s",test_name)) $fatal(1,"Missing test name");
        trace_file=$fopen(trace_path,"w");
        if(!trace_file) $fatal(1,"Cannot open trace");
        #1; rst_n=1;
        $readmemh(firmware,memory_system.ram.memory);
        #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
    end
    always @(posedge clk) begin
        if(rst_n) begin
            cycles=cycles+1;
            timer_value<=timer_value+1;
            if(mmio_rsp_valid && mmio_rsp_ready) mmio_rsp_valid<=0;
            if(mmio_req_valid && mmio_req_ready) begin
                if(!mmio_req_write || mmio_req_strobe!==4'hf) $fatal(1,"ISA invalid mailbox access");
                if(mmio_req_address==32'h10000004) $fatal(1,"ISA failure testnum=%0d",mmio_req_data);
                if(mmio_req_address!==32'h10000000 || mmio_req_data!==32'd1) $fatal(1,"ISA invalid success address=%08x data=%08x",mmio_req_address,mmio_req_data);
                if(passed) $fatal(1,"ISA duplicate success");
                passed<=1;
                mmio_rsp_valid<=1;
            end
            if(trace_valid) begin
                $fdisplay(trace_file,"R %08x %08x %0d %0d %08x",trace_pc,trace_instruction,trace_write,trace_rd,trace_data);
                if(trace_write && trace_rd==0) $fatal(1,"ISA x0 write");
            end
            if(trap_valid) begin
                $fdisplay(trace_file,"T %08x %08x %08x",trap_pc,trap_cause,trap_value);
                $fatal(1,"ISA unexpected trap cause=%0d pc=%08x value=%08x",trap_cause,trap_pc,trap_value);
            end
            if(memory_maintenance_ready && memory_maintenance_error) $fatal(1,"ISA maintenance failure");
            if(passed) begin
                success_wait=success_wait+1;
                if(success_wait==16) final_flush<=1;
            end
            if(final_flush && memory_maintenance_ready) begin
                $display("PASS ISA name=%s cycles=%0d retired=%0d predictor=%0d cache=%0d sets=%0d loadbubble=%0d fastihit=%0d",test_name,cycle_count,retired_count,PREDICTOR,ENABLE_CACHE,CACHE_SETS,LOAD_USE_BUBBLE,FAST_ICACHE_HIT);
                $fclose(trace_file);
                $writememh(memory_path,memory_system.ram.memory);
                $finish;
            end
            if(cycles>200000) $fatal(1,"ISA watchdog expired pc=%08x",trace_pc);
        end
    end
endmodule
