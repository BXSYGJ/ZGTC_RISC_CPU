`timescale 1ns/1ps
module cache_tb;
    parameter integer ADDRESS_BITS=32;
    parameter TEST_NAME="";
    parameter integer READONLY=0;
    parameter integer FAST_READ_HIT=0;
    parameter integer FAST_WRITE_HIT=0;
    parameter integer READ_OVERLAP=0;
    parameter integer CHECK_LOOKUP_DATA=0;
    parameter integer CHECK_REQUEST_CAPTURE=0;
    parameter integer CACHE_SET_BITS=1;
    parameter integer GEOMETRY_STREAM=0;
    parameter integer CHECK_TAG_PIPELINE=0;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,req_valid=0,req_write=0,rsp_ready=0,flush_valid=0;
    reg [31:0] req_address=0,req_data=0;
    reg [3:0] req_strobe=0;
    wire req_ready,rsp_valid,rsp_error,flush_ready,flush_error;
    wire [31:0] rsp_data;
    wire cmd_valid,cmd_write,w_valid,w_last,b_ready,r_ready;
    wire [31:0] cmd_address,w_data;
    wire [7:0] cmd_length;
    reg cmd_ready=0,w_ready=0,b_valid=0,b_error=0,r_valid=0,r_last=0,r_error=0;
    reg [31:0] r_data=0;
    wire [31:0] hit_count,miss_count,writeback_count;
    reg [31:0] memory[0:16383],staging[0:3];
    reg [31:0] golden[0:255];
    reg [31:0] geometry_expected[0:16383];
    reg [31:0] transaction_state=32'h2468ace1;
    reg [31:0] random_address,random_data,random_mask;
    reg [3:0] random_strobe;
    reg random_write;
    reg active=0,active_write=0,active_error=0;
    reg [31:0] active_address=0;
    integer active_beat=0,active_final=3,command_count=0,checks=0,cycles=0,word_index;
    integer snapshot_commands,baseline_writebacks;
    integer lookup_hit_checks=0,lookup_miss_checks=0,valid_data_checks=0;
    integer address_capture_checks=0,address_hold_checks=0,address_reset_checks=0;
    reg [31:0] expected_request_address=0;
    reg [31:0] random_state=32'h98765432;
    reg inject_read_error=0,inject_write_error=0,inject_early_last=0,inject_late_last=0;
    reg cmd_held=0,w_held=0;
    reg [31:0] held_address,held_data;
    reg held_write,held_last;
    reg [7:0] held_length;
    rv32_cache #(.ADDRESS_BITS(ADDRESS_BITS),.SET_BITS(CACHE_SET_BITS),.WORD_BITS(2),.READ_ONLY(READONLY),.FAST_WRITE_HIT(FAST_WRITE_HIT),.FAST_READ_HIT(FAST_READ_HIT),.READ_OVERLAP(READ_OVERLAP)) cache(.*);
    task automatic check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL cache %s cycle=%0d addr=%08x response=%08x error=%b",label_text,cycles,req_address,rsp_data,rsp_error);
        end
    endtask
    always @(posedge clk) if(rst_n && CHECK_LOOKUP_DATA!=0) begin
        if(cache.fast_lookup && !rsp_error) begin
            check(rsp_data===cache.current_word,"lookup data independent of hit qualification");
            if(cache.hit0 || cache.hit1) lookup_hit_checks=lookup_hit_checks+1;
            else begin
                check(!rsp_valid,"lookup miss never invents a response");
                lookup_miss_checks=lookup_miss_checks+1;
            end
        end
        if(rsp_valid) begin
            check(rsp_data===(rsp_error ? 32'b0 : cache.fast_hit ? cache.current_word : cache.response_data),
                "valid response equals hit-qualified reference value");
            valid_data_checks=valid_data_checks+1;
        end
    end
    always @(posedge clk) if(CHECK_REQUEST_CAPTURE!=0) begin
        if(!rst_n) begin
            expected_request_address=0;
            address_reset_checks=address_reset_checks+1;
        end else if(req_ready && (req_valid || CHECK_REQUEST_CAPTURE==2)) begin
            expected_request_address={{(32-ADDRESS_BITS){1'b0}},req_address[ADDRESS_BITS-1:0]};
            address_capture_checks=address_capture_checks+1;
        end else address_hold_checks=address_hold_checks+1;
        #1;
        check(cache.request_address===expected_request_address,"request address capture/hold/reset");
    end
    always @(negedge clk) if(CHECK_REQUEST_CAPTURE==2) begin
        #1;
        if(rst_n && !req_valid) begin
            req_address=random_state | 32'h80000003;
            if(CHECK_TAG_PIPELINE!=0 && !req_ready)
                req_address=(cache.request_address ^ 32'h10) | 32'h3;
            req_data=~random_state; req_strobe=random_state[7:4]; req_write=random_state[8];
        end
    end
    task slow_overlap_stream;
        integer accepted_requests,received_responses,stream_cycles;
        begin
            accepted_requests=0; received_responses=0; stream_cycles=0;
            @(negedge clk); req_valid=1; req_write=0; req_address=0; rsp_ready=1;
            while(received_responses<64) begin
                @(posedge clk);
                stream_cycles=stream_cycles+1;
                if(req_valid && req_ready) accepted_requests=accepted_requests+1;
                if(rsp_valid && rsp_ready) begin
                    check(!rsp_error && rsp_data===(32'h10000000+32'(received_responses%4)),"ordered handshaked slow overlap response");
                    received_responses=received_responses+1;
                end
                @(negedge clk);
                req_valid=accepted_requests<64; req_address=32'(accepted_requests%4)*4;
                rsp_ready=(stream_cycles%5)!=0;
            end
            req_valid=0; rsp_ready=0;
            check(accepted_requests==64,"slow overlap accepts exactly the returned requests");
        end
    endtask
    task transact(input [31:0] address,input bit writing,input [31:0] data_value,input [3:0] strobe,input [31:0] expected,input bit expected_error);
        reg [31:0] held_response;
        reg held_error;
        begin
            @(negedge clk); req_valid=1; req_address=address; req_write=writing; req_data=data_value; req_strobe=strobe;
            @(posedge clk); while(!req_ready) @(posedge clk);
            @(negedge clk); req_valid=0;
            @(posedge clk); while(!rsp_valid) @(posedge clk);
            check(rsp_error===expected_error,"response error");
            if(expected_error) check(rsp_data==0,"cache errors return zero data");
            if(!writing && !expected_error) check(rsp_data===expected,"read data");
            held_response=rsp_data; held_error=rsp_error;
            repeat(3) begin
                @(posedge clk); check(rsp_valid && rsp_data===held_response && rsp_error===held_error,"response backpressure stability");
            end
            @(negedge clk); rsp_ready=1;
            @(posedge clk);
            @(negedge clk); rsp_ready=0;
        end
    endtask
    task flush_cache(input bit expected_error);
        begin
            @(negedge clk); flush_valid=1;
            @(posedge clk); while(!flush_ready) @(posedge clk);
            check(flush_error===expected_error,"flush result");
            @(negedge clk); flush_valid=0;
        end
    endtask
    task overlap_pair(input bit first_write,input [31:0] first_data,input [3:0] first_strobe,
                      input bit second_write,input [31:0] second_data,input [3:0] second_strobe,
                      input [31:0] first_expected,input [31:0] second_expected);
        begin
            @(negedge clk); req_valid=1; req_address=0; req_write=first_write; req_data=first_data; req_strobe=first_strobe; rsp_ready=1;
            @(posedge clk); check(req_ready,"RW pair starts idle");
            @(negedge clk); req_write=second_write; req_data=second_data; req_strobe=second_strobe;
            @(posedge clk); while(!rsp_valid) @(posedge clk);
            check(req_ready && !rsp_error,"RW response accepts successor");
            if(!first_write) check(rsp_data===first_expected,"read before overlapped write sees old value");
            @(negedge clk); req_valid=0;
            @(posedge clk); while(!rsp_valid) @(posedge clk);
            check(!rsp_error,"RW successor succeeds");
            if(!second_write) check(rsp_data===second_expected,"read after overlapped write sees new value");
            @(negedge clk); rsp_ready=0;
            check(!rsp_valid && req_ready,"RW pair consumes each response once");
        end
    endtask
    task overlap_read_write;
        reg [31:0] previous_hits;
        begin
            previous_hits=hit_count;
            overlap_pair(0,0,0,1,32'habcdef12,4'b0101,32'h10000000,0);
            overlap_pair(1,32'h76543210,4'b1010,0,0,0,0,32'h76cd3212);
            overlap_pair(1,32'h00000034,4'b0001,1,32'h00560000,4'b0100,0,0);
            transact(0,0,0,0,32'h76563234,0);
            check(hit_count==previous_hits+7,"RW overlap counts seven requests exactly once");
            flush_cache(0);
            check(memory[0]==32'h76563234,"RW overlapped writes survive dirty flush");
            transact(0,1,32'h10000000,15,0,0);
            flush_cache(0);
            transact(0,0,0,0,32'h10000000,0);
            snapshot_commands=command_count;
        end
    endtask
    task fast_write_checks;
        reg [31:0] expected_word,write_value,strobe_mask,saved_hits,stream_base;
        integer saved_commands;
        begin
            expected_word=memory[0];
            transact(0,0,0,0,expected_word,0);
            saved_commands=command_count;
            for(integer strobe_index=0;strobe_index<16;strobe_index=strobe_index+1) begin
                saved_hits=hit_count;
                write_value=32'ha5963cc3 ^ (32'(strobe_index)*32'h01020304);
                strobe_mask={{8{strobe_index[3]}},{8{strobe_index[2]}},{8{strobe_index[1]}},{8{strobe_index[0]}}};
                @(negedge clk); req_valid=1; req_write=1; req_address=0; req_data=write_value; req_strobe=4'(strobe_index); rsp_ready=0;
                @(posedge clk); check(req_ready,"hot write accepts request");
                @(negedge clk); req_valid=0; req_address=4; req_write=0; req_data=~write_value; req_strobe=0;
                @(posedge clk);
                check(rsp_valid && !rsp_error,"hot write responds on lookup cycle");
                check(rsp_data===expected_word,"hot write response contains previous word");
                repeat(3) begin
                    @(posedge clk);
                    check(rsp_valid && !rsp_error && rsp_data===expected_word && !req_ready,"hot write holds previous word under backpressure");
                end
                check(hit_count==saved_hits+1 && command_count==saved_commands,"blocked write counted once without backend command");
                if(strobe_index==0) check(!cache.dirty[cache.hit_line],"zero-strobe fast write keeps clean line clean");
                @(negedge clk); rsp_ready=1;
                @(posedge clk); check(rsp_valid && rsp_data===expected_word,"write response consumed once");
                @(negedge clk); rsp_ready=0;
                expected_word=(expected_word & ~strobe_mask) | (write_value & strobe_mask);
                transact(0,0,0,0,expected_word,0);
            end
            if(READ_OVERLAP!=0) begin
                saved_hits=hit_count; stream_base=expected_word;
                @(negedge clk); req_valid=1; req_write=1; req_address=0; req_data=stream_base+1; req_strobe=15; rsp_ready=1;
                @(posedge clk); check(req_ready,"write stream accepts first request");
                for(integer stream_index=0;stream_index<64;stream_index=stream_index+1) begin
                    @(negedge clk); req_valid=stream_index!=63; req_data=stream_base+32'(stream_index)+2;
                    @(posedge clk);
                    check(rsp_valid && req_ready && !rsp_error,"one ordered write response per cycle");
                    check(rsp_data===stream_base+32'(stream_index),"write stream returns sequential previous values");
                end
                @(negedge clk); rsp_ready=0;
                check(!rsp_valid && req_ready && hit_count==saved_hits+64 && command_count==saved_commands,"write stream drains and counts exactly once");
                expected_word=stream_base+64;
                transact(0,0,0,0,expected_word,0);
            end
            flush_cache(0);
            check(memory[0]===expected_word,"fast writes survive dirty flush");
            transact(0,0,0,0,expected_word,0);
            @(negedge clk); req_valid=1; req_address=0; req_write=1; req_data=~expected_word; req_strobe=15; rsp_ready=1;
            @(posedge clk); check(req_ready,"reset probe accepts write request");
            @(negedge clk); req_valid=0; rst_n=0;
            #1; check(!rsp_valid,"reset cancels write before lookup commit edge");
            @(negedge clk); rst_n=1; rsp_ready=0;
            repeat(3) begin @(posedge clk); check(!rsp_valid,"reset write does not leak a response"); end
            transact(0,0,0,0,expected_word,0);
            flush_cache(0);
            check(memory[0]===expected_word,"reset-canceled write has no stored side effect");
        end
    endtask
    task overlap_stream;
        reg [31:0] previous_hits;
        begin
            previous_hits=hit_count;
            @(negedge clk); req_valid=1; req_address=0; req_write=0; rsp_ready=1;
            @(posedge clk); check(req_ready,"stream first request");
            for(integer stream_index=0;stream_index<64;stream_index=stream_index+1) begin
                @(negedge clk); req_valid=stream_index!=63; req_address=32'((stream_index+1)%4)*4;
                @(posedge clk);
                check(rsp_valid && !rsp_error && rsp_data==32'h10000000+32'(stream_index%4),"one ordered hot response per cycle");
                check(req_ready,"response accepts next request without idle bubble");
            end
            @(negedge clk); rsp_ready=0;
            check(!rsp_valid && hit_count==previous_hits+64 && command_count==snapshot_commands,"stream drains and counts exactly once");
            req_valid=1; req_address=0; req_write=0;
            @(posedge clk); check(req_ready,"backpressure first request");
            @(negedge clk); req_address=4;
            repeat(4) begin
                @(posedge clk); check(rsp_valid && !rsp_error && rsp_data==32'h10000000 && !req_ready,"blocked response blocks next request");
            end
            @(negedge clk); rsp_ready=1;
            @(posedge clk); check(req_ready && rsp_valid,"release consumes and replaces");
            @(negedge clk); req_address=2;
            @(posedge clk); check(req_ready && rsp_valid && !rsp_error && rsp_data==32'h10000001,"valid to misaligned overlap");
            @(negedge clk); req_address=0;
            @(posedge clk); check(req_ready && rsp_valid && rsp_error,"error response accepts recovery request");
            @(negedge clk); req_address=8; flush_valid=1;
            @(posedge clk); check(rsp_valid && !rsp_error && rsp_data==32'h10000000 && !req_ready,"flush blocks replacement request");
            @(negedge clk); req_valid=0; rsp_ready=0;
            @(posedge clk); while(!flush_ready) @(posedge clk);
            check(!flush_error,"overlap flush completes");
            @(negedge clk); flush_valid=0;
            transact(0,0,0,0,32'h10000000,0);
            snapshot_commands=command_count;
        end
    endtask
    always @(negedge clk) begin
        if(rst_n) begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            cmd_ready=!active && !b_valid && !r_valid && random_state[0];
            w_ready=active && active_write && !b_valid && random_state[1];
        end
    end
    always @(posedge clk) begin
        if(rst_n) begin
            cycles=cycles+1;
            if(cmd_held) check(cmd_valid && cmd_address===held_address && cmd_write===held_write && cmd_length===held_length,"command stability");
            if(w_held) check(w_valid && w_data===held_data && w_last===held_last,"write beat stability");
            cmd_held=cmd_valid && !cmd_ready; held_address=cmd_address; held_write=cmd_write; held_length=cmd_length;
            w_held=w_valid && !w_ready; held_data=w_data; held_last=w_last;
            if(cmd_valid && cmd_ready) begin
                check(!active && cmd_length==3 && cmd_address[3:0]==0,"line burst command");
                command_count=command_count+1;
                active<=1; active_write<=cmd_write; active_address<=cmd_address; active_beat<=0;
                active_error<=cmd_write ? inject_write_error : inject_read_error;
                active_final<=inject_early_last ? 1 : inject_late_last ? 4 : 3;
            end
            if(active && !active_write && !r_valid && random_state[2]) begin
                r_valid<=1; r_data<=memory[int'(active_address[15:2])+active_beat];
                r_error<=active_error && active_beat==1; r_last<=active_beat==active_final;
            end
            if(r_valid && r_ready) begin
                r_valid<=0;
                if(r_last) active<=0;
                else active_beat<=active_beat+1;
            end
            if(w_valid && w_ready) begin
                check(w_last===(active_beat==3),"write burst last beat");
                staging[active_beat]<=w_data;
                if(w_last) begin b_valid<=1; b_error<=active_error; end
                else active_beat<=active_beat+1;
            end
            if(b_valid && b_ready) begin
                b_valid<=0; active<=0;
                if(!b_error) begin
                    for(word_index=0;word_index<4;word_index=word_index+1)
                        memory[int'(active_address[15:2])+word_index]<=staging[word_index];
                end
            end
            if(cycles>200000) $fatal(1,"Cache watchdog expired");
        end
    end
    task large_writable_access(input [31:0] address,input bit writing,input [31:0] data_value,input [3:0] strobe);
        reg [31:0] mask_value;
        begin
            mask_value={{8{strobe[3]}},{8{strobe[2]}},{8{strobe[1]}},{8{strobe[0]}}};
            transact(address,writing,data_value,strobe,geometry_expected[address[15:2]],0);
            if(writing) geometry_expected[address[15:2]]=
                (geometry_expected[address[15:2]] & ~mask_value) | (data_value & mask_value);
        end
    endtask
    task large_writable_memory_check;
        begin
            for(integer compare_index=0;compare_index<16384;compare_index=compare_index+1)
                check(memory[compare_index]===geometry_expected[compare_index],"full-capacity writeback memory comparison");
        end
    endtask
    task large_writable_checks;
        integer group_index,word_offset,strobe_index,request_index;
        reg [31:0] tested_address,conflict_stride,data_value;
        begin
            check(READONLY==0,"geometry stream is writable");
            conflict_stride=32'd1<<(CACHE_SET_BITS+4);
            transact(0,0,0,0,32'h10000000,0);
            snapshot_commands=command_count;
            if(READ_OVERLAP!=0 && FAST_READ_HIT!=0) overlap_stream();
            if(READ_OVERLAP!=0 && FAST_READ_HIT==0) slow_overlap_stream();
            flush_cache(0);
            for(integer expected_index=0;expected_index<16384;expected_index=expected_index+1)
                geometry_expected[expected_index]=memory[expected_index];
            for(group_index=0;group_index<2;group_index=group_index+1) begin
                for(word_offset=3;word_offset>=0;word_offset=word_offset-1) begin
                    tested_address=32'(group_index)*conflict_stride+32'(word_offset)*4;
                    data_value=32'h1a2b3c4d ^ (32'(group_index)<<16) ^ 32'(word_offset);
                    large_writable_access(tested_address,1,data_value,15);
                end
            end
            inject_write_error=1;
            transact(2*conflict_stride+12,0,0,0,0,1);
            transact(2*conflict_stride+12,1,32'hbad0bad0,15,0,1);
            large_writable_access(0,0,0,0);
            large_writable_access(conflict_stride,0,0,0);
            flush_cache(1);
            large_writable_access(0,0,0,0);
            inject_write_error=0;
            flush_cache(0);
            large_writable_memory_check();
            for(group_index=0;group_index<3;group_index=group_index+1) begin
                for(strobe_index=0;strobe_index<16;strobe_index=strobe_index+1) begin
                    tested_address=32'(group_index)*conflict_stride+conflict_stride-16+32'(3-strobe_index%4)*4;
                    data_value=32'hc3d2e1f0 ^ (32'(group_index)<<24) ^ (32'(strobe_index)*32'h01020408);
                    large_writable_access(tested_address,1,data_value,strobe_index[3:0]);
                    large_writable_access(tested_address,0,0,0);
                end
            end
            for(request_index=0;request_index<512;request_index=request_index+1) begin
                transaction_state=transaction_state^(transaction_state<<13);
                transaction_state=transaction_state^(transaction_state>>17);
                transaction_state=transaction_state^(transaction_state<<5);
                tested_address={16'b0,transaction_state[15:2],2'b0};
                large_writable_access(tested_address,transaction_state[16],transaction_state^32'ha5c39e71,transaction_state[20:17]);
            end
            flush_cache(0);
            large_writable_memory_check();
            inject_read_error=1; transact(32'hf000,0,0,0,0,1); inject_read_error=0;
            large_writable_access(32'hf000,0,0,0);
            inject_early_last=1; transact(32'hf010,0,0,0,0,1); inject_early_last=0;
            large_writable_access(32'hf010,0,0,0);
            inject_late_last=1; transact(32'hf020,0,0,0,0,1); inject_late_last=0;
            large_writable_access(32'hf020,0,0,0);
            transact(1,0,0,0,0,1);
            if(ADDRESS_BITS<32) transact(32'h10000,0,0,0,0,1);
            large_writable_access(32'hf02c,1,32'hffffffff,0);
            flush_cache(0);
            large_writable_memory_check();
            $display("PASS cache writable geometry sets=%0d checks=%0d commands=%0d",1<<CACHE_SET_BITS,checks,command_count);
            $finish;
        end
    endtask
    task large_readonly_capacity_checks;
        integer group_index,set_index,word_offset;
        reg [31:0] tested_address,conflict_stride,misses_before,hits_before;
        integer commands_before;
        begin
            check(READONLY!=0,"capacity sweep is read-only");
            check(CACHE_SET_BITS==9 || CACHE_SET_BITS==10,"supported expanded capacity geometry");
            conflict_stride=32'd1<<(CACHE_SET_BITS+4);
            for(group_index=0;group_index<2;group_index=group_index+1)
                for(set_index=0;set_index<(1<<CACHE_SET_BITS);set_index=set_index+1) begin
                    tested_address=32'(group_index)*conflict_stride+32'(set_index)*16;
                    transact(tested_address,0,0,0,32'h10000000+(tested_address>>2),0);
                end
            misses_before=miss_count; hits_before=hit_count; commands_before=command_count;
            for(group_index=0;group_index<2;group_index=group_index+1)
                for(set_index=0;set_index<(1<<CACHE_SET_BITS);set_index=set_index+1)
                    for(word_offset=0;word_offset<4;word_offset=word_offset+1) begin
                        tested_address=32'(group_index)*conflict_stride+32'(set_index)*16+32'(word_offset)*4;
                        transact(tested_address,0,0,0,32'h10000000+(tested_address>>2),0);
                    end
            check(miss_count==misses_before && command_count==commands_before,"full advertised capacity remains resident");
            check(hit_count-hits_before==(1<<(CACHE_SET_BITS+3)),"all resident words are hits");
            for(set_index=0;set_index<(1<<CACHE_SET_BITS);set_index=set_index+1) begin
                tested_address=2*conflict_stride+32'(set_index)*16;
                transact(tested_address,0,0,0,32'h10000000+(tested_address>>2),0);
            end
            check(miss_count-misses_before==(1<<CACHE_SET_BITS),"third tag replaces exactly one way per set");
            misses_before=miss_count; hits_before=hit_count; commands_before=command_count;
            for(group_index=1;group_index<3;group_index=group_index+1)
                for(set_index=0;set_index<(1<<CACHE_SET_BITS);set_index=set_index+1)
                    for(word_offset=0;word_offset<4;word_offset=word_offset+1) begin
                        tested_address=32'(group_index)*conflict_stride+32'(set_index)*16+32'(word_offset)*4;
                        transact(tested_address,0,0,0,32'h10000000+(tested_address>>2),0);
                    end
            check(miss_count==misses_before && command_count==commands_before,"LRU replacement preserves the other complete way");
            check(hit_count-hits_before==(1<<(CACHE_SET_BITS+3)),"replacement resident words are hits");
            flush_cache(0);
            commands_before=command_count;
            transact(0,0,0,0,32'h10000000,0);
            check(command_count==commands_before+1,"flush invalidates expanded capacity");
            $display("PASS instruction capacity sets=%0d bytes=%0d checks=%0d",1<<CACHE_SET_BITS,1<<(CACHE_SET_BITS+5),checks);
            $finish;
        end
    endtask

    task large_readonly_checks;
        integer group_index,set_index,word_offset,request_index;
        reg [31:0] tested_address,conflict_stride;
        begin
            check(READONLY!=0,"geometry stream is read-only");
            conflict_stride=32'd1<<(CACHE_SET_BITS+4);
            if(CHECK_TAG_PIPELINE!=0) begin
                transact(16,0,0,0,32'h10000004,0);
                transact(conflict_stride+16,0,0,0,32'h10000004+(conflict_stride>>2),0);
                transact(conflict_stride+12,0,0,0,32'h10000003+(conflict_stride>>2),0);
                flush_cache(0);
            end
            for(group_index=0;group_index<3;group_index=group_index+1) begin
                for(set_index=0;set_index<4;set_index=set_index+1) begin
                    for(word_offset=3;word_offset>=0;word_offset=word_offset-1) begin
                        tested_address=32'(group_index)*conflict_stride+32'(set_index)*16+32'(word_offset)*4;
                        transact(tested_address,0,0,0,32'h10000000+(tested_address>>2),0);
                    end
                end
            end
            for(request_index=0;request_index<256;request_index=request_index+1) begin
                transaction_state={transaction_state[30:0],transaction_state[31]^transaction_state[21]^transaction_state[1]^transaction_state[0]};
                tested_address={16'b0,transaction_state[15:2],2'b0};
                transact(tested_address,0,0,0,32'h10000000+(tested_address>>2),0);
                if(request_index%64==63) flush_cache(0);
            end
            inject_read_error=1; transact(12,0,0,0,0,1); inject_read_error=0;
            transact(12,0,0,0,32'h10000003,0);
            inject_early_last=1; transact(28,0,0,0,0,1); inject_early_last=0;
            transact(28,0,0,0,32'h10000007,0);
            inject_late_last=1; transact(44,0,0,0,0,1); inject_late_last=0;
            transact(44,0,0,0,32'h1000000b,0);
            transact(1,0,0,0,0,1);
            transact(0,1,32'hdeadbeef,15,0,1);
            if(ADDRESS_BITS<32) transact(32'h10000,0,0,0,0,1);
            transact(0,0,0,0,32'h10000000,0);
            snapshot_commands=command_count;
            if(READ_OVERLAP!=0 && FAST_READ_HIT!=0) overlap_stream();
            if(READ_OVERLAP!=0 && FAST_READ_HIT==0) slow_overlap_stream();
            flush_cache(0);
            $display("PASS cache geometry sets=%0d checks=%0d",1<<CACHE_SET_BITS,checks);
            $finish;
        end
    endtask
    initial begin
        for(word_index=0;word_index<16384;word_index=word_index+1) memory[word_index]=32'h10000000+32'(word_index);
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
        if(CHECK_REQUEST_CAPTURE==2) repeat(16) @(negedge clk);
        if(GEOMETRY_STREAM!=0) begin
            if(GEOMETRY_STREAM==2) large_readonly_capacity_checks();
            if(READONLY!=0) large_readonly_checks();
            else large_writable_checks();
        end
        transact(0,0,0,0,32'h10000000,0);
        snapshot_commands=command_count;
        transact(4,0,0,0,32'h10000001,0);
        check(command_count==snapshot_commands && miss_count==1 && hit_count==1,"line hit avoids backend");
        if(FAST_READ_HIT!=0) begin
            @(negedge clk); req_valid=1; req_address=4; req_write=0; rsp_ready=1;
            @(posedge clk); while(!req_ready) @(posedge clk);
            @(negedge clk); req_valid=0;
            @(posedge clk);
            check(rsp_valid && !rsp_error && rsp_data==32'h10000001,"hot read responds in LOOKUP cycle");
            @(negedge clk);
            check(!rsp_valid && req_ready,"early response consumed exactly once");
            check(hit_count==2 && miss_count==1 && command_count==snapshot_commands,"early hit counts once without backend");
            rsp_ready=0;
        end
        if(READ_OVERLAP!=0 && FAST_READ_HIT!=0) overlap_stream();
        if(READ_OVERLAP!=0 && FAST_READ_HIT==0) slow_overlap_stream();
        if(READ_OVERLAP!=0 && FAST_READ_HIT!=0 && READONLY==0) overlap_read_write();
        baseline_writebacks=int'(writeback_count);
        if(READONLY==0) begin
            if(FAST_READ_HIT!=0) begin
                @(negedge clk); req_valid=1; req_address=0; req_write=1; req_data=32'h10000000; req_strobe=15; rsp_ready=0;
                @(posedge clk); check(req_ready,"store request accepted");
                @(negedge clk); req_valid=0;
                @(posedge clk); check(rsp_valid==(FAST_WRITE_HIT!=0),"store uses only explicit write-hit mode");
                @(negedge clk);
                check(rsp_valid && !rsp_error && cache.dirty[0],"store completes through registered response");
                repeat(3) begin @(posedge clk); check(rsp_valid && !rsp_error,"store response survives backpressure"); end
                @(negedge clk); rsp_ready=1;
                @(posedge clk);
                @(negedge clk); rsp_ready=0;
                check(!rsp_valid,"store response consumed once");
            end
            transact(0,1,32'haabbccdd,4'b0101,0,0);
            transact(0,0,0,0,32'h10bb00dd,0);
            check(memory[0]==32'h10000000,"write-back defers memory update");
        end else begin
            transact(0,1,32'haabbccdd,15,0,1);
            check(command_count==snapshot_commands,"read-only cache rejects writes");
        end
        transact(32'h20,0,0,0,32'h10000008,0);
        snapshot_commands=command_count;
        transact(0,0,0,0,READONLY==0 ? 32'h10bb00dd : 32'h10000000,0);
        check(command_count==snapshot_commands,"both ways coexist");
        transact(32'h40,0,0,0,32'h10000010,0);
        transact(32'h20,0,0,0,32'h10000008,0);
        check(writeback_count==32'(baseline_writebacks)+(READONLY==0 ? 1 : 0),"LRU dirty replacement");
        if(READONLY==0) check(memory[0]==32'h10bb00dd,"dirty line writeback data");
        flush_cache(0);
        snapshot_commands=command_count;
        transact(32'h20,0,0,0,32'h10000008,0);
        check(command_count==snapshot_commands+1,"flush invalidates clean lines");
        transact(1,0,0,0,0,1);
        inject_read_error=1;
        transact(32'h80,0,0,0,0,1);
        inject_read_error=0;
        transact(32'h80,0,0,0,32'h10000020,0);
        inject_early_last=1;
        transact(32'h90,0,0,0,0,1);
        inject_early_last=0;
        transact(32'h90,0,0,0,32'h10000024,0);
        inject_late_last=1;
        transact(32'ha0,0,0,0,0,1);
        inject_late_last=0;
        transact(32'ha0,0,0,0,32'h10000028,0);
        flush_cache(0);
        if(READONLY==0) begin
            transact(0,1,32'h01234567,15,0,0);
            transact(32'h20,1,32'h89abcdef,15,0,0);
            inject_write_error=1;
            transact(32'h40,0,0,0,0,1);
            check(memory[0]==32'h10bb00dd,"failed writeback has no memory side effects");
            transact(32'h40,1,32'hbad0bad0,15,0,1);
            check(memory[16]==32'h10000010,"failed eviction cannot commit younger write");
            transact(0,0,0,0,32'h01234567,0);
            flush_cache(1);
            transact(0,0,0,0,32'h01234567,0);
            inject_write_error=0;
            flush_cache(0);
            check(memory[0]==32'h01234567 && memory[8]==32'h89abcdef,"retry flush preserves dirty data");
            transact(0,1,32'hffffffff,0,0,0);
            flush_cache(0);
            check(memory[0]==32'h01234567,"zero byte enable has no effect");
        end
        if(FAST_WRITE_HIT!=0 && READONLY==0) fast_write_checks();
        for(integer golden_index=0;golden_index<256;golden_index=golden_index+1) golden[golden_index]=memory[golden_index];
        for(integer transaction_index=0;transaction_index<512;transaction_index=transaction_index+1) begin
            transaction_state=transaction_state^(transaction_state<<13);
            transaction_state=transaction_state^(transaction_state>>17);
            transaction_state=transaction_state^(transaction_state<<5);
            random_address={22'b0,transaction_state[7:0],2'b0};
            random_write=transaction_state[8]; random_strobe=transaction_state[12:9];
            random_data=transaction_state^32'ha5a5c3c3;
            random_mask={{8{random_strobe[3]}},{8{random_strobe[2]}},{8{random_strobe[1]}},{8{random_strobe[0]}}};
            transact(random_address,random_write,random_data,random_strobe,golden[random_address[9:2]],READONLY!=0 && random_write);
            if(random_write && READONLY==0) golden[random_address[9:2]]=(golden[random_address[9:2]] & ~random_mask) | (random_data & random_mask);
        end
        flush_cache(0);
        for(integer golden_index=0;golden_index<256;golden_index=golden_index+1)
            check(memory[golden_index]===golden[golden_index],"random stream final memory comparison");
        if(CHECK_REQUEST_CAPTURE!=0) begin
            check(address_capture_checks>100 && address_hold_checks>100 && address_reset_checks>0,"request capture coverage");
            $display("REQUEST_CAPTURE accepted=%0d held=%0d reset=%0d",address_capture_checks,address_hold_checks,address_reset_checks);
        end
        if(CHECK_LOOKUP_DATA!=0) begin
            check(valid_data_checks>0,"valid response equivalence coverage");
            if(FAST_READ_HIT!=0 || (FAST_WRITE_HIT!=0 && READONLY==0))
                check(lookup_hit_checks>0 && lookup_miss_checks>0,"lookup hit and miss coverage");
            $display("LOOKUP_DATA hits=%0d misses=%0d valid=%0d",lookup_hit_checks,lookup_miss_checks,valid_data_checks);
        end
        if(TEST_NAME!="") $display("PASS %s checks=%0d commands=%0d",TEST_NAME,checks,command_count);
        else if(READONLY==0 && READ_OVERLAP!=0) $display("PASS cache_rw_overlap checks=%0d commands=%0d",checks,command_count);
        else if(READONLY==0 && FAST_READ_HIT!=0) $display("PASS cache_rw_fast checks=%0d commands=%0d",checks,command_count);
        else if(READONLY==0) $display("PASS cache checks=%0d commands=%0d hits=%0d misses=%0d writebacks=%0d",checks,command_count,hit_count,miss_count,writeback_count);
        else if(READ_OVERLAP!=0) $display("PASS cache_ro_overlap checks=%0d commands=%0d",checks,command_count);
        else if(FAST_READ_HIT!=0) $display("PASS cache_ro_fast checks=%0d commands=%0d",checks,command_count);
        else $display("PASS cache_ro checks=%0d commands=%0d",checks,command_count);
        $finish;
    end
endmodule
