`timescale 1ns/1ps
module mmio_shadow_tb;
    parameter integer MEMORY_BITS=14,DATA_SETS=6,INSTRUCTION_SETS=9;
    parameter integer ENABLE_CACHE=1,DATA_OVERLAP=1,FAST_READ=1,FAST_WRITE=1;
    parameter integer MMIO_WAIT=0,MMIO_LATENCY=0;
    localparam integer MEMORY_WORDS=1<<MEMORY_BITS;
    localparam integer REQUESTS=240;
    localparam integer SHADOW=ENABLE_CACHE!=0 && DATA_OVERLAP!=0 && MEMORY_BITS<=26;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    reg d_req_valid=0,d_req_write=0,d_rsp_ready=0,i_req_valid=0,maintenance_valid=0;
    reg [31:0] d_req_address=0,d_req_data=0;
    reg [3:0] d_req_strobe=0;
    wire [1:0] d_req_ready,d_rsp_valid,d_rsp_error,i_req_ready,i_rsp_valid,i_rsp_error;
    wire [31:0] d_rsp_data[0:1],i_rsp_data[0:1];
    wire [1:0] maintenance_ready,maintenance_error;
    wire [1:0] mmio_req_valid,mmio_req_ready,mmio_req_write,mmio_rsp_valid,mmio_rsp_ready,mmio_rsp_error;
    wire [31:0] mmio_req_address[0:1],mmio_req_data[0:1],mmio_rsp_data[0:1];
    wire [3:0] mmio_req_strobe[0:1];
    wire [31:0] i_hits[0:1],i_misses[0:1],d_hits[0:1],d_misses[0:1],d_writebacks[0:1];
    wire [31:0] mmio_value[0:1],mmio_accepted[0:1],mmio_writes[0:1];
    reg [31:0] golden_memory[0:MEMORY_WORDS-1];
    reg [31:0] expected_data[0:REQUESTS-1];
    reg expected_error[0:REQUESTS-1],expected_write[0:REQUESTS-1];
    reg [31:0] queued_mmio_address[0:REQUESTS-1],queued_mmio_data[0:REQUESTS-1];
    reg queued_mmio_write[0:REQUESTS-1];
    reg [3:0] queued_mmio_strobe[0:REQUESTS-1];
    reg [31:0] golden_mmio=0,mask_value;
    integer accepted=0,responded=0,mmio_queued=0,mmio_served=0,expected_mmio_writes=0;
    integer cycles=0,checks=0,shadow_accepts=0,orphan_accepts=0,shadow_returns=0,handovers=0;
    integer instruction_requests=0,instruction_responses=0;
    reg current_error;
    task automatic check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL mmio_shadow %s cycle=%0d accepted=%0d responded=%0d",label_text,cycles,accepted,responded);
        end
    endtask
    rv32_memory_system_reference #(.MEMORY_ADDRESS_BITS(MEMORY_BITS),.ICACHE_SET_BITS(INSTRUCTION_SETS),.CACHE_SET_BITS(DATA_SETS),.ENABLE_CACHE(ENABLE_CACHE),.DATA_OVERLAP(DATA_OVERLAP),.FAST_DCACHE_READ(FAST_READ),.FAST_DCACHE_WRITE(FAST_WRITE),.FAST_ICACHE_HIT(1),.FETCH_OVERLAP(1)) reference(
        .clk(clk),.rst_n(rst_n),.i_req_valid(i_req_valid),.i_req_ready(i_req_ready[0]),.i_req_address(32'b0),.i_rsp_valid(i_rsp_valid[0]),.i_rsp_ready(1'b1),.i_rsp_data(i_rsp_data[0]),.i_rsp_error(i_rsp_error[0]),
        .d_req_valid(d_req_valid),.d_req_ready(d_req_ready[0]),.d_req_address(d_req_address),.d_req_write(d_req_write),.d_req_data(d_req_data),.d_req_strobe(d_req_strobe),.d_rsp_valid(d_rsp_valid[0]),.d_rsp_ready(d_rsp_ready),.d_rsp_data(d_rsp_data[0]),.d_rsp_error(d_rsp_error[0]),
        .maintenance_valid(maintenance_valid),.maintenance_ready(maintenance_ready[0]),.maintenance_error(maintenance_error[0]),
        .mmio_req_valid(mmio_req_valid[0]),.mmio_req_ready(mmio_req_ready[0]),.mmio_req_address(mmio_req_address[0]),.mmio_req_data(mmio_req_data[0]),.mmio_req_strobe(mmio_req_strobe[0]),.mmio_req_write(mmio_req_write[0]),.mmio_rsp_valid(mmio_rsp_valid[0]),.mmio_rsp_ready(mmio_rsp_ready[0]),.mmio_rsp_data(mmio_rsp_data[0]),.mmio_rsp_error(mmio_rsp_error[0]),
        .i_hit_count(i_hits[0]),.i_miss_count(i_misses[0]),.d_hit_count(d_hits[0]),.d_miss_count(d_misses[0]),.d_writeback_count(d_writebacks[0]));
    rv32_memory_system #(.MEMORY_ADDRESS_BITS(MEMORY_BITS),.ICACHE_SET_BITS(INSTRUCTION_SETS),.CACHE_SET_BITS(DATA_SETS),.ENABLE_CACHE(ENABLE_CACHE),.DATA_OVERLAP(DATA_OVERLAP),.FAST_DCACHE_READ(FAST_READ),.FAST_DCACHE_WRITE(FAST_WRITE),.FAST_ICACHE_HIT(1),.FETCH_OVERLAP(1)) candidate(
        .clk(clk),.rst_n(rst_n),.i_req_valid(i_req_valid),.i_req_ready(i_req_ready[1]),.i_req_address(32'b0),.i_rsp_valid(i_rsp_valid[1]),.i_rsp_ready(1'b1),.i_rsp_data(i_rsp_data[1]),.i_rsp_error(i_rsp_error[1]),
        .d_req_valid(d_req_valid),.d_req_ready(d_req_ready[1]),.d_req_address(d_req_address),.d_req_write(d_req_write),.d_req_data(d_req_data),.d_req_strobe(d_req_strobe),.d_rsp_valid(d_rsp_valid[1]),.d_rsp_ready(d_rsp_ready),.d_rsp_data(d_rsp_data[1]),.d_rsp_error(d_rsp_error[1]),
        .maintenance_valid(maintenance_valid),.maintenance_ready(maintenance_ready[1]),.maintenance_error(maintenance_error[1]),
        .mmio_req_valid(mmio_req_valid[1]),.mmio_req_ready(mmio_req_ready[1]),.mmio_req_address(mmio_req_address[1]),.mmio_req_data(mmio_req_data[1]),.mmio_req_strobe(mmio_req_strobe[1]),.mmio_req_write(mmio_req_write[1]),.mmio_rsp_valid(mmio_rsp_valid[1]),.mmio_rsp_ready(mmio_rsp_ready[1]),.mmio_rsp_data(mmio_rsp_data[1]),.mmio_rsp_error(mmio_rsp_error[1]),
        .i_hit_count(i_hits[1]),.i_miss_count(i_misses[1]),.d_hit_count(d_hits[1]),.d_miss_count(d_misses[1]),.d_writeback_count(d_writebacks[1]));
    for(genvar device_index=0;device_index<2;device_index=device_index+1) begin : devices
        mmio_shadow_device #(.WAIT_CYCLES(MMIO_WAIT),.RESPONSE_LATENCY(MMIO_LATENCY)) device(
            .clk(clk),.rst_n(rst_n),.req_valid(mmio_req_valid[device_index]),.req_ready(mmio_req_ready[device_index]),
            .req_address(mmio_req_address[device_index]),.req_data(mmio_req_data[device_index]),
            .req_write(mmio_req_write[device_index]),.req_strobe(mmio_req_strobe[device_index]),
            .rsp_valid(mmio_rsp_valid[device_index]),.rsp_ready(mmio_rsp_ready[device_index]),
            .rsp_data(mmio_rsp_data[device_index]),.rsp_error(mmio_rsp_error[device_index]),
            .value(mmio_value[device_index]),.accepted(mmio_accepted[device_index]),.writes(mmio_writes[device_index]));
    end
    always @(posedge clk) if(rst_n) begin
        cycles=cycles+1;
        check({d_req_ready[0],d_rsp_valid[0],d_rsp_error[0],i_req_ready[0],i_rsp_valid[0],i_rsp_error[0],maintenance_ready[0],maintenance_error[0]}===
              {d_req_ready[1],d_rsp_valid[1],d_rsp_error[1],i_req_ready[1],i_rsp_valid[1],i_rsp_error[1],maintenance_ready[1],maintenance_error[1]},"cycle-exact CPU and maintenance controls");
        if(d_rsp_valid[0]) check(d_rsp_data[0]===d_rsp_data[1],"cycle-exact valid CPU response data");
        if(i_rsp_valid[0]) check(i_rsp_data[0]===i_rsp_data[1],"cycle-exact instruction response data");
        check({i_hits[0],i_misses[0],d_hits[0],d_misses[0],d_writebacks[0]}===
              {i_hits[1],i_misses[1],d_hits[1],d_misses[1],d_writebacks[1]},"cache counters unchanged");
        check({mmio_req_valid[0],mmio_rsp_ready[0],mmio_value[0],mmio_accepted[0],mmio_writes[0]}===
              {mmio_req_valid[1],mmio_rsp_ready[1],mmio_value[1],mmio_accepted[1],mmio_writes[1]},"cycle-exact peripheral controls and side effects");
        if(mmio_req_valid[0]) check({mmio_req_address[0],mmio_req_data[0],mmio_req_write[0],mmio_req_strobe[0]}===
              {mmio_req_address[1],mmio_req_data[1],mmio_req_write[1],mmio_req_strobe[1]},"cycle-exact full MMIO payload");
        check({candidate.cmd_valid,candidate.cmd_write,candidate.cmd_address,candidate.cmd_length,candidate.w_valid,candidate.w_last}===
              {reference.cmd_valid,reference.cmd_write,reference.cmd_address,reference.cmd_length,reference.w_valid,reference.w_last},"cycle-exact backend commands");
        if(candidate.w_valid) check(candidate.w_data===reference.w_data,"cycle-exact backend write data");
        if(candidate.cmd_valid) begin
            check(candidate.cmd_address[31:28]==0,"MMIO shadow never reaches backend RAM");
            if(ENABLE_CACHE!=0) check((candidate.cmd_address>>(MEMORY_BITS+2))==0,"cached backend stays in physical range");
        end
        if(i_req_valid && i_req_ready[0]) instruction_requests=instruction_requests+1;
        if(i_rsp_valid[0]) instruction_responses=instruction_responses+1;
        if(mmio_req_valid[0] && mmio_req_ready[0]) begin
            check(mmio_served<mmio_queued,"peripheral request must have a CPU owner");
            check({mmio_req_address[0],mmio_req_data[0],mmio_req_write[0],mmio_req_strobe[0]}===
                  {queued_mmio_address[mmio_served],queued_mmio_data[mmio_served],queued_mmio_write[mmio_served],queued_mmio_strobe[mmio_served]},"each MMIO transaction delivered exactly once and in order");
            mmio_served=mmio_served+1;
        end
        if(d_rsp_valid[0] && d_rsp_ready) begin
            check(responded<accepted,"CPU response has an accepted owner");
            check(d_rsp_error[0]===expected_error[responded],"CPU error follows owning request");
            if(expected_error[responded]) check(d_rsp_data[0]==0,"owned error response is zero");
            else if(!expected_write[responded]) check(d_rsp_data[0]===expected_data[responded],"CPU read equals independent architectural model");
            responded=responded+1;
        end
        if(d_req_valid && d_req_ready[0]) begin
            check(accepted<REQUESTS,"request inventory bounded");
            expected_write[accepted]=d_req_write;
            mask_value={{8{d_req_strobe[3]}},{8{d_req_strobe[2]}},{8{d_req_strobe[1]}},{8{d_req_strobe[0]}}};
            if(|d_req_address[31:28]) begin
                current_error=d_req_address[3];
                expected_data[accepted]=current_error ? 32'b0 : golden_mmio;
                queued_mmio_address[mmio_queued]=d_req_address; queued_mmio_data[mmio_queued]=d_req_data;
                queued_mmio_write[mmio_queued]=d_req_write; queued_mmio_strobe[mmio_queued]=d_req_strobe;
                mmio_queued=mmio_queued+1;
                if(d_req_write && !current_error) begin
                    golden_mmio=(golden_mmio & ~mask_value) | (d_req_data & mask_value);
                    expected_mmio_writes=expected_mmio_writes+1;
                end
            end else begin
                current_error=(d_req_address>>(MEMORY_BITS+2))!=0 || d_req_address[1:0]!=0;
                expected_data[accepted]=current_error ? 32'b0 : golden_memory[d_req_address[MEMORY_BITS+1:2]];
                if(d_req_write && !current_error)
                    golden_memory[d_req_address[MEMORY_BITS+1:2]]=(golden_memory[d_req_address[MEMORY_BITS+1:2]] & ~mask_value) | (d_req_data & mask_value);
            end
            expected_error[accepted]=current_error;
            accepted=accepted+1;
            if(d_rsp_valid[0] && d_rsp_ready) handovers=handovers+1;
        end
        if(SHADOW!=0 && candidate.cache_req_valid[1] && candidate.cache_req_ready[1] && |d_req_address[31:28]) begin
            shadow_accepts=shadow_accepts+1;
            if(!(d_req_valid && d_req_ready[0])) begin
                check(candidate.data_mmio,"unowned shadow belongs only to existing MMIO routing state");
                orphan_accepts=orphan_accepts+1;
            end
        end
        if(SHADOW!=0 && candidate.data_mmio && candidate.cache_rsp_valid[1]) begin
            check(candidate.cache_rsp_error[1] && candidate.cache_rsp_data[1]==0,"discarded shadow is only a range error");
            check(candidate.cache_rsp_ready[1],"MMIO shadow is drained even after its CPU owner completes");
            shadow_returns=shadow_returns+1;
        end
        if(cycles>200000) $fatal(1,"FAIL mmio_shadow watchdog");
    end
    task drive(input integer request_index);
        begin
            d_req_valid=request_index<REQUESTS; d_req_write=0; d_req_strobe=15;
            d_req_data=32'h12345678 ^ (32'(request_index)*32'h01020408);
            case(request_index%12)
                0: begin d_req_address=32'h10000000; d_req_write=1; end
                1: d_req_address=32'h10000000;
                2: begin d_req_address=32'hf0000004; d_req_write=1; end
                3: begin d_req_address=32'(request_index%64)*4; d_req_write=1; end
                4: d_req_address=32'((request_index-1)%64)*4;
                5: d_req_address=32'b1<<(MEMORY_BITS+2);
                6: begin d_req_address=32'ha0000008; d_req_write=1; end
                7: d_req_address=0;
                8: begin d_req_address=32'(1+(request_index/12)%15)<<28; d_req_write=1; d_req_strobe=4'(request_index/12); end
                9: d_req_address=32'(1+(request_index/12)%15)<<28;
                10: d_req_address=1;
                11: begin d_req_address=16; d_req_write=1; d_req_strobe=0; end
            endcase
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        for(integer word_index=0;word_index<MEMORY_WORDS;word_index=word_index+1) begin
            golden_memory[word_index]=32'h10203040+32'(word_index);
            candidate.ram.memory[word_index]=golden_memory[word_index];
            reference.ram.memory[word_index]=golden_memory[word_index];
        end
        repeat(3) @(negedge clk); rst_n=1; i_req_valid=1; d_rsp_ready=1; drive(0);
        while(responded<REQUESTS) begin
            @(negedge clk);
            drive(accepted);
            d_rsp_ready=cycles<16 || cycles%7!=2 && cycles%7!=3;
        end
        d_req_valid=0; i_req_valid=0; d_rsp_ready=1;
        repeat(5) @(negedge clk);
        check(accepted==REQUESTS && responded==REQUESTS,"all CPU transactions completed");
        check(instruction_requests==instruction_responses && instruction_requests>100,"concurrent instruction requests all complete");
        check(mmio_served==mmio_queued && mmio_accepted[0]==32'(mmio_queued),"exact peripheral delivery inventory");
        check(mmio_writes[0]==32'(expected_mmio_writes) && mmio_value[0]==golden_mmio,"exact independent MMIO side effects");
        if(SHADOW!=0) begin
            check(shadow_accepts>=mmio_queued && shadow_returns==shadow_accepts,"all accepted shadow errors drained");
            if(MMIO_LATENCY==0) check(orphan_accepts>0,"zero-latency MMIO exercises unowned shadow acceptance");
        end else check(shadow_accepts==0 && shadow_returns==0,"fallback has no shadow traffic");
        maintenance_valid=1;
        @(posedge clk); while(!maintenance_ready[0]) @(posedge clk);
        check(!maintenance_error[0],"maintenance succeeds");
        @(negedge clk); maintenance_valid=0;
        for(integer word_index=0;word_index<MEMORY_WORDS;word_index=word_index+1)
            check(candidate.ram.memory[word_index]===golden_memory[word_index] && reference.ram.memory[word_index]===golden_memory[word_index],"full memory equals independent model after writeback");
        $display("PASS mmio_shadow checks=%0d cycles=%0d requests=%0d mmio=%0d writes=%0d shadow=%0d orphan=%0d returns=%0d handovers=%0d",checks,cycles,accepted,mmio_queued,expected_mmio_writes,shadow_accepts,orphan_accepts,shadow_returns,handovers);
        $finish;
    end
endmodule

module mmio_shadow_device #(
    parameter integer WAIT_CYCLES=0,
    parameter integer RESPONSE_LATENCY=0
)(
    input wire clk,rst_n,req_valid,
    output wire req_ready,
    input wire [31:0] req_address,req_data,
    input wire req_write,
    input wire [3:0] req_strobe,
    output wire rsp_valid,
    input wire rsp_ready,
    output wire [31:0] rsp_data,
    output wire rsp_error,
    output reg [31:0] value,accepted,writes
);
    reg pending=0,stored_error=0;
    reg [31:0] stored_data=0;
    integer wait_count=0,delay_count=0;
    wire immediate_response=RESPONSE_LATENCY==0 && req_valid && req_ready;
    wire [31:0] mask={{8{req_strobe[3]}},{8{req_strobe[2]}},{8{req_strobe[1]}},{8{req_strobe[0]}}};
    assign req_ready=!pending && wait_count>=WAIT_CYCLES;
    assign rsp_valid=(pending && delay_count==0) || immediate_response;
    assign rsp_error=immediate_response ? req_address[3] : stored_error;
    assign rsp_data=immediate_response ? (req_address[3] ? 32'b0 : value) : stored_data;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            pending<=0; stored_error<=0; stored_data<=0; wait_count<=0; delay_count<=0;
            value<=0; accepted<=0; writes<=0;
        end else begin
            if(!req_valid || req_ready) wait_count<=0;
            else wait_count<=wait_count+1;
            if(pending) begin
                if(delay_count>0) delay_count<=delay_count-1;
                else if(rsp_ready) pending<=0;
            end
            if(req_valid && req_ready) begin
                accepted<=accepted+1;
                stored_data<=req_address[3] ? 32'b0 : value;
                stored_error<=req_address[3];
                delay_count<=RESPONSE_LATENCY>0 ? RESPONSE_LATENCY-1 : 0;
                pending<=!(RESPONSE_LATENCY==0 && rsp_ready);
                if(req_write && !req_address[3]) begin
                    value<=(value & ~mask) | (req_data & mask);
                    writes<=writes+1;
                end
            end
        end
    end
endmodule
