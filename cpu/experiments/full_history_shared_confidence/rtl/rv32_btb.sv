`timescale 1ns/1ps
module rv32_btb #(
    parameter integer INDEX_BITS=4,
    parameter integer ADDRESS_BITS=32,
    parameter integer HASH_INDEX=1,
    parameter integer HASH_ROTATE=4,
    parameter integer HISTORY_BITS=4,
    parameter integer COUNTER_BITS=2
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
    localparam integer CONFIDENCE_BITS=COUNTER_BITS>1 ? COUNTER_BITS-1 : 1;
    localparam [CONFIDENCE_BITS-1:0] MAX_CONFIDENCE=COUNTER_BITS==1 ? {CONFIDENCE_BITS{1'b0}} : {CONFIDENCE_BITS{1'b1}};
    localparam [CONFIDENCE_BITS-1:0] CONFIDENCE_ONE={{(CONFIDENCE_BITS-1){1'b0}},1'b1};
    reg [ENTRIES-1:0] valid;
    reg [TAG_BITS-1:0] tags [0:ENTRIES-1];
    reg [ADDRESS_BITS-3:0] targets [0:ENTRIES-1];
    reg [HISTORY_BITS-1:0] history [0:ENTRIES-1];
    reg conditional [0:ENTRIES-1];
    reg [CONFIDENCE_BITS-1:0] confidence [0:ENTRIES-1];
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
    wire [PATTERNS-1:0] update_prediction;
    assign prediction_hit=(fetch_pc >> ADDRESS_BITS)==0 && valid[fetch_index] &&
        tags[fetch_index]==fetch_tag && fetch_pc[1:0]==0;
    assign predicted_taken=prediction_hit && (!conditional[fetch_index] || pattern_prediction[history[fetch_index]]);
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
            if (allocate_entry)
                confidence[update_index]<=0;
            else if (update_conditional) begin
                if (update_prediction[history[update_index]]==update_taken) begin
                    if (confidence[update_index]!=MAX_CONFIDENCE)
                        confidence[update_index]<=confidence[update_index]+CONFIDENCE_ONE;
                end else if (confidence[update_index]!=0)
                    confidence[update_index]<=confidence[update_index]-CONFIDENCE_ONE;
            end
        end
    end
    genvar pattern;
    generate for (pattern=0;pattern<PATTERNS;pattern=pattern+1) begin: pattern_banks
        localparam [HISTORY_BITS-1:0] PATTERN_INDEX=pattern[HISTORY_BITS-1:0];
        reg direction [0:ENTRIES-1];
        assign pattern_prediction[pattern]=direction[fetch_index];
        assign update_prediction[pattern]=direction[update_index];
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
            end else if (!invalidate && train_update) begin
                if (allocate_entry)
                    direction[update_index]<=update_taken;
                else if (update_conditional && history[update_index]==PATTERN_INDEX && confidence[update_index]==0)
                    direction[update_index]<=update_taken;
            end
        end
    end endgenerate
endmodule
