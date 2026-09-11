`timescale 1ns/1ps
module fifo_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,in_valid=0,out_ready=0;
    reg [7:0] in_data=0;
    wire in_ready,out_valid;
    wire [7:0] out_data;
    wire [2:0] count;
    reg [7:0] expected[0:4095];
    integer head=0,tail=0,checks=0,full_seen=0,empty_seen=0,full_exchange=0;
    reg [31:0] random_state=32'h13572468;
    rv32_fifo #(.DEPTH_BITS(2)) fifo(.*);
    task check(input bit condition,input string label_text);
        begin checks=checks+1; if(!condition) $fatal(1,"FAIL FIFO %s",label_text); end
    endtask
    always @(posedge clk) begin
        if(rst_n) begin
            check(int'(count)==tail-head,"occupancy matches model");
            check(out_valid===(tail!=head),"empty validity");
            check(in_ready===((tail-head)<4 || (out_valid && out_ready)),"full readiness");
            if(count==0) empty_seen=empty_seen+1;
            if(count==4) full_seen=full_seen+1;
            if(count==4 && in_valid && out_ready) full_exchange=full_exchange+1;
            if(out_valid && out_ready) begin check(out_data===expected[head],"FIFO order"); head=head+1; end
            if(in_valid && in_ready) begin expected[tail]=in_data; tail=tail+1; end
        end
    end
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
        for(integer trial=0;trial<2048;trial=trial+1) begin
            @(negedge clk);
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            in_data=8'(tail);
            if(trial<12) begin in_valid=1; out_ready=0; end
            else if(trial<24) begin in_valid=1; out_ready=1; end
            else if(trial<36) begin in_valid=0; out_ready=1; end
            else begin in_valid=random_state[0]; out_ready=random_state[1]; end
        end
        @(negedge clk); in_valid=0; out_ready=1;
        repeat(5) @(negedge clk);
        check(head==tail && full_seen>0 && empty_seen>0 && full_exchange>0,"coverage and final drain");
        $display("PASS fifo checks=%0d transfers=%0d full_exchange=%0d",checks,tail,full_exchange);
        $finish;
    end
endmodule
