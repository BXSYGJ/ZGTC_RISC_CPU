`timescale 1ns/1ps
`ifndef TIMER_PROG_HEX
`define TIMER_PROG_HEX "build/rtos/timer/idle.hex"
`endif
`ifndef TIMER_PROG_EVEN_HEX
`define TIMER_PROG_EVEN_HEX "build/rtos/timer/idle_even.hex"
`endif
`ifndef TIMER_PROG_ODD_HEX
`define TIMER_PROG_ODD_HEX "build/rtos/timer/idle_odd.hex"
`endif
module tb_machine_timer;
    reg clk=0;
    always #4 clk=~clk;
    reg rst_n=0;
    reg write_valid=0;
    reg [1:0] word_address=0;
    reg [31:0] write_data=0;
    reg [3:0] write_strobe=0;
    wire [31:0] read_data;
    wire [63:0] timer_value;
    wire timer_irq;
    integer checks=0;
    reg [63:0] before_time;

    machine_timer dut (.clk(clk),.rst_n(rst_n),.write_valid(write_valid),
        .word_address(word_address),.write_data(write_data),
        .write_strobe(write_strobe),.read_data(read_data),
        .timer_value(timer_value),.timer_irq(timer_irq));

    task check;
        input condition;
        input [511:0] label;
        begin
            if (condition !== 1'b1) $fatal(1,"timer check failed: %0s",label);
            checks=checks+1;
        end
    endtask
    task write_word;
        input [1:0] address;
        input [31:0] data;
        input [3:0] strobes;
        begin
            @(negedge clk);
            word_address=address; write_data=data; write_strobe=strobes;
            write_valid=1;
            @(posedge clk); #1;
            @(negedge clk); write_valid=0;
        end
    endtask
    task read_check;
        input [1:0] address;
        input [31:0] expected;
        begin
            word_address=address; #1;
            check(read_data===expected,"register readback");
        end
    endtask

    initial begin
        repeat(3) @(posedge clk);
        #1; check(timer_value===0,"reset time");
        check(!timer_irq,"reset IRQ masked by max compare");
        read_check(2,32'hffffffff); read_check(3,32'hffffffff);
        @(negedge clk); rst_n=1;
        repeat(7) @(posedge clk);
        #1; check(timer_value===7,"one increment each core clock");

        write_word(2,32'h12345678,4'b1111);
        read_check(2,32'h12345678);
        write_word(2,32'haabbccdd,4'b0101);
        read_check(2,32'h12bb56dd);
        write_word(2,32'h00000000,4'b0000);
        read_check(2,32'h12bb56dd);
        write_word(3,32'h10203040,4'b1111);
        write_word(3,32'haabbccdd,4'b1010);
        read_check(3,32'haa20cc40);
        check(!timer_irq,"partial compare does not spuriously fire");

        // Time write byte strobes, high-word carry, and zero-strobe no-op.
        write_word(1,32'h11223344,4'b1111);
        read_check(1,32'h11223344);
        write_word(1,32'haabbccdd,4'b0101);
        read_check(1,32'h11bb33dd);
        write_word(0,32'hfffffffe,4'b1111);
        repeat(3) @(posedge clk);
        #1; check(timer_value[63:32]===32'h11bb33de,"32-bit timer rollover");
        before_time=timer_value;
        write_word(0,32'h00000000,4'b0000);
        check(timer_value>before_time,"zero-strobe time write keeps counting");

        // RV32 compare update sequence: high=-1, low, final high.
        write_word(3,32'hffffffff,4'b1111);
        write_word(2,32'hffffffff,4'b1111);
        write_word(1,32'h00000000,4'b1111);
        write_word(0,32'h00000000,4'b1111);
        write_word(2,32'd32,4'b1111);
        write_word(3,32'd0,4'b1111);
        check(!timer_irq,"future deadline does not fire");
        wait(timer_value==32); #1;
        check(timer_irq,"IRQ fires exactly at equal deadline");
        repeat(5) @(posedge clk);
        #1; check(timer_irq,"IRQ remains level asserted past deadline");
        write_word(3,32'hffffffff,4'b1111);
        check(!timer_irq,"RV32 high-word masking deasserts IRQ");
        before_time=timer_value;
        write_word(2,32'd125100,4'b1111);
        write_word(3,32'd0,4'b1111);
        wait(timer_irq); #1;
        check(timer_value===64'd125100,"125 MHz compare deadline exact");
        check(timer_value-before_time>125000,"millisecond-scale timer ran");
        @(negedge clk); rst_n=0;
        #1; check(timer_value===0 && !timer_irq,"asynchronous reset restores idle");
        $display("MACHINE_TIMER_PASS checks=%0d clock_hz=125000000",checks);
        $finish;
    end
    initial begin #2000000; $fatal(1,"timer timeout"); end
endmodule

module tb_timer_mmio;
    reg clk=0;
    always #4 clk=~clk;
    reg rst_n=0;
    reg bus_valid=0, bus_write=0, bus_rsp_ready=0;
    reg [31:0] bus_address=0,bus_data=0;
    reg [3:0] bus_strobe=0;
    wire uart_valid,alive,trap,soft_start,ddvalid,ddwrite,ddready;
    wire [7:0] uart_data,led;
    wire [31:0] cause,ddaddress,dddata;
    wire [3:0] ddstrobe;
    integer checks=0;
    reg [31:0] got,held;

    rv32_cpu_subsys #(.IMEM_WORDS(4096),.DMEM_WORDS(8192),
        .PROG_HEX(`TIMER_PROG_HEX), .PROG_EVEN_HEX(`TIMER_PROG_EVEN_HEX),
        .PROG_ODD_HEX(`TIMER_PROG_ODD_HEX)) dut (
        .clk(clk),.rst_n(rst_n),.npu_busy(1'b0),.npu_done(1'b0),
        .npu_timeout(1'b0),.npu_probs_valid(1'b0),.npu_probs_pct(8'd0),
        .npu_probs_idx(4'd0),.npu_top1(4'd0),.npu_cycles(32'd0),
        .ddr_ok(1'b1),.ddr_err(1'b0),.ddr_sts(32'd0),
        .uart_valid(uart_valid),.uart_data(uart_data),.uart_ready(1'b1),
        .cpu_led(led),.cpu_alive(alive),.cpu_trap(trap),.cpu_trap_cause(cause),
        .npu_soft_start(soft_start),.dd_req_valid(ddvalid),.dd_req_ready(1'b1),
        .dd_req_address(ddaddress),.dd_req_write(ddwrite),.dd_req_data(dddata),
        .dd_req_strobe(ddstrobe),.dd_rsp_valid(1'b0),.dd_rsp_ready(ddready),
        .dd_rsp_data(32'd0),.dd_rsp_error(1'b0));

    task check;
        input condition;
        input [511:0] label;
        begin
            if (condition !== 1'b1) $fatal(1,"MMIO check failed: %0s",label);
            checks=checks+1;
        end
    endtask

    task transaction;
        input is_write;
        input [31:0] address,data;
        input [3:0] strobes;
        input expected_error;
        begin
            @(negedge clk);
            bus_valid=1; bus_write=is_write; bus_address=address;
            bus_data=data; bus_strobe=strobes; bus_rsp_ready=0;
            @(posedge clk);
            while (!dut.d_req_ready) @(posedge clk);
            #1; check(dut.d_rsp_valid,"registered response");
            check(dut.d_rsp_error===expected_error,"range error status");
            got=dut.d_rsp_data; held=got;
            @(negedge clk); bus_valid=0;
            // Changing unaccepted payloads must not replay a timer store.
            bus_data=32'hfeedface;
            repeat(3) begin
                @(posedge clk); #1;
                check(dut.d_rsp_valid && dut.d_rsp_data===held,"held response");
            end
            @(negedge clk); bus_rsp_ready=1;
            @(posedge clk); #1;
            @(negedge clk); bus_rsp_ready=0;
        end
    endtask

    initial begin
        // The real core is present. Only its bus-master outputs are overridden
        // for this peripheral protocol test; RTOS firmware tests run it normally.
        force dut.i_req_valid=1'b0;
        force dut.d_req_valid=bus_valid;
        force dut.d_req_write=bus_write;
        force dut.d_req_address=bus_address;
        force dut.d_req_data=bus_data;
        force dut.d_req_strobe=bus_strobe;
        force dut.d_rsp_ready=bus_rsp_ready;
        repeat(3) @(posedge clk);
        @(negedge clk); rst_n=1;
        transaction(0,32'h00000000,0,0,0);
        check(got===32'h0000006f,"directly initialized data ROM first word");
        transaction(0,32'h00003ffc,0,0,0);
        check(got===32'd0,"directly initialized data ROM last word");
        transaction(0,32'h80000038,0,0,0);
        check(got===32'hffffffff,"reset compare low via MMIO");
        transaction(0,32'h8000003c,0,0,0);
        check(got===32'hffffffff,"reset compare high via MMIO");
        transaction(1,32'h80000038,32'h12345678,4'hf,0);
        transaction(1,32'h80000038,32'haabbccdd,4'h5,0);
        transaction(0,32'h80000038,0,0,0);
        check(got===32'h12bb56dd,"MMIO strobes and no replay under backpressure");
        transaction(0,32'h80000030,0,0,0);
        check(got>0,"MMIO live mtime");
        transaction(1,32'h20007ffc,32'h12345678,4'hf,0);
        transaction(0,32'h20007ffc,0,0,0);
        check(got===32'h12345678,"parameterized RAM last word");
        transaction(1,32'h20007ffc,32'haabbccdd,4'h5,0);
        transaction(0,32'h20007ffc,0,0,0);
        check(got===32'h12bb56dd,"upper RAM byte writes");
        transaction(0,32'h20008000,0,0,1);
        transaction(0,32'h00004000,0,0,1);
        $display("TIMER_MMIO_PASS checks=%0d rom_bytes=16384 ram_bytes=32768",checks);
        $finish;
    end
    initial begin #200000; $fatal(1,"MMIO timeout"); end
endmodule
