`timescale 1ns/1ps
module gpio_diagnostic_tb;
    parameter integer FAST_CONFIGURATION=0;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,serial_rx=1,key_pressed=0;
    wire key=~key_pressed;
    wire serial_tx,maintenance_fault,trace_valid,trap_valid;
    wire [7:0] gpio_output;
    wire [31:0] status_code,trace_pc,trace_instruction,trap_cause;
    wire [63:0] cycle_count,retired_count;
    integer checks=0,cycles=0,external_traps=0,received=0,consumed=0;
    reg [7:0] received_bytes[0:8191];
    string firmware;
    rv32_board_top #(.CLOCK_HZ(3200),.UART_BAUD(100),.ENABLE_M(FAST_CONFIGURATION),
        .CACHE_SET_BITS(FAST_CONFIGURATION ? 6 : 4),.ICACHE_SET_BITS(FAST_CONFIGURATION ? 8 : 0),
        .BTB_INDEX_BITS(FAST_CONFIGURATION ? 8 : 4),.FAST_ICACHE_HIT(FAST_CONFIGURATION),
        .FETCH_OVERLAP(FAST_CONFIGURATION),.FAST_DCACHE_READ(FAST_CONFIGURATION),
        .FAST_DCACHE_WRITE(FAST_CONFIGURATION),.EARLY_D_REQUEST(FAST_CONFIGURATION),
        .DATA_OVERLAP(FAST_CONFIGURATION)) board(.clk(clk),.rst_n(rst_n),.key(key),.uart_rx(serial_rx),.uart_tx(serial_tx),.led(gpio_output));
    assign status_code=board.soc.status_code;
    assign trace_pc=board.soc.trace_pc;
    assign trap_valid=board.soc.trap_valid;
    assign trap_cause=board.soc.trap_cause;
    assign maintenance_fault=board.soc.maintenance_fault;
    task automatic check(input bit condition,input string label_text);
        begin checks=checks+1; if(!condition) $fatal(1,"FAIL GPIO %s PC=%08x status=%08x",label_text,trace_pc,status_code); end
    endtask
    task automatic send_rx(input [7:0] value);
        begin
            @(negedge clk); serial_rx=0; repeat(32) @(negedge clk);
            for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin serial_rx=value[bit_index]; repeat(32) @(negedge clk); end
            serial_rx=1; repeat(32) @(negedge clk);
        end
    endtask
    task automatic expect_text(input string expected);
        begin
            for(integer byte_index=0;byte_index<expected.len();byte_index=byte_index+1) begin
                wait(received>consumed);
                if(received_bytes[consumed]!==expected[byte_index])
                    $fatal(1,"FAIL GPIO UART offset=%0d actual=%02x expected=%02x",consumed,received_bytes[consumed],expected[byte_index]);
                consumed=consumed+1;
            end
            checks=checks+1;
        end
    endtask
    task automatic command(input [7:0] value,input string expected);
        begin send_rx(value); expect_text(expected); end
    endtask
    task automatic state_report(input integer level,input integer count,input integer pending,input integer last_pending,input integer enabled);
        begin
            command("S",{$sformatf("GPIO I=%08x N=%08x P=%08x L=%08x E=%08x",level,count,pending,last_pending,enabled),8'h0d,8'h0a});
        end
    endtask
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware");
        #1; rst_n=1; $readmemh(firmware,board.soc.memory_system.ram.memory);
        #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
        expect_text({"GPIO READY S=status A=arm D=disarm",8'h0d,8'h0a});
        state_report(2,0,0,0,0);
        command("A",{"GPIO ARMED",8'h0d,8'h0a});
        state_report(2,0,0,0,1);
        send_rx(8'h0d);
        send_rx(8'h0a);
        repeat(3000) @(negedge clk);
        check(received==consumed,"terminal CRLF ignored without response");
        command(8'h55,{"GPIO UNKNOWN",8'h0d,8'h0a});
        command(8'haa,{"GPIO UNKNOWN",8'h0d,8'h0a});
        state_report(2,0,0,0,1);
        check(external_traps==0,"UART-only GPIO bit1 transitions do not interrupt");
        @(negedge clk); key_pressed=1;
        repeat(3000) @(negedge clk);
        state_report(3,1,0,1,1);
        state_report(3,1,0,1,1);
        check(external_traps==1 && gpio_output==1,"held key does not retrigger");
        command("A",{"GPIO RELEASE KEY FIRST",8'h0d,8'h0a});
        state_report(3,1,0,1,1);
        @(negedge clk); key_pressed=0;
        repeat(3000) @(negedge clk);
        state_report(2,1,0,1,1);
        check(external_traps==1,"falling edge is not an interrupt");
        @(negedge clk); key_pressed=1;
        repeat(3000) @(negedge clk);
        state_report(3,2,0,1,1);
        check(external_traps==2 && gpio_output==2,"second rising edge");
        command("D",{"GPIO DISARMED",8'h0d,8'h0a});
        @(negedge clk); key_pressed=0;
        repeat(20) @(negedge clk); key_pressed=1;
        repeat(3000) @(negedge clk);
        state_report(3,2,1,1,0);
        check(external_traps==2,"masked edge pending without trap");
        command("A",{"GPIO RELEASE KEY FIRST",8'h0d,8'h0a});
        state_report(3,2,1,1,0);
        @(negedge clk); key_pressed=0;
        repeat(3000) @(negedge clk);
        command("A",{"GPIO ARMED",8'h0d,8'h0a});
        state_report(2,0,0,0,1);
        check(external_traps==2 && gpio_output==0,"rearm clears stale pending and count");
        @(negedge clk); key_pressed=1;
        repeat(3000) @(negedge clk);
        state_report(3,1,0,1,1);
        check(external_traps==3,"edge after rearm");
        repeat(100) @(negedge clk);
        check(received==consumed,"no unsolicited UART output");
        rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
        expect_text({"GPIO READY S=status A=arm D=disarm",8'h0d,8'h0a});
        state_report(3,0,0,0,0);
        check(external_traps==3,"reset while held does not enable interrupts");
        repeat(100) @(negedge clk);
        check(received==consumed,"final UART fully checked");
        $display("PASS gpio_diagnostic configuration=%0d checks=%0d cycles=%0d interrupts=%0d",FAST_CONFIGURATION,checks,cycles,external_traps);
        $finish;
    end
    initial begin : serial_monitor
        reg [7:0] observed;
        forever begin
            @(negedge serial_tx);
            if(rst_n) begin
                #160; check(serial_tx===0,"start bit");
                for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin #320; observed[bit_index]=serial_tx; end
                #320; check(serial_tx===1,"stop bit");
                check(received<8192,"UART capture capacity");
                received_bytes[received]=observed;
                received=received+1;
            end
        end
    end
    always @(posedge clk) begin
        if(rst_n) begin
            cycles=cycles+1;
            if(trap_valid) begin
                check(trap_cause==32'h8000000b,"only external interrupts permitted");
                external_traps=external_traps+1;
                if(external_traps>3) $fatal(1,"FAIL GPIO interrupt storm");
            end
            if(status_code[31:16]==16'hdead) $fatal(1,"GPIO firmware failed status=%08x",status_code);
            if(maintenance_fault) $fatal(1,"GPIO maintenance fault");
            if(cycles>1500000) $fatal(1,"GPIO watchdog PC=%08x UART=%0d/%0d",trace_pc,consumed,received);
        end
    end
endmodule
