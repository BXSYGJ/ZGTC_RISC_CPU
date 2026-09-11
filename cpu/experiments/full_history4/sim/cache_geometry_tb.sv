`timescale 1ns/1ps
module cache_geometry_case #(
    parameter integer INSTRUCTION_BITS=0,DATA_BITS=4,CACHE_ENABLED=1
)(output reg done=0);
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    localparam integer EFFECTIVE_I=INSTRUCTION_BITS!=0 ? INSTRUCTION_BITS : DATA_BITS;
    localparam [31:0] EXPECTED_CONFIG=32'h0e020001 | (DATA_BITS<<8) |
        ((EFFECTIVE_I!=DATA_BITS ? EFFECTIVE_I : 0)<<12) | (CACHE_ENABLED==0 ? 2 : 0);
    rv32_soc #(.ICACHE_SET_BITS(INSTRUCTION_BITS),.CACHE_SET_BITS(DATA_BITS),.ENABLE_CACHE(CACHE_ENABLED)) soc(
        .clk(clk),.rst_n(rst_n),.serial_rx(1'b1),.gpio_input(8'b0)
    );
    if(CACHE_ENABLED!=0) begin : physical_geometry
        initial begin
            #1;
            if(soc.memory_system.caches[0].enabled.cache.SET_BITS!=EFFECTIVE_I ||
                soc.memory_system.caches[1].enabled.cache.SET_BITS!=DATA_BITS)
                $fatal(1,"cache geometry physical widths");
            if($bits(soc.memory_system.caches[0].enabled.cache.request_tag)!=12-EFFECTIVE_I ||
                $bits(soc.memory_system.caches[1].enabled.cache.request_tag)!=12-DATA_BITS)
                $fatal(1,"cache geometry tag widths");
        end
    end
    initial begin
        force soc.mmio_req_valid=1'b0;
        force soc.mmio_req_address=32'h10000404;
        force soc.mmio_req_write=1'b0;
        force soc.mmio_req_data=32'b0;
        force soc.mmio_req_strobe=4'b0;
        force soc.mmio_rsp_ready=1'b0;
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
        @(negedge clk); force soc.mmio_req_valid=1'b1;
        @(posedge clk);
        while(!soc.mmio_req_ready) @(posedge clk);
        @(negedge clk); force soc.mmio_req_valid=1'b0;
        while(!soc.mmio_rsp_valid) @(negedge clk);
        if(soc.mmio_rsp_error || soc.mmio_rsp_data!==EXPECTED_CONFIG)
            $fatal(1,"cache geometry MMIO configuration");
        repeat(3) begin
            @(negedge clk);
            if(!soc.mmio_rsp_valid || soc.mmio_rsp_data!==EXPECTED_CONFIG)
                $fatal(1,"cache geometry stalled configuration");
        end
        force soc.mmio_rsp_ready=1'b1;
        @(negedge clk); done=1;
    end
endmodule
module cache_geometry_tb;
    wire [5:0] done;
    cache_geometry_case #(.INSTRUCTION_BITS(0),.DATA_BITS(4)) inherited(done[0]);
    cache_geometry_case #(.INSTRUCTION_BITS(4),.DATA_BITS(4)) equal_width(done[1]);
    cache_geometry_case #(.INSTRUCTION_BITS(8),.DATA_BITS(6)) large_instruction(done[2]);
    cache_geometry_case #(.INSTRUCTION_BITS(8),.DATA_BITS(7)) medium_data(done[3]);
    cache_geometry_case #(.INSTRUCTION_BITS(1),.DATA_BITS(3)) small_instruction(done[4]);
    cache_geometry_case #(.INSTRUCTION_BITS(8),.DATA_BITS(6),.CACHE_ENABLED(0)) bypass(done[5]);
    initial begin
        wait(&done); $display("PASS cache_geometry checks=6"); $finish;
    end
    initial begin #10000; $fatal(1,"cache geometry timeout"); end
endmodule
