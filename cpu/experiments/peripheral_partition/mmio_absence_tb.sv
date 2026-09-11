`timescale 1ns/1ps
module mmio_absence_tb;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    wire trap_valid,maintenance_fault,serial_tx;
    wire [31:0] trap_cause;
    wire [7:0] gpio_output;
    integer write_access=0,cycles=0;
    rv32_soc #(.ENABLE_M(1),.ENABLE_CACHE(1),.CACHE_SET_BITS(6),.ICACHE_SET_BITS(9),.ENABLE_PREDICTOR(1),.LOAD_USE_BUBBLE(1),.FAST_ICACHE_HIT(1),.FAST_DCACHE_READ(1),.FAST_DCACHE_WRITE(1),.FETCH_OVERLAP(1),.DATA_OVERLAP(1),.EARLY_D_REQUEST(1),.BTB_INDEX_BITS(8)) soc(
        .clk(clk),.rst_n(rst_n),.serial_rx(1'b0),.gpio_input(8'hff),
        .serial_tx(serial_tx),.gpio_output(gpio_output),.trap_valid(trap_valid),.trap_cause(trap_cause),.maintenance_fault(maintenance_fault)
    );
    initial begin
        if(!$value$plusargs("write=%d",write_access) || (write_access!=0 && write_access!=1)) $fatal(1,"Invalid access test mode");
        #1; rst_n=1;
        soc.memory_system.ram.memory[0]=32'h04000093;
        soc.memory_system.ram.memory[1]=32'h30509073;
        soc.memory_system.ram.memory[2]=32'h100000b7;
        soc.memory_system.ram.memory[3]=write_access ? 32'h0000a023 : 32'h0000a103;
        soc.memory_system.ram.memory[4]=32'h0000006f;
        soc.memory_system.ram.memory[16]=32'h0000006f;
        #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
    end
    always @(negedge clk) begin
        if(rst_n) begin
            cycles=cycles+1;
            if(cycles>10000) $fatal(1,"Missing invalid MMIO fault");
            if(serial_tx!==1'b1 || gpio_output!==8'b0 || soc.irq_external!==0 || soc.irq_timer!==0 || soc.irq_software!==0 || soc.timer_value!==0 || maintenance_fault) $fatal(1,"Unexpected bare peripheral activity");
            if(trap_valid) begin
                if(trap_cause!==(write_access ? 32'd7 : 32'd5) || soc.unused_trap_pc!==32'd12 || soc.unused_trap_value!==32'h10000000) $fatal(1,"Wrong absent MMIO trap");
                $display("PASS absent MMIO write=%0d cause=%0d cycles=%0d",write_access,trap_cause,cycles);
                $finish;
            end
        end
    end
endmodule
