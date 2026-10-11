`timescale 1ns/1ps
module rv32_cache #(
    parameter integer ADDRESS_BITS=32,
    parameter integer SET_BITS=4,
    parameter integer WORD_BITS=2,
    parameter integer READ_ONLY=0,
    parameter integer FETCH_PAIR=0,
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
    output wire [31:0] rsp_pair_data,
    output wire [1:0] rsp_is_c,rsp_pair_is_c,
    output wire rsp_pair_valid,
    output wire rsp_error,
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
    reg [3:0] stored_state;
    reg stored_rsp_error,request_check_pending;
    reg [31:0] request_error_address;
    reg [31:0] response_data;
    reg [31:0] response_pair_data;
    wire [LINES-1:0] dirty;
    wire replacement_dirty,scan_dirty;
    wire [LINES-1:0] valid;
    wire valid_ready;
    (* syn_ramstyle="lut_ram" *) reg lru_storage[0:SETS-1];
    reg [TAG_BITS-1:0] tags[0:LINES-1];
    (* syn_maxfan=32 *) reg [31:0] request_address;
    reg [31:0] request_data,victim_base;
    reg [3:0] request_strobe;
    reg request_write,request_missed,flushing,fill_failed;
    wire request_input_error=request_check_pending && ((|request_error_address) || (READ_ONLY!=0 && request_write));
    wire [3:0] state=request_input_error ? RESPONSE : stored_state;
    assign rsp_error=request_input_error || stored_rsp_error;
    reg [SET_BITS:0] victim,scan_line;
    reg [WORD_BITS-1:0] beat;
    wire [SET_BITS-1:0] request_set=request_address[WORD_BITS+SET_BITS+1:WORD_BITS+2];
    wire [WORD_BITS-1:0] request_word=request_address[WORD_BITS+1:2];
    wire [TAG_BITS-1:0] request_tag=request_address[ADDRESS_BITS-1:WORD_BITS+SET_BITS+2];
    wire [SET_BITS:0] way0={1'b0,request_set},way1={1'b1,request_set};
    wire lookup_valid0,lookup_valid1;
    wire [TAG_BITS-1:0] lookup_tag0,lookup_tag1;
    wire hit0=lookup_valid0 && lookup_tag0==request_tag;
    wire hit1=lookup_valid1 && lookup_tag1==request_tag;
    wire [SET_BITS:0] hit_line=hit1 ? way1 : way0;
    wire [SET_BITS:0] replacement=!lookup_valid0 ? way0 : !lookup_valid1 ? way1 : {lru_storage[request_set],request_set};
    wire [31:0] current_word;
    wire [31:0] current_pair_word;
    wire [1:0] current_is_c,current_pair_is_c;
    function automatic [1:0] compact_halves(input [31:0] word_data);
        begin compact_halves={word_data[17:16]!=2'b11,word_data[1:0]!=2'b11}; end
    endfunction
    generate if(READ_ONLY==0) begin : ram_dirty
        (* syn_ramstyle="lut_ram" *) reg storage[0:LINES-1];
        assign replacement_dirty=storage[replacement];
        assign scan_dirty=storage[scan_line];
        wire store_dirty=state==LOOKUP && (hit0 || hit1) && request_write && |request_strobe;
        wire clear_dirty=(state==WB_ACK && b_valid && !b_error) ||
            (state==FILL_CMD && cmd_ready) ||
            (state==FILL_DATA && r_valid && r_last && !fill_failed && !r_error && last_beat) ||
            (state==FLUSH_SCAN && !(valid[scan_line] && scan_dirty));
        wire [SET_BITS:0] write_line=state==LOOKUP ? hit_line : state==FLUSH_SCAN ? scan_line : victim;
        for(genvar dirty_index=0;dirty_index<LINES;dirty_index=dirty_index+1) begin : view
            assign dirty[dirty_index]=storage[dirty_index];
        end
        always @(posedge clk) if(rst_n && (store_dirty || clear_dirty)) storage[write_line]<=store_dirty;
    end else begin : clean_readonly
        assign dirty={LINES{1'b0}};
        assign replacement_dirty=0;
        assign scan_dirty=0;
    end endgenerate
    wire [31:0] byte_mask={{8{request_strobe[3]}},{8{request_strobe[2]}},{8{request_strobe[1]}},{8{request_strobe[0]}}};
    wire last_beat=&beat;
    wire [1:0] unused_request_alignment=request_address[1:0];
    assign req_ready=valid_ready && (state==IDLE || (READ_OVERLAP!=0 && rsp_valid && rsp_ready)) && !flush_valid;
    wire fast_lookup=((FAST_READ_HIT!=0 && !request_write) || (FAST_WRITE_HIT!=0 && request_write && READ_ONLY==0)) && state==LOOKUP;
    wire fast_hit=fast_lookup && (hit0 || hit1);
    assign rsp_valid=state==RESPONSE || fast_hit;
    assign rsp_data=rsp_error ? 32'b0 : fast_lookup ? current_word : response_data;
    assign rsp_pair_data=fast_lookup ? current_pair_word : response_pair_data;
    assign rsp_is_c=rsp_error ? 2'b11 : fast_lookup ? current_is_c : compact_halves(response_data);
    assign rsp_pair_is_c=fast_lookup ? current_pair_is_c : compact_halves(response_pair_data);
    assign rsp_pair_valid=READ_ONLY!=0 && FETCH_PAIR!=0 && !request_address[2] && !rsp_error;
    assign flush_ready=state==FLUSH_DONE;
    assign cmd_valid=state==WB_CMD || state==FILL_CMD;
    assign cmd_write=state==WB_CMD;
    assign cmd_address=state==WB_CMD ? victim_base : {request_address[31:WORD_BITS+2],{(WORD_BITS+2){1'b0}}};
    assign cmd_length=LINE_LENGTH[7:0];
    assign w_valid=state==WB_DATA;
    assign w_last=last_beat;
    assign b_ready=state==WB_ACK;
    assign r_ready=state==FILL_DATA;
    generate if(READ_ONLY==0 || FETCH_PAIR==0) begin : asynchronous_tags
        assign lookup_tag0=tags[way0];
        assign lookup_tag1=tags[way1];
    end endgenerate
    generate
        if(READ_ONLY!=0) begin : ram_valid
            localparam integer VALID_OFFSET_BITS=SET_BITS>7 ? 7 : SET_BITS;
            localparam integer VALID_BANK_BITS=SET_BITS-VALID_OFFSET_BITS;
            localparam integer VALID_BANKS=1<<VALID_BANK_BITS;
            wire [SETS-1:0] valid_way0,valid_way1;
            wire [VALID_BANKS-1:0] bank_valid0,bank_valid1;
            reg [(VALID_BANK_BITS>0 ? VALID_BANK_BITS : 1)-1:0] read_valid_bank;
            reg clearing;
            reg [SET_BITS-1:0] clear_set;
            reg read_valid0,read_valid1,forward_valid0,forward_valid1;
            wire [SET_BITS-1:0] read_set=req_address[WORD_BITS+SET_BITS+1:WORD_BITS+2];
            wire finish_fill=state==FILL_DATA && r_valid && r_last;
            wire fill_commit=finish_fill && last_beat && !r_error && !fill_failed;
            wire update_valid=(state==FILL_CMD && cmd_ready) || finish_fill || state==FLUSH_SCAN;
            wire update_way=state==FLUSH_SCAN ? scan_line[SET_BITS] : victim[SET_BITS];
            wire [SET_BITS-1:0] write_set=clearing ? clear_set :
                state==FLUSH_SCAN ? scan_line[SET_BITS-1:0] : victim[SET_BITS-1:0];
            wire write_value=!clearing && fill_commit;
            assign valid_ready=!clearing;
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin clearing<=1; clear_set<=0; end
                else if(clearing) begin
                    if(&clear_set) clearing<=0;
                    else clear_set<=clear_set+1'b1;
                end
            end
            for(genvar valid_bank=0;valid_bank<VALID_BANKS;valid_bank=valid_bank+1) begin : banks
                (* syn_ramstyle="lut_ram" *) reg storage0[0:(1<<VALID_OFFSET_BITS)-1];
                (* syn_ramstyle="lut_ram" *) reg storage1[0:(1<<VALID_OFFSET_BITS)-1];
                reg read0,read1;
                wire selected_bank=(write_set >> VALID_OFFSET_BITS)==valid_bank;
                always @(posedge clk) begin
                    if(rst_n && selected_bank) begin
                        if(clearing || (update_valid && !update_way))
                            storage0[write_set[VALID_OFFSET_BITS-1:0]]<=write_value;
                        if(clearing || (update_valid && update_way))
                            storage1[write_set[VALID_OFFSET_BITS-1:0]]<=write_value;
                    end
                    if(req_ready) begin
                        read0<=storage0[read_set[VALID_OFFSET_BITS-1:0]];
                        read1<=storage1[read_set[VALID_OFFSET_BITS-1:0]];
                    end
                end
                assign bank_valid0[valid_bank]=read0;
                assign bank_valid1[valid_bank]=read1;
                for(genvar valid_offset=0;valid_offset<(1<<VALID_OFFSET_BITS);valid_offset=valid_offset+1) begin : view
                    assign valid_way0[(valid_bank<<VALID_OFFSET_BITS)+valid_offset]=storage0[valid_offset];
                    assign valid_way1[(valid_bank<<VALID_OFFSET_BITS)+valid_offset]=storage1[valid_offset];
                end
            end
            always @(posedge clk) begin
                if(req_ready) begin
                    read_valid_bank<=read_set >> VALID_OFFSET_BITS;
                    read_valid0<=valid_way0[read_set];
                    read_valid1<=valid_way1[read_set];
                end
            end
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin forward_valid0<=0; forward_valid1<=0; end
                else if(req_ready) begin forward_valid0<=0; forward_valid1<=0; end
                else if(fill_commit) begin
                    if(!victim[SET_BITS]) forward_valid0<=1;
                    else forward_valid1<=1;
                end
            end
            assign lookup_valid0=forward_valid0 || (FETCH_PAIR!=0 ? bank_valid0[read_valid_bank] : read_valid0);
            assign lookup_valid1=forward_valid1 || (FETCH_PAIR!=0 ? bank_valid1[read_valid_bank] : read_valid1);
            // Preserve the metadata view used by cache diagnostics. In read-only
            // hardware the dirty bits are zero, so the FSM's wide reads prune out.
            for(genvar valid_index=0;valid_index<SETS;valid_index=valid_index+1) begin : view
                assign valid[valid_index]=valid_way0[valid_index];
                assign valid[SETS+valid_index]=valid_way1[valid_index];
            end
        end else begin : register_valid
            assign valid_ready=1'b1;
            assign valid=writable_valid;
            reg [LINES-1:0] writable_valid;
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) writable_valid<=0;
                else case(state)
                    WB_ACK: if(b_valid && !b_error) writable_valid[victim]<=0;
                    FILL_CMD: if(cmd_ready) writable_valid[victim]<=0;
                    FILL_DATA: if(r_valid && r_last)
                        writable_valid[victim]<=!fill_failed && !r_error && last_beat;
                    FLUSH_SCAN: if(!(valid[scan_line] && scan_dirty))
                        writable_valid[scan_line]<=0;
                    default: begin end
                endcase
            end
            if(READ_ONLY==0 && SET_BITS>4) begin : banked_valid
                localparam integer BANK_BITS=SET_BITS-4;
                localparam integer BANKS=1<<BANK_BITS;
                wire [3:0] valid_offset=req_address[WORD_BITS+5:WORD_BITS+2];
                wire [BANK_BITS-1:0] valid_bank=req_address[WORD_BITS+SET_BITS+1:WORD_BITS+6];
                wire fill_commit=state==FILL_DATA && r_valid && r_last && last_beat && !r_error && !fill_failed;
                reg [BANK_BITS-1:0] read_bank;
                wire [BANKS-1:0] read_valid0,read_valid1;
                always @(posedge clk or negedge rst_n) begin
                    if(!rst_n) read_bank<=0;
                    else if(req_ready) read_bank<=valid_bank;
                end
                for(genvar bank_index=0;bank_index<BANKS;bank_index=bank_index+1) begin : banks
                    reg valid0,valid1;
                    wire [15:0] bank_valid0=valid[bank_index*16+:16];
                    wire [15:0] bank_valid1=valid[SETS+bank_index*16+:16];
                    always @(posedge clk or negedge rst_n) begin
                        if(!rst_n) begin valid0<=0; valid1<=0; end
                        else if(req_ready) begin
                            valid0<=bank_valid0[valid_offset];
                            valid1<=bank_valid1[valid_offset];
                        end else if(fill_commit) begin
                            if(!victim[SET_BITS]) valid0<=1;
                            else valid1<=1;
                        end
                    end
                    assign read_valid0[bank_index]=valid0;
                    assign read_valid1[bank_index]=valid1;
                end
                assign lookup_valid0=read_valid0[read_bank];
                assign lookup_valid1=read_valid1[read_bank];
            end else begin : synchronous_valid
                wire [SET_BITS-1:0] valid_set=req_address[WORD_BITS+SET_BITS+1:WORD_BITS+2];
                wire [SET_BITS:0] valid_way0={1'b0,valid_set},valid_way1={1'b1,valid_set};
                wire fill_commit=state==FILL_DATA && r_valid && r_last && last_beat && !r_error && !fill_failed;
                reg read_valid0,read_valid1;
                always @(posedge clk or negedge rst_n) begin
                    if(!rst_n) begin read_valid0<=0; read_valid1<=0; end
                    else if(req_ready) begin
                        read_valid0<=valid[valid_way0];
                        read_valid1<=valid[valid_way1];
                    end else if(fill_commit) begin
                        if(!victim[SET_BITS]) read_valid0<=1;
                        else read_valid1<=1;
                    end
                end
                assign lookup_valid0=read_valid0;
                assign lookup_valid1=read_valid1;

            end
        end
    endgenerate
    generate
        if(READ_ONLY!=0 && FETCH_PAIR!=0) begin : synchronous_pair
            wire [SET_BITS+WORD_BITS-2:0] read_index=req_ready ?
                req_address[WORD_BITS+SET_BITS+1:3] : {request_set,request_word[WORD_BITS-1:1]};
            wire [SET_BITS+WORD_BITS-2:0] fill_index={victim[SET_BITS-1:0],beat[WORD_BITS-1:1]};
            wire fill_write=state==FILL_DATA && r_valid && !r_error && !fill_failed;
            wire [31:0] pair_word[0:1];
            wire [1:0] compact_way0[0:1],compact_way1[0:1];
            for(genvar bank=0;bank<2;bank=bank+1) begin : banks
                localparam integer BANK_WIDTH=bank==0 ? 32+TAG_BITS : 32;
                (* syn_ramstyle="block_ram" *) reg [BANK_WIDTH-1:0] storage_way0[0:SETS*WORDS/2-1];
                (* syn_ramstyle="block_ram" *) reg [BANK_WIDTH-1:0] storage_way1[0:SETS*WORDS/2-1];
                reg [BANK_WIDTH-1:0] read_way0,read_way1,forward_data;
                wire [BANK_WIDTH-1:0] refill_data;
                reg forward_way0,forward_way1;
                (* syn_keep=1 *) wire [1:0] read_compact0=compact_halves(read_way0[31:0]);
                (* syn_keep=1 *) wire [1:0] read_compact1=compact_halves(read_way1[31:0]);
                (* syn_keep=1 *) wire [1:0] forward_compact=compact_halves(forward_data[31:0]);
                assign compact_way0[bank]=forward_way0 ? forward_compact : read_compact0;
                assign compact_way1[bank]=forward_way1 ? forward_compact : read_compact1;
                wire bank_write=fill_write && beat[0]==(bank!=0);
                if(bank==0) begin : tag_storage
                    assign refill_data={request_tag,r_data};
                    assign lookup_tag0=forward_way0 ? forward_data[BANK_WIDTH-1:32] : read_way0[BANK_WIDTH-1:32];
                    assign lookup_tag1=forward_way1 ? forward_data[BANK_WIDTH-1:32] : read_way1[BANK_WIDTH-1:32];
                end else begin : data_storage
                    assign refill_data=r_data;
                end
                always @(posedge clk) begin
                    if(rst_n && bank_write && !victim[SET_BITS]) storage_way0[fill_index]<=refill_data;
                    if(rst_n && bank_write && victim[SET_BITS]) storage_way1[fill_index]<=refill_data;
                    read_way0<=storage_way0[read_index];
                    read_way1<=storage_way1[read_index];
                    forward_data<=refill_data;
                end
                always @(posedge clk or negedge rst_n) begin
                    if(!rst_n) begin forward_way0<=0; forward_way1<=0; end
                    else begin
                        forward_way0<=bank_write && !victim[SET_BITS] && fill_index=={request_set,request_word[WORD_BITS-1:1]};
                        forward_way1<=bank_write && victim[SET_BITS] && fill_index=={request_set,request_word[WORD_BITS-1:1]};
                    end
                end
                assign pair_word[bank]=hit1 ? (forward_way1 ? forward_data[31:0] : read_way1[31:0]) :
                    (forward_way0 ? forward_data[31:0] : read_way0[31:0]);
            end
            assign current_word=request_word[0] ? pair_word[1] : pair_word[0];
            assign current_pair_word=pair_word[1];
            (* syn_keep=1 *) wire [1:0] requested_compact0=request_word[0] ? compact_way0[1] : compact_way0[0];
            (* syn_keep=1 *) wire [1:0] requested_compact1=request_word[0] ? compact_way1[1] : compact_way1[0];
            assign current_is_c=hit1 ? requested_compact1 : requested_compact0;
            assign current_pair_is_c=hit1 ? compact_way1[1] : compact_way0[1];
            assign w_data=32'b0;
        end else if(READ_ONLY!=0) begin : synchronous_readonly
            assign current_pair_word=0;
            assign current_is_c=compact_halves(current_word);
            assign current_pair_is_c=2'b11;
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
        end else begin : synchronous_writable
            assign current_pair_word=0;
            assign current_is_c=compact_halves(current_word);
            assign current_pair_is_c=2'b11;
            (* syn_ramstyle="block_ram" *) reg [31:0] storage_way0[0:SETS*WORDS-1];
            (* syn_ramstyle="block_ram" *) reg [31:0] storage_way1[0:SETS*WORDS-1];
            reg [31:0] read_way0,read_way1,forward_data;
            reg forward_way0,forward_way1;
            wire store_hit=state==LOOKUP && (hit0 || hit1) && request_write && |request_strobe;
            wire store_fill=state==FILL_DATA && r_valid && !r_error && !fill_failed;
            wire store_way=store_hit ? hit_line[SET_BITS] : victim[SET_BITS];
            wire [SET_BITS+WORD_BITS-1:0] store_index=store_hit ?
                {request_set,request_word} : {victim[SET_BITS-1:0],beat};
            wire [31:0] store_data=store_hit ?
                (current_word & ~byte_mask) | (request_data & byte_mask) : r_data;
            wire writeback_read=state==WB_CMD || state==WB_DATA;
            wire [WORD_BITS-1:0] read_beat=state==WB_CMD ? {WORD_BITS{1'b0}} :
                state==WB_DATA && w_ready && !last_beat ? beat+1'b1 : beat;
            wire [SET_BITS+WORD_BITS-1:0] read_index=req_ready ?
                req_address[WORD_BITS+SET_BITS+1:2] : writeback_read ?
                {victim[SET_BITS-1:0],read_beat} : {request_set,request_word};
            wire [31:0] word_way0=forward_way0 ? forward_data : read_way0;
            wire [31:0] word_way1=forward_way1 ? forward_data : read_way1;
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin end
                else if((store_hit || store_fill) && !store_way) storage_way0[store_index]<=store_data;
            end
            always @(posedge clk) begin
                read_way0<=storage_way0[read_index];
            end
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin end
                else if((store_hit || store_fill) && store_way) storage_way1[store_index]<=store_data;
            end
            always @(posedge clk) begin
                read_way1<=storage_way1[read_index];
            end
            always @(posedge clk or negedge rst_n) begin
                if(!rst_n) begin forward_way0<=0; forward_way1<=0; end
                else begin
                    forward_way0<=(store_hit || store_fill) && !store_way && store_index==read_index;
                    forward_way1<=(store_hit || store_fill) && store_way && store_index==read_index;
                end
            end
            always @(posedge clk) forward_data<=store_data;
            wire read_select0=!hit1 && !forward_way0;
            wire read_select1=hit1 && !forward_way1;
            wire read_forward=hit1 ? forward_way1 : forward_way0;
            assign current_word=(read_way0 & {32{read_select0}}) |
                (read_way1 & {32{read_select1}}) | (forward_data & {32{read_forward}});
            assign w_data=victim[SET_BITS] ? word_way1 : word_way0;
        end
    endgenerate
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin end
        else if(state==LOOKUP && (hit0 || hit1)) lru_storage[request_set]<=!hit_line[SET_BITS];
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            stored_state<=IDLE;
            request_check_pending<=0; request_error_address<=0;
            request_address<=0; request_data<=0; request_strobe<=0; request_write<=0;
            request_missed<=0; flushing<=0; fill_failed<=0;
            victim<=0; victim_base<=0; scan_line<=0; beat<=0;
            response_data<=0; response_pair_data<=0; stored_rsp_error<=0; flush_error<=0;
            hit_count<=0; miss_count<=0; writeback_count<=0;
        end else begin
            request_check_pending<=req_valid && req_ready;
            if(request_input_error) stored_rsp_error<=1;
            case(state)
                IDLE: begin
                    if(flush_valid) begin
                        flushing<=1; scan_line<=0; flush_error<=0; stored_state<=FLUSH_SCAN;
                    end
                end
                LOOKUP: begin
                    if(hit0 || hit1) begin
                        response_data<=current_word; response_pair_data<=current_pair_word; stored_rsp_error<=0;
                        if(!request_missed) hit_count<=hit_count+1;
                        stored_state<=fast_hit && rsp_ready ? IDLE : RESPONSE;
                    end else begin
                        request_missed<=1; miss_count<=miss_count+1;
                        victim<=replacement;
                        victim_base<=READ_ONLY!=0 ? 32'b0 : {{(32-ADDRESS_BITS){1'b0}},tags[replacement],request_set,{(WORD_BITS+2){1'b0}}};
                        beat<=0;
                        stored_state<=(valid[replacement] && replacement_dirty) ? WB_CMD : FILL_CMD;
                    end
                end
                WB_CMD: if(cmd_ready) begin beat<=0; stored_state<=WB_DATA; end
                WB_DATA: if(w_ready) begin
                    if(last_beat) stored_state<=WB_ACK;
                    else beat<=beat+1'b1;
                end
                WB_ACK: if(b_valid) begin
                    if(b_error) begin
                        if(flushing) begin flush_error<=1; stored_state<=FLUSH_DONE; end
                        else begin response_data<=0; stored_rsp_error<=1; stored_state<=RESPONSE; end
                    end else begin
                        writeback_count<=writeback_count+1;
                        if(flushing) begin
                            if(&scan_line) stored_state<=FLUSH_DONE;
                            else begin scan_line<=scan_line+1'b1; stored_state<=FLUSH_SCAN; end
                        end else stored_state<=FILL_CMD;
                    end
                end
                FILL_CMD: if(cmd_ready) begin
                     fill_failed<=0; beat<=0; stored_state<=FILL_DATA;
                end
                FILL_DATA: if(r_valid) begin
                    if(r_error || r_last!=last_beat) fill_failed<=1;
                    if(r_last) begin
                        if(fill_failed || r_error || !last_beat) begin
                             response_data<=0; stored_rsp_error<=1; stored_state<=RESPONSE;
                        end else begin
                            tags[victim]<=request_tag;
                            stored_state<=LOOKUP;
                        end
                    end else if(!last_beat) beat<=beat+1'b1;
                end
                RESPONSE: stored_state<=rsp_ready ? IDLE : RESPONSE;
                FLUSH_SCAN: begin
                    if(valid[scan_line] && scan_dirty) begin
                        victim<=scan_line;
                        victim_base<=READ_ONLY!=0 ? 32'b0 : {{(32-ADDRESS_BITS){1'b0}},tags[scan_line],scan_line[SET_BITS-1:0],{(WORD_BITS+2){1'b0}}};
                        stored_state<=WB_CMD;
                    end else begin
                        if(&scan_line) stored_state<=FLUSH_DONE;
                        else scan_line<=scan_line+1'b1;
                    end
                end
                FLUSH_DONE: if(flush_valid) stored_state<=IDLE;
                default: stored_state<=IDLE;
            endcase
            if(req_ready) begin
                request_error_address<=req_address & ((32'hffffffff<<ADDRESS_BITS) | 32'h3);
                request_address<={{(32-ADDRESS_BITS){1'b0}},req_address[ADDRESS_BITS-1:0]}; request_data<=req_data;
                request_strobe<=req_strobe; request_write<=req_write;
            end
            if(req_valid && req_ready) begin
                request_missed<=0; flushing<=0; stored_rsp_error<=0;
                stored_state<=LOOKUP;
            end
        end
    end
endmodule
