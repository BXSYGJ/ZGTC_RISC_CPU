`timescale 1ns/1ps
module rv32_btb #(
    parameter integer INDEX_BITS=4,
    parameter integer ADDRESS_BITS=32,
    parameter integer HASH_INDEX=1,
    parameter integer HASH_ROTATE=4,
    parameter integer HISTORY_BITS=3,
    parameter integer COUNTER_BITS=2,
    parameter integer LOOP_INDEX_BITS=1,
    parameter integer LOOP_INDEX_SHIFT=5,
    parameter integer LOOP_COUNT_BITS=5
) (
    input wire clk,
    input wire rst_n,
    input wire invalidate,
    input wire [31:0] fetch_pc,
    output wire predicted_taken,
    output wire [31:0] predicted_target,
    output wire prediction_hit,
    input wire update_valid,
    input wire [31:0] update_pc,
    input wire [31:0] update_target,
    input wire update_taken,
    input wire update_conditional
);
    localparam integer ENTRIES=1<<INDEX_BITS;
    localparam integer TAG_BITS=ADDRESS_BITS-2-INDEX_BITS;
    localparam integer PATTERNS=1<<HISTORY_BITS;
    localparam integer ROTATE=HASH_ROTATE%INDEX_BITS;
    localparam [COUNTER_BITS-1:0] WEAK_TAKEN={1'b1,{(COUNTER_BITS-1){1'b0}}};
    localparam [COUNTER_BITS-1:0] WEAK_NOT_TAKEN={1'b0,{(COUNTER_BITS-1){1'b1}}};
    reg [ENTRIES-1:0] valid;
    reg [TAG_BITS-1:0] tags [0:ENTRIES-1];
    reg [ADDRESS_BITS-3:0] targets [0:ENTRIES-1];
    reg [HISTORY_BITS-1:0] history [0:ENTRIES-1];
    reg conditional [0:ENTRIES-1];
    wire [INDEX_BITS-1:0] fetch_hash=fetch_pc[2*INDEX_BITS+1:INDEX_BITS+2];
    wire [INDEX_BITS-1:0] update_hash=update_pc[2*INDEX_BITS+1:INDEX_BITS+2];
    wire [INDEX_BITS-1:0] fetch_fold=(fetch_hash << ROTATE) | (fetch_hash >> (INDEX_BITS-ROTATE));
    wire [INDEX_BITS-1:0] update_fold=(update_hash << ROTATE) | (update_hash >> (INDEX_BITS-ROTATE));
    (* syn_maxfan=24 *) wire [INDEX_BITS-1:0] fetch_index=fetch_pc[INDEX_BITS+1:2] ^
        (HASH_INDEX!=0 ? fetch_fold : {INDEX_BITS{1'b0}});
    wire [INDEX_BITS-1:0] update_index=update_pc[INDEX_BITS+1:2] ^
        (HASH_INDEX!=0 ? update_fold : {INDEX_BITS{1'b0}});
    wire [TAG_BITS-1:0] fetch_tag=fetch_pc[ADDRESS_BITS-1:INDEX_BITS+2];
    wire [TAG_BITS-1:0] update_tag=update_pc[ADDRESS_BITS-1:INDEX_BITS+2];
    wire train_update=update_valid && (update_pc >> ADDRESS_BITS)==0 &&
        (update_target >> ADDRESS_BITS)==0 && update_pc[1:0]==0 && update_target[1:0]==0;
    wire allocate_entry=!valid[update_index] || tags[update_index]!=update_tag ||
        conditional[update_index]!=update_conditional;
    wire [PATTERNS-1:0] pattern_prediction;
    assign prediction_hit=(fetch_pc >> ADDRESS_BITS)==0 && valid[fetch_index] &&
        tags[fetch_index]==fetch_tag && fetch_pc[1:0]==0;
    localparam integer LOOP_ENTRIES=1<<LOOP_INDEX_BITS;
    reg [LOOP_ENTRIES-1:0] loop_valid;
    reg [ADDRESS_BITS-3:0] loop_tags [0:LOOP_ENTRIES-1];
    reg [LOOP_COUNT_BITS-1:0] loop_count [0:LOOP_ENTRIES-1];
    reg [LOOP_COUNT_BITS-1:0] loop_trip [0:LOOP_ENTRIES-1];
    reg [1:0] loop_confidence [0:LOOP_ENTRIES-1];
    reg loop_overflow [0:LOOP_ENTRIES-1];
    reg loop_direction [0:LOOP_ENTRIES-1];
    reg loop_ahead_direction [0:LOOP_ENTRIES-1];
    wire [LOOP_INDEX_BITS-1:0] loop_fetch_index;
    wire [LOOP_INDEX_BITS-1:0] loop_update_index;
    genvar loop_index_bit;
    generate for (loop_index_bit=0;loop_index_bit<LOOP_INDEX_BITS;loop_index_bit=loop_index_bit+1) begin: loop_index_wires
        if (loop_index_bit+LOOP_INDEX_SHIFT<INDEX_BITS) begin: mapped
            assign loop_fetch_index[loop_index_bit]=fetch_index[loop_index_bit+LOOP_INDEX_SHIFT];
            assign loop_update_index[loop_index_bit]=update_index[loop_index_bit+LOOP_INDEX_SHIFT];
        end else begin: unused_index
            assign loop_fetch_index[loop_index_bit]=1'b0;
            assign loop_update_index[loop_index_bit]=1'b0;
        end
    end endgenerate
    wire loop_fetch_match=loop_valid[loop_fetch_index] &&
        loop_tags[loop_fetch_index]==fetch_pc[ADDRESS_BITS-1:2];
    wire loop_update_match=loop_valid[loop_update_index] &&
        loop_tags[loop_update_index]==update_pc[ADDRESS_BITS-1:2];
    wire loop_use=loop_fetch_match && loop_confidence[loop_fetch_index][1];
    wire loop_pending_taken=!invalidate && train_update && update_conditional && update_taken &&
        update_target<update_pc && fetch_pc[ADDRESS_BITS-1:2]==update_pc[ADDRESS_BITS-1:2];
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            loop_valid<=0;
        end else if (invalidate) begin
            loop_valid<=0;
        end else if (train_update) begin
            if (update_conditional && update_target<update_pc) begin
                loop_valid[loop_update_index]<=1;
                loop_tags[loop_update_index]<=update_pc[ADDRESS_BITS-1:2];
                if (!loop_update_match) begin
                    loop_count[loop_update_index]<=update_taken ? {{(LOOP_COUNT_BITS-1){1'b0}},1'b1} : {LOOP_COUNT_BITS{1'b0}};
                    loop_trip[loop_update_index]<=0;
                    loop_confidence[loop_update_index]<=0;
                    loop_overflow[loop_update_index]<=0;
                    loop_direction[loop_update_index]<=1;
                    loop_ahead_direction[loop_update_index]<=0;
                end else if (update_taken) begin
                    if (loop_count[loop_update_index]=={LOOP_COUNT_BITS{1'b1}}) begin
                        loop_overflow[loop_update_index]<=1;
                        loop_confidence[loop_update_index]<=0;
                        loop_direction[loop_update_index]<=0;
                        loop_ahead_direction[loop_update_index]<=0;
                    end else begin
                        loop_count[loop_update_index]<=loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-1){1'b0}},1'b1};
                        loop_direction[loop_update_index]<=(loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-1){1'b0}},1'b1})<loop_trip[loop_update_index];
                        loop_ahead_direction[loop_update_index]<=({1'b0,loop_count[loop_update_index]}+{{(LOOP_COUNT_BITS-1){1'b0}},2'b10})<{1'b0,loop_trip[loop_update_index]};
                    end
                end else begin
                    loop_count[loop_update_index]<=0;
                    loop_overflow[loop_update_index]<=0;
                    if (loop_overflow[loop_update_index] || loop_count[loop_update_index]==0) begin
                        loop_trip[loop_update_index]<=0;
                        loop_confidence[loop_update_index]<=0;
                        loop_direction[loop_update_index]<=0;
                        loop_ahead_direction[loop_update_index]<=0;
                    end else begin
                        loop_trip[loop_update_index]<=loop_count[loop_update_index];
                        loop_direction[loop_update_index]<=1;
                        loop_ahead_direction[loop_update_index]<=loop_count[loop_update_index]>1;
                        if (loop_trip[loop_update_index]==loop_count[loop_update_index]) begin
                            if (loop_confidence[loop_update_index]!=2'b11)
                                loop_confidence[loop_update_index]<=loop_confidence[loop_update_index]+2'b01;
                        end else begin
                            loop_confidence[loop_update_index]<=0;
                        end
                    end
                end
            end else if (loop_update_match) begin
                loop_valid[loop_update_index]<=0;
            end
        end
    end
    assign predicted_taken=prediction_hit && (!conditional[fetch_index] ||
        (loop_use ? (loop_pending_taken ? loop_ahead_direction[loop_fetch_index] : loop_direction[loop_fetch_index]) : pattern_prediction[history[fetch_index]]));
    assign predicted_target=prediction_hit ? {{(32-ADDRESS_BITS){1'b0}},targets[fetch_index],2'b00} : fetch_pc+32'd4;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid<=0;
        end else if (invalidate) begin
            valid<=0;
        end else if (train_update) begin
            valid[update_index]<=1;
            tags[update_index]<=update_tag;
            targets[update_index]<=update_target[ADDRESS_BITS-1:2];
            conditional[update_index]<=update_conditional;
            if (allocate_entry)
                history[update_index]<=update_conditional ? {{(HISTORY_BITS-1){1'b0}},update_taken} : {HISTORY_BITS{1'b0}};
            else if (update_conditional)
                history[update_index]<=(history[update_index] << 1) | {{(HISTORY_BITS-1){1'b0}},update_taken};
        end
    end
    genvar pattern;
    generate for (pattern=0;pattern<PATTERNS;pattern=pattern+1) begin: pattern_banks
        localparam [HISTORY_BITS-1:0] PATTERN_INDEX=pattern[HISTORY_BITS-1:0];
        reg [COUNTER_BITS-1:0] counters [0:ENTRIES-1];
        assign pattern_prediction[pattern]=counters[fetch_index][COUNTER_BITS-1];
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
            end else if (!invalidate && train_update) begin
                if (allocate_entry)
                    counters[update_index]<=update_taken ? WEAK_TAKEN : WEAK_NOT_TAKEN;
                else if (update_conditional && history[update_index]==PATTERN_INDEX) begin
                    if (update_taken && counters[update_index]!={COUNTER_BITS{1'b1}})
                        counters[update_index]<=counters[update_index]+{{(COUNTER_BITS-1){1'b0}},1'b1};
                    else if (!update_taken && counters[update_index]!={COUNTER_BITS{1'b0}})
                        counters[update_index]<=counters[update_index]-{{(COUNTER_BITS-1){1'b0}},1'b1};
                end
            end
        end
    end endgenerate
endmodule
