`timescale 1ns/1ps
module cache_valid_banks_pairs_tb;
    parameter integer ADDRESS_BITS=16;
    parameter integer READONLY=0;
    parameter integer FAST_READ_HIT=1;
    parameter integer FAST_WRITE_HIT=1;
    parameter integer READ_OVERLAP=1;
    parameter integer CACHE_SET_BITS=1;
    parameter integer GEOMETRY_STREAM=0;
    parameter integer CHECK_SYNC_READ=0;
    parameter integer CHECK_SYNC_WRITE=0;
    parameter integer CHECK_TAG_PIPELINE=0;
    cache_tb #(.ADDRESS_BITS(ADDRESS_BITS),.READONLY(READONLY),.FAST_READ_HIT(FAST_READ_HIT),
        .FAST_WRITE_HIT(FAST_WRITE_HIT),.READ_OVERLAP(READ_OVERLAP),.CHECK_REQUEST_CAPTURE(2),
        .CACHE_SET_BITS(CACHE_SET_BITS),.GEOMETRY_STREAM(GEOMETRY_STREAM),
        .CHECK_TAG_PIPELINE(CHECK_TAG_PIPELINE)) exercised();
    wire ref_req_ready,ref_rsp_valid,ref_rsp_error,ref_flush_ready,ref_flush_error;
    wire ref_cmd_valid,ref_cmd_write,ref_w_valid,ref_w_last,ref_b_ready,ref_r_ready;
    wire [31:0] ref_rsp_data,ref_cmd_address,ref_w_data,ref_hits,ref_misses,ref_writebacks;
    wire [7:0] ref_cmd_length;
    reg [31:0] expected_address=0,expected_data=0;
    reg [3:0] expected_strobe=0;
    reg expected_write=0;
    integer idle_samples=0,busy_holds=0,backpressure_holds=0,flush_holds=0,overlap_samples=0,compared_cycles=0;
    integer readonly_checks=0;
    rv32_cache_reference #(.ADDRESS_BITS(ADDRESS_BITS),.SET_BITS(CACHE_SET_BITS),.WORD_BITS(2),.READ_ONLY(READONLY),
        .FAST_READ_HIT(FAST_READ_HIT),.FAST_WRITE_HIT(FAST_WRITE_HIT),.READ_OVERLAP(READ_OVERLAP)) reference_cache(
        .clk(exercised.clk),.rst_n(exercised.rst_n),.req_valid(exercised.req_valid),.req_ready(ref_req_ready),
        .req_address(exercised.req_address),.req_write(exercised.req_write),.req_data(exercised.req_data),
        .req_strobe(exercised.req_strobe),.rsp_valid(ref_rsp_valid),.rsp_ready(exercised.rsp_ready),
        .rsp_data(ref_rsp_data),.rsp_error(ref_rsp_error),.flush_valid(exercised.flush_valid),
        .flush_ready(ref_flush_ready),.flush_error(ref_flush_error),.cmd_valid(ref_cmd_valid),
        .cmd_ready(exercised.cmd_ready),.cmd_write(ref_cmd_write),.cmd_address(ref_cmd_address),
        .cmd_length(ref_cmd_length),.w_valid(ref_w_valid),.w_ready(exercised.w_ready),.w_data(ref_w_data),
        .w_last(ref_w_last),.b_valid(exercised.b_valid),.b_ready(ref_b_ready),.b_error(exercised.b_error),
        .r_valid(exercised.r_valid),.r_ready(ref_r_ready),.r_data(exercised.r_data),.r_last(exercised.r_last),
        .r_error(exercised.r_error),.hit_count(ref_hits),.miss_count(ref_misses),.writeback_count(ref_writebacks));
    task automatic check(input bit condition,input string label_text);
        if(!condition) $fatal(1,"FAIL cache ready payload %s cycle=%0d",label_text,compared_cycles);
    endtask
    always @(posedge exercised.clk) begin
        if(!exercised.rst_n) begin
            expected_address=0; expected_data=0; expected_strobe=0; expected_write=0;
        end else begin
            compared_cycles=compared_cycles+1;
            check({exercised.req_ready,exercised.rsp_valid,exercised.rsp_error,exercised.flush_ready,
                exercised.flush_error,exercised.cmd_valid,exercised.w_valid,exercised.b_ready,exercised.r_ready}===
                {ref_req_ready,ref_rsp_valid,ref_rsp_error,ref_flush_ready,ref_flush_error,ref_cmd_valid,
                ref_w_valid,ref_b_ready,ref_r_ready},"reference control equivalence");
            check({exercised.hit_count,exercised.miss_count,exercised.writeback_count}===
                {ref_hits,ref_misses,ref_writebacks},"reference counters equivalence");
            check({exercised.cache.state,exercised.cache.valid,exercised.cache.dirty}===
                {reference_cache.state,reference_cache.valid,reference_cache.dirty},
                "reference transaction and cache metadata equivalence");
            for(integer metadata_set=0;metadata_set<(1<<CACHE_SET_BITS);metadata_set=metadata_set+1)
                check(exercised.cache.lru_storage[metadata_set]===reference_cache.lru_storage[metadata_set],
                    "reference LRU array equivalence");
            check({exercised.cache.lookup_valid0,exercised.cache.lookup_valid1}===
                {reference_cache.lookup_valid0,reference_cache.lookup_valid1},"reference sampled validity equivalence");
            if(exercised.rsp_valid) check(exercised.rsp_data===ref_rsp_data,"reference valid response data");
            if(exercised.cmd_valid) check({exercised.cmd_write,exercised.cmd_address,exercised.cmd_length}===
                {ref_cmd_write,ref_cmd_address,ref_cmd_length},"reference memory command");
            if(exercised.w_valid) check({exercised.w_data,exercised.w_last}==={ref_w_data,ref_w_last},
                "reference writeback payload");
            if(READONLY!=0) begin
                check(exercised.cache.dirty==='0 && !exercised.w_valid &&
                    !(exercised.cmd_valid && exercised.cmd_write) && exercised.writeback_count==0,
                    "readonly cache never dirties a line or issues writeback");
                check(exercised.w_data===32'b0,"readonly writeback payload is statically zero");
                readonly_checks=readonly_checks+1;
            end
            if(exercised.req_ready) begin
                expected_address={{(32-ADDRESS_BITS){1'b0}},exercised.req_address[ADDRESS_BITS-1:0]};
                expected_data=exercised.req_data; expected_strobe=exercised.req_strobe; expected_write=exercised.req_write;
                if(!exercised.req_valid && exercised.cache.state==0) idle_samples=idle_samples+1;
                if(exercised.req_valid && exercised.rsp_valid && exercised.rsp_ready) overlap_samples=overlap_samples+1;
            end else begin
                busy_holds=busy_holds+1;
                if(exercised.rsp_valid && !exercised.rsp_ready) backpressure_holds=backpressure_holds+1;
                if(exercised.flush_valid) flush_holds=flush_holds+1;
            end
        end
        #1;
        check({exercised.cache.request_address,exercised.cache.request_data,exercised.cache.request_strobe,
            exercised.cache.request_write}==={expected_address,expected_data,expected_strobe,expected_write},
            "all payload registers sample only in ready window and hold otherwise");
    end
    generate if(CHECK_SYNC_READ!=0 && READONLY!=0) begin : sync_read_coverage
        integer forwarded_way0=0,forwarded_way1=0;
        always @(posedge exercised.clk) if(exercised.rst_n && exercised.cache.state==1) begin
            if(exercised.cache.hit0 && exercised.cache.synchronous_readonly.forward_way0)
                forwarded_way0=forwarded_way0+1;
            if(exercised.cache.hit1 && exercised.cache.synchronous_readonly.forward_way1)
                forwarded_way1=forwarded_way1+1;
        end
        final begin
            if(forwarded_way0==0 || forwarded_way1==0) $fatal(1,"FAIL cache synchronous final-beat forwarding coverage");
            $display("SYNC_READ forwarded_way0=%0d forwarded_way1=%0d",forwarded_way0,forwarded_way1);
        end
    end endgenerate

    generate if(CHECK_SYNC_WRITE!=0 && READONLY==0) begin : sync_write_coverage
        integer forwarded_way0=0,forwarded_way1=0,writeback_starts=0,writeback_beats=0,writeback_stalls=0;
        integer store_collisions=0;
        always @(posedge exercised.clk) if(exercised.rst_n) begin
            if(exercised.cache.state==1) begin
                if(exercised.cache.hit0 && exercised.cache.synchronous_writable.forward_way0)
                    forwarded_way0=forwarded_way0+1;
                if(exercised.cache.hit1 && exercised.cache.synchronous_writable.forward_way1)
                    forwarded_way1=forwarded_way1+1;
            end
            if(exercised.cache.synchronous_writable.store_hit &&
                exercised.cache.synchronous_writable.store_index==exercised.cache.synchronous_writable.read_index)
                store_collisions=store_collisions+1;
            if(exercised.cache.state==2 && exercised.cmd_ready) writeback_starts=writeback_starts+1;
            if(exercised.w_valid) begin
                if(exercised.w_ready) writeback_beats=writeback_beats+1;
                else writeback_stalls=writeback_stalls+1;
            end
        end
        final begin
            if(forwarded_way0==0 || forwarded_way1==0 || store_collisions==0 ||
                writeback_starts==0 || writeback_beats==0 || writeback_stalls==0)
                $fatal(1,"FAIL cache synchronous writable forwarding/writeback coverage");
            $display("SYNC_WRITE forward0=%0d forward1=%0d stores=%0d wb_starts=%0d wb_beats=%0d wb_stalls=%0d",
                forwarded_way0,forwarded_way1,store_collisions,writeback_starts,writeback_beats,writeback_stalls);
        end
    end endgenerate
    final begin
        if(!(idle_samples>=16 && busy_holds>100 && backpressure_holds>100 && flush_holds>0))
            $fatal(1,"FAIL cache ready payload idle busy backpressure flush coverage");
        if(READ_OVERLAP!=0 && overlap_samples==0) $fatal(1,"FAIL cache ready payload accepted overlap coverage");
        if(READONLY!=0 && readonly_checks<100) $fatal(1,"FAIL cache readonly writeback coverage");
        if(READONLY!=0) $display("READONLY_WRITEBACK invariant_cycles=%0d",readonly_checks);
        $display("READY_PAYLOAD idle=%0d busy=%0d backpressure=%0d flush=%0d overlap=%0d compared=%0d",
            idle_samples,busy_holds,backpressure_holds,flush_holds,overlap_samples,compared_cycles);
    end
endmodule
