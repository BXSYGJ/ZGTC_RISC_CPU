`timescale 1ns/1ps
module machine_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,retire=0,irq_external=0,irq_software=0,irq_timer=0;
    reg [63:0] timer_value=64'h123456789abcdef0;
    reg [11:0] read_address=0,write_address=0;
    reg read_write_intent=0,write_valid=0,trap_enter=0,return_from_trap=0;
    reg [31:0] write_data=0,trap_pc=0,trap_cause=0,trap_value=0;
    wire [31:0] read_data,return_pc,trap_target,interrupt_cause;
    wire read_illegal,interrupt_pending;
    wire [63:0] cycle_count,retired_count;
    integer checks=0;
    rv32_machine machine(.*);
    task check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL machine %s data=%08x",label_text,read_data);
        end
    endtask
    task write_csr(input [11:0] address,input [31:0] value);
        begin
            @(negedge clk); write_valid=1; write_address=address; write_data=value;
            @(posedge clk); #1;
            @(negedge clk); write_valid=0;
        end
    endtask
    task read_csr(input [11:0] address,input [31:0] expected);
        begin
            read_address=address; read_write_intent=0; #1;
            check(!read_illegal && read_data===expected,"CSR read");
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        @(negedge clk); rst_n=1;
        read_csr(12'h300,32'h1800);
        read_csr(12'h301,32'h40000100);
        read_csr(12'hc01,32'h9abcdef0);
        read_csr(12'hc81,32'h12345678);
        read_address=12'hc00; read_write_intent=1; #1; check(read_illegal,"read-only cycle write");
        read_address=12'h999; read_write_intent=0; #1; check(read_illegal,"unimplemented CSR");
        write_csr(12'h304,32'hffffffff); read_csr(12'h304,32'h888);
        irq_timer=1; #1; check(!interrupt_pending,"global interrupt mask");
        write_csr(12'h300,32'h8); #1;
        check(interrupt_pending && interrupt_cause==32'h80000007,"timer interrupt");
        irq_software=1; #1; check(interrupt_cause==32'h80000003,"software priority");
        irq_external=1; #1; check(interrupt_cause==32'h8000000b,"external priority");
        read_csr(12'h344,32'h888);
        write_csr(12'h344,0); read_csr(12'h344,32'h888);
        write_csr(12'h305,32'h101);
        trap_cause=32'h8000000b; #1; check(trap_target==32'h12c,"vectored interrupt target");
        trap_cause=2; #1; check(trap_target==32'h100,"synchronous exception remains direct");
        @(negedge clk); trap_enter=1; trap_pc=32'h82; trap_value=32'hffffffff;
        @(posedge clk); #1; check(!interrupt_pending && return_pc==32'h80,"trap saves aligned PC and masks IRQ");
        @(negedge clk); trap_enter=0;
        read_csr(12'h300,32'h1880);
        read_csr(12'h342,2); read_csr(12'h343,32'hffffffff);
        @(negedge clk); return_from_trap=1;
        @(posedge clk); #1; check(interrupt_pending,"mret restores MIE");
        @(negedge clk); return_from_trap=0;
        read_csr(12'h300,32'h1888);
        write_csr(12'h305,32'h103); read_csr(12'h305,32'h100);
        write_csr(12'h341,32'hffffffff); read_csr(12'h341,32'hfffffffc);
        write_csr(12'h300,32'hffffffff); read_csr(12'h300,32'h1888);
        write_csr(12'h306,32'hffffffff); read_csr(12'h306,7);
        write_csr(12'hb82,1);
        write_csr(12'hb02,32'hfffffffe);
        @(negedge clk); retire=1;
        repeat(2) @(posedge clk);
        @(negedge clk); retire=0;
        check(retired_count==64'h200000000,"instret rollover");
        @(negedge clk); retire=1; write_valid=1; write_address=12'hb02; write_data=7;
        @(posedge clk); #1; check(retired_count==64'h200000007,"counter write overrides increment");
        @(negedge clk); retire=0; write_valid=0;
        read_csr(12'hc02,7); read_csr(12'hc82,2);
        check(cycle_count>0,"cycle counter advances");
        $display("PASS machine checks=%0d",checks);
        $finish;
    end
    initial begin #20000; $fatal(1,"Machine watchdog timeout"); end
endmodule
