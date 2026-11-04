// -----------------------------------------------------------------------------
// File    : top_integration_lab.v
// Module  : top_integration_lab
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Integration lab top: bus-level hookup of the three v0 lab
//           modules (uart_app_boot, ui_scene_top, logits_snap) inside ONE
//           clock and reset domain, plus a flat MMIO-style write decoder
//           that mimics the future rv32_cpu_subsys MMIO mux.  This is an
//           experiment harness only - it is NOT the production instrec_top
//           and touches neither the NPU nor the mel engine.
//
// Flat write address map (single 32-bit write port, word addressed):
//   0x000..0x0FF  ui_scene descriptor word write (wr_addr = addr[7:0])
//   0x100         ui_scene COMMIT register
//   0x200         LOGIT_IDX  write (logits_snap read pointer, see idx_q)
//   0x204         SNAP_CTRL  write (bit0 latch, bit1 epoch clear)
//   0x400..0x5FF  ui_scene glyph sequence byte (mapped into the
//                  module-internal 0x200..0x3FF glyph window; the internal
//                  window itself is NOT exposed flat because 0x200/0x204
//                  are taken by the snapshot registers - a production mux
//                  must give ui_scene its own base address instead)
//
// Fake NPU result generator (drives logits_in):
//   after app_ready rises, every vsync edge advances a fixed-seed 32-bit
//   LCG (x = 1664525*x + 1013904223 mod 2^32, seed 0x5EED0001) and the
//   published vector becomes slot i = lcg + i*0x11111111 (16 slots, one
//   deterministic vector per frame).  A latch request fires one cycle
//   after every 4th frame boundary; a SNAP_CTRL[0] write latches too
//   (that path is internal to logits_snap).  frame_id_in / epoch_in come
//   from top-level counters (epoch counts mode-switch events), mode is
//   constant 0 for the lab.
//
// Minimal execution monitor:
//   once app_ready is high the monitor walks the loader IRAM read port
//   starting at app_entry and latches the first four instruction words
//   onto iram_probe[127:0] (word0 in the lowest bits) with
//   iram_probe_valid held high afterwards.
//
// Coding: SV-2005 subset, one module per file, pure ASCII comments.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module top_integration_lab #(
    // UART baud divider: round(125e6/115200) = 1085.
    parameter integer BAUD_DIV = 1085
) (
    input  wire         clk,
    input  wire         rst_n,

    // serial loader pins (115200 8N1)
    input  wire         uart_rxd,
    output wire         uart_txd,

    // flat MMIO-style write port (mimics the rv32 MMIO mux)
    input  wire [31:0]  mmio_addr,
    input  wire [31:0]  mmio_wdata,
    input  wire         mmio_wen,

    // rendered video (same clock domain as core, lab simplification)
    output wire [23:0]  rgb,
    output wire         de,
    output wire         hs,
    output wire         vs,

    // loader status
    output wire         app_ready,
    output wire [31:0]  app_entry,
    output wire [15:0]  app_bytes,
    output wire [127:0] iram_probe,
    output wire         iram_probe_valid,

    // snapshot status (MMIO read side brought out for the lab)
    output wire [31:0]  snap_idx_q,
    output wire [31:0]  snap_meta_q,
    output wire         snap_valid,
    output wire [7:0]   snap_epoch,
    output wire [7:0]   probe_frame_id,

    // scene renderer status
    output wire         commit_ack,
    output wire         active_bank
);

    // ------------------------------------------------------------------
    // Loader status wires (kept visible for future debugging)
    // ------------------------------------------------------------------
    wire        busy_w;
    wire [3:0]  status_state_w;
    wire [7:0]  last_error_w;
    wire [7:0]  last_nak_seq_w;

    wire [31:0] iram_rdata_w;

    // ------------------------------------------------------------------
    // Execution monitor state (sole driver of the loader IRAM read port)
    // ------------------------------------------------------------------
    localparam [1:0] P_IDLE = 2'd0;
    localparam [1:0] P_READ = 2'd1;
    localparam [1:0] P_DONE = 2'd2;

    reg  [1:0]   probe_state;
    reg  [2:0]   probe_cnt;
    reg  [9:0]   probe_addr;
    reg  [127:0] probe_words;
    reg          probe_valid;

    // ------------------------------------------------------------------
    // Fake NPU result generator state
    // ------------------------------------------------------------------
    localparam [31:0] LCG_SEED = 32'h5EED0001;
    localparam [31:0] LCG_MUL  = 32'd1664525;
    localparam [31:0] LCG_ADD  = 32'd1013904223;

    reg  [31:0]  lcg_state;
    reg  [511:0] fake_logits;
    reg  [7:0]   frame_cnt;
    reg  [7:0]   epoch_cnt;
    reg          auto_latch_d;

    integer      i;

    wire [63:0]  lcg_prod = LCG_MUL * lcg_state;
    wire [31:0]  lcg_next = lcg_prod[31:0] + LCG_ADD;

    // ------------------------------------------------------------------
    // Flat MMIO write decode (combinational)
    // ------------------------------------------------------------------
    wire ui_desc_sel   = mmio_wen && (mmio_addr[31:8] == 24'h000000);
    wire ui_commit_sel = mmio_wen && (mmio_addr[31:8] == 24'h000001)
                                  && (mmio_addr[7:0] == 8'h00);
    wire ui_glyph_sel  = mmio_wen && (mmio_addr[31:9] == 23'h000002);
    wire idx_sel       = mmio_wen && (mmio_addr == 32'h00000200);
    wire ctrl_sel      = mmio_wen && (mmio_addr == 32'h00000204);

    wire        ui_wr_en   = ui_desc_sel || ui_commit_sel || ui_glyph_sel;
    wire [11:0] ui_wr_addr = ui_commit_sel ? 12'h100 :
                             ui_glyph_sel  ? {3'b001, mmio_addr[8:0]} :
                                             {4'b0000, mmio_addr[7:0]};
    wire [3:0]  ui_wr_be   = ui_glyph_sel ? 4'b0001 : 4'b1111;

    // ------------------------------------------------------------------
    // Module instances
    // ------------------------------------------------------------------
    uart_app_boot #(.BAUD_DIV(BAUD_DIV)) u_boot (
        .clk           (clk),
        .rst_n         (rst_n),
        .uart_rxd      (uart_rxd),
        .uart_txd      (uart_txd),
        .iram_raddr    (probe_addr),
        .iram_rdata    (iram_rdata_w),
        .app_ready     (app_ready),
        .app_entry     (app_entry),
        .busy          (busy_w),
        .status_state  (status_state_w),
        .bytes_received(app_bytes),
        .last_error    (last_error_w),
        .last_nak_seq  (last_nak_seq_w)
    );

    ui_scene_top u_scene (
        .clk        (clk),
        .rst_n      (rst_n),
        .wr_addr    (ui_wr_addr),
        .wr_data    (mmio_wdata),
        .wr_be      (ui_wr_be),
        .wr_en      (ui_wr_en),
        .commit_ack (commit_ack),
        .active_bank(active_bank),
        .rgb        (rgb),
        .de_out     (de),
        .hs_out     (hs),
        .vs_out     (vs)
    );

    logits_snap #(.SLOT_COUNT(8'd16)) u_snap (
        .clk        (clk),
        .rst_n      (rst_n),
        .logits_in  (fake_logits),
        .frame_id_in(frame_cnt),
        .mode_id_in (8'd0),
        .epoch_in   (epoch_cnt),
        .latch_req  (auto_latch_d),
        .idx_wen    (idx_sel),
        .idx_wdata  (mmio_wdata),
        .ctrl_wen   (ctrl_sel),
        .ctrl_wdata (mmio_wdata),
        .idx_q      (snap_idx_q),
        .meta_q     (snap_meta_q),
        .snap_valid (snap_valid),
        .snap_epoch (snap_epoch)
    );

    // ------------------------------------------------------------------
    // Status output mapping
    // ------------------------------------------------------------------
    assign iram_probe       = probe_words;
    assign iram_probe_valid = probe_valid;
    assign probe_frame_id   = frame_cnt;

    // ------------------------------------------------------------------
    // Fake NPU result generator: frame-edge detection, LCG advance,
    // per-frame vector publish, automatic latch every 4th frame and the
    // epoch counter (incremented on every SNAP_CTRL[1] mode-switch write).
    // ------------------------------------------------------------------
    reg  vs_d;
    wire frame_edge = vs && !vs_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            vs_d         <= 1'b0;
            lcg_state    <= LCG_SEED;
            fake_logits  <= 512'd0;
            frame_cnt    <= 8'd0;
            epoch_cnt    <= 8'd0;
            auto_latch_d <= 1'b0;
        end else begin
            vs_d         <= vs;
            auto_latch_d <= app_ready && frame_edge
                            && (frame_cnt[1:0] == 2'b11);

            if (frame_edge && app_ready) begin
                frame_cnt <= frame_cnt + 8'd1;
                lcg_state <= lcg_next;
                for (i = 0; i < 16; i = i + 1)
                    fake_logits[i*32 +: 32] <= lcg_next + (i * 32'h11111111);
            end

            if (ctrl_sel && mmio_wdata[1])
                epoch_cnt <= epoch_cnt + 8'd1;
        end
    end

    // ------------------------------------------------------------------
    // Minimal execution monitor: after app_ready, read four instruction
    // words from the loader IRAM starting at app_entry (word address =
    // entry >> 2) and latch them onto probe_words.
    //   cycle 0 : address = word0 (issued)
    //   cycle 1 : word0 data valid -> latch, address = word1
    //   cycle 2 : word1 valid -> latch, address = word2
    //   cycle 3 : word2 valid -> latch, address = word3
    //   cycle 4 : word3 valid -> latch, done
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            probe_state <= P_IDLE;
            probe_cnt   <= 3'd0;
            probe_addr  <= 10'd0;
            probe_words <= 128'd0;
            probe_valid <= 1'b0;
        end else begin
            case (probe_state)
                P_IDLE: begin
                    if (app_ready) begin
                        probe_addr  <= app_entry[11:2];
                        probe_cnt   <= 3'd0;
                        probe_state <= P_READ;
                    end
                end
                P_READ: begin
                    probe_cnt <= probe_cnt + 3'd1;
                    if (probe_cnt < 3'd3)
                        probe_addr <= probe_addr + 10'd1;
                    case (probe_cnt)
                        3'd1: probe_words[31:0]   <= iram_rdata_w;
                        3'd2: probe_words[63:32]  <= iram_rdata_w;
                        3'd3: probe_words[95:64]  <= iram_rdata_w;
                        3'd4: begin
                            probe_words[127:96] <= iram_rdata_w;
                            probe_valid         <= 1'b1;
                            probe_state         <= P_DONE;
                        end
                        default: ;
                    endcase
                end
                P_DONE: begin
                    probe_valid <= 1'b1;
                end
                default: probe_state <= P_IDLE;
            endcase
        end
    end

endmodule
