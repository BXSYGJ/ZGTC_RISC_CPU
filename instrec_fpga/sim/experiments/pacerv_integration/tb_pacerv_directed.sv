// tb_pacerv_directed: execute RV32IMC against the integrated local/shared map.
`timescale 1ns/1ps
module tb_pacerv_directed;
    reg clk = 0;
    reg rst_n = 0;
    always #5 clk = ~clk;
    wire uart_valid;
    wire [7:0] uart_data;
    wire [7:0] cpu_led;
    wire cpu_alive, cpu_trap, npu_soft_start;
    wire [31:0] cpu_trap_cause;
    wire dd_req_valid, dd_req_ready, dd_req_write, dd_rsp_ready;
    wire [31:0] dd_req_address, dd_req_data;
    wire [3:0] dd_req_strobe;
    reg dd_rsp_valid = 0;
    reg [31:0] dd_rsp_data = 0;
    reg dd_rsp_error = 0;
    integer cycles = 0;
    integer requests = 0;
    integer responses = 0;
    integer traps = 0;
    integer starts = 0;
    integer crossed = 0;
    integer paired = 0;
    integer request_stalls = 0;
    reg pending = 0;
    reg [31:0] request_address, request_data;
    reg [3:0] request_strobe;
    reg request_write;
    integer delay_count = 0;
    reg [31:0] memory [0:3];
    reg stalled = 0;
    reg [68:0] held_request;
    integer lane;

    assign dd_req_ready = !pending && !dd_rsp_valid && (cycles % 7 != 1);

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
        for (lane = 0; lane < 4; lane = lane + 1) memory[lane] = 0;
        repeat (5) @(negedge clk);
        rst_n = 1;
    end

    always @(posedge clk) begin
        if (rst_n) begin
            cycles <= cycles + 1;
            if (dut.maintenance_valid && dut.maintenance_ready &&
                (dut.d_pend || dut.dd_active || (dd_req_valid && dd_req_ready)))
                $fatal(1, "maintenance completed with an accepted DDR/local transaction");
            if (stalled && (!dd_req_valid ||
                held_request !== {dd_req_address, dd_req_write, dd_req_data, dd_req_strobe}))
                $fatal(1, "DDR request changed under backpressure");
            stalled <= dd_req_valid && !dd_req_ready;
            if (dd_req_valid && !dd_req_ready) request_stalls <= request_stalls + 1;
            held_request <= {dd_req_address, dd_req_write, dd_req_data, dd_req_strobe};

            if (dd_req_valid && dd_req_ready) begin
                if (pending || dd_rsp_valid) $fatal(1, "more than one DDR request");
                pending <= 1;
                request_address <= dd_req_address;
                request_write <= dd_req_write;
                request_data <= dd_req_data;
                request_strobe <= dd_req_strobe;
                delay_count <= requests == 0 ? 1100 : (3 + requests % 5);
                requests <= requests + 1;
            end
            if (pending) begin
                if (delay_count != 0) delay_count <= delay_count - 1;
                else begin
                    pending <= 0;
                    dd_rsp_valid <= 1;
                    dd_rsp_error <= 0;
                    dd_rsp_data <= 0;
                    if (request_address[31:20] == 12'h400) begin
                        if (request_write) begin
                            for (lane = 0; lane < 4; lane = lane + 1)
                                if (request_strobe[lane])
                                    memory[request_address[3:2]][lane*8 +: 8] <= request_data[lane*8 +: 8];
                        end else dd_rsp_data <= memory[request_address[3:2]];
                    end else if (request_address == 32'h4100_0000) begin
                        if (request_write) dd_rsp_error <= 1;
                        else dd_rsp_data <= 32'hdeca_fbad;
                    end else dd_rsp_error <= 1;
                end
            end
            if (dd_rsp_valid && dd_rsp_ready) begin
                dd_rsp_valid <= 0;
                responses <= responses + 1;
            end
            if (cpu_trap) begin
                traps <= traps + 1;
                if (cpu_trap_cause != 7) $fatal(1, "unexpected trap %d pc=%h", cpu_trap_cause, dut.trap_pc_u);
            end
            if (npu_soft_start) starts <= starts + 1;
            if (dut.trace_valid_u && dut.trace_pc_u[1]) crossed <= crossed + 1;
            if (dut.i_rsp_valid && dut.i_rsp_ready && dut.i_rsp_pair_valid) paired <= paired + 1;
            if (cpu_alive && cpu_led == 8'hee)
                $fatal(1, "firmware check failed test=%0d pc=%h", dut.u_core.registers[23], dut.trace_pc_u);
            if (cpu_alive && cpu_led == 8'ha5) begin
                if (requests != 11 || responses != 11 || traps != 1 || starts != 1 || crossed == 0 || paired == 0 || request_stalls == 0)
                    $fatal(1, "coverage req=%0d rsp=%0d traps=%0d starts=%0d crossed=%0d pair=%0d",
                           requests, responses, traps, starts, crossed, paired);
                if (memory[0] !== 32'hbeef_a578) $fatal(1, "DDR byte strobes failed");
                $display("PACERV_DIRECTED_PASS cycles=%0d retired=%0d checks=25 DDR=%0d traps=%0d crossed=%0d pairs=%0d request_stalls=%0d",
                         cycles, dut.retired_count, responses, traps, crossed, paired, request_stalls);
                $finish;
            end
            if (cycles > 30000) $fatal(1, "timeout pc=%h test=%0d DDR=%0d/%0d", dut.trace_pc_u, dut.u_core.registers[23], requests, responses);
        end
    end
endmodule
