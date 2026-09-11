`timescale 1ns/1ps
module rv32_btb #(
    parameter integer INDEX_BITS=4,
    parameter integer ADDRESS_BITS=32,
    parameter integer HASH_INDEX=1,
    parameter integer HASH_ROTATE=4,
    parameter integer HISTORY_BITS=3,
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
    localparam integer SET_INDEX_BITS=INDEX_BITS>1 ? INDEX_BITS-1 : 1;
    localparam integer TAG_BITS=ADDRESS_BITS-2-INDEX_BITS;
    localparam integer PATTERNS=1<<HISTORY_BITS;
    localparam integer ROTATE=HASH_ROTATE%INDEX_BITS;
    localparam [COUNTER_BITS-1:0] WEAK_TAKEN={1'b1,{(COUNTER_BITS-1){1'b0}}};
    localparam [COUNTER_BITS-1:0] WEAK_NOT_TAKEN={1'b0,{(COUNTER_BITS-1){1'b1}}};
    reg [ENTRIES-1:0] valid;
    reg [TAG_BITS:0] tags [0:ENTRIES-1];
    reg [(ENTRIES/2)-1:0] replacement_way;
    reg [ADDRESS_BITS-3:0] targets [0:ENTRIES-1];
    reg [HISTORY_BITS-1:0] history [0:ENTRIES-1];
    reg conditional [0:ENTRIES-1];
    wire [INDEX_BITS-1:0] fetch_hash=fetch_pc[2*INDEX_BITS+1:INDEX_BITS+2];
    wire [INDEX_BITS-1:0] update_hash=update_pc[2*INDEX_BITS+1:INDEX_BITS+2];
    wire [INDEX_BITS-1:0] fetch_fold=(fetch_hash << ROTATE) | (fetch_hash >> (INDEX_BITS-ROTATE));
    wire [INDEX_BITS-1:0] update_fold=(update_hash << ROTATE) | (update_hash >> (INDEX_BITS-ROTATE));
    wire [INDEX_BITS-1:0] fetch_hash_index=fetch_pc[INDEX_BITS+1:2] ^
        (HASH_INDEX!=0 ? fetch_fold : {INDEX_BITS{1'b0}});
    wire [INDEX_BITS-1:0] update_hash_index=update_pc[INDEX_BITS+1:2] ^
        (HASH_INDEX!=0 ? update_fold : {INDEX_BITS{1'b0}});
    wire [INDEX_BITS-1:0] fetch_base=fetch_hash_index << 1;
    wire [INDEX_BITS-1:0] update_base=update_hash_index << 1;
    wire [SET_INDEX_BITS-1:0] update_set=update_base[INDEX_BITS-1 -: SET_INDEX_BITS];
    wire [INDEX_BITS-1:0] fetch_second=fetch_base | {{(INDEX_BITS-1){1'b0}},1'b1};
    wire [INDEX_BITS-1:0] update_second=update_base | {{(INDEX_BITS-1){1'b0}},1'b1};
    wire [TAG_BITS:0] fetch_tag={fetch_pc[ADDRESS_BITS-1:INDEX_BITS+2],fetch_hash_index[INDEX_BITS-1]};
    wire [TAG_BITS:0] update_tag={update_pc[ADDRESS_BITS-1:INDEX_BITS+2],update_hash_index[INDEX_BITS-1]};
    wire fetch_hit_first=valid[fetch_base] && tags[fetch_base]==fetch_tag;
    wire fetch_hit_second=valid[fetch_second] && tags[fetch_second]==fetch_tag;
    wire update_hit_first=valid[update_base] && tags[update_base]==update_tag;
    wire update_hit_second=valid[update_second] && tags[update_second]==update_tag;
    wire [INDEX_BITS-1:0] update_index=update_hit_first ? update_base : update_hit_second ? update_second :
        !valid[update_base] ? update_base : !valid[update_second] ? update_second :
        replacement_way[update_set] ? update_second : update_base;
    wire train_update=update_valid && (update_pc >> ADDRESS_BITS)==0 &&
        (update_target >> ADDRESS_BITS)==0 && update_pc[1:0]==0 && update_target[1:0]==0;
    wire allocate_entry=!valid[update_index] || tags[update_index]!=update_tag ||
        conditional[update_index]!=update_conditional;
    wire [PATTERNS-1:0] first_pattern_prediction;
    wire [PATTERNS-1:0] second_pattern_prediction;
    wire first_taken=!conditional[fetch_base] || first_pattern_prediction[history[fetch_base]];
    wire second_taken=!conditional[fetch_second] || second_pattern_prediction[history[fetch_second]];
    assign prediction_hit=(fetch_pc >> ADDRESS_BITS)==0 && (fetch_hit_first || fetch_hit_second) &&
        fetch_pc[1:0]==0;
    assign predicted_taken=prediction_hit && (fetch_hit_second ? second_taken : first_taken);
    wire [ADDRESS_BITS-3:0] selected_target=fetch_hit_second ? targets[fetch_second] : targets[fetch_base];
    assign predicted_target=prediction_hit ? {{(32-ADDRESS_BITS){1'b0}},selected_target,2'b00} : fetch_pc+32'd4;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid<=0;
            replacement_way<=0;
        end else if (invalidate) begin
            valid<=0;
            replacement_way<=0;
        end else if (train_update) begin
            valid[update_index]<=1;
            replacement_way[update_set]<=!update_index[0];
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
        assign first_pattern_prediction[pattern]=counters[fetch_base][COUNTER_BITS-1];
        assign second_pattern_prediction[pattern]=counters[fetch_second][COUNTER_BITS-1];
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
