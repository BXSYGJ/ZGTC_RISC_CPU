`timescale 1ns / 1ps
`ifndef ROM_PROG_HEX
`define ROM_PROG_HEX "build/rtos/firmware/prog.hex"
`endif
`ifndef ROM_EVEN_HEX
`define ROM_EVEN_HEX "build/rtos/firmware/prog_even.hex"
`endif
`ifndef ROM_ODD_HEX
`define ROM_ODD_HEX "build/rtos/firmware/prog_odd.hex"
`endif

module tb_rom_readout;
    reg clk = 0;
    always #4 clk = !clk;
    reg rst_n = 0;
    reg fetch_valid = 0, fetch_ready = 0, data_valid = 0;
    reg [31:0] fetch_address = 0, fetch_pair = 4, data_address = 0;
    wire uart_valid, cpu_alive, cpu_trap, npu_soft_start;
    wire [7:0] uart_data, cpu_led;
    wire [31:0] cpu_trap_cause, dd_req_address, dd_req_data;
    wire [3:0] dd_req_strobe;
    wire dd_req_valid, dd_req_write, dd_rsp_ready;
    reg [31:0] expected [0:4095];
    integer index, fetches = 0, data_reads = 0, stalled_cycles = 0;

    rv32_cpu_subsys #(
        .IMEM_WORDS(4096), .DMEM_WORDS(4096),
        .PROG_HEX(`ROM_PROG_HEX), .PROG_EVEN_HEX(`ROM_EVEN_HEX),
        .PROG_ODD_HEX(`ROM_ODD_HEX)
    ) dut (
        .clk(clk), .rst_n(rst_n), .npu_busy(1'b0), .npu_done(1'b0),
        .npu_timeout(1'b0), .npu_probs_valid(1'b0), .npu_probs_pct(8'd0),
        .npu_probs_idx(4'd0), .npu_top1(4'd0), .npu_cycles(32'd0),
        .ddr_ok(1'b1), .ddr_err(1'b0), .ddr_sts(32'd0),
        .uart_valid(uart_valid), .uart_data(uart_data), .uart_ready(1'b1),
        .cpu_led(cpu_led), .cpu_alive(cpu_alive), .cpu_trap(cpu_trap),
        .cpu_trap_cause(cpu_trap_cause), .npu_soft_start(npu_soft_start),
        .dd_req_valid(dd_req_valid), .dd_req_ready(1'b0),
        .dd_req_address(dd_req_address), .dd_req_write(dd_req_write),
        .dd_req_data(dd_req_data), .dd_req_strobe(dd_req_strobe),
        .dd_rsp_valid(1'b0), .dd_rsp_ready(dd_rsp_ready),
        .dd_rsp_data(32'd0), .dd_rsp_error(1'b0)
    );

    task fetch_check;
        input [31:0] address;
        input [31:0] pair_address;
        input integer stall;
        reg [31:0] wanted, paired;
        reg valid_address, valid_pair;
        integer hold_cycle;
        begin
            valid_address = address < 16384 && address[1:0] == 0;
            valid_pair = valid_address && pair_address < 16384 && pair_address == address + 4;
            wanted = valid_address ? expected[address / 4] : 32'd0;
            paired = valid_pair ? expected[pair_address / 4] : 32'd0;
            @(negedge clk);
            fetch_address = address;
            fetch_pair = pair_address;
            fetch_valid = 1;
            fetch_ready = 0;
            while (!dut.i_req_ready) @(negedge clk);
            @(posedge clk); #1;
            if (!dut.i_rsp_valid || dut.i_rsp_error != !valid_address ||
                dut.i_rsp_data !== wanted || dut.i_rsp_pair_valid != valid_pair)
                $fatal(1, "ROM fetch mismatch address=%h actual=%h expected=%h error=%b",
                       address, dut.i_rsp_data, wanted, dut.i_rsp_error);
            if (valid_pair && dut.i_rsp_pair_data !== paired)
                $fatal(1, "ROM paired word mismatch address=%h pair=%h actual=%h expected=%h",
                       address, pair_address, dut.i_rsp_pair_data, paired);
            if (dut.i_rsp_is_c !== {wanted[17:16] != 2'b11, wanted[1:0] != 2'b11})
                $fatal(1, "ROM compressed metadata mismatch address=%h", address);
            for (hold_cycle = 0; hold_cycle < stall; hold_cycle = hold_cycle + 1) begin
                @(posedge clk); #1;
                if (!dut.i_rsp_valid || dut.i_rsp_data !== wanted ||
                    (valid_pair && dut.i_rsp_pair_data !== paired))
                    $fatal(1, "ROM response changed during backpressure address=%h", address);
                stalled_cycles = stalled_cycles + 1;
            end
            @(negedge clk);
            fetch_valid = 0;
            fetch_ready = 1;
            @(posedge clk); #1;
            if (dut.i_rsp_valid) $fatal(1, "ROM fetch response did not retire");
            @(negedge clk);
            fetch_ready = 0;
            fetches = fetches + 1;
        end
    endtask

    task data_check;
        input [31:0] address;
        reg [31:0] wanted;
        reg valid_address;
        begin
            valid_address = address < 16384;
            wanted = valid_address ? expected[address / 4] : 32'd0;
            @(negedge clk);
            data_address = address;
            data_valid = 1;
            while (!dut.d_req_ready) @(negedge clk);
            @(posedge clk); #1;
            if (!dut.d_rsp_valid || dut.d_rsp_error != !valid_address ||
                dut.d_rsp_data !== wanted)
                $fatal(1, "ROM data read mismatch address=%h actual=%h expected=%h error=%b",
                       address, dut.d_rsp_data, wanted, dut.d_rsp_error);
            @(negedge clk);
            data_valid = 0;
            @(posedge clk); #1;
            @(negedge clk);
            data_reads = data_reads + 1;
        end
    endtask

    initial begin
        /* Exercise the wrapper's real memory request/response paths. The core
         * remains present; only its outgoing bus requests are replaced. */
        force dut.i_req_valid = fetch_valid;
        force dut.i_req_address = fetch_address;
        force dut.i_req_pair_address = fetch_pair;
        force dut.i_rsp_ready = fetch_ready;
        force dut.d_req_valid = data_valid;
        force dut.d_req_address = data_address;
        force dut.d_req_write = 1'b0;
        force dut.d_req_data = 32'd0;
        force dut.d_req_strobe = 4'd0;
        force dut.d_rsp_ready = 1'b1;
        for (index = 0; index < 4096; index = index + 1) expected[index] = 0;
        $readmemh(`ROM_PROG_HEX, expected);
        repeat (4) @(posedge clk);
        @(negedge clk); rst_n = 1;
        for (index = 0; index < 4096; index = index + 1) begin
            fetch_check(index * 4, (index + 1) * 4,
                        index % 13 == 0 ? 3 : 0);
            data_check(index * 4);
        end
        fetch_check(16380, 16384, 3);
        fetch_check(16380, 16376, 1);
        fetch_check(4, 0, 1);
        fetch_check(1, 5, 1);
        fetch_check(16384, 16380, 3);
        fetch_check(32'h00010000, 32'h00010004, 1);
        data_check(16384);
        data_check(32'h00010000);
        $display("ROM_READOUT_PASS words=4096 fetches=%0d data_reads=%0d stalled_cycles=%0d first=%h last=%h",
                 fetches, data_reads, stalled_cycles, expected[0], expected[4095]);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "ROM readout watchdog");
    end
endmodule
