`timescale 1ns/1ps
module soc_tb;
    parameter integer FAULT_TEST=0;
    parameter integer EXTERNAL_UART=0;
    parameter integer ENABLE_PREDICTOR=1;
    parameter integer LOAD_USE_BUBBLE=0;
    parameter integer FAST_ICACHE_HIT=0;
    parameter integer FAST_DCACHE_READ=0;
    parameter integer FAST_DCACHE_WRITE=0;
    parameter integer FETCH_OVERLAP=0;
    parameter integer DATA_OVERLAP=0;
    parameter integer EARLY_D_REQUEST=0;
    parameter integer BTB_INDEX_BITS=4;
    parameter integer ICACHE_SET_BITS=0;
    parameter integer CACHE_SET_BITS=4;
    parameter integer ENABLE_CACHE=1;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,serial_rx=1;
    reg [7:0] gpio_input=0;
    wire serial_tx,maintenance_fault,trace_valid,trap_valid;
    wire [7:0] gpio_output;
    wire [31:0] status_code,trace_pc,trace_instruction,trap_cause;
    wire [63:0] cycle_count,retired_count;
    integer checks=0,transmitted=0,software_traps=0,timer_traps=0,external_traps=0,cycles=0,trace_file;
    reg [31:0] bss_start,bss_end;
    reg [63:0] halted_retired;
    string firmware,trace_path;
    string expected={"ZGTC RV32I",8'h0d,8'h0a,"ZSOC PASS",8'h0d,8'h0a};
    rv32_soc #(.ENABLE_M(1),.DATA_OVERLAP(DATA_OVERLAP),.BTB_INDEX_BITS(BTB_INDEX_BITS),.EARLY_D_REQUEST(EARLY_D_REQUEST),.CLOCK_HZ(3200),.BAUD(100),.ENABLE_PREDICTOR(ENABLE_PREDICTOR),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.FETCH_OVERLAP(FETCH_OVERLAP),.FAST_DCACHE_WRITE(FAST_DCACHE_WRITE),.FAST_DCACHE_READ(FAST_DCACHE_READ),.FAST_ICACHE_HIT(FAST_ICACHE_HIT),.ICACHE_SET_BITS(ICACHE_SET_BITS),.CACHE_SET_BITS(CACHE_SET_BITS),.ENABLE_CACHE(ENABLE_CACHE)) soc(.*);
    task automatic check(input bit condition,input string label_text);
        begin checks=checks+1; if(!condition) $fatal(1,"FAIL SoC %s PC=%08x status=%08x",label_text,trace_pc,status_code); end
    endtask
    task send_rx(input [7:0] value);
        begin
            @(negedge clk); serial_rx=0; repeat(32) @(negedge clk);
            for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin serial_rx=value[bit_index]; repeat(32) @(negedge clk); end
            serial_rx=1; repeat(32) @(negedge clk);
        end
    endtask
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware");
        if(!$value$plusargs("trace=%s",trace_path)) $fatal(1,"Missing trace path");
        if(!$value$plusargs("bss_start=%h",bss_start)) $fatal(1,"Missing BSS start");
        if(!$value$plusargs("bss_end=%h",bss_end)) $fatal(1,"Missing BSS end");
        check(bss_end>bss_start && bss_end<=65536 && bss_start[1:0]==0 && bss_end[1:0]==0,"valid BSS range");
        check($bits(soc.core.predictor.tags[0])==soc.MEMORY_ADDRESS_BITS-BTB_INDEX_BITS,"BTB tags follow physical instruction range");
        check($bits(soc.core.predictor.targets[0])==soc.MEMORY_ADDRESS_BITS,"BTB targets store aligned physical words");
        trace_file=$fopen(trace_path,"w");
        if(!trace_file) $fatal(1,"Cannot open trace");
        #1; rst_n=1; $readmemh(firmware,soc.memory_system.ram.memory);
        for(integer word_index=int'(bss_start/4);word_index<int'(bss_end/4);word_index=word_index+1) soc.memory_system.ram.memory[word_index]=32'hdeadbeef;
        #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
        wait(status_code==32'h100);
        if(EXTERNAL_UART!=0) send_rx(8'ha5);
        else begin
            @(negedge clk); gpio_input=1;
            wait(status_code==32'h101);
            send_rx(8'ha5);
        end
    end
    initial begin : serial_monitor
        reg [7:0] observed;
        forever begin
            @(negedge serial_tx);
            if(rst_n) begin
                #160; check(serial_tx===0,"start bit");
                for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin #320; observed[bit_index]=serial_tx; end
                #320; check(serial_tx===1,"stop bit");
                if(transmitted>=expected.len() || observed!==expected[transmitted])
                    $display("UART mismatch byte=%0d observed=%02x expected=%02x",transmitted,observed,expected[transmitted]);
                check(transmitted<expected.len() && observed===expected[transmitted],"C software UART stream");
                transmitted=transmitted+1;
            end
        end
    end
    initial begin
        if(FAULT_TEST!=0) begin
            wait(soc.maintenance_valid);
            wait(soc.memory_ready);
            force soc.memory_error=1'b1;
            repeat(2) @(negedge clk);
            release soc.memory_error;
            repeat(20) @(negedge clk);
            check(maintenance_fault,"maintenance error latched");
            halted_retired=retired_count;
            repeat(100) @(negedge clk);
            check(retired_count==halted_retired && status_code==32'h100,"fault prevents fence retirement and later software execution");
            $display("PASS soc_fault checks=%0d cycles=%0d",checks,cycle_count);
            $fclose(trace_file); $finish;
        end
    end
    always @(posedge clk) begin
        if(rst_n) begin
            cycles=cycles+1;
            if(trace_valid) $fdisplay(trace_file,"%0d R %08x %08x",cycle_count,trace_pc,trace_instruction);
            if(trap_valid) begin
                $fdisplay(trace_file,"%0d T %08x",cycle_count,trap_cause);
                case(trap_cause)
                    32'h80000003: software_traps=software_traps+1;
                    32'h80000007: timer_traps=timer_traps+1;
                    32'h8000000b: external_traps=external_traps+1;
                    default: $fatal(1,"Unexpected SoC trap %08x PC=%08x",trap_cause,trace_pc);
                endcase
            end
            if(status_code[31:16]==16'hdead) $fatal(1,"C self-test failed status=%08x",status_code);
            if(FAULT_TEST==0 && maintenance_fault) $fatal(1,"Unexpected cache maintenance fault");
            if(status_code==32'hcafe0001) begin
                check(software_traps==1 && timer_traps==1 && external_traps==1,"all three interrupts exactly once");
                check(gpio_output==8'ha5 && transmitted==expected.len(),"GPIO and complete serial output");
                $display("PASS soc checks=%0d cycles=%0d retired=%0d uart_bytes=%0d interrupts=%0d/%0d/%0d",checks,cycle_count,retired_count,transmitted,software_traps,timer_traps,external_traps);
                $fclose(trace_file); $finish;
            end
            if(cycles>200000) $fatal(1,"SoC watchdog expired PC=%08x status=%08x",trace_pc,status_code);
        end
    end
endmodule
