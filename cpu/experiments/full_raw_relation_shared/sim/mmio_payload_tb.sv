`timescale 1ns/1ps
module mmio_payload_tb;
    parameter integer ENABLE_CACHE=1;
    parameter integer DATA_OVERLAP=1;
    parameter integer FAST_CACHE=1;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    wire i_req_valid=0,i_rsp_ready=1;
    wire [31:0] i_req_address=0;
    wire i_req_ready,i_rsp_valid,i_rsp_error;
    wire [31:0] i_rsp_data;
    reg d_req_valid=0,d_req_write=0,d_rsp_ready=0,maintenance_valid=0;
    reg [31:0] d_req_address=0,d_req_data=0;
    reg [3:0] d_req_strobe=0;
    wire d_req_ready,d_rsp_valid,d_rsp_error,maintenance_ready,maintenance_error;
    wire [31:0] d_rsp_data;
    wire mmio_req_valid,mmio_req_write,mmio_rsp_ready;
    wire [31:0] mmio_req_address,mmio_req_data;
    wire [3:0] mmio_req_strobe;
    reg mmio_rsp_valid=0,mmio_rsp_error=0,peripheral_allow=1;
    reg [31:0] mmio_rsp_data=0;
    integer peripheral_wait=0,required_wait=0;
    wire mmio_req_ready=peripheral_allow && !mmio_rsp_valid && peripheral_wait>=required_wait;
    wire [31:0] i_hit_count,i_miss_count,d_hit_count,d_miss_count,d_writeback_count;
    wire [68:0] input_payload={d_req_address,d_req_data,d_req_strobe,d_req_write};
    wire [68:0] output_payload={mmio_req_address,mmio_req_data,mmio_req_strobe,mmio_req_write};
    reg [68:0] sampled_payload,expected_mmio_payload;
    reg sampled_pending=0,owned=0,expected_mmio=0,expected_write=0,expected_error=0;
    reg [31:0] expected_data,random_state=32'h42f017a3;
    reg [31:0] golden[0:63];
    integer checks=0,prefill_checks=0,hold_checks=0,requests=0,responses=0,mmio_accepts=0,cache_accepts=0,error_responses=0;
    rv32_memory_system #(.ENABLE_CACHE(ENABLE_CACHE),.DATA_OVERLAP(DATA_OVERLAP),
        .FAST_DCACHE_READ(FAST_CACHE),.FAST_DCACHE_WRITE(FAST_CACHE),
        .MEMORY_ADDRESS_BITS(6),.CACHE_SET_BITS(1)) memory_system(.*);
    task automatic check(input bit condition,input string label_text);
        begin checks=checks+1; if(!condition) $fatal(1,"FAIL mmio_payload %s",label_text); end
    endtask
    function automatic [31:0] peripheral_result(input [31:0] address,input [31:0] data,input [3:0] strobe,input bit write_request);
        peripheral_result=address ^ data ^ {28'b0,strobe} ^ {31'b0,write_request} ^ 32'h762134ab;
    endfunction
    task automatic noise;
        begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            d_req_address=random_state; d_req_data=~random_state;
            d_req_strobe=random_state[7:4]; d_req_write=random_state[2];
        end
    endtask
    always @(posedge clk) begin
        if(rst_n) begin
            sampled_pending=memory_system.mmio_request_pending;
            sampled_payload=sampled_pending ? output_payload : input_payload;
            #1;
            if(rst_n) begin
                if(sampled_pending) begin
                    check(output_payload===sampled_payload,"pending payload cannot follow changing CPU pins");
                    hold_checks=hold_checks+1;
                end else begin
                    check(output_payload===sampled_payload,"idle payload sampling is independent of request qualification");
                    prefill_checks=prefill_checks+1;
                end
            end
        end
    end
    always @(posedge clk) begin
        if(!rst_n) begin
            mmio_rsp_valid<=0; mmio_rsp_error<=0; mmio_rsp_data<=0; peripheral_wait<=0;
            owned=0; requests=0; responses=0; mmio_accepts=0; cache_accepts=0; error_responses=0;
        end else begin
            if(!mmio_req_valid || mmio_req_ready) peripheral_wait<=0;
            else peripheral_wait<=peripheral_wait+1;
            if(mmio_req_valid) begin
                check(owned && expected_mmio,"MMIO valid requires an accepted MMIO owner");
                check(output_payload===expected_mmio_payload,"valid MMIO payload equals accepted CPU request");
            end
            if(mmio_rsp_valid && mmio_rsp_ready) mmio_rsp_valid<=0;
            if(mmio_req_valid && mmio_req_ready) begin
                mmio_accepts=mmio_accepts+1;
                mmio_rsp_valid<=1; mmio_rsp_error<=mmio_req_address[3];
                mmio_rsp_data<=peripheral_result(mmio_req_address,mmio_req_data,mmio_req_strobe,mmio_req_write);
            end
            if(d_rsp_valid) begin
                check(owned,"no response without an owner");
                check(d_rsp_error===expected_error,"response error belongs to accepted request");
                if(expected_mmio || !expected_write) check(d_rsp_data===expected_data,"response data belongs to accepted request");
            end
            if(d_rsp_valid && d_rsp_ready) begin
                owned=0; responses=responses+1;
                if(expected_error) error_responses=error_responses+1;
            end
            if(d_req_valid && d_req_ready) begin
                check(!owned,"at most one owned transaction");
                owned=1; requests=requests+1; expected_mmio=|d_req_address[31:28];
                expected_write=d_req_write; expected_error=expected_mmio && d_req_address[3];
                expected_mmio_payload=input_payload;
                if(expected_mmio) expected_data=peripheral_result(d_req_address,d_req_data,d_req_strobe,d_req_write);
                else begin
                    cache_accepts=cache_accepts+1; expected_data=golden[d_req_address[7:2]];
                    if(d_req_write) for(integer byte_index=0;byte_index<4;byte_index=byte_index+1)
                        if(d_req_strobe[byte_index]) golden[d_req_address[7:2]][8*byte_index+:8]=d_req_data[8*byte_index+:8];
                end
            end
        end
    end
    task automatic transaction(input [31:0] address,input bit write_request,input [31:0] data,input [3:0] strobe,input integer stalls);
        begin
            @(negedge clk); required_wait=stalls; d_req_valid=1; d_req_address=address;
            d_req_write=write_request; d_req_data=data; d_req_strobe=strobe; d_rsp_ready=0;
            @(posedge clk); while(!d_req_ready) @(posedge clk);
            @(negedge clk); d_req_valid=0; noise();
            while(!d_rsp_valid) begin @(negedge clk); noise(); end
            repeat(3) begin @(negedge clk); noise(); end
            d_rsp_ready=1;
            @(posedge clk); check(d_rsp_valid,"held response completes exactly once");
            @(negedge clk); d_rsp_ready=0; noise();
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        for(integer word_index=0;word_index<64;word_index=word_index+1) begin
            memory_system.ram.memory[word_index]=32'ha0000000+32'(word_index);
            golden[word_index]=32'ha0000000+32'(word_index);
        end
        repeat(3) @(negedge clk); rst_n=1;
        repeat(12) begin @(negedge clk); noise(); end
        peripheral_allow=0; d_req_valid=1; d_req_address=32'h10000000; d_req_write=1;
        d_req_data=32'habcd1234; d_req_strobe=4'b0101;
        @(posedge clk); check(d_req_ready,"accept pending request before reset");
        @(negedge clk); d_req_valid=0; noise();
        repeat(4) begin @(negedge clk); noise(); end
        rst_n=0;
        #1; check(!mmio_req_valid && !d_rsp_valid,"reset cancels pending request");
        repeat(3) @(negedge clk); rst_n=1; peripheral_allow=1;
        repeat(6) begin @(negedge clk); noise(); check(!mmio_req_valid && !d_rsp_valid,"reset request never replays"); end
        for(integer transaction_index=0;transaction_index<72;transaction_index=transaction_index+1) begin
            if(transaction_index%3==0)
                transaction(32'((transaction_index%16)*4),transaction_index[1],random_state,transaction_index[3:0],transaction_index%6);
            else
                transaction(32'h10000000 | (random_state & 32'h000000fc),transaction_index[0],random_state,transaction_index[3:0],transaction_index%6);
        end
        check(requests==72 && responses==72 && mmio_accepts==48 && cache_accepts==24,"all mixed requests complete once");
        check(!owned && error_responses>0 && prefill_checks>0 && hold_checks>0,"error prefill and held payload coverage");
        $display("PASS mmio_payload checks=%0d requests=%0d mmio=%0d cache=%0d errors=%0d prefill=%0d held=%0d",checks,requests,mmio_accepts,cache_accepts,error_responses,prefill_checks,hold_checks);
        $finish;
    end
    initial begin #200000; $fatal(1,"MMIO payload watchdog"); end
endmodule

