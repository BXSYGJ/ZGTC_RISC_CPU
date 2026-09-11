`timescale 1ns/1ps
module timer_next_native_tb;
    reg clk=0;
    reg rst_n=0;
    wire irq_timer;
    integer checks=0;
    reg [63:0] corners [0:15];
    reg [63:0] random_state=64'hc48e7f92051bd63a;
    reg [63:0] sample_value,sample_compare;
    timer_native_comparison dut(.timer_value_next(sample_value),.timer_compare_next(sample_compare),.timer_interrupt_next(irq_timer));
    function automatic [63:0] next_random(input [63:0] source);
        reg [63:0] mixed;
        begin
            mixed=source^(source<<13);
            mixed=mixed^(mixed>>7);
            next_random=mixed^(mixed<<17);
        end
    endfunction
    task check_pair(input [63:0] value_input,input [63:0] compare_input);
        begin
            sample_value=value_input;
            sample_compare=compare_input;
            #1;
            checks=checks+1;
            if(irq_timer!==(value_input>=compare_input))
                $fatal(1,"timer comparison differs value=%h compare=%h irq=%b",value_input,compare_input,irq_timer);
        end
    endtask
    initial begin
        #1;rst_n=1;#1;rst_n=0;#1;rst_n=1;
        corners[0]=0;corners[1]=1;corners[2]=64'hffffffffffffffff;corners[3]=64'hfffffffffffffffe;
        corners[4]=64'h00000000ffffffff;corners[5]=64'h0000000100000000;corners[6]=64'h0000000100000001;
        corners[7]=64'h7fffffff00000000;corners[8]=64'h8000000000000000;corners[9]=64'h7fffffffffffffff;
        corners[10]=64'h80000000ffffffff;corners[11]=64'hffffffff00000000;corners[12]=64'h0000000080000000;
        corners[13]=64'h000000007fffffff;corners[14]=64'h55555555aaaaaaaa;corners[15]=64'haaaaaaaa55555555;
        for(integer value_index=0;value_index<16;value_index=value_index+1)
            for(integer compare_index=0;compare_index<16;compare_index=compare_index+1)
                check_pair(corners[value_index],corners[compare_index]);
        for(integer sample_index=0;sample_index<10000;sample_index=sample_index+1) begin
            random_state=next_random(random_state);sample_value=random_state;
            random_state=next_random(random_state);sample_compare=random_state;
            check_pair(sample_value,sample_compare);
            check_pair(sample_value,{sample_value[63:32],sample_compare[31:0]});
            check_pair(sample_value,sample_value);
            check_pair({sample_value[63:32],32'hffffffff},{sample_value[63:32]+32'd1,32'b0});
        end
        if(checks!=40256) $fatal(1,"incomplete timer comparison inventory");
        $display("PASS timer_next_native checks=%0d",checks);
        $finish;
    end
endmodule
