`timescale 1ns/1ps
module rv32_alu (
    input wire [31:0] operand_a,
    input wire [31:0] operand_b,
    input wire [3:0] operation,
    output reg [31:0] result
);
    always @* begin
        case (operation)
            0: result=operand_a+operand_b;
            1: result=operand_a-operand_b;
            2: result=operand_a<<operand_b[4:0];
            3: result={31'b0,($signed(operand_a)<$signed(operand_b))};
            4: result={31'b0,(operand_a<operand_b)};
            5: result=operand_a^operand_b;
            6: result=operand_a>>operand_b[4:0];
            7: result=$signed(operand_a)>>>operand_b[4:0];
            8: result=operand_a|operand_b;
            9: result=operand_a&operand_b;
            default: result=0;
        endcase
    end
endmodule
