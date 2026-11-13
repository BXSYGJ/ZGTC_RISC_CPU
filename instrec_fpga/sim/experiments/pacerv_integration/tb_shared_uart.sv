`timescale 1ns/1ps
// Exercise the production top's actual UART arbitration. Unrelated IP is
// left unelaborated with Icarus -i; the real UART transmitter remains present.
module tb_shared_uart;
    reg clk=0,rst_n=0;
    always #4 clk=~clk;
    wire tx;
    instrec_top dut(.clk(clk),.rst_n(rst_n),.key1_n(1'b1),.uart_rx(1'b1),.uart_tx(tx),
        .i2s_bck(1'b0),.i2s_lrck(1'b0),.i2s_sd(1'b0),.ref_clk_p(clk),.ref_clk_n(!clk));
    defparam dut.u_uart_tx.BAUD_DIV=4;
    reg [3:0] valid=0;
    wire w_valid=valid[3],b_valid=valid[2],d_valid=valid[1],c_valid=valid[0];
    reg [7:0] w_data=8'h10,b_data=8'h30,d_data=8'h50,c_data=8'h70;
    integer w_count=0,b_count=0,d_count=0,c_count=0;
    reg [7:0] expected[0:31];
    integer accepted=0,received=0,pops=0,bit_index;
    reg [7:0] value;
    initial begin
        force dut.core_clk=clk;
        force dut.core_clk_rst_n=rst_n;
        force dut.wl_tx_valid=w_valid; force dut.wl_tx_data=w_data;
        force dut.dbg_tx_valid=b_valid; force dut.dbg_tx_data=b_data;
        force dut.dg_tx_valid=d_valid; force dut.dg_tx_data=d_data;
        force dut.cpu_tx_valid=c_valid; force dut.cpu_tx_data=c_data;
        repeat(8) @(negedge clk);
        rst_n=1;
        valid=4'hf;
        #100000; $fatal(1,"Shared UART timeout accepted=%0d received=%0d",accepted,received);
    end
    always @(posedge clk) if(rst_n) begin
        pops=0;
        if(valid[3] && dut.wl_tx_ready) begin
            expected[accepted]=w_data; accepted=accepted+1; pops=pops+1;
            w_data<=w_data+1; w_count=w_count+1;
            if(w_count==8) valid[3]<=0;
        end
        if(valid[2] && dut.dbg_tx_ready) begin
            expected[accepted]=b_data; accepted=accepted+1; pops=pops+1;
            b_data<=b_data+1; b_count=b_count+1;
            if(b_count==8) valid[2]<=0;
        end
        if(valid[1] && dut.dg_tx_ready) begin
            expected[accepted]=d_data; accepted=accepted+1; pops=pops+1;
            d_data<=d_data+1; d_count=d_count+1;
            if(d_count==8) valid[1]<=0;
        end
        if(valid[0] && dut.cpu_tx_ready) begin
            expected[accepted]=c_data; accepted=accepted+1; pops=pops+1;
            c_data<=c_data+1; c_count=c_count+1;
            if(c_count==8) valid[0]<=0;
        end
        if(pops>1) $fatal(1,"Multiple UART owners consumed the same beat pops=%0d",pops);
        if(received==32 && accepted==32 && valid==0 && !dut.u_uart_tx.busy) begin
            $display("SHARED_UART_PASS sources=4 bytes=32 no_duplicate_pop=1 wire_exact=1");
            $finish;
        end
    end
    initial forever begin
        @(negedge tx); #48;
        for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin
            value[bit_index]=tx; #32;
        end
        if(tx!==1 || value!==expected[received])
            $fatal(1,"Shared UART wire mismatch byte=%0d got=%h expected=%h",received,value,expected[received]);
        received=received+1;
    end
endmodule
