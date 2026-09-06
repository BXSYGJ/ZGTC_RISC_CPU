`timescale 1ns/1ps
module cache_tb;
    parameter integer ADDRESS_BITS=32;
    parameter TEST_NAME="";
    parameter integer READONLY=0;
    parameter integer FAST_READ_HIT=0;
    parameter integer FAST_WRITE_HIT=0;
    parameter integer READ_OVERLAP=0;
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
    reg [31:0] memory[0:255],staging[0:3];
    reg [31:0] golden[0:255];
    reg [31:0] transaction_state=32'h2468ace1;
    reg [31:0] random_address,random_data,random_mask;
    reg [3:0] random_strobe;
    reg random_write;
    reg active=0,active_write=0,active_error=0;
    reg [31:0] active_address=0;
    integer active_beat=0,active_final=3,command_count=0,checks=0,cycles=0,word_index;
    integer snapshot_commands,baseline_writebacks;
    reg [31:0] random_state=32'h98765432;
    reg inject_read_error=0,inject_write_error=0,inject_early_last=0,inject_late_last=0;
    reg cmd_held=0,w_held=0;
    reg [31:0] held_address,held_data;
    reg held_write,held_last;
    reg [7:0] held_length;
    rv32_cache #(.ADDRESS_BITS(ADDRESS_BITS),.SET_BITS(1),.WORD_BITS(2),.READ_ONLY(READONLY),.FAST_WRITE_HIT(FAST_WRITE_HIT),.FAST_READ_HIT(FAST_READ_HIT),.READ_OVERLAP(READ_OVERLAP)) cache(.*);
    task automatic check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL cache %s cycle=%0d addr=%08x response=%08x error=%b",label_text,cycles,req_address,rsp_data,rsp_error);
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
            req_valid=1; req_address=0;
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
                r_valid<=1; r_data<=memory[int'(active_address[9:2])+active_beat];
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
                        memory[int'(active_address[9:2])+word_index]<=staging[word_index];
                end
            end
            if(cycles>200000) $fatal(1,"Cache watchdog expired");
        end
    end
    initial begin
        for(word_index=0;word_index<256;word_index=word_index+1) memory[word_index]=32'h10000000+32'(word_index);
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
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
        if(READ_OVERLAP!=0) overlap_stream();
        if(READ_OVERLAP!=0 && READONLY==0) overlap_read_write();
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
