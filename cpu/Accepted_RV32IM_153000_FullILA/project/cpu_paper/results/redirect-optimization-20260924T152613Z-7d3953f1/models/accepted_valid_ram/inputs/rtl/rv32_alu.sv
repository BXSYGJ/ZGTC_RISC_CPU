`timescale 1ns/1ps
module rv32_alu (
    input wire [31:0] operand_a,
    input wire [31:0] operand_b,
    input wire [3:0] operation,
    output reg [31:0] result
);
    wire [16:0] sum_low={1'b0,operand_a[15:0]}+{1'b0,operand_b[15:0]};
    (* syn_keep=1 *) wire [15:0] sum_high_zero;
    (* syn_keep=1 *) wire [15:0] sum_high_one;
    wire [16:0] difference_low={1'b0,operand_a[15:0]}-{1'b0,operand_b[15:0]};
    (* syn_keep=1 *) wire [15:0] difference_high_zero;
    (* syn_keep=1 *) wire [15:0] difference_high_one;
    assign sum_high_zero=operand_a[31:16]+operand_b[31:16];
    assign sum_high_one=operand_a[31:16]+operand_b[31:16]+16'd1;
    assign difference_high_zero=operand_a[31:16]-operand_b[31:16];
    assign difference_high_one=operand_a[31:16]-operand_b[31:16]-16'd1;
    wire [15:0] sum_high=sum_low[16] ? sum_high_one : sum_high_zero;
    wire [15:0] difference_high=difference_low[16] ? difference_high_one : difference_high_zero;
    wire shift_left=operation==2;
    wire [31:0] reversed_operand,shift_operand;
    wire signed [32:0] extended_shift_operand;
    wire [31:0] shifted_operand;
    wire unused_shifted_sign;
    wire [31:0] reversed_shifted,shift_result;
    generate for(genvar shift_bit=0;shift_bit<32;shift_bit=shift_bit+1) begin: shift_reverse
        assign reversed_operand[shift_bit]=operand_a[31-shift_bit];
        assign reversed_shifted[shift_bit]=shifted_operand[31-shift_bit];
    end endgenerate
    assign shift_operand=shift_left ? reversed_operand : operand_a;
    assign extended_shift_operand={operation==7 ? operand_a[31] : 1'b0,shift_operand};
    assign {unused_shifted_sign,shifted_operand}=extended_shift_operand>>>operand_b[4:0];
    assign shift_result=shift_left ? reversed_shifted : shifted_operand[31:0];
    always @* begin
        case (operation)
            0: result={sum_high,sum_low[15:0]};
            1: result={difference_high,difference_low[15:0]};
            2,6,7: result=shift_result;
            3: result={31'b0,($signed(operand_a)<$signed(operand_b))};
            4: result={31'b0,(operand_a<operand_b)};
            5: result=operand_a^operand_b;
            8: result=operand_a|operand_b;
            9: result=operand_a&operand_b;
            default: result=0;
        endcase
    end
endmodule
