`timescale 1ns/1ps
module timer_increment_native_tb;
    reg [63:0] timer_value=0;
    wire [63:0] timer_incremented;
    reg [63:0] random_state=64'h2c6f735bd14a98e1;
    integer checks=0;
    timer_native_increment dut(.timer_value(timer_value),.timer_incremented(timer_incremented));
    task check_value(input [63:0] value);
        begin
            timer_value=value;#1;
            if(timer_incremented!==(value+64'd1)) $fatal(1,"FAIL timer native increment value=%h actual=%h",value,timer_incremented);
            checks=checks+1;
        end
    endtask
    initial begin
        for(integer bit_index=0;bit_index<64;bit_index=bit_index+1) begin
            check_value((64'd1<<bit_index)-64'd1);
            check_value(64'd1<<bit_index);
            check_value(~(64'd1<<bit_index));
        end
        for(integer sample=0;sample<4096;sample=sample+1) begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>7);
            random_state=random_state^(random_state<<17);
            check_value(random_state);
        end
        if(checks!=4288) $fatal(1,"FAIL incomplete native increment test");
        $display("PASS timer native increment checks=%0d",checks);
        $finish;
    end
endmodule
