`timescale 1ns/1ps
module uncached_tb;
    parameter integer READONLY=0;
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
    reg [31:0] memory[0:63],golden[0:63];
    reg [31:0] random_state=32'h19260817,transaction_state=32'h87654321;
    reg active=0,active_write=0,active_error=0,extra_beat=0;
    reg [31:0] active_address=0;
    reg inject_read_error=0,inject_write_error=0,inject_extra_beat=0;
    reg cmd_held=0,w_held=0;
    reg [31:0] held_address,held_data;
    reg held_write,held_last;
    integer command_count=0,checks=0,cycles=0,word_index,iteration,before_commands;
    reg [31:0] random_address,random_data,byte_mask;
    reg [3:0] random_strobe;
    rv32_uncached #(.READ_ONLY(READONLY)) dut(.*);
    task check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL uncached %s cycle=%0d",label_text,cycles);
        end
    endtask
    task transact(input [31:0] address,input bit writing,input [31:0] data_value,input [3:0] strobe,input [31:0] expected,input bit expected_error);
        reg [31:0] held_response;
        reg held_error;
        begin
            @(negedge clk); req_valid=1; req_address=address; req_write=writing; req_data=data_value; req_strobe=strobe;
            @(posedge clk); while(!req_ready) @(posedge clk);
            @(negedge clk); req_valid=0; req_address=32'hdeadbeef; req_data=0; req_strobe=0; req_write=0;
            @(posedge clk); while(!rsp_valid) @(posedge clk);
            check(rsp_error===expected_error,"response error");
            if(!writing && !expected_error) check(rsp_data===expected,"read data");
            held_response=rsp_data; held_error=rsp_error;
            repeat(4) begin
                @(posedge clk);
                check(rsp_valid && rsp_data===held_response && rsp_error===held_error && !req_ready,"response stability");
            end
            @(negedge clk); rsp_ready=1;
            @(posedge clk);
            @(negedge clk); rsp_ready=0;
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
            if(cycles>40000) $fatal(1,"uncached timeout");
            if(cmd_held) check(cmd_valid && cmd_address===held_address && cmd_write===held_write && cmd_length==0,"command stability");
            if(w_held) check(w_valid && w_data===held_data && w_last===held_last,"write stability");
            cmd_held=cmd_valid && !cmd_ready; held_address=cmd_address; held_write=cmd_write;
            w_held=w_valid && !w_ready; held_data=w_data; held_last=w_last;
            if(cmd_valid && cmd_ready) begin
                check(!active && cmd_length==0 && cmd_address[1:0]==0,"one-word command");
                command_count=command_count+1;
                active<=1; active_write<=cmd_write; active_address<=cmd_address;
                active_error<=cmd_address>=256 || (cmd_write ? inject_write_error : inject_read_error);
                extra_beat<=inject_extra_beat;
            end
            if(active && !active_write && !r_valid && random_state[2]) begin
                r_valid<=1; r_data<=memory[active_address[7:2]];
                r_error<=active_error; r_last<=!extra_beat;
            end
            if(r_valid && r_ready) begin
                r_valid<=0;
                if(r_last) active<=0;
                else extra_beat<=0;
            end
            if(w_valid && w_ready) begin
                check(w_last,"single write beat");
                if(!active_error) memory[active_address[7:2]]<=w_data;
                active<=0; b_valid<=1; b_error<=active_error;
            end
            if(b_valid && b_ready) b_valid<=0;
        end
    end
    initial begin
        for(word_index=0;word_index<64;word_index=word_index+1) begin
            memory[word_index]=32'habcd0000+word_index;
            golden[word_index]=memory[word_index];
        end
        repeat(4) @(negedge clk);
        rst_n=1;
        transact(0,0,0,0,golden[0],0);
        memory[0]=32'h99887766; golden[0]=memory[0];
        before_commands=command_count;
        transact(0,0,0,0,golden[0],0);
        check(command_count==before_commands+1,"repeated read reaches memory rather than cache");
        for(iteration=0;iteration<256;iteration=iteration+1) begin
            transaction_state=transaction_state^(transaction_state<<13);
            transaction_state=transaction_state^(transaction_state>>17);
            transaction_state=transaction_state^(transaction_state<<5);
            random_address={24'b0,transaction_state[5:0],2'b0};
            random_data=transaction_state;
            random_strobe=iteration[3:0];
            byte_mask={{8{random_strobe[3]}},{8{random_strobe[2]}},{8{random_strobe[1]}},{8{random_strobe[0]}}};
            before_commands=command_count;
            transact(random_address,1,random_data,random_strobe,0,READONLY!=0);
            if(READONLY==0) begin
                golden[random_address[7:2]]=(golden[random_address[7:2]] & ~byte_mask) | (random_data & byte_mask);
                check(command_count==before_commands+(random_strobe==0 ? 0 : random_strobe==15 ? 1 : 2),"store command count");
            end else check(command_count==before_commands,"readonly rejects without command");
            transact(random_address,0,0,0,golden[random_address[7:2]],0);
        end
        before_commands=command_count;
        transact(2,0,0,0,0,1);
        transact(1,1,123,15,0,1);
        check(command_count==before_commands,"unaligned rejected locally");
        transact(256,0,0,0,0,1);
        inject_read_error=1;
        transact(0,0,0,0,0,1);
        if(READONLY==0) begin
            before_commands=command_count;
            transact(0,1,0,3,0,1);
            check(command_count==before_commands+1,"failed partial read does not issue write");
        end
        inject_read_error=0; inject_extra_beat=1;
        transact(0,0,0,0,0,1);
        inject_extra_beat=0;
        if(READONLY==0) begin
            inject_write_error=1;
            transact(0,1,0,15,0,1);
            inject_write_error=0;
            transact(0,0,0,0,golden[0],0);
        end
        before_commands=command_count;
        @(negedge clk); flush_valid=1; req_valid=1;
        @(posedge clk); while(!flush_ready) begin check(!req_ready,"flush priority"); @(posedge clk); end
        repeat(3) begin @(posedge clk); check(flush_ready && !flush_error && !req_ready,"flush held"); end
        @(negedge clk); flush_valid=0; req_valid=0;
        repeat(3) @(negedge clk);
        check(command_count==before_commands,"flush has no memory traffic");
        check(hit_count==0 && miss_count==0 && writeback_count==0,"disabled cache counters zero");
        for(word_index=0;word_index<64;word_index=word_index+1)
            check(memory[word_index]===golden[word_index],"full memory comparison");
        if(READONLY==0) $display("PASS uncached checks=%0d commands=%0d",checks,command_count);
        else $display("PASS uncached_ro checks=%0d commands=%0d",checks,command_count);
        $finish;
    end
endmodule
