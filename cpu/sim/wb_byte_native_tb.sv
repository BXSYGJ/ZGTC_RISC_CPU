`timescale 1ns/1ps
module wb_byte_native_tb;
    reg [31:0] compare_next_a=0,compare_next_b=0,compare_next_wb=0;
    wire [3:0] wb_a_equal,wb_a_less,wb_b_equal,wb_b_less;
    integer sample_index,byte_index,checks=0;
    reg [7:0] first,second,third;
    wb_byte_native dut(.*);
    initial begin
        for(sample_index=0;sample_index<65536;sample_index=sample_index+1) begin
            for(byte_index=0;byte_index<4;byte_index=byte_index+1) begin
                first=sample_index[7:0]+8'(byte_index*37);
                second=sample_index[15:8]+8'(byte_index*19);
                third=sample_index[7:0]^8'(byte_index*53);
                compare_next_a[byte_index*8+:8]=first;
                compare_next_wb[byte_index*8+:8]=second;
                compare_next_b[byte_index*8+:8]=third;
            end
            #1;
            for(byte_index=0;byte_index<4;byte_index=byte_index+1) begin
                first=compare_next_a[byte_index*8+:8];
                second=compare_next_wb[byte_index*8+:8];
                third=compare_next_b[byte_index*8+:8];
                if(wb_a_equal[byte_index] !== (first==second) || wb_a_less[byte_index] !== (first<second) || wb_b_equal[byte_index] !== (second==third) || wb_b_less[byte_index] !== (second<third))
                    $fatal(1,"FAIL wb_byte_native sample=%0d byte=%0d",sample_index,byte_index);
                checks=checks+2;
            end
        end
        if(checks!=524288) $fatal(1,"FAIL wb_byte_native inventory");
        $display("PASS wb_byte_native checks=%0d",checks);
        $finish;
    end
endmodule
