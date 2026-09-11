`timescale 1ns/1ps
module alu_shared_shift_tb;
    reg [31:0] operand_a,operand_b;
    reg [3:0] operation;
    wire [31:0] baseline_result,candidate_result;
    integer checks=0;
    integer background,source_bit,bit_state,shift_amount,command_index,amount_code,amount_bit,pattern_index;
    reg [31:0] source_pattern;
    reg [4:0] amount_pattern;
    rv32_alu_baseline baseline(.operand_a(operand_a),.operand_b(operand_b),.operation(operation),.result(baseline_result));
    rv32_alu_candidate candidate(.operand_a(operand_a),.operand_b(operand_b),.operation(operation),.result(candidate_result));
    function automatic state_value(input integer digit);
        case(digit)
            0: state_value=1'b0;
            1: state_value=1'b1;
            2: state_value=1'bx;
            default: state_value=1'bz;
        endcase
    endfunction
    task automatic check_shift(input [31:0] source,input [4:0] amount,input [3:0] command);
        reg [31:0] expected;
        begin
            operand_a=source;
            operand_b={27'h7ffffff,amount};
            operation=command;
            case(command)
                2: expected=source<<amount;
                6: expected=source>>amount;
                7: expected=$signed(source)>>>amount;
                default: expected=0;
            endcase
            #1;
            if(candidate_result!==expected || baseline_result!==expected)
                $fatal(1,"FAIL shared_shift op=%b source=%h amount=%b expected=%h baseline=%h candidate=%h",command,source,amount,expected,baseline_result,candidate_result);
            checks=checks+1;
        end
    endtask
    initial begin
        for(background=0;background<2;background=background+1)
            for(source_bit=0;source_bit<32;source_bit=source_bit+1)
                for(bit_state=0;bit_state<4;bit_state=bit_state+1)
                    for(shift_amount=0;shift_amount<32;shift_amount=shift_amount+1) begin
                        source_pattern=background ? 32'hffffffff : 32'b0;
                        source_pattern[source_bit]=state_value(bit_state);
                        for(command_index=0;command_index<3;command_index=command_index+1)
                            check_shift(source_pattern,shift_amount[4:0],command_index==0 ? 4'd2 : command_index==1 ? 4'd6 : 4'd7);
                    end
        for(amount_code=0;amount_code<1024;amount_code=amount_code+1) begin
            for(amount_bit=0;amount_bit<5;amount_bit=amount_bit+1)
                amount_pattern[amount_bit]=state_value((amount_code>>(2*amount_bit))&3);
            for(pattern_index=0;pattern_index<6;pattern_index=pattern_index+1) begin
                case(pattern_index)
                    0: source_pattern=0;
                    1: source_pattern=32'hffffffff;
                    2: source_pattern=32'h80000001;
                    3: source_pattern=32'ha5a55a5a;
                    4: source_pattern={1'bz,31'b0};
                    default: source_pattern={1'bx,31'h7fffffff};
                endcase
                for(command_index=0;command_index<3;command_index=command_index+1)
                    check_shift(source_pattern,amount_pattern,command_index==0 ? 4'd2 : command_index==1 ? 4'd6 : 4'd7);
            end
        end
        if(checks!=43008) $fatal(1,"Wrong shared-shift case inventory");
        $display("PASS shared_shift checks=%0d data_checks=24576 amount_checks=18432",checks);
        $finish;
    end
endmodule
