`timescale 1ns/1ps
module scope_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,serial_rx=1,key_pressed=0;
    wire [7:0] gpio_input={6'b0,serial_rx,key_pressed};
    wire serial_tx,maintenance_fault,trace_valid,trap_valid;
    wire [7:0] gpio_output;
    wire [31:0] status_code,trace_pc,trace_instruction,trap_cause;
    wire [63:0] cycle_count,retired_count;
    integer uart_file,cycles=0,dumps=0,empty_count=0,timeout_count=0;
    string firmware,uart_path,line_text="";
    rv32_soc #(.CLOCK_HZ(3200),.BAUD(100)) soc(.*);
    task send_byte(input [7:0] value,input integer bit_cycles);
        begin
            @(negedge clk); serial_rx=0; repeat(bit_cycles) @(negedge clk);
            for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin serial_rx=value[bit_index]; repeat(bit_cycles) @(negedge clk); end
            serial_rx=1; repeat(bit_cycles) @(negedge clk);
        end
    endtask
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware");
        if(!$value$plusargs("uart=%s",uart_path)) $fatal(1,"Missing UART log");
        uart_file=$fopen(uart_path,"w");
        if(!uart_file) $fatal(1,"Cannot open UART log");
        #1; rst_n=1; $readmemh(firmware,soc.memory_system.ram.memory);
        #1; rst_n=0; repeat(4) @(negedge clk); rst_n=1;
        wait(status_code==32'ha1100000);
        send_byte("D",32); wait(empty_count==1);
        send_byte("K",32); wait(status_code==32'ha1100001);
        wait(timeout_count==1);
        send_byte("A",32); wait(status_code==32'ha1100001);
        send_byte(8'h55,2813);
        wait(status_code==32'ha1100003);
        send_byte("D",32); wait(dumps==1); wait(status_code==32'ha1100003);
        send_byte("K",32); wait(status_code==32'ha1100001);
        @(negedge clk); key_pressed=1;
        repeat(8000) @(negedge clk); key_pressed=0;
        repeat(8000) @(negedge clk); key_pressed=1;
        repeat(8000) @(negedge clk); key_pressed=0;
        wait(status_code==32'ha1100003);
        send_byte("D",32); wait(dumps==2); wait(status_code==32'ha1100003);
        $fclose(uart_file);
        if(gpio_output!==8'h08) $fatal(1,"Wrong ready LED state");
        $display("PASS scope cycles=%0d dumps=%0d timeout=%0d empty=%0d",cycles,dumps,timeout_count,empty_count);
        $finish;
    end
    initial begin : monitor
        reg [7:0] observed;
        forever begin
            @(negedge serial_tx);
            if(rst_n) begin
                #160; if(serial_tx!==0) $fatal(1,"UART start");
                for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin #320; observed[bit_index]=serial_tx; end
                #320; if(serial_tx!==1) $fatal(1,"UART stop");
                $fwrite(uart_file,"%c",observed);
                if(observed==10) begin
                    if(line_text=="EMPTY") empty_count=empty_count+1;
                    if(line_text=="TIMEOUT") timeout_count=timeout_count+1;
                    if(line_text.len()>=4 && line_text.substr(0,3)=="END ") dumps=dumps+1;
                    line_text="";
                end else line_text={line_text,$sformatf("%c",observed)};
            end
        end
    end
    always @(negedge clk) if(rst_n) begin
        cycles=cycles+1;
        if(trap_valid||maintenance_fault) $fatal(1,"Scope fault PC=%08x cause=%08x",trace_pc,trap_cause);
        if(cycles>10000000) $fatal(1,"Scope watchdog status=%08x dumps=%0d",status_code,dumps);
    end
endmodule
