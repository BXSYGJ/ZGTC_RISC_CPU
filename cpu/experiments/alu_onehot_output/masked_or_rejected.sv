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
    reg [9:0] decoded_operation;
    (* syn_keep=1 *) wire [9:0] operation_select;
    wire [31:0] shift_left=operand_a<<operand_b[4:0];
    wire [31:0] shift_right=operand_a>>operand_b[4:0];
    wire [31:0] shift_arithmetic=$signed(operand_a)>>>operand_b[4:0];
    assign operation_select=decoded_operation;
    always @* begin
        case (operation)
            0: decoded_operation=10'b0000000001;
            1: decoded_operation=10'b0000000010;
            2: decoded_operation=10'b0000000100;
            3: decoded_operation=10'b0000001000;
            4: decoded_operation=10'b0000010000;
            5: decoded_operation=10'b0000100000;
            6: decoded_operation=10'b0001000000;
            7: decoded_operation=10'b0010000000;
            8: decoded_operation=10'b0100000000;
            9: decoded_operation=10'b1000000000;
            default: decoded_operation=0;
        endcase
        result=({32{operation_select[0]}} & {sum_high,sum_low[15:0]}) |
               ({32{operation_select[1]}} & {difference_high,difference_low[15:0]}) |
               ({32{operation_select[2]}} & shift_left) |
               ({32{operation_select[3]}} & {31'b0,($signed(operand_a)<$signed(operand_b))}) |
               ({32{operation_select[4]}} & {31'b0,(operand_a<operand_b)}) |
               ({32{operation_select[5]}} & (operand_a^operand_b)) |
               ({32{operation_select[6]}} & shift_right) |
               ({32{operation_select[7]}} & shift_arithmetic) |
               ({32{operation_select[8]}} & (operand_a|operand_b)) |
               ({32{operation_select[9]}} & (operand_a&operand_b));
    end
endmodule
