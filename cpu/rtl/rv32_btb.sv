`timescale 1ns/1ps
module rv32_btb #(
    parameter integer INDEX_BITS=4
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
    localparam integer TAG_BITS=30-INDEX_BITS;
    reg [ENTRIES-1:0] valid;
    reg [TAG_BITS-1:0] tags [0:ENTRIES-1];
    reg [31:0] targets [0:ENTRIES-1];
    reg [1:0] counters [0:ENTRIES-1];
    reg [ENTRIES-1:0] conditional;
    wire [INDEX_BITS-1:0] fetch_index=fetch_pc[INDEX_BITS+1:2];
    wire [INDEX_BITS-1:0] update_index=update_pc[INDEX_BITS+1:2];
    wire [TAG_BITS-1:0] fetch_tag=fetch_pc[31:INDEX_BITS+2];
    wire [TAG_BITS-1:0] update_tag=update_pc[31:INDEX_BITS+2];
    assign prediction_hit=valid[fetch_index] && tags[fetch_index]==fetch_tag && fetch_pc[1:0]==0;
    assign predicted_taken=prediction_hit && (!conditional[fetch_index] || counters[fetch_index][1]);
    assign predicted_target=prediction_hit ? targets[fetch_index] : fetch_pc+32'd4;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid<=0;
            conditional<=0;
        end else if (invalidate) begin
            valid<=0;
        end else if (update_valid && update_pc[1:0]==0 && update_target[1:0]==0) begin
            valid[update_index]<=1;
            tags[update_index]<=update_tag;
            targets[update_index]<=update_target;
            conditional[update_index]<=update_conditional;
            if (!valid[update_index] || tags[update_index]!=update_tag || conditional[update_index]!=update_conditional)
                counters[update_index]<=update_taken ? 2'b10 : 2'b01;
            else if (update_taken && counters[update_index]!=2'b11)
                counters[update_index]<=counters[update_index]+2'b01;
            else if (!update_taken && counters[update_index]!=2'b00)
                counters[update_index]<=counters[update_index]-2'b01;
        end
    end
endmodule
