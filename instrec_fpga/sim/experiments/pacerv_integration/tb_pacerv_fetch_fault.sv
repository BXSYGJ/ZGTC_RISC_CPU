// Architectural fetch faults: ROM-end straddle and low/high out-of-range jumps.
`timescale 1ns/1ps
module tb_pacerv_fetch_fault;
    reg clk = 0, rst_n = 0;
    always #4.571428571 clk = ~clk;
    wire uart_valid, cpu_alive, cpu_trap, npu_soft_start;
    wire [7:0] uart_data, cpu_led;
    wire [31:0] cpu_trap_cause;
    wire dd_req_valid, dd_req_write, dd_rsp_ready;
    wire [31:0] dd_req_address, dd_req_data;
    wire [3:0] dd_req_strobe;
    rv32_cpu_subsys #(
        .PROG_HEX("sim/experiments/pacerv_integration/pacerv_directed.hex")
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .npu_busy(1'b0), .npu_done(1'b0), .npu_timeout(1'b0),
        .npu_probs_valid(1'b0), .npu_probs_pct(8'd0), .npu_probs_idx(4'd0),
        .npu_top1(4'd0), .npu_cycles(32'd0),
        .ddr_ok(1'b1), .ddr_err(1'b0), .ddr_sts(32'd1),
        .uart_valid(uart_valid), .uart_data(uart_data), .uart_ready(1'b1),
        .cpu_led(cpu_led), .cpu_alive(cpu_alive), .cpu_trap(cpu_trap),
        .cpu_trap_cause(cpu_trap_cause), .npu_soft_start(npu_soft_start),
        .dd_req_valid(dd_req_valid), .dd_req_ready(1'b1),
        .dd_req_address(dd_req_address), .dd_req_write(dd_req_write),
        .dd_req_data(dd_req_data), .dd_req_strobe(dd_req_strobe),
        .dd_rsp_valid(1'b0), .dd_rsp_ready(dd_rsp_ready),
        .dd_rsp_data(32'd0), .dd_rsp_error(1'b0)
    );
    task check_jump;
        input [31:0] target, expected_fault_address;
        reg [31:0] upper, lower;
        integer elapsed;
        begin
            @(negedge clk); rst_n = 0;
            repeat (4) @(negedge clk);
            upper = (target + 32'h800) & 32'hfffff000;
            lower = target - upper;
            dut.imem_even[0] = 32'h10000093; // addi x1,zero,0x100
            dut.imem_odd[0] = 32'h30509073;  // csrw mtvec,x1
            dut.imem_even[1] = upper | 32'h000000b7;
            dut.imem_odd[1] = {lower[11:0],20'h08093};
            dut.imem_even[2] = 32'h00008067; // jalr zero,x1,0
            dut.imem_even[32] = 32'h0000006f;
            dut.imem_odd[1023] = 32'h00730001;
            rst_n = 1;
            elapsed = 0;
            while (!cpu_trap && elapsed < 2000) begin
                @(negedge clk); elapsed = elapsed + 1;
            end
            if (!cpu_trap || cpu_trap_cause !== 32'd1 ||
                dut.trap_pc_u !== target || dut.trap_value_u !== expected_fault_address)
                $fatal(1, "fetch fault target=%h trap=%b cause=%h pc=%h value=%h",
                       target, cpu_trap, cpu_trap_cause, dut.trap_pc_u, dut.trap_value_u);
        end
    endtask
    initial begin
        check_jump(32'h00002000, 32'h00002000);
        check_jump(32'h80002000, 32'h80002000);
        check_jump(32'h00001ffe, 32'h00002000);
        $display("PACERV_FETCH_FAULT_PASS cases=3 cause=1 pc_and_mtval_exact=1 no_alias=1");
        $finish;
    end
endmodule
