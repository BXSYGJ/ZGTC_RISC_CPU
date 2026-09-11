`timescale 1ns/1ps
module rv32_cache #(
    parameter integer ADDRESS_BITS=32,
    parameter integer SET_BITS=4,
    parameter integer WORD_BITS=2,
    parameter integer READ_ONLY=0,
    parameter integer FAST_READ_HIT=0,
    parameter integer FAST_WRITE_HIT=0,
    parameter integer READ_OVERLAP=0
) (
    input wire clk,
    input wire rst_n,
    input wire req_valid,
    output wire req_ready,
    input wire [31:0] req_address,
    input wire req_write,
    input wire [31:0] req_data,
    input wire [3:0] req_strobe,
    output wire rsp_valid,
    input wire rsp_ready,
    output wire [31:0] rsp_data,
    output reg rsp_error,
    input wire flush_valid,
    output wire flush_ready,
    output reg flush_error,
    output wire cmd_valid,
    input wire cmd_ready,
    output wire cmd_write,
    output wire [31:0] cmd_address,
    output wire [7:0] cmd_length,
    output wire w_valid,
    input wire w_ready,
    output wire [31:0] w_data,
    output wire w_last,
    input wire b_valid,
    output wire b_ready,
    input wire b_error,
    input wire r_valid,
    output wire r_ready,
    input wire [31:0] r_data,
    input wire r_last,
    input wire r_error,
    output reg [31:0] hit_count,
    output reg [31:0] miss_count,
    output reg [31:0] writeback_count
);
    localparam integer SETS=1<<SET_BITS;
    localparam integer WORDS=1<<WORD_BITS;
    localparam integer LINES=2*SETS;
    localparam integer TAG_BITS=ADDRESS_BITS-2-SET_BITS-WORD_BITS;
    localparam [31:0] LINE_LENGTH=WORDS-1;
    localparam [3:0] IDLE=0,LOOKUP=1,WB_CMD=2,WB_DATA=3,WB_ACK=4,
        FILL_CMD=5,FILL_DATA=6,RESPONSE=7,FLUSH_SCAN=8,FLUSH_DONE=9;
    reg [3:0] state;
    reg [31:0] response_data;
    reg [LINES-1:0] valid,dirty;
    reg [SETS-1:0] lru;
    reg [TAG_BITS-1:0] tags[0:LINES-1];
    (* syn_maxfan=64 *) reg [31:0] request_address;
    reg [31:0] request_data,victim_base;
    reg [3:0] request_strobe;
    reg request_write,request_missed,flushing,fill_failed;
    reg [SET_BITS:0] victim,scan_line;
    reg [WORD_BITS-1:0] beat;
    wire [SET_BITS-1:0] request_set=request_address[WORD_BITS+SET_BITS+1:WORD_BITS+2];
    wire [WORD_BITS-1:0] request_word=request_address[WORD_BITS+1:2];
    wire [TAG_BITS-1:0] request_tag=request_address[ADDRESS_BITS-1:WORD_BITS+SET_BITS+2];
    wire [SET_BITS:0] way0={1'b0,request_set},way1={1'b1,request_set};
    wire hit0=valid[way0] && tags[way0]==request_tag;
    wire hit1=valid[way1] && tags[way1]==request_tag;
    wire [SET_BITS:0] hit_line=hit1 ? way1 : way0;
    wire [SET_BITS:0] replacement=!valid[way0] ? way0 : !valid[way1] ? way1 : {lru[request_set],request_set};
    wire [31:0] current_word;
    wire [31:0] byte_mask={{8{request_strobe[3]}},{8{request_strobe[2]}},{8{request_strobe[1]}},{8{request_strobe[0]}}};
    wire last_beat=&beat;
    wire [1:0] unused_request_alignment=request_address[1:0];
    assign req_ready=(state==IDLE || (READ_OVERLAP!=0 && rsp_valid && rsp_ready)) && !flush_valid;
    wire fast_lookup=((FAST_READ_HIT!=0 && !request_write) || (FAST_WRITE_HIT!=0 && request_write && READ_ONLY==0)) && state==LOOKUP;
    wire fast_hit=fast_lookup && (hit0 || hit1);
    assign rsp_valid=state==RESPONSE || fast_hit;
    assign rsp_data=rsp_error ? 32'b0 : fast_lookup ? current_word : response_data;
    assign flush_ready=state==FLUSH_DONE;
    assign cmd_valid=state==WB_CMD || state==FILL_CMD;
    assign cmd_write=state==WB_CMD;
    assign cmd_address=state==WB_CMD ? victim_base : {request_address[31:WORD_BITS+2],{(WORD_BITS+2){1'b0}}};
    assign cmd_length=LINE_LENGTH[7:0];
    assign w_valid=state==WB_DATA;
    assign w_last=last_beat;
    assign b_ready=state==WB_ACK;
    assign r_ready=state==FILL_DATA;
    generate
        if(READ_ONLY!=0) begin : synchronous_readonly
            wire [63:0] unused_readonly_payload={request_data,byte_mask};
            (* syn_ramstyle="block_ram" *) reg [31:0] storage_way0[0:SETS*WORDS-1];
            (* syn_ramstyle="block_ram" *) reg [31:0] storage_way1[0:SETS*WORDS-1];
            reg [31:0] read_way0,read_way1,forward_data;
            reg forward_way0,forward_way1;
            wire [SET_BITS+WORD_BITS-1:0] read_index=req_ready ?
                req_address[WORD_BITS+SET_BITS+1:2] : {request_set,request_word};
            wire [SET_BITS+WORD_BITS-1:0] fill_index={victim[SET_BITS-1:0],beat};
            wire fill_write=state==FILL_DATA && r_valid && !r_error && !fill_failed;
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin end
                else if(fill_write && !victim[SET_BITS]) storage_way0[fill_index]<=r_data;
            end
            always @(posedge clk) begin
                read_way0<=storage_way0[read_index];
            end
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin end
                else if(fill_write && victim[SET_BITS]) storage_way1[fill_index]<=r_data;
            end
            always @(posedge clk) begin
                read_way1<=storage_way1[read_index];
            end
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin forward_way0<=0; forward_way1<=0; end
                else begin
                    forward_way0<=fill_write && !victim[SET_BITS] && fill_index==read_index;
                    forward_way1<=fill_write && victim[SET_BITS] && fill_index==read_index;
                end
            end
            always @(posedge clk) forward_data<=r_data;
            assign current_word=hit1 ? (forward_way1 ? forward_data : read_way1) :
                (forward_way0 ? forward_data : read_way0);
            assign w_data=32'b0;
        end else begin : asynchronous_writable
            reg [31:0] storage[0:LINES*WORDS-1];
            wire store_hit=state==LOOKUP && (hit0 || hit1) && request_write && |request_strobe;
            wire store_fill=state==FILL_DATA && r_valid && !r_error && !fill_failed;
            wire [SET_BITS+WORD_BITS:0] store_index=store_hit ? {hit_line,request_word} : {victim,beat};
            wire [31:0] store_data=store_hit ? (current_word & ~byte_mask) | (request_data & byte_mask) : r_data;
            assign current_word=storage[{hit_line,request_word}];
            assign w_data=storage[{victim,beat}];
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin end
                else if(store_hit || store_fill) storage[store_index]<=store_data;
            end
        end
    endgenerate
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE; valid<=0; dirty<=0; lru<=0;
            request_address<=0; request_data<=0; request_strobe<=0; request_write<=0;
            request_missed<=0; flushing<=0; fill_failed<=0;
            victim<=0; victim_base<=0; scan_line<=0; beat<=0;
            response_data<=0; rsp_error<=0; flush_error<=0;
            hit_count<=0; miss_count<=0; writeback_count<=0;
        end else begin
            case(state)
                IDLE: begin
                    if(flush_valid) begin
                        flushing<=1; scan_line<=0; flush_error<=0; state<=FLUSH_SCAN;
                    end
                end
                LOOKUP: begin
                    if(hit0 || hit1) begin
                        response_data<=current_word; rsp_error<=0;
                        if(request_write && READ_ONLY==0 && |request_strobe) begin
                            dirty[hit_line]<=1;
                        end
                        lru[request_set]<=!hit_line[SET_BITS];
                        if(!request_missed) hit_count<=hit_count+1;
                        state<=fast_hit && rsp_ready ? IDLE : RESPONSE;
                    end else begin
                        request_missed<=1; miss_count<=miss_count+1;
                        victim<=replacement;
                        victim_base<={{(32-ADDRESS_BITS){1'b0}},tags[replacement],request_set,{(WORD_BITS+2){1'b0}}};
                        beat<=0;
                        state<=(valid[replacement] && dirty[replacement]) ? WB_CMD : FILL_CMD;
                    end
                end
                WB_CMD: if(cmd_ready) begin beat<=0; state<=WB_DATA; end
                WB_DATA: if(w_ready) begin
                    if(last_beat) state<=WB_ACK;
                    else beat<=beat+1'b1;
                end
                WB_ACK: if(b_valid) begin
                    if(b_error) begin
                        if(flushing) begin flush_error<=1; state<=FLUSH_DONE; end
                        else begin response_data<=0; rsp_error<=1; state<=RESPONSE; end
                    end else begin
                        writeback_count<=writeback_count+1;
                        dirty[victim]<=0; valid[victim]<=0;
                        if(flushing) begin
                            if(&scan_line) state<=FLUSH_DONE;
                            else begin scan_line<=scan_line+1'b1; state<=FLUSH_SCAN; end
                        end else state<=FILL_CMD;
                    end
                end
                FILL_CMD: if(cmd_ready) begin
                    valid[victim]<=0; dirty[victim]<=0; fill_failed<=0; beat<=0; state<=FILL_DATA;
                end
                FILL_DATA: if(r_valid) begin
                    if(r_error || r_last!=last_beat) fill_failed<=1;
                    if(r_last) begin
                        if(fill_failed || r_error || !last_beat) begin
                            valid[victim]<=0; response_data<=0; rsp_error<=1; state<=RESPONSE;
                        end else begin
                            tags[victim]<=request_tag; valid[victim]<=1; dirty[victim]<=0;
                            state<=LOOKUP;
                        end
                    end else if(!last_beat) beat<=beat+1'b1;
                end
                RESPONSE: if(rsp_ready) state<=IDLE;
                FLUSH_SCAN: begin
                    if(valid[scan_line] && dirty[scan_line]) begin
                        victim<=scan_line;
                        victim_base<={{(32-ADDRESS_BITS){1'b0}},tags[scan_line],scan_line[SET_BITS-1:0],{(WORD_BITS+2){1'b0}}};
                        state<=WB_CMD;
                    end else begin
                        valid[scan_line]<=0; dirty[scan_line]<=0;
                        if(&scan_line) state<=FLUSH_DONE;
                        else scan_line<=scan_line+1'b1;
                    end
                end
                FLUSH_DONE: if(flush_valid) state<=IDLE;
                default: state<=IDLE;
            endcase
            if(req_ready) begin
                request_address<={{(32-ADDRESS_BITS){1'b0}},req_address[ADDRESS_BITS-1:0]}; request_data<=req_data;
                request_strobe<=req_strobe; request_write<=req_write;
            end
            if(req_valid && req_ready) begin
                request_missed<=0; flushing<=0; rsp_error<=0;
                if((req_address >> ADDRESS_BITS)!=0 || req_address[1:0]!=0 || (READ_ONLY!=0 && req_write)) begin
                    rsp_error<=1; state<=RESPONSE;
                end else state<=LOOKUP;
            end
        end
    end
endmodule
