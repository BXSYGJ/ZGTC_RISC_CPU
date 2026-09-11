`timescale 1ns/1ps
module early_compare_byte_tb;
    reg [31:0] early_operand_a=0,early_operand_b=0;
    wire early_equal,early_unsigned_less,early_signed_less;
    integer checks=0;
    reg [31:0] random_state=32'h635ac91e;
    reg [31:0] first_value,second_value,mask_value;
    early_compare_probe dut(.*);
    task automatic check_values(input [31:0] first,input [31:0] second);
        begin
            early_operand_a=first; early_operand_b=second; #1;
            if(early_equal!==(first==second) || early_unsigned_less!==(first<second) ||
               early_signed_less!==($signed(first)<$signed(second)))
                $fatal(1,"FAIL early_compare_byte first=%08x second=%08x equal=%b unsigned_less=%b signed_less=%b",first,second,early_equal,early_unsigned_less,early_signed_less);
            checks=checks+1;
        end
    endtask
    function automatic [31:0] next_random(input [31:0] value);
        reg [31:0] mixed;
        begin
            mixed=value^(value<<13); mixed=mixed^(mixed>>17);
            next_random=mixed^(mixed<<5);
        end
    endfunction
    initial begin
        for(integer lane=0;lane<4;lane=lane+1) begin
            for(integer first_byte=0;first_byte<256;first_byte=first_byte+1)
                for(integer second_byte=0;second_byte<256;second_byte=second_byte+1) begin
                    mask_value=32'hff<<(lane*8);
                    first_value=(32'h5a5a5a5a & ~mask_value) | (first_byte<<(lane*8));
                    second_value=(32'h5a5a5a5a & ~mask_value) | (second_byte<<(lane*8));
                    check_values(first_value,second_value);
                    if(lane>0) begin
                        mask_value=(32'h1<<(lane*8))-1;
                        check_values(first_value | mask_value,second_value & ~mask_value);
                        check_values(first_value & ~mask_value,second_value | mask_value);
                    end
                end
            $display("COVER early_compare_byte lane=%0d",lane);
        end
        for(integer bit_index=0;bit_index<32;bit_index=bit_index+1) begin
            first_value=32'h1<<bit_index;
            check_values(first_value,0); check_values(0,first_value);
            check_values(first_value,first_value); check_values(~first_value,first_value);
            check_values(first_value-1,first_value); check_values(first_value,first_value-1);
        end
        for(integer sample=0;sample<65536;sample=sample+1) begin
            random_state=next_random(random_state); first_value=random_state;
            random_state=next_random(random_state); second_value=random_state;
            check_values(first_value,second_value);
            check_values(first_value,first_value);
        end
        if(checks!=786624) $fatal(1,"FAIL early_compare_byte incomplete coverage checks=%0d",checks);
        $display("PASS early_compare_byte checks=%0d byte_pairs=262144 random_pairs=65536",checks);
        $finish;
    end
endmodule
