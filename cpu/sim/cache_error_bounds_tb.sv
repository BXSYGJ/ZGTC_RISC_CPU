`timescale 1ns/1ps
module cache_error_bounds_tb;
    parameter integer ADDRESS_BITS=10;
    parameter integer SET_BITS=1;
    parameter integer READ_ONLY=0;
    parameter integer FAST_READ_HIT=1;
    parameter integer FAST_WRITE_HIT=1;
    parameter integer READ_OVERLAP=1;
    parameter TEST_NAME="cache_error_bounds";
    localparam integer MEMORY_WORDS=1<<(ADDRESS_BITS-2);
    localparam [31:0] LIMIT=32'd1<<ADDRESS_BITS;
    localparam [31:0] LAST_WORD=LIMIT-4;
    localparam integer LINES=2*(1<<SET_BITS);
    reg clk=0,rst_n=0,req_valid=0,req_write=0,rsp_ready=0,flush_valid=0;
    always #5 clk=~clk;
    reg [31:0] req_address=0,req_data=0;
    reg [3:0] req_strobe=15;
    wire req_ready,rsp_valid,rsp_error,flush_ready,flush_error;
    wire [31:0] rsp_data;
    wire cmd_valid,cmd_ready,cmd_write,w_valid,w_ready,w_last,b_valid,b_ready,b_error;
    wire r_valid,r_ready,r_last,r_error;
    wire [31:0] cmd_address,w_data,r_data,hit_count,miss_count,writeback_count;
    wire [7:0] cmd_length;
    integer checks=0,commands=0,writes=0,saved_commands,saved_writes;
    reg [31:0] saved_hits,saved_misses;
    reg [LINES-1:0] saved_valid,saved_dirty;
    reg [(1<<SET_BITS)-1:0] saved_lru;
    reg [31:0] first_expected,last_expected;
    rv32_cache #(.ADDRESS_BITS(ADDRESS_BITS),.SET_BITS(SET_BITS),.WORD_BITS(2),.READ_ONLY(READ_ONLY),.FAST_READ_HIT(FAST_READ_HIT),.FAST_WRITE_HIT(FAST_WRITE_HIT),.READ_OVERLAP(READ_OVERLAP)) cache(.*);
    rv32_burst_ram #(.ADDRESS_BITS(ADDRESS_BITS-2),.BUFFER_BITS(2)) backend(
        .clk(clk),.rst_n(rst_n),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_write(cmd_write),.cmd_address(cmd_address),.cmd_length(cmd_length),
        .w_valid(w_valid),.w_ready(w_ready),.w_data(w_data),.w_last(w_last),.b_valid(b_valid),.b_ready(b_ready),.b_error(b_error),
        .r_valid(r_valid),.r_ready(r_ready),.r_data(r_data),.r_last(r_last),.r_error(r_error)
    );
    task automatic check(input bit condition,input string label_text);
        begin checks=checks+1; if(!condition) $fatal(1,"FAIL cache_error_bounds %s address=%08x",label_text,req_address); end
    endtask
    always @(posedge clk) if(rst_n && cmd_valid && cmd_ready) begin
        commands=commands+1; if(cmd_write) writes=writes+1;
        check(cmd_address[3:0]==0 && cmd_length==3,"backend line geometry");
        check({1'b0,cmd_address}+33'd16<={1'b0,LIMIT},"backend command stays in physical range");
    end
    task automatic transact(input [31:0] address,input bit writing,input [31:0] data_value,input bit expected_error,input [31:0] expected_data);
        reg [31:0] held_data;
        reg held_error;
        begin
            @(negedge clk); req_valid=1; req_address=address; req_write=writing; req_data=data_value; rsp_ready=0;
            @(posedge clk); while(!req_ready) @(posedge clk);
            @(negedge clk); req_valid=0;
            if(expected_error) check(rsp_valid && rsp_error && rsp_data==0,"invalid input responds immediately after acceptance");
            @(posedge clk); while(!rsp_valid) @(posedge clk);
            check(rsp_error===expected_error,"physical address response error");
            if(expected_error) check(rsp_data==0,"bounded errors return zero data");
            if(!writing && !expected_error) check(rsp_data===expected_data,"physical address read data");
            held_data=rsp_data; held_error=rsp_error;
            repeat(3) begin
                @(posedge clk); check(rsp_valid && rsp_error===held_error && rsp_data===held_data,"bounded response remains stable");
            end
            @(negedge clk); rsp_ready=1;
            @(posedge clk);
            @(negedge clk); rsp_ready=0;
            check(!rsp_valid,"single bounded response consumed");
        end
    endtask
    task automatic overlap_fault;
        begin
            @(negedge clk); req_valid=1; req_address=0; req_write=0; rsp_ready=0;
            @(posedge clk); check(req_ready,"overlap starts idle");
            @(negedge clk); req_address=LIMIT;
            @(posedge clk); while(!rsp_valid) @(posedge clk);
            repeat(3) begin
                check(!req_ready && rsp_valid && !rsp_error && rsp_data==first_expected,"held valid response precedes invalid alias");
                @(posedge clk);
            end
            @(negedge clk); rsp_ready=1;
            @(posedge clk); check(req_ready && rsp_valid && !rsp_error,"valid response overlaps invalid request");
            @(negedge clk); req_address=LAST_WORD;
            @(posedge clk); check(req_ready && rsp_valid && rsp_error,"invalid response overlaps valid request");
            @(negedge clk); req_valid=0;
            @(posedge clk); while(!rsp_valid) @(posedge clk);
            check(!rsp_error && rsp_data==last_expected,"valid successor survives invalid alias");
            @(negedge clk); rsp_ready=0;
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        for(integer word_index=0;word_index<MEMORY_WORDS;word_index=word_index+1) backend.memory[word_index]=32'h10000000+32'(word_index);
        repeat(3) @(negedge clk); rst_n=1;
        check($bits(cache.request_tag)==ADDRESS_BITS-SET_BITS-4,"bounded tag width follows physical geometry");
        transact(LIMIT,0,0,1,0);
        check(commands==0 && hit_count==0 && miss_count==0,"cold invalid access never reaches cache lookup or backend");
        first_expected=32'h10000000; last_expected=32'h10000000+32'(MEMORY_WORDS-1);
        transact(0,0,0,0,first_expected);
        transact(LAST_WORD,0,0,0,last_expected);
        if(READ_ONLY==0) begin
            first_expected=32'hdeadbeef; last_expected=32'hcafebeef;
            transact(0,1,first_expected,0,0);
            transact(LAST_WORD,1,last_expected,0,0);
        end
        saved_commands=commands; saved_writes=writes; saved_hits=hit_count; saved_misses=miss_count;
        saved_valid=cache.valid; saved_dirty=cache.dirty;
        for(integer saved_set=0;saved_set<(1<<SET_BITS);saved_set=saved_set+1) saved_lru[saved_set]=cache.lru_storage[saved_set];
        for(integer upper_bit=ADDRESS_BITS;upper_bit<32;upper_bit=upper_bit+1) begin
            transact((32'b1<<upper_bit)|4,0,0,1,0);
            transact((32'b1<<upper_bit)|LAST_WORD,1,32'h87654321,1,0);
            check(commands==saved_commands && writes==saved_writes,"invalid alias causes no backend side effects");
            check(hit_count==saved_hits && miss_count==saved_misses,"invalid alias does not become a cache lookup");
            check(cache.valid==saved_valid && cache.dirty==saved_dirty,"invalid alias leaves cache metadata unchanged");
            for(integer checked_set=0;checked_set<(1<<SET_BITS);checked_set=checked_set+1)
                check(cache.lru_storage[checked_set]===saved_lru[checked_set],"invalid alias leaves LRU array unchanged");
        end
        transact(0,0,0,0,first_expected);
        transact(LAST_WORD,0,0,0,last_expected);
        for(integer alignment=1;alignment<4;alignment=alignment+1) begin
            transact(32'(alignment),0,0,1,0);
            transact(LAST_WORD+32'(alignment),1,32'hffffffff,1,0);
        end
        if(READ_ONLY!=0) transact(0,1,32'habcdef01,1,0);
        if(READ_OVERLAP!=0) overlap_fault();
        check(commands==saved_commands && writes==saved_writes,"hot and invalid accesses do not evict dirty data");
        check(backend.memory[0]==32'h10000000 && backend.memory[MEMORY_WORDS-1]==32'h10000000+32'(MEMORY_WORDS-1),"write-back has not committed early");
        @(negedge clk); flush_valid=1;
        @(posedge clk); while(!flush_ready) @(posedge clk);
        check(!flush_error,"bounded dirty flush succeeds");
        @(negedge clk); flush_valid=0;
        check(backend.memory[0]==first_expected && backend.memory[MEMORY_WORDS-1]==last_expected,"first and last dirty lines write back to full addresses");
        check(writes==saved_writes+(READ_ONLY==0 ? 2 : 0),"exact dirty writeback count");
        transact(0,0,0,0,first_expected);
        transact(LAST_WORD,0,0,0,last_expected);
        $display("PASS %s checks=%0d address_bits=%0d sets_bits=%0d",TEST_NAME,checks,ADDRESS_BITS,SET_BITS);
        $finish;
    end
    initial begin #1000000; $fatal(1,"Cache bounds watchdog"); end
endmodule
