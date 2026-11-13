// tb_pacerv_backpressure: exercise wrapper response retention independently.
`timescale 1ns/1ps
module tb_pacerv_backpressure;
    reg clk = 0;
    reg rst_n = 0;
    always #5 clk = ~clk;
    wire uart_valid, cpu_alive, cpu_trap, npu_soft_start;
    wire [7:0] uart_data, cpu_led;
    wire [31:0] cpu_trap_cause;
    wire dd_req_valid, dd_req_write, dd_rsp_ready;
    wire [31:0] dd_req_address, dd_req_data;
    wire [3:0] dd_req_strobe;
    reg dd_req_ready = 1;
    reg dd_rsp_valid = 0;
    reg [31:0] dd_rsp_data = 0;
    reg dd_rsp_error = 0;
    integer held;

    task check_fetch;
        input [31:0] primary_address, pair_address;
        input expected_error, expected_pair;
        begin
            @(negedge clk);
            force dut.i_req_address = primary_address;
            force dut.i_req_pair_address = pair_address;
            force dut.i_req_valid = 1;
            force dut.i_rsp_ready = 0;
            @(negedge clk);
            force dut.i_req_valid = 0;
            if (!dut.i_rsp_valid || dut.i_rsp_error !== expected_error ||
                dut.i_rsp_pair_valid !== expected_pair)
                $fatal(1, "ROM pair validation primary=%h pair=%h error=%b pairvalid=%b",
                       primary_address, pair_address, dut.i_rsp_error, dut.i_rsp_pair_valid);
            force dut.i_rsp_ready = 1;
            @(negedge clk);
        end
    endtask

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
        .dd_req_valid(dd_req_valid), .dd_req_ready(dd_req_ready),
        .dd_req_address(dd_req_address), .dd_req_write(dd_req_write),
        .dd_req_data(dd_req_data), .dd_req_strobe(dd_req_strobe),
        .dd_rsp_valid(dd_rsp_valid), .dd_rsp_ready(dd_rsp_ready),
        .dd_rsp_data(dd_rsp_data), .dd_rsp_error(dd_rsp_error)
    );

    initial begin
        // Isolate the bus adapter from the execution core for protocol stress.
        force dut.i_req_valid = 0;
        force dut.d_req_valid = 0;
        force dut.i_rsp_ready = 0;
        force dut.d_rsp_ready = 0;
        force dut.d_req_write = 0;
        force dut.d_req_data = 0;
        force dut.d_req_strobe = 4'hf;
        repeat (3) @(negedge clk);
        rst_n = 1;
        force dut.i_req_address = 0;
        force dut.i_req_pair_address = 4;
        force dut.i_req_valid = 1;
        @(negedge clk);
        force dut.i_req_valid = 0;
        force dut.d_req_address = 32'h8000_0000;
        force dut.d_req_valid = 1;
        @(negedge clk);
        force dut.d_req_valid = 0;
        for (held = 0; held < 1500; held = held + 1) begin
            @(negedge clk);
            if (!dut.i_rsp_valid || !dut.i_rsp_pair_valid || dut.i_rsp_data !== 32'h21370001 ||
                !dut.d_rsp_valid || dut.d_rsp_data !== 32'h52564331)
                $fatal(1, "local response was lost under long backpressure cycle=%0d", held);
        end
        force dut.i_rsp_ready = 1;
        force dut.d_rsp_ready = 1;
        @(negedge clk);
        if (dut.i_rsp_valid || dut.d_rsp_valid) $fatal(1, "local response did not drain");
        force dut.i_rsp_ready = 0;
        force dut.d_rsp_ready = 0;
        force dut.d_req_address = 32'h4000_0040;
        force dut.d_req_valid = 1;
        @(negedge clk);
        force dut.d_req_valid = 0;
        dd_rsp_valid = 1;
        dd_rsp_data = 32'hcafe_1234;
        for (held = 0; held < 1500; held = held + 1) begin
            @(negedge clk);
            if (dd_rsp_ready || !dut.d_rsp_valid || dut.d_rsp_data !== 32'hcafe_1234 ||
                dut.maintenance_ready || dut.d_req_ready)
                $fatal(1, "DDR response/backpressure state changed cycle=%0d", held);
        end
        force dut.d_rsp_ready = 1;
        @(negedge clk);
        dd_rsp_valid = 0;
        if (!dut.maintenance_ready || dut.d_rsp_valid) $fatal(1, "DDR completion did not drain");
        check_fetch(32'h00000000, 32'h00000004, 0, 1);
        check_fetch(32'h00001ff8, 32'h00001ffc, 0, 1);
        check_fetch(32'h00001ffc, 32'h00002000, 0, 0);
        check_fetch(32'h00001ffc, 32'h00000000, 0, 0);
        check_fetch(32'h00000000, 32'h00000008, 0, 0);
        check_fetch(32'h00000000, 32'h00000006, 0, 0);
        check_fetch(32'h00002000, 32'h00002004, 1, 0);
        check_fetch(32'hfffffffc, 32'h00000000, 1, 0);
        $display("PACERV_BACKPRESSURE_PASS local_hold=1500 DDR_hold=1500 ROM_pair_cases=8");
        $finish;
    end
endmodule
