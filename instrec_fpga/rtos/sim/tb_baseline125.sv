// Execute the original selected 125 MHz firmware and execution core.
// The accelerator/DDR models are peripheral stimuli; no CPU state is forced.
`timescale 1ns/1ps
`ifndef BASELINE_PROG_HEX
`define BASELINE_PROG_HEX "rtos/baseline125/src/cpu/prog_pacerv.hex"
`endif
module tb_baseline125;
    localparam integer MAX_CYCLES = 4000000;
    reg clk = 0;
    reg rst_n = 0;
    always #4 clk = ~clk;

    wire uart_valid;
    wire [7:0] uart_data;
    reg uart_ready = 0;
    wire [7:0] cpu_led;
    wire cpu_alive, cpu_trap, npu_soft_start;
    wire [31:0] cpu_trap_cause;
    reg npu_busy = 0;
    reg npu_done = 0;
    reg npu_timeout = 0;
    reg npu_probs_valid = 0;
    reg [7:0] npu_probs_pct = 0;
    reg [3:0] npu_probs_idx = 0;
    reg [3:0] npu_top1 = 0;
    reg [31:0] npu_cycles = 0;
    wire dd_req_valid, dd_req_write, dd_rsp_ready;
    wire [31:0] dd_req_address, dd_req_data;
    wire [3:0] dd_req_strobe;
    wire dd_req_ready;
    reg dd_rsp_valid = 0;
    reg [31:0] dd_rsp_data = 0;
    reg dd_rsp_error = 0;

    rv32_cpu_subsys #(
        .IMEM_WORDS(2048), .DMEM_WORDS(2048),
        .PROG_HEX(`BASELINE_PROG_HEX)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .npu_busy(npu_busy), .npu_done(npu_done), .npu_timeout(npu_timeout),
        .npu_probs_valid(npu_probs_valid), .npu_probs_pct(npu_probs_pct),
        .npu_probs_idx(npu_probs_idx), .npu_top1(npu_top1), .npu_cycles(npu_cycles),
        .ddr_ok(1'b1), .ddr_err(1'b0), .ddr_sts(32'd1),
        .uart_valid(uart_valid), .uart_data(uart_data), .uart_ready(uart_ready),
        .cpu_led(cpu_led), .cpu_alive(cpu_alive), .cpu_trap(cpu_trap),
        .cpu_trap_cause(cpu_trap_cause), .npu_soft_start(npu_soft_start),
        .dd_req_valid(dd_req_valid), .dd_req_ready(dd_req_ready),
        .dd_req_address(dd_req_address), .dd_req_write(dd_req_write),
        .dd_req_data(dd_req_data), .dd_req_strobe(dd_req_strobe),
        .dd_rsp_valid(dd_rsp_valid), .dd_rsp_ready(dd_rsp_ready),
        .dd_rsp_data(dd_rsp_data), .dd_rsp_error(dd_rsp_error)
    );

    integer cycles = 0;
    integer starts = 0;
    integer clears = 0;
    integer completed_results = 0;
    integer timer_traps = 0;
    integer yield_traps = 0;
    integer returns = 0;
    integer timer_writes = 0;
    integer last_timer_trap = 0;
    integer min_tick_spacing = MAX_CYCLES;
    integer max_tick_spacing = 0;
    integer uart_bytes = 0;
    integer uart_gap = 0;
    integer uart_pressure = 0;
    integer uart_peak = 0;
    integer npu_countdown = 0;
    integer npu_pulse = 0;
    integer finish_countdown = 0;
    reg finish_seen = 0;
    reg npu_pending = 0;
    reg [31:0] memory [0:255];
    reg ddr_pending = 0;
    reg [31:0] request_address, request_data;
    reg [3:0] request_strobe;
    reg request_write;
    integer ddr_countdown = 0;
    integer requests = 0;
    integer responses = 0;
    integer request_stalls = 0;
    reg stalled = 0;
    reg [68:0] held_request;
    integer lane;
    string uart_line = "";
    string uart_log = "";

    function automatic bit log_has(string needle);
        integer j;
        begin
            log_has = 0;
            for (j = 0; j + needle.len() <= uart_log.len(); j = j + 1)
                if (uart_log.substr(j, j + needle.len() - 1) == needle)
                    log_has = 1;
        end
    endfunction

    assign dd_req_ready = !ddr_pending && !dd_rsp_valid && (cycles % 11 != 1);

    initial begin
        for (lane = 0; lane < 256; lane = lane + 1) memory[lane] = 0;
        repeat (8) @(negedge clk);
        rst_n = 1;
    end

    always @(posedge clk) begin
        if (rst_n) begin
            cycles <= cycles + 1;
            if ($test$plusargs("rtos_progress") && cycles % 250000 == 0)
                $display("RTOS_PROGRESS cycle=%0d pc=%h SP=%h ticks=%0d yields=%0d starts=%0d LED=%h",
                         cycles, dut.trace_pc_u, dut.u_core.registers[2],
                         timer_traps, yield_traps, starts, cpu_led);

            // Byte-ready has regular stalls and a longer deterministic pause.
            if (uart_valid && uart_ready) uart_gap <= 16;
            else if (uart_gap > 0) uart_gap <= uart_gap - 1;
            uart_ready <= uart_gap == 0 && (cycles % 4096 < 3900);
            if (dut.tx_count > uart_peak) uart_peak <= dut.tx_count;
            if (dut.tx_count == 16) uart_pressure <= uart_pressure + 1;
            if (uart_valid && uart_ready) begin
                uart_bytes <= uart_bytes + 1;
                if (uart_data == 8'h0a) begin
                    $display("RTOS_UART %s", uart_line);
                    uart_log = {uart_log, uart_line, "\n"};
                    uart_line = "";
                end else if (uart_data != 8'h0d) begin
                    uart_line = {uart_line, $sformatf("%c", uart_data)};
                end
            end

            if (cpu_trap)
                $fatal(1, "unexpected baseline trap cause=%h pc=%h", cpu_trap_cause, dut.trap_pc_u);
            if (dut.ctrl_clear) clears <= clears + 1;

            // One outstanding DDR transaction with acceptance backpressure,
            // variable response latency and persistent response-valid.
            if (stalled && (!dd_req_valid ||
                held_request !== {dd_req_address, dd_req_write, dd_req_data, dd_req_strobe}))
                $fatal(1, "DDR request changed under backpressure");
            stalled <= dd_req_valid && !dd_req_ready;
            held_request <= {dd_req_address, dd_req_write, dd_req_data, dd_req_strobe};
            if (dd_req_valid && !dd_req_ready) request_stalls <= request_stalls + 1;
            if (dd_req_valid && dd_req_ready) begin
                if (ddr_pending || dd_rsp_valid) $fatal(1, "multiple DDR requests");
                ddr_pending <= 1;
                request_address <= dd_req_address;
                request_write <= dd_req_write;
                request_data <= dd_req_data;
                request_strobe <= dd_req_strobe;
                ddr_countdown <= requests == 0 ? 1100 : 3 + requests % 9;
                requests <= requests + 1;
            end
            if (ddr_pending) begin
                if (ddr_countdown != 0) ddr_countdown <= ddr_countdown - 1;
                else begin
                    ddr_pending <= 0;
                    dd_rsp_valid <= 1;
                    dd_rsp_error <= 0;
                    dd_rsp_data <= 0;
                    if (request_address >= 32'h40000000 && request_address < 32'h40100000) begin
                        if (request_write) begin
                            for (lane = 0; lane < 4; lane = lane + 1)
                                if (request_strobe[lane])
                                    memory[request_address[9:2]][lane*8 +: 8] <= request_data[lane*8 +: 8];
                        end else dd_rsp_data <= memory[request_address[9:2]];
                    end else if (request_address == 32'h41300000 && !request_write) begin
                        dd_rsp_data <= 32'h5a5a00ff;
                    end else begin
                        dd_rsp_error <= 1;
                    end
                end
            end
            if (dd_rsp_valid && dd_rsp_ready) begin
                dd_rsp_valid <= 0;
                responses <= responses + 1;
            end

            // A real MMIO start arms each accelerator response. No response is
            // emitted before firmware asks for it. Busy spans multiple ticks.
            if (npu_soft_start) begin
                if (npu_pending || npu_busy) $fatal(1, "NPU launch while busy");
                starts <= starts + 1;
                npu_pending <= 1;
                npu_busy <= 1;
                npu_countdown <= 30000;
                $display("RTOS_NPU_START sequence=%0d cycle=%0d", starts + 1, cycles);
            end
            if (npu_pending) begin
                if (npu_countdown != 0) npu_countdown <= npu_countdown - 1;
                else begin
                    npu_pending <= 0;
                    npu_busy <= 0;
                    npu_pulse <= 2;
                    if (starts == 2) begin
                        npu_timeout <= 1;
                        $display("RTOS_NPU_INJECT timeout sequence=2 cycle=%0d", cycles);
                    end else begin
                        npu_done <= 1;
                        npu_probs_valid <= 1;
                        npu_top1 <= starts == 1 ? 4'd5 : 4'd2;
                        npu_probs_idx <= starts == 1 ? 4'd3 : 4'd6;
                        npu_probs_pct <= starts == 1 ? 8'd87 : 8'd64;
                        npu_cycles <= starts == 1 ? 32'd12345 : 32'd54321;
                        completed_results <= completed_results + 1;
                        $display("RTOS_NPU_INJECT result sequence=%0d cycle=%0d", starts, cycles);
                    end
                end
            end
            if (npu_pulse != 0) begin
                npu_pulse <= npu_pulse - 1;
                if (npu_pulse == 1) begin
                    npu_done <= 0;
                    npu_timeout <= 0;
                    npu_probs_valid <= 0;
                    // Capture must retain the event cycle value after this.
                    npu_cycles <= 32'd99999;
                end
            end

            if (starts >= 2 && clears >= 1 && !finish_seen) begin
                finish_seen <= 1;
                finish_countdown <= 10000;
            end
            if (finish_seen) begin
                if (finish_countdown != 0) finish_countdown <= finish_countdown - 1;
                else if (!uart_valid && uart_gap == 0) begin
                    if (requests < 200 || requests != responses || uart_bytes < 80 ||
                        !log_has("PACERV IMC OK 0") || !log_has("PACERV DDR OK 0 CRC=") ||
                        !log_has("RV32 BOOT") || !log_has("RV32 MMIO OK") ||
                        !log_has("RV32 ISA OK") ||
                        !log_has("RV32 BENCH cycles=") || !log_has("acc=0xf2d8888b") ||
                        !log_has("NPU top1=5 last_class=3 last_p=87 c=12345"))
                        $fatal(1, "baseline coverage UART=%s", uart_log);
                    $display("BASELINE125_CPU_PASS hz=125000000 cycles=%0d starts=%0d clears=%0d DDR=%0d/%0d UART=%0d",
                             cycles, starts, clears, requests, responses, uart_bytes);
                    $finish;
                end
            end
            if (cycles > MAX_CYCLES)
                $fatal(1, "watchdog pc=%h ticks=%0d yields=%0d starts=%0d LED=%h UART=%s",
                       dut.trace_pc_u, timer_traps, yield_traps, starts, cpu_led, uart_log);
        end
    end
endmodule
