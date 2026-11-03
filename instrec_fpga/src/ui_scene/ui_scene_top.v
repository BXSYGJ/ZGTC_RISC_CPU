// -----------------------------------------------------------------------------
// File    : ui_scene_top.v
// Module  : ui_scene_top
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Top level of the software-defined UI v0 scene renderer
//           (work package D, UI Scene ABI v0).
//
//           Wires the CPU-facing scene table (double-bank descriptor RAM +
//           glyph sequence RAM + COMMIT/ACK handshake, ui_scene_table) to
//           the scan renderer (ui_scene_render).  The renderer produces
//           the 640x360 v0 timing, feeds the frame boundary strobe back to
//           the table for the atomic active-bank switch, prefetches the
//           descriptor words of the active bank into its slot shadow
//           registers during blanking and outputs the mutually aligned
//           rgb / de / hs / vs pixel stream.
//
//           CPU view (single write port, bank-agnostic):
//             0x000..0x0FF descriptor word (32-bit, byte enable)
//             0x100        COMMIT register
//             0x200..0x3FF glyph sequence byte (wr_be[0])
//           commit_ack rises after the bank switch took effect at a frame
//           boundary; active_bank reports which bank is being scanned.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module ui_scene_top (
    input  wire        clk,
    input  wire        rst_n,

    // CPU write port (always targets the back bank).
    input  wire [11:0] wr_addr,
    input  wire [31:0] wr_data,
    input  wire [3:0]  wr_be,
    input  wire        wr_en,

    // Commit handshake and bank status.
    output wire        commit_ack,
    output wire        active_bank,

    // Rendered video (640x360 v0 canvas, four-cycle aligned pipeline).
    output wire [23:0] rgb,
    output wire        de_out,
    output wire        hs_out,
    output wire        vs_out
);

    // Descriptor prefetch channel (renderer -> table).
    wire [7:0]  desc_rd_addr;
    wire [31:0] desc_rd_data;

    // Glyph sequence lookup channel (renderer -> table).
    wire [8:0]  glyph_rd_addr;
    wire [7:0]  glyph_rd_data;

    // Frame boundary strobe (renderer -> table).
    wire        frame_start;

    ui_scene_table u_table (
        .clk           (clk),
        .rst_n         (rst_n),
        .wr_addr       (wr_addr),
        .wr_data       (wr_data),
        .wr_be         (wr_be),
        .wr_en         (wr_en),
        .frame_start   (frame_start),
        .commit_ack    (commit_ack),
        .active_bank   (active_bank),
        .desc_rd_addr  (desc_rd_addr),
        .desc_rd_data  (desc_rd_data),
        .glyph_rd_addr (glyph_rd_addr),
        .glyph_rd_data (glyph_rd_data)
    );

    ui_scene_render u_render (
        .clk           (clk),
        .rst_n         (rst_n),
        .desc_rd_addr  (desc_rd_addr),
        .desc_rd_data  (desc_rd_data),
        .glyph_rd_addr (glyph_rd_addr),
        .glyph_rd_data (glyph_rd_data),
        .rgb           (rgb),
        .de_out        (de_out),
        .hs_out        (hs_out),
        .vs_out        (vs_out),
        .frame_start   (frame_start)
    );

endmodule
