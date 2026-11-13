`timescale 1ns/1ps
// Protocol-level simulation only: the real build uses generated PG200 DDR IP.
module tb_remote_pg200;
    parameter integer AUDIO = 0;
    parameter integer NO_KEY_RESET = 0;
    reg clk=0, resetn=NO_KEY_RESET, board_clk27=0;
    always #4 clk=~clk;
    always #18.519 board_clk27=~board_clk27;
    wire tx;
    wire [7:0] led;
    wire cs,rst,ck,ckn,cke,ras,cas,we,odt;
    wire [14:0] addr;
    wire [2:0] bank;
    wire [3:0] dqs,dqsn,dm;
    wire [31:0] dq;
    remote_pg200_top #(.UART_DIV(2)) dut (
        .board_clk27(board_clk27),.ref_clk_p(clk),.ref_clk_n(!clk),.resetn(resetn),.uart_tx(tx),.led(led),
        .mem_cs_n(cs),.mem_rst_n(rst),.mem_ck(ck),.mem_ck_n(ckn),.mem_cke(cke),
        .mem_ras_n(ras),.mem_cas_n(cas),.mem_we_n(we),.mem_odt(odt),
        .mem_a(addr),.mem_ba(bank),.mem_dqs(dqs),.mem_dqs_n(dqsn),.mem_dq(dq),.mem_dm(dm)
    );
    reg [143:0] tail=0;
    wire [143:0] next_tail={tail[135:0],dut.cpu_uart_data};
    reg overlap_seen=0;
    reg [31:0] cpu_requests=0;
    reg [31:0] masks=0;
    reg audio_imc_seen=0, audio_ddr_seen=0, audio_bench_seen=0, audio_npu_seen=0;
    reg accel_completion_seen=0;
    reg completion_pending=0;
    reg [7:0] serial_expected [0:4095];
    integer accepted_bytes=0, received_bytes=0, bit_index;
    reg [7:0] received_byte;
    // Decode the physical UART wire as well as checking the CPU-side FIFO.
    // UART_DIV=2, core period=8 ns: one serial bit lasts 16 ns.
    initial forever begin
        @(negedge tx);
        #24;
        for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin
            received_byte[bit_index]=tx;
            #16;
        end
        if(tx!==1'b1) $fatal(1,"UART stop bit missing");
        if(received_bytes>=accepted_bytes || received_byte!==serial_expected[received_bytes])
            $fatal(1,"UART wire mismatch byte=%0d got=%h expected=%h",received_bytes,received_byte,serial_expected[received_bytes]);
        received_bytes=received_bytes+1;
    end
    always @(posedge clk) if (resetn) begin
        if(completion_pending && received_bytes==accepted_bytes && !dut.uart.busy) begin
            $display("REMOTE_UART_WIRE PASS bytes=%0d",received_bytes);
            $finish;
        end
        if(dut.accel_done_event) accel_completion_seen<=1;
        if (dut.cpu_trap) $fatal(1,"Unexpected CPU trap cause=%h",dut.trap_cause);
        if (dut.cpu_cmd_valid && dut.accel_cmd_valid) overlap_seen<=1;
        if (dut.dd_valid && dut.dd_ready) begin
            cpu_requests<=cpu_requests+1;
            if(dut.dd_write && dut.dd_strobe!=4'hf) masks<=masks+1;
        end
        if(dut.cpu_uart_valid && dut.cpu_uart_ready) begin
            serial_expected[accepted_bytes]=dut.cpu_uart_data;
            accepted_bytes=accepted_bytes+1;
            tail<=next_tail;
            $write("%c",dut.cpu_uart_data);
            $fflush();
            if(next_tail[119:0]=="PACERV IMC OK 0") audio_imc_seen<=1;
            if(next_tail[119:0]=="PACERV DDR OK 0") audio_ddr_seen<=1;
            if(next_tail[79:0]=="0xf2d8888b") audio_bench_seen<=1;
            if(next_tail[71:0]=="NPU top1=") audio_npu_seen<=1;
            if(AUDIO && audio_npu_seen && dut.cpu_uart_data==8'd10) begin
                if(!audio_imc_seen || !audio_ddr_seen || !audio_bench_seen || masks!=48 || !accel_completion_seen)
                    $fatal(1,"Audio firmware checks missing imc=%0d ddr=%0d bench=%0d masks=%0d",audio_imc_seen,audio_ddr_seen,audio_bench_seen,masks);
                if(dut.to_err || (|dut.addr_err) || dut.share_fault || dut.bridge_fault)
                    $fatal(1,"Audio firmware shared-controller fault");
                $display("REMOTE_AUDIO_PROTOCOL_SIM PASS masks=%0d cpu_requests=%0d",masks,cpu_requests);
                completion_pending<=1;
            end
            if(next_tail[135:0]=="PACERV_SHARED FAIL") $fatal(1,"Firmware reported failure");
            if(next_tail=="PACERV_SHARED PASS") begin
                if (!overlap_seen || masks!=2 || cpu_requests<1500 || !dut.boot_done || !dut.accel_done)
                    $fatal(1,"Coverage missing overlap=%0d masks=%0d requests=%0d boot=%0d accelerator=%0d",overlap_seen,masks,cpu_requests,dut.boot_done,dut.accel_done);
                if(dut.to_err || (|dut.addr_err) || dut.share_fault || dut.bridge_fault)
                    $fatal(1,"Shared-controller fault");
                $display("\nREMOTE_PROTOCOL_SIM PASS overlap=1 masks=2 cpu_requests=%0d",cpu_requests);
                completion_pending<=1;
            end
        end
    end
    initial begin
        repeat(8) @(posedge clk);
        resetn<=1;
        repeat(AUDIO ? 600000 : 300000) @(posedge clk);
        $fatal(1,"Remote harness firmware timeout pc=%h",dut.cpu.trace_pc_u);
    end
endmodule
