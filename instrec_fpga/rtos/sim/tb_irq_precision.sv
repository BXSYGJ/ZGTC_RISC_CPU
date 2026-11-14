`timescale 1ns/1ps
module tb_irq_precision;
    reg clk=0;
    always #4 clk=~clk;
    reg rst_n=0;
    wire uart_valid,alive,trap,soft_start,ddvalid,ddwrite,ddready;
    wire [7:0] uart_data,led;
    wire [31:0] cause,ddaddress,dddata;
    wire [3:0] ddstrobe;
    reg dd_rsp_valid=0;
    reg [31:0] dd_rsp_data=0;
    integer wait_count=0,requests=0,completed=0,traps=0;
    integer compressed_retired=0;
    reg saw_stalled_irq=0;

    rv32_cpu_subsys #(.IMEM_WORDS(8192),.DMEM_WORDS(4096),
        .PROG_HEX("build/rtos/irq_precision/irq.hex")) dut (
        .clk(clk),.rst_n(rst_n),.npu_busy(1'b0),.npu_done(1'b0),
        .npu_timeout(1'b0),.npu_probs_valid(1'b0),.npu_probs_pct(8'd0),
        .npu_probs_idx(4'd0),.npu_top1(4'd0),.npu_cycles(32'd0),
        .ddr_ok(1'b1),.ddr_err(1'b0),.ddr_sts(32'd0),
        .uart_valid(uart_valid),.uart_data(uart_data),.uart_ready(1'b1),
        .cpu_led(led),.cpu_alive(alive),.cpu_trap(trap),.cpu_trap_cause(cause),
        .npu_soft_start(soft_start),.dd_req_valid(ddvalid),.dd_req_ready(1'b1),
        .dd_req_address(ddaddress),.dd_req_write(ddwrite),.dd_req_data(dddata),
        .dd_req_strobe(ddstrobe),.dd_rsp_valid(dd_rsp_valid),.dd_rsp_ready(ddready),
        .dd_rsp_data(dd_rsp_data),.dd_rsp_error(1'b0));

    always @(posedge clk) begin
        if (rst_n) begin
            if (ddvalid) begin
                if (ddwrite || ddaddress != 32'h40000000 || requests != 0)
                    $fatal(1,"unexpected DDR request");
                requests<=requests+1;
                wait_count<=3000;
            end
            if (wait_count>0) begin
                wait_count<=wait_count-1;
                if (dut.timer_irq) saw_stalled_irq<=1;
                if (trap) $fatal(1,"interrupt overtook an outstanding DDR load");
                if (wait_count==1) begin
                    dd_rsp_valid<=1;
                    dd_rsp_data<=32'h89abcdef;
                end
            end
            if (dd_rsp_valid && ddready) begin
                dd_rsp_valid<=0;
                completed<=completed+1;
            end
            if (dut.trace_valid_u && dut.trace_pc_u==`IRQ_RESUME_PC)
                compressed_retired<=compressed_retired+1;
            if (trap) begin
                traps<=traps+1;
                if (cause!=32'h80000007 || dut.trap_pc_u!=`IRQ_RESUME_PC)
                    $fatal(1,"wrong precise IRQ cause/PC: %h %h expectedPC=%h",cause,dut.trap_pc_u,`IRQ_RESUME_PC);
                if (completed!=1 || dut.u_core.registers[10]!==32'h89abcdef)
                    $fatal(1,"older DDR load was not retired before IRQ");
                if (dut.u_core.registers[18]!==10)
                    $fatal(1,"younger compressed instruction retired before IRQ");
            end
        end
    end

    initial begin
        repeat(4) @(posedge clk);
        @(negedge clk); rst_n=1;
        wait(alive); #1;
        if (led!==8'ha5 || requests!=1 || completed!=1 || traps!=1 ||
            !saw_stalled_irq || compressed_retired!=1)
            $fatal(1,"IRQ accounting mismatch");
        if (dut.u_core.registers[10]!==32'h89abcdef || dut.u_core.registers[18]!==11 ||
            dut.u_core.registers[20]!==32'h80000007 ||
            dut.u_core.registers[21]!==`IRQ_RESUME_PC ||
            (dut.u_core.registers[22] & 32'h88)!==32'h80 ||
            (dut.u_core.registers[23] & 32'h8)!==32'h8 ||
            dut.u_core.registers[25]!==32'h80 ||
            dut.u_core.registers[26]!==32'h13579120 ||
            dut.u_core.registers[27]!==32'h13579135)
            $fatal(1,"CSR/mret/RVC state mismatch");
        $display("IRQ_PRECISION_PASS ddr_stall=3000 irq_pending_during_stall=1 mepc=%h rvc_retired=1 csr_hazards=pass",dut.u_core.registers[21]);
        $finish;
    end
    initial begin #1000000; $fatal(1,"IRQ precision timeout"); end
endmodule

module tb_rom_boundary;
    reg clk=0;
    always #4 clk=~clk;
    reg rst_n=0;
    wire uart_valid,alive,trap,soft_start,ddvalid,ddwrite,ddready;
    wire [7:0] uart_data,led;
    wire [31:0] cause,ddaddress,dddata;
    wire [3:0] ddstrobe;
    integer traps=0;

    rv32_cpu_subsys #(.IMEM_WORDS(8192),.DMEM_WORDS(4096),
        .PROG_HEX("build/rtos/irq_precision/rom_edge.hex")) dut (
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
    always @(posedge clk) begin
        if (rst_n && trap) begin
            traps<=traps+1;
            if (cause!=1 || dut.trap_pc_u!=32'h8000)
                $fatal(1,"wrong ROM boundary fault cause=%h pc=%h",cause,dut.trap_pc_u);
        end
    end
    initial begin
        repeat(4) @(posedge clk);
        @(negedge clk); rst_n=1;
        wait(alive); #1;
        if (led!==8'ha5 || traps!=1 || dut.u_core.registers[10]!==1 ||
            dut.u_core.registers[11]!==18 || dut.u_core.registers[20]!==1 ||
            dut.u_core.registers[21]!==32'h8000)
            $fatal(1,"ROM edge RVC/straddled instruction state mismatch");
        $display("ROM_BOUNDARY_PASS rom_bytes=32768 straddled_pc=00007ffa final_rvc_pc=00007ffe fault_pc=00008000");
        $finish;
    end
    initial begin #1000000; $fatal(1,"ROM boundary timeout"); end
endmodule
