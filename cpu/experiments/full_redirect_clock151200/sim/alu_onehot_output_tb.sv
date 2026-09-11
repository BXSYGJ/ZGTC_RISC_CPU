`timescale 1ns/1ps
module alu_onehot_output_tb;
    reg [31:0] operand_a=0,operand_b=0;
    reg [3:0] operation=0;
    wire [31:0] baseline_result,candidate_result;
    reg [31:0] edges[0:15];
    reg [31:0] random_state=32'h104729;
    reg [31:0] random_first,random_second;
    reg [3:0] unknown_operation;
    integer checks=0;
    rv32_alu_baseline baseline(.operand_a(operand_a),.operand_b(operand_b),.operation(operation),.result(baseline_result));
    rv32_alu_candidate candidate(.operand_a(operand_a),.operand_b(operand_b),.operation(operation),.result(candidate_result));
    task automatic check_case(input [31:0] first,input [31:0] second,input [3:0] opcode);
        begin
            operand_a=first; operand_b=second; operation=opcode;
            #1;
            if(candidate_result!==baseline_result)
                $fatal(1,"FAIL onehot_output op=%b first=%h second=%h expected=%h actual=%h",operation,first,second,baseline_result,candidate_result);
            checks=checks+1;
        end
    endtask
    task next_random;
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
        end
    endtask
    initial begin
        edges[0]=0; edges[1]=1; edges[2]=32'h0000ffff; edges[3]=32'h00010000;
        edges[4]=32'h00010001; edges[5]=32'h0001ffff; edges[6]=32'hffff0000; edges[7]=32'hffffffff;
        edges[8]=32'h7fffffff; edges[9]=32'h80000000; edges[10]=32'h7fff0000; edges[11]=32'h8000ffff;
        edges[12]=32'h5555ffff; edges[13]=32'haaaa0000; edges[14]=32'h55550000; edges[15]=32'haaaaffff;
        for(integer first=0;first<16;first=first+1)
            for(integer second=0;second<16;second=second+1)
                for(integer opcode=0;opcode<16;opcode=opcode+1)
                    check_case(edges[first],edges[second],opcode[3:0]);
        for(integer position=0;position<32;position=position+1)
            for(integer amount=0;amount<32;amount=amount+1)
                for(integer opcode=0;opcode<16;opcode=opcode+1) begin
                    check_case(32'd1<<position,32'hffffffe0|amount,opcode[3:0]);
                    check_case(~(32'd1<<position),32'hffffffe0|amount,opcode[3:0]);
                end
        for(integer trial=0;trial<1000;trial=trial+1) begin
            next_random; random_first=random_state;
            next_random; random_second=random_state;
            for(integer opcode=0;opcode<16;opcode=opcode+1)
                check_case(random_first,random_second,opcode[3:0]);
        end
        for(integer encoded=0;encoded<256;encoded=encoded+1) begin
            for(integer digit=0;digit<4;digit=digit+1)
                case((encoded>>(digit*2))&3)
                    0: unknown_operation[digit]=0;
                    1: unknown_operation[digit]=1;
                    2: unknown_operation[digit]=1'bx;
                    3: unknown_operation[digit]=1'bz;
                endcase
            check_case(32'h89abcdef,32'h76543210,unknown_operation);
            check_case(32'hxxxxxxxx,32'hzzzzzzzz,unknown_operation);
        end
        for(integer opcode=0;opcode<16;opcode=opcode+1) begin
            check_case(32'h123x5678,32'h00000004,opcode[3:0]);
            check_case(32'h80000000,32'h0000000x,opcode[3:0]);
            check_case(32'hz0000000,32'h00000010,opcode[3:0]);
            check_case(32'h00000000,32'hzzzzzzzz,opcode[3:0]);
        end
        if(checks!=53440) $fatal(1,"Incomplete onehot output coverage: %0d",checks);
        $display("PASS onehot_output checks=%0d",checks);
        $finish;
    end
endmodule
