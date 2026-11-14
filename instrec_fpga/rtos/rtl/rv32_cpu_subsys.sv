// ---------------------------------------------------------------------------
// File    : rv32_cpu_subsys.sv
// Module  : rv32_cpu_subsys
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : 125 MHz PaceRV system with machine timer for the RTOS port.
//
// INTEGRATION
//   The frozen H3 execution core runs in the existing core_clk domain and
//   supervises the audio/NPU system through the original MMIO register map.
//
//     * the CPU fetches from an 8 KiB on-chip ROM that holds the firmware,
//     * it reads/writes an 8 KiB data RAM (byte strobes supported),
//     * it observes the accelerator (npu_busy/done/timeout/top1/probs/cycles,
//       DDR3 self-test status) through a 32-bit MMIO window,
//     * it drives the shared 115200 UART transmitter through a 16-byte FIFO,
//     * it issues NPU soft starts through CTRL[0],
//     * it accesses the system DDR through one captured request/response path.
//
//   Everything here runs in the core_clk (DDR3 user clock) domain, which is
//   the same domain as npu_top / mel_engine / uart_tx, so no CDC is added.
//
// MEMORY MAP (CPU byte addresses)
//   0x0000_0000 .. 0x0000_1FFF  ROM  8 KiB  (firmware, read-only, $readmemh)
//   0x2000_0000 .. 0x2000_1FFF  RAM  8 KiB  (data/bss/stack, byte strobes)
//   0x4000_0000 .. 0x400F_FFFF  shared DDR application read/write window
//   0x4100_0000 .. 0x415F_FFFF  shared DDR observation alias (bridge validates)
//   0x8000_0000 +                MMIO (see the decoder below)
//   anything else                       -> bus error (i_rsp_error/d_rsp_error)
//
// BUS PROTOCOL
//   One outstanding request per channel. Local storage has one-cycle latency;
//   shared DDR latency follows the system arbiter. Every response is held until
//   its valid/ready handshake, including arbitrarily long backpressure.
//   This integration uses local ROM/RAM and shared DDR data; it does not use
//   the cache/backing-memory arrangement of the standalone H3 CoreMark result.
//
// MMIO MAP
//   0x8000_0000 R  ID          0x52564331 ("RVC1")
//   0x8000_0004 R  STATUS      [0] npu_busy      [1] npu_done sticky
//                              [2] npu_timeout   [3] probs sticky
//                              [5] ddr_ok        [6] ddr_err
//                              [11:8] npu_top1   [15:12] probs_idx
//                              [23:16] probs_pct
//   0x8000_0008 R  PROBS       {8'h0, pct[7:0], 4'h0, idx[3:0]}
//   0x8000_000C W  UART_TX     byte to transmit (stalls if the FIFO is full)
//   0x8000_0010 R  UART_ST     [0] tx_ready, [5:1] FIFO occupancy
//   0x8000_0014 W  LED         [7:0] board LEDs
//   0x8000_0018 R  CYCLE_LO    mcycle[31:0]
//   0x8000_001C R  INSTRET_LO  minstret[31:0]
//   0x8000_0020 R  DDR_STS     {8'h0, stage[1:0], err, ok, 4'h0, npu_timeout,
//                               dbg_to_state[2:0], cmd_to_err[3:0], to_err}
//   0x8000_0024 W  CTRL        [0] NPU soft start (1-cycle pulse)
//                              [1] clear the sticky status bits
//   0x8000_0028 R  NPU_CYCLES  npu_top cycle counter
//   0x8000_0030 RW MTIME_LO    free-running core-clock timer, low word
//   0x8000_0034 RW MTIME_HI    timer high word; use hi/lo/hi reads
//   0x8000_0038 RW MTIMECMP_LO machine timer compare, low word
//   0x8000_003C RW MTIMECMP_HI compare high word (reset all ones)
//   irq_timer is level-sensitive while MTIME >= MTIMECMP. All four timer
//   registers support byte strobes. RV32 software rearms with compare high
//   = all ones, then compare low, then final compare high.
// ---------------------------------------------------------------------------
`timescale 1ns / 1ps


module rv32_cpu_subsys #(
    parameter integer ENABLE_M         = 1,
    parameter integer ENABLE_PREDICTOR = 1,
    parameter integer ENABLE_C         = 1,
    parameter integer FETCH_OVERLAP    = 1,
    parameter integer EARLY_D_REQUEST  = 1,
    parameter integer BTB_INDEX_BITS   = 8,
    parameter [31:0]  RESET_VECTOR     = 32'h0000_0000,
    parameter integer IMEM_WORDS       = 2048,   // 8 KiB
    parameter integer DMEM_WORDS       = 2048,   // 8 KiB
    parameter PROG_HEX                 = "src/cpu/prog.hex",
    parameter PROG_EVEN_HEX            = "src/cpu/prog_even.hex",
    parameter PROG_ODD_HEX             = "src/cpu/prog_odd.hex"
) (
    input  wire        clk,
    input  wire        rst_n,

    // accelerator / system observation (core_clk domain)
    input  wire        npu_busy,
    input  wire        npu_done,
    input  wire        npu_timeout,
    input  wire        npu_probs_valid,
    input  wire [7:0]  npu_probs_pct,
    input  wire [3:0]  npu_probs_idx,
    input  wire [3:0]  npu_top1,
    input  wire [31:0] npu_cycles,
    input  wire        ddr_ok,
    input  wire        ddr_err,
    input  wire [31:0] ddr_sts,

    // byte stream into the shared UART transmitter
    output wire        uart_valid,
    output wire [7:0]  uart_data,
    input  wire        uart_ready,

    // board / status
    output reg  [7:0]  cpu_led,
    output reg         cpu_alive,
    output wire        cpu_trap,
    output wire [31:0] cpu_trap_cause,
    output reg         npu_soft_start,

    // One outstanding shared-DDR data request. Addresses are CPU byte addresses.
    output wire        dd_req_valid,
    input  wire        dd_req_ready,
    output wire [31:0] dd_req_address,
    output wire        dd_req_write,
    output wire [31:0] dd_req_data,
    output wire [3:0]  dd_req_strobe,
    input  wire        dd_rsp_valid,
    output wire        dd_rsp_ready,
    input  wire [31:0] dd_rsp_data,
    input  wire        dd_rsp_error
);

    localparam integer IAW = $clog2(IMEM_WORDS);
    localparam integer DAW = $clog2(DMEM_WORDS);
    localparam [31:0] DMEM_BASE = 32'h2000_0000;
    localparam [31:0] DMEM_END = DMEM_BASE + DMEM_WORDS * 4;

    localparam [31:0] CPU_ID = 32'h5256_4331;   // "RVC1"

    // =====================================================================
    // Core
    // =====================================================================
    wire        i_req_valid, i_req_ready;
    wire [31:0] i_req_address, i_req_pair_address;
    wire        i_rsp_valid, i_rsp_ready;
    wire [31:0] i_rsp_data, i_rsp_pair_data;
    wire [1:0]  i_rsp_is_c, i_rsp_pair_is_c;
    wire        i_rsp_pair_valid;
    wire        i_rsp_error;
    wire        d_req_valid, d_req_ready;
    wire [31:0] d_req_address;
    wire [31:0] d_req_data;
    wire [3:0]  d_req_strobe;
    wire        d_req_write;
    wire        d_rsp_valid, d_rsp_ready;
    wire [31:0] d_rsp_data;
    wire        d_rsp_error;
    wire        maintenance_valid;
    wire        maintenance_ready;
    wire [63:0] cycle_count, retired_count;
    wire [63:0] timer_value;
    wire timer_irq;
    wire [31:0] timer_rdata;
    wire timer_write = d_req_valid && d_req_ready && d_req_write &&
                       (d_req_address[31:4] == 28'h8000003);

    machine_timer u_machine_timer (
        .clk          (clk),
        .rst_n        (rst_n),
        .write_valid  (timer_write),
        .word_address (d_req_address[3:2]),
        .write_data   (d_req_data),
        .write_strobe (d_req_strobe),
        .read_data    (timer_rdata),
        .timer_value  (timer_value),
        .timer_irq    (timer_irq)
    );

    // PDS's front end rejects an empty '.port()' connection, so every unused
    // observer output is parked on a named, deliberately unread net.
    wire        trace_valid_u, trace_write_u;
    wire [31:0] trace_pc_u, trace_instruction_u, trace_data_u;
    wire [4:0]  trace_rd_u;
    wire [31:0] trap_pc_u, trap_value_u;
    wire [4:0]  pipeline_valid_u;

    rv32_core #(
        .RESET_VECTOR     (RESET_VECTOR),
        .ENABLE_PREDICTOR (ENABLE_PREDICTOR),
        .ENABLE_M         (ENABLE_M),
        .ENABLE_C         (ENABLE_C),
        .FETCH_ADDRESS_BITS(32),
        .FETCH_OVERLAP    (FETCH_OVERLAP),
        .EARLY_D_REQUEST  (EARLY_D_REQUEST),
        .BTB_INDEX_BITS   (BTB_INDEX_BITS),
        .BTB_ADDRESS_BITS (32),
        .LOAD_USE_BUBBLE  (1)
    ) u_core (
        .clk              (clk),
        .rst_n            (rst_n),
        .i_req_valid      (i_req_valid),
        .i_req_ready      (i_req_ready),
        .i_req_address    (i_req_address),
        .i_req_pair_address(i_req_pair_address),
        .i_rsp_valid      (i_rsp_valid),
        .i_rsp_ready      (i_rsp_ready),
        .i_rsp_data       (i_rsp_data),
        .i_rsp_pair_data  (i_rsp_pair_data),
        .i_rsp_is_c       (i_rsp_is_c),
        .i_rsp_pair_is_c  (i_rsp_pair_is_c),
        .i_rsp_pair_valid (i_rsp_pair_valid),
        .i_rsp_error      (i_rsp_error),
        .d_req_valid      (d_req_valid),
        .d_req_ready      (d_req_ready),
        .d_req_address    (d_req_address),
        .d_req_data       (d_req_data),
        .d_req_strobe     (d_req_strobe),
        .d_req_write      (d_req_write),
        .d_rsp_valid      (d_rsp_valid),
        .d_rsp_ready      (d_rsp_ready),
        .d_rsp_data       (d_rsp_data),
        .d_rsp_error      (d_rsp_error),
        .maintenance_valid(maintenance_valid),
        .maintenance_ready(maintenance_ready),
        .timer_value      (timer_value),
        .irq_external     (1'b0),
        .irq_software     (1'b0),
        .irq_timer        (timer_irq),
        .trace_valid      (trace_valid_u),
        .trace_pc         (trace_pc_u),
        .trace_instruction(trace_instruction_u),
        .trace_write      (trace_write_u),
        .trace_rd         (trace_rd_u),
        .trace_data       (trace_data_u),
        .trap_valid       (cpu_trap),
        .trap_pc          (trap_pc_u),
        .trap_cause       (cpu_trap_cause),
        .trap_value       (trap_value_u),
        .pipeline_valid   (pipeline_valid_u),
        .cycle_count      (cycle_count),
        .retired_count    (retired_count)
    );

    // =====================================================================
    // Instruction ROM: parity banks supply two adjacent words per request.
    // =====================================================================
    reg [31:0] imem_even [0:(IMEM_WORDS/2)-1];
    reg [31:0] imem_odd [0:(IMEM_WORDS/2)-1];
    // Second copy of the same image for the DATA port.  A load from a ROM
    // address is a normal RISC-V access (".data load source", string literals),
    // and giving it its own array keeps both ports single-read, without
    // arbitration. Resource inference is checked in each routed build.
    reg [31:0] rom_d [0:IMEM_WORDS-1];

    integer init_word;
    initial begin
        // Initialize the actual read arrays. PDS does not propagate a
        // readmemh of a temporary array through subsequent array copies.
        // Eight data words and four words in each instruction bank per
        // iteration keep 16/32 KiB ROMs below PDS's 2000-iteration limit.
        for (init_word = 0; init_word < IMEM_WORDS/8; init_word = init_word + 1) begin
            rom_d[init_word*8] = 32'd0;
            rom_d[init_word*8+1] = 32'd0;
            rom_d[init_word*8+2] = 32'd0;
            rom_d[init_word*8+3] = 32'd0;
            rom_d[init_word*8+4] = 32'd0;
            rom_d[init_word*8+5] = 32'd0;
            rom_d[init_word*8+6] = 32'd0;
            rom_d[init_word*8+7] = 32'd0;
            imem_even[init_word*4] = 32'd0;
            imem_odd[init_word*4] = 32'd0;
            imem_even[init_word*4+1] = 32'd0;
            imem_odd[init_word*4+1] = 32'd0;
            imem_even[init_word*4+2] = 32'd0;
            imem_odd[init_word*4+2] = 32'd0;
            imem_even[init_word*4+3] = 32'd0;
            imem_odd[init_word*4+3] = 32'd0;
        end
        $readmemh(PROG_EVEN_HEX, imem_even);
        $readmemh(PROG_ODD_HEX, imem_odd);
        $readmemh(PROG_HEX, rom_d);
    end

    // =====================================================================
    // Data RAM (8 KiB, four byte lanes so the byte strobes map onto BRAM
    // byte-write enables without a 32-bit read-modify-write shim)
    // =====================================================================
    (* syn_ramstyle = "block_ram" *) reg [7:0] dmem0 [0:DMEM_WORDS-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] dmem1 [0:DMEM_WORDS-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] dmem2 [0:DMEM_WORDS-1];
    (* syn_ramstyle = "block_ram" *) reg [7:0] dmem3 [0:DMEM_WORDS-1];

    // =====================================================================
    // MMIO registers and sticky status
    // =====================================================================
    reg        npu_done_st, npu_probs_st, npu_timeout_st;
    reg [7:0]  probs_pct_q;
    reg [3:0]  probs_idx_q;
    reg [31:0] result_cycles_q;

    wire ctrl_write = d_req_valid && d_req_ready && d_req_write &&
                      (d_req_address == 32'h8000_0024);
    wire ctrl_start = ctrl_write && d_req_data[0];
    wire ctrl_clear = ctrl_write && d_req_data[1];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            npu_done_st    <= 1'b0;
            npu_probs_st   <= 1'b0;
            npu_timeout_st <= 1'b0;
            probs_pct_q    <= 8'd0;
            probs_idx_q    <= 4'd0;
            result_cycles_q <= 32'd0;
            npu_soft_start <= 1'b0;
        end else begin
            npu_soft_start <= ctrl_start;
            if (ctrl_clear) begin
                npu_done_st    <= 1'b0;
                npu_probs_st   <= 1'b0;
                npu_timeout_st <= 1'b0;
            end
            // A simultaneous new event wins over software acknowledgement.
            if (npu_done)          npu_done_st    <= 1'b1;
            if (npu_timeout)       npu_timeout_st <= 1'b1;
            if (npu_probs_valid) begin
                npu_probs_st <= 1'b1;
                probs_pct_q  <= npu_probs_pct;
                probs_idx_q  <= npu_probs_idx;
                result_cycles_q <= npu_cycles;
            end
        end
    end

    // Board LEDs / "the CPU is running" indicator: a firmware MMIO write is
    // the proof of life (no free-running counter needed).
    wire led_write = d_req_valid && d_req_ready && d_req_write &&
                     (d_req_address == 32'h8000_0014);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cpu_led   <= 8'd0;
            cpu_alive <= 1'b0;
        end else if (led_write) begin
            cpu_led   <= d_req_data[7:0];
            cpu_alive <= 1'b1;
        end
    end

    // =====================================================================
    // UART transmit FIFO (16 bytes)
    // =====================================================================
    reg [7:0]  txq [0:15];
    reg [4:0]  tx_wr, tx_rd;

    wire [4:0] tx_count  = tx_wr - tx_rd;
    wire       tx_push   = d_req_valid && d_req_ready && d_req_write &&
                           (d_req_address == 32'h8000_000C) && (tx_count != 5'd16);
    wire       tx_ready  = (tx_count != 5'd16);

    assign uart_valid = (tx_count != 5'd0);
    assign uart_data  = txq[tx_rd[3:0]];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tx_wr <= 5'd0;
            tx_rd <= 5'd0;
        end else begin
            if (tx_push) begin
                txq[tx_wr[3:0]] <= d_req_data[7:0];
                tx_wr <= tx_wr + 5'd1;
            end
            if (uart_valid && uart_ready) begin
                tx_rd <= tx_rd + 5'd1;
            end
        end
    end

    // =====================================================================
    // MMIO read mux (combinationally selected at request accept, registered
    // into the response register so the 1-cycle latency is uniform)
    // =====================================================================
    reg [31:0] mmio_rdata;

    always @(*) begin
        case (d_req_address)
            32'h8000_0000: mmio_rdata = CPU_ID;
            32'h8000_0004: mmio_rdata = {8'h00, probs_pct_q, probs_idx_q,
                                         npu_top1, 1'b0, ddr_err, ddr_ok,
                                         1'b0, npu_probs_st, npu_timeout_st,
                                         npu_done_st, npu_busy};
            32'h8000_0008: mmio_rdata = {8'h00, 8'h00, probs_pct_q, 4'h0, probs_idx_q};
            32'h8000_0010: mmio_rdata = {26'h0, tx_count, tx_ready};
            32'h8000_0018: mmio_rdata = cycle_count[31:0];
            32'h8000_001C: mmio_rdata = retired_count[31:0];
            32'h8000_0020: mmio_rdata = ddr_sts;
            32'h8000_0028: mmio_rdata = result_cycles_q;
            32'h8000_0030, 32'h8000_0034,
            32'h8000_0038, 32'h8000_003C: mmio_rdata = timer_rdata;
            default:       mmio_rdata = 32'h0000_0000;
        endcase
    end

    // =====================================================================
    // Instruction channel: ROM only, anything else is a bus error
    // =====================================================================
    reg        i_pend;
    reg [31:0] i_even_q, i_odd_q;
    reg        i_primary_odd_q, i_pair_odd_q, i_pair_valid_q;
    reg        i_err_q;
    wire i_address_ok = (i_req_address[31:IAW+2] == 0) && (i_req_address[1:0] == 0);
    // Range qualification makes this narrow word increment equivalent to
    // byte-address +4, including the ROM-end carry, without a 32-bit adder.
    wire [IAW:0] i_next_word = {1'b0, i_req_address[IAW+1:2]} + 1'b1;
    wire i_pair_address_ok = (i_req_pair_address[31:IAW+2] == 0) &&
                             (i_req_pair_address[1:0] == 0) &&
                             !i_next_word[IAW] &&
                             (i_req_pair_address[IAW+1:2] == i_next_word[IAW-1:0]);
    wire [IAW-2:0] i_even_index = i_req_address[2] ?
        i_req_pair_address[IAW+1:3] : i_req_address[IAW+1:3];
    wire [IAW-2:0] i_odd_index = i_req_address[2] ?
        i_req_address[IAW+1:3] : i_req_pair_address[IAW+1:3];

    assign i_req_ready = !i_pend || i_rsp_ready;

    // A single synchronous read per parity bank; imem is initialization only.
    always @(posedge clk) begin
        if (i_req_valid && i_req_ready) begin
            i_even_q <= imem_even[i_even_index];
            i_odd_q <= imem_odd[i_odd_index];
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            i_pend  <= 1'b0;
            i_primary_odd_q <= 1'b0;
            i_pair_odd_q <= 1'b0;
            i_pair_valid_q <= 1'b0;
            i_err_q <= 1'b0;
        end else if (i_req_valid && i_req_ready) begin
            i_pend <= 1'b1;
            i_primary_odd_q <= i_req_address[2];
            i_pair_odd_q <= i_req_pair_address[2];
            i_pair_valid_q <= i_address_ok && i_pair_address_ok;
            i_err_q <= !i_address_ok;
        end else if (i_rsp_valid && i_rsp_ready) begin
            i_pend <= 1'b0;
        end
    end

    assign i_rsp_valid = i_pend;
    assign i_rsp_data  = i_err_q ? 32'd0 : (i_primary_odd_q ? i_odd_q : i_even_q);
    assign i_rsp_pair_data = i_pair_odd_q ? i_odd_q : i_even_q;
    assign i_rsp_pair_valid = i_pair_valid_q;
    assign i_rsp_is_c = {i_rsp_data[17:16] != 2'b11, i_rsp_data[1:0] != 2'b11};
    assign i_rsp_pair_is_c = {i_rsp_pair_data[17:16] != 2'b11, i_rsp_pair_data[1:0] != 2'b11};
    assign i_rsp_error = i_err_q;

    // =====================================================================
    // Data channel: RAM / MMIO / bus error
    // =====================================================================
    reg        d_pend;
    reg [31:0] d_rsp_q;
    reg [31:0] d_rom_q;
    (* syn_ramstyle = "block_ram" *) reg [7:0] d_ram0_q, d_ram1_q, d_ram2_q, d_ram3_q;
    wire [31:0] d_ram_q = {d_ram3_q, d_ram2_q, d_ram1_q, d_ram0_q};
    reg        d_ram_sel_q, d_rom_sel_q;
    reg        d_ram_write_q;
    reg [DAW-1:0] d_ram_word_q;
    reg [31:0] d_ram_data_q;
    reg [3:0] d_ram_strobe_q;
    reg        d_err_q;
    reg        dd_active;

    wire d_acc      = d_req_valid && d_req_ready;
    wire d_is_mmio  = d_req_address[31];
    wire d_is_ddr   = (d_req_address[31:20] == 12'h400) ||
                     ((d_req_address >= 32'h4100_0000) &&
                      (d_req_address < 32'h4160_0000));
    wire d_is_ram   = (d_req_address >= DMEM_BASE) &&
                      (d_req_address < DMEM_END);
    wire d_is_rom   = (d_req_address[31:IAW+2] == {(32-IAW-2){1'b0}});
    wire [DAW-1:0] d_word = d_req_address[DAW+1:2];
    wire [IAW-1:0] d_rom_word = d_req_address[IAW+1:2];

    // Preserve UART stores under backpressure, even for firmware which does
    // not poll UART_ST before every write.
    assign d_req_ready = !d_pend && !dd_active && (!d_is_ddr || dd_req_ready) &&
                         !(d_req_write && d_req_address == 32'h8000_000C && !tx_ready);

    assign dd_req_valid = d_req_valid && d_is_ddr && !d_pend && !dd_active;
    assign dd_req_address = d_req_address;
    assign dd_req_write = d_req_write;
    assign dd_req_data = d_req_data;
    assign dd_req_strobe = d_req_strobe;
    assign dd_rsp_ready = dd_active && d_rsp_ready;
    // Accepted data transactions are exactly the two registered busy states.
    // FENCE.I reaches MEM after older memory work has completed; younger data
    // requests are blocked/flushed by the core's maintenance barrier.
    assign maintenance_ready = !dd_active && !d_pend;

    // Reset-free synchronous memory read registers let PDS infer block RAM.
    // Read on each idle-channel edge, including the request-accept edge.
    // Registered busy state holds both results through response backpressure;
    // address-range decoding stays out of the physical memory enable path.
    always @(posedge clk) begin
        if (!d_pend && !dd_active) begin
            d_ram0_q <= dmem0[d_word];
            d_ram1_q <= dmem1[d_word];
            d_ram2_q <= dmem2[d_word];
            d_ram3_q <= dmem3[d_word];
            d_rom_q <= rom_d[d_rom_word];
            // Snapshot MMIO in parallel with local memory. Busy state alone
            // holds the response; address admission is not on its enable path.
            d_rsp_q <= mmio_rdata;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) dd_active <= 1'b0;
        else if (d_acc && d_is_ddr) dd_active <= 1'b1;
        else if (dd_rsp_valid && dd_rsp_ready) dd_active <= 1'b0;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            d_pend  <= 1'b0;
            d_err_q <= 1'b0;
            d_ram_sel_q <= 1'b0;
            d_rom_sel_q <= 1'b0;
        end else if (d_acc && !d_is_ddr) begin
            d_pend <= 1'b1;
            d_ram_sel_q <= d_is_ram && !d_is_mmio;
            d_rom_sel_q <= d_is_rom && !d_is_mmio && !d_is_ram;
            if (d_is_mmio) begin
                d_err_q <= 1'b0;
            end else if (d_is_ram) begin
                d_err_q <= 1'b0;
            end else if (d_is_rom) begin
                d_err_q <= 1'b0;
            end else begin
                d_err_q <= 1'b1;
            end
        end else if (d_rsp_valid && d_rsp_ready) begin
            d_pend <= 1'b0;
        end
    end

    assign d_rsp_valid = dd_active ? dd_rsp_valid : d_pend;
    assign d_rsp_data  = dd_active ? dd_rsp_data :
                         d_ram_sel_q ? d_ram_q : d_rom_sel_q ? d_rom_q : d_rsp_q;
    assign d_rsp_error = dd_active ? dd_rsp_error : d_err_q;

    // Capture the RAM write before driving the physical memory enables.
    // The write commits on the first possible response-consumption edge;
    // backpressure can delay acknowledgement. The one-outstanding channel
    // admits the next request only after acknowledgement, preserving latency
    // and subsequent load values under the original bus contract.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            d_ram_write_q <= 1'b0;
            d_ram_word_q <= {DAW{1'b0}};
            d_ram_data_q <= 32'd0;
            d_ram_strobe_q <= 4'd0;
        end else begin
            d_ram_write_q <= d_acc && d_is_ram && d_req_write;
            if (d_acc && d_is_ram && d_req_write) begin
                d_ram_word_q <= d_word;
                d_ram_data_q <= d_req_data;
                d_ram_strobe_q <= d_req_strobe;
            end
        end
    end

    // Byte lanes use one reset-free synchronous read and write port each.
    always @(posedge clk) begin
        if (d_ram_write_q) begin
            if (d_ram_strobe_q[0]) dmem0[d_ram_word_q] <= d_ram_data_q[7:0];
            if (d_ram_strobe_q[1]) dmem1[d_ram_word_q] <= d_ram_data_q[15:8];
            if (d_ram_strobe_q[2]) dmem2[d_ram_word_q] <= d_ram_data_q[23:16];
            if (d_ram_strobe_q[3]) dmem3[d_ram_word_q] <= d_ram_data_q[31:24];
        end
    end

endmodule
