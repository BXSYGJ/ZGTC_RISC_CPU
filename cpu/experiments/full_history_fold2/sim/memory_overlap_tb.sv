`timescale 1ns/1ps
module memory_overlap_tb;
    parameter integer DATA_OVERLAP=1;
    parameter integer FAST_DCACHE_READ=1;
    parameter integer ICACHE_SET_BITS=0;
    parameter integer FAST_DCACHE_WRITE=0;
    parameter integer MMIO_STALL_CYCLES=0;
    parameter TEST_NAME="memory_overlap";
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    wire i_req_valid=0,i_rsp_ready=1;
    wire [31:0] i_req_address=0;
    wire i_req_ready,i_rsp_valid,i_rsp_error;
    wire [31:0] i_rsp_data;
    reg d_req_valid=0,d_req_write=0,d_rsp_ready=0,maintenance_valid=0;
    reg [31:0] d_req_address=0,d_req_data=0;
    reg [3:0] d_req_strobe=15;
    wire d_req_ready,d_rsp_valid,d_rsp_error,maintenance_ready,maintenance_error;
    wire [31:0] d_rsp_data;
    wire mmio_req_valid,mmio_req_write,mmio_rsp_ready;
    wire [31:0] mmio_req_address,mmio_req_data;
    wire [3:0] mmio_req_strobe;
    reg mmio_rsp_valid=0,mmio_rsp_error=0;
    reg [31:0] mmio_rsp_data=0,mmio_value=0;
    reg mmio_allow=1,mmio_held=0;
    reg [31:0] held_mmio_address,held_mmio_data;
    reg [3:0] held_mmio_strobe;
    reg held_mmio_write;
    integer mmio_wait=0;
    wire mmio_req_ready=mmio_allow && !mmio_rsp_valid && mmio_wait>=MMIO_STALL_CYCLES;
    wire [31:0] i_hit_count,i_miss_count,d_hit_count,d_miss_count,d_writeback_count;
    integer checks=0,outstanding=0,requests=0,responses=0,handovers=0,cache_to_mmio=0,mmio_to_cache=0,mmio_writes=0;
    rv32_memory_system #(.DATA_OVERLAP(DATA_OVERLAP),.FAST_DCACHE_WRITE(FAST_DCACHE_WRITE),.FAST_DCACHE_READ(FAST_DCACHE_READ),.ICACHE_SET_BITS(ICACHE_SET_BITS),.CACHE_SET_BITS(1)) memory_system(.*);
    task automatic check(input bit condition,input string label_text);
        begin checks=checks+1; if(!condition) $fatal(1,"FAIL memory_overlap %s",label_text); end
    endtask
    always @(posedge clk) begin
        if(!rst_n) begin outstanding=0; mmio_wait<=0; mmio_held<=0; mmio_rsp_valid<=0; mmio_rsp_error<=0; mmio_rsp_data<=0; mmio_value<=0; mmio_writes<=0; end
        else begin
            if(!mmio_req_valid || mmio_req_ready) mmio_wait<=0;
            else mmio_wait<=mmio_wait+1;
            if(mmio_held) check(mmio_req_valid && mmio_req_address==held_mmio_address && mmio_req_data==held_mmio_data && mmio_req_strobe==held_mmio_strobe && mmio_req_write==held_mmio_write,"registered MMIO request remains stable until acceptance");
            mmio_held<=mmio_req_valid && !mmio_req_ready;
            if(mmio_req_valid && !mmio_req_ready) begin
                held_mmio_address<=mmio_req_address; held_mmio_data<=mmio_req_data; held_mmio_strobe<=mmio_req_strobe; held_mmio_write<=mmio_req_write;
            end
            if(mmio_rsp_valid && mmio_rsp_ready) mmio_rsp_valid<=0;
            if(mmio_req_valid && mmio_req_ready) begin
                mmio_rsp_valid<=1; mmio_rsp_error<=mmio_req_address==32'h10000008; mmio_rsp_data<=mmio_value;
                if(mmio_req_write && mmio_req_address==32'h10000000) begin
                    check(mmio_req_strobe==15,"MMIO write lanes");
                    mmio_value<=mmio_req_data; mmio_writes<=mmio_writes+1;
                end
            end
            if(d_rsp_valid && d_rsp_ready) begin
                check(outstanding==1,"one owned response before completion"); outstanding=outstanding-1; responses=responses+1;
            end
            if(d_req_valid && d_req_ready) begin
                check(outstanding==0,"at most one pending data transaction"); outstanding=outstanding+1; requests=requests+1;
                if(d_rsp_valid && d_rsp_ready) begin
                    handovers=handovers+1;
                    if(!memory_system.data_mmio && |d_req_address[31:28]) cache_to_mmio=cache_to_mmio+1;
                    if(memory_system.data_mmio && !(|d_req_address[31:28])) mmio_to_cache=mmio_to_cache+1;
                end
            end
        end
    end
    always @(negedge clk) if(rst_n) check(memory_system.data_active==1'(outstanding),"request handover preserves active owner");
    task pair(input [31:0] first_address,input bit first_write,input [31:0] first_data,
              input [31:0] second_address,input bit second_write,input [31:0] second_data,
              input [31:0] first_expected,input bit first_error,input [31:0] second_expected);
        begin
            @(negedge clk); d_req_valid=1; d_req_address=first_address; d_req_write=first_write; d_req_data=first_data; d_rsp_ready=0;
            @(posedge clk); check(d_req_ready,"pair starts with an idle owner");
            @(negedge clk); d_req_address=second_address; d_req_write=second_write; d_req_data=second_data;
            @(posedge clk); while(!d_rsp_valid) @(posedge clk);
            repeat(3) begin
                check(!d_req_ready && d_rsp_valid && d_rsp_error===first_error,"response backpressure blocks successor");
                if(!first_write && !first_error) check(d_rsp_data===first_expected,"held response belongs to old owner");
                @(posedge clk);
            end
            @(negedge clk); d_rsp_ready=1;
            @(posedge clk); check(d_req_ready && d_rsp_valid,"old response and next request overlap");
            check(d_rsp_error===first_error,"old error retained through ownership transfer");
            @(negedge clk); d_req_valid=0;
            @(posedge clk); while(!d_rsp_valid) @(posedge clk);
            check(!d_rsp_error,"successor response error clears");
            if(!second_write) check(d_rsp_data===second_expected,"successor response has correct owner and data");
            @(negedge clk); d_rsp_ready=0;
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        for(integer word_index=0;word_index<16;word_index=word_index+1) memory_system.ram.memory[word_index]=32'h10000000+32'(word_index);
        repeat(3) @(negedge clk); rst_n=1;
        check($bits(memory_system.caches[0].enabled.cache.request_tag)==memory_system.MEMORY_ADDRESS_BITS-(ICACHE_SET_BITS!=0 ? ICACHE_SET_BITS : memory_system.CACHE_SET_BITS)-memory_system.CACHE_WORD_BITS,"instruction cache inherits backing address bound");
        check($bits(memory_system.caches[1].enabled.cache.request_tag)==memory_system.MEMORY_ADDRESS_BITS-memory_system.CACHE_SET_BITS-memory_system.CACHE_WORD_BITS,"data cache inherits backing address bound");
        pair(0,0,0,32'h10000000,1,32'h1234,32'h10000000,0,0);
        pair(32'h10000000,0,0,4,0,0,32'h1234,0,32'h10000001);
        pair(32'h10000008,0,0,8,0,0,0,1,32'h10000002);
        pair(0,1,32'hdeadbeef,0,0,0,0,0,32'hdeadbeef);
        check(requests==8 && responses==8 && outstanding==0,"all requests complete exactly once");
        check(handovers==4 && cache_to_mmio==1 && mmio_to_cache==2,"cache and MMIO handover coverage");
        check(mmio_writes==1 && mmio_value==32'h1234,"MMIO side effect occurs once");
        @(negedge clk); maintenance_valid=1;
        @(posedge clk); while(!maintenance_ready) @(posedge clk);
        check(!maintenance_error && memory_system.ram.memory[0]==32'hdeadbeef,"maintenance writes back overlapped store");
        @(negedge clk); maintenance_valid=0;
        @(negedge clk); mmio_allow=0; d_req_valid=1; d_req_address=32'h10000000; d_req_write=1; d_req_data=32'hbad01234;
        @(posedge clk); check(d_req_ready,"MMIO register accepts while peripheral is stalled");
        @(negedge clk); d_req_valid=0; d_req_address=32'h10000008; d_req_data=0; d_req_write=0; d_req_strobe=0;
        repeat(3) begin
            @(posedge clk); check(mmio_req_valid && mmio_req_address==32'h10000000 && mmio_req_data==32'hbad01234 && mmio_req_write && mmio_req_strobe==15 && !d_rsp_valid,"MMIO payload is latched independently of CPU pins");
        end
        @(negedge clk); rst_n=0;
        #1; check(!mmio_req_valid && !d_rsp_valid,"reset discards pending MMIO request");
        repeat(2) @(negedge clk); rst_n=1; mmio_allow=1;
        repeat(6) begin
            @(posedge clk); check(!mmio_req_valid && !d_rsp_valid && mmio_writes==0,"reset request never reaches peripheral");
        end
        $display("PASS %s checks=%0d handovers=%0d",TEST_NAME,checks,handovers);
        $finish;
    end
    initial begin #100000; $fatal(1,"Memory overlap watchdog"); end
endmodule
