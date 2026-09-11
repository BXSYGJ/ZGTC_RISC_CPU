`timescale 1ns/1ps
module coremark_bare_tb #(parameter integer CLOCK_HZ=157500000);
    reg clk=0;
    always #(500000000.0/CLOCK_HZ) clk=~clk;
    reg rst_n=0;
    wire maintenance_fault,trap_valid;
    wire [31:0] trap_cause;
    integer cycles=0,result_address,result_word,output_file,result_file,output_size;
    reg [31:0] output_word;
    string firmware,output_path,result_path;
    rv32_soc #(.DATA_OVERLAP(1),.BTB_INDEX_BITS(8),.EARLY_D_REQUEST(1),.ENABLE_M(1),.CLOCK_HZ(CLOCK_HZ),.ENABLE_PREDICTOR(1),.LOAD_USE_BUBBLE(1),.FETCH_OVERLAP(1),.FAST_DCACHE_WRITE(1),.FAST_DCACHE_READ(1),.FAST_ICACHE_HIT(1),.ICACHE_SET_BITS(9),.CACHE_SET_BITS(6),.ENABLE_CACHE(1)) soc(
        .clk(clk),.rst_n(rst_n),.serial_rx(1'b1),.gpio_input(8'b0),
        .maintenance_fault(maintenance_fault),.trap_valid(trap_valid),.trap_cause(trap_cause)
    );
    initial begin
        if(!$value$plusargs("firmware=%s",firmware) || !$value$plusargs("output=%s",output_path) || !$value$plusargs("result=%s",result_path) || !$value$plusargs("result_address=%h",result_address)) $fatal(1,"Missing bare benchmark arguments");
        if(result_address<0 || result_address+4128>65536 || result_address%8!=0) $fatal(1,"Invalid result object address");
        result_word=result_address/4;
        output_file=$fopen(output_path,"w");
        result_file=$fopen(result_path,"w");
        if(!output_file || !result_file) $fatal(1,"Cannot create benchmark evidence");
        #1; rst_n=1; $readmemh(firmware,soc.memory_system.ram.memory);
        #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
    end
    always @(negedge clk) begin
        if(rst_n) begin
            cycles=cycles+1;
            if(cycles>10000000) $fatal(1,"Bare benchmark timeout");
            if(maintenance_fault || trap_valid || soc.mmio_req_valid) $fatal(1,"Unexpected peripheral request or fault: %h",trap_cause);
            if(soc.memory_system.ram.memory[result_word]===32'hc0100001) begin
                output_size=soc.memory_system.ram.memory[result_word+6];
                if(soc.memory_system.ram.memory[result_word+7]!==0 || output_size<=0 || output_size>4096) $fatal(1,"Invalid RAM output length/overflow");
                for(integer byte_index=0;byte_index<output_size;byte_index=byte_index+1) begin
                    output_word=soc.memory_system.ram.memory[result_word+8+byte_index/4];
                    $fwrite(output_file,"%c",(output_word>>(8*(byte_index%4)))&32'hff);
                end
                $fdisplay(result_file,"{\"clock_hz\":%0d,\"cycles\":%0d,\"retired\":%0d,\"testbench_cycles\":%0d,\"output_bytes\":%0d}",soc.memory_system.ram.memory[result_word+1],{soc.memory_system.ram.memory[result_word+3],soc.memory_system.ram.memory[result_word+2]},{soc.memory_system.ram.memory[result_word+5],soc.memory_system.ram.memory[result_word+4]},cycles,output_size);
                $fclose(output_file); $fclose(result_file);
                $display("PASS bare CoreMark RAM output cycles=%0d bytes=%0d",cycles,output_size);
                $finish;
            end
        end
    end
endmodule
