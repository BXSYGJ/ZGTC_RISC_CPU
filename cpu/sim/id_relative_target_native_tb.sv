`timescale 1ns/1ps
module id_relative_target_native_tb;
    reg [31:0] instruction=0,pc=0;
    wire [31:0] actual,immediate;
    wire is_branch,is_jal;
    integer sample_index,checks=0;
    relative_native_adder candidate(.id_instruction(instruction),.id_pc(pc),.value(actual));
    rv32_decode #(.ENABLE_M(1)) reference(.instruction(instruction),.immediate(immediate),.is_branch(is_branch),.is_jal(is_jal));
    initial begin
        for(sample_index=0;sample_index<32768;sample_index=sample_index+1) begin
            instruction=$random;
            if(sample_index%8<6) begin
                instruction[6:0]=7'h63;
                case(sample_index%8)
                    0: instruction[14:12]=0;
                    1: instruction[14:12]=1;
                    2: instruction[14:12]=4;
                    3: instruction[14:12]=5;
                    4: instruction[14:12]=6;
                    default: instruction[14:12]=7;
                endcase
            end else instruction[6:0]=7'h6f;
            case(sample_index%4)
                0: pc=32'hfffffff0;
                1: pc=32'h0000ffff;
                2: pc=32'h7ffffffe;
                default: pc=$random;
            endcase
            #1;
            if(!(is_branch || is_jal) || actual!==(pc+immediate))
                $fatal(1,"FAIL relative native target instruction=%h pc=%h immediate=%h expected=%h actual=%h",instruction,pc,immediate,pc+immediate,actual);
            checks=checks+1;
        end
        $display("PASS relative native target checks=%0d branches=24576 jal=8192",checks);
        $finish;
    end
endmodule
