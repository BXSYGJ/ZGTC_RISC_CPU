// -----------------------------------------------------------------------------
// File    : ui_scene_table.v
// Module  : ui_scene_table
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Scene descriptor storage for the software-defined UI v0
//           (work package D, UI Scene ABI v0).
//
//           Holds two banks of the 32-slot x 8-word descriptor table and two
//           banks of the 512-entry glyph sequence RAM.  The CPU write port
//           uses a bank-agnostic linear address space and is always routed
//           to the back bank (the bank that is NOT currently scanned), so
//           scene updates can never tear the visible frame:
//
//             wr_addr 0x000..0x0FF : descriptor word (slot*8 + word), 32-bit
//                                    writes with per-byte enable wr_be[3:0]
//             wr_addr 0x100        : COMMIT register (any write posts a
//                                    commit request)
//             wr_addr 0x200..0x3FF : glyph sequence byte 0..511 (wr_be[0])
//
//           On the frame boundary strobe (frame_start, the vsync rising edge
//           produced by ui_scene_render) a pending commit request atomically
//           toggles the active bank and raises commit_ack.  commit_ack is
//           cleared by the next COMMIT write, so the CPU can poll it to
//           learn that the new scene is already being scanned.
//
//           Read ports are registered (one-cycle synchronous reads) and are
//           always served from the active bank: desc_rd is a sequential
//           prefetch port used by the renderer to refresh its slot shadow
//           registers during blanking, glyph_rd is the random-access glyph
//           id lookup used inside the pixel pipeline.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module ui_scene_table #(
    // Number of descriptor slots per bank (word count = SLOT_COUNT * 8).
    parameter [5:0] SLOT_COUNT = 6'd32,
    // Depth of the glyph sequence RAM per bank.
    parameter [9:0] GLYPH_DEPTH = 10'd512
) (
    input  wire        clk,
    input  wire        rst_n,

    // CPU write port (linear, bank-agnostic, always targets the back bank).
    input  wire [11:0] wr_addr,
    input  wire [31:0] wr_data,
    input  wire [3:0]  wr_be,
    input  wire        wr_en,

    // Frame boundary strobe (single-cycle vsync rising edge marker).
    input  wire        frame_start,

    // Commit handshake and bank status.
    output wire        commit_ack,
    output wire        active_bank,

    // Descriptor prefetch read port (active bank, one-cycle read).
    input  wire [7:0]  desc_rd_addr,
    output wire [31:0] desc_rd_data,

    // Glyph sequence read port (active bank, one-cycle read).
    input  wire [8:0]  glyph_rd_addr,
    output wire [7:0]  glyph_rd_data
);

    // -----------------------------------------------------------------
    // Linear address map constants.
    // -----------------------------------------------------------------
    localparam [11:0] ADDR_COMMIT = 12'h100;

    wire is_desc_wr   = wr_en && (wr_addr[11:8] == 4'h0);
    wire is_commit_wr = wr_en && (wr_addr == ADDR_COMMIT);
    wire is_glyph_wr  = wr_en && (wr_addr[11:9] == 3'b001);

    wire [7:0] desc_wa = wr_addr[7:0];
    wire [8:0] glyph_wa = wr_addr[8:0];

    // -----------------------------------------------------------------
    // Storage: two banks of descriptors and glyph sequences.
    // -----------------------------------------------------------------
    reg [31:0] desc0 [0:255];
    reg [31:0] desc1 [0:255];
    reg [7:0]  glyph0 [0:511];
    reg [7:0]  glyph1 [0:511];

    // -----------------------------------------------------------------
    // Bank control: active_bank selects the scanned bank, the write port
    // always lands on the opposite (back) bank.
    // -----------------------------------------------------------------
    reg       bank_state;
    reg       commit_req;
    reg       ack_state;
    wire      back_bank = ~bank_state;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bank_state  <= 1'b0;
            commit_req  <= 1'b0;
            ack_state   <= 1'b0;
        end else if (is_commit_wr) begin
            // A new commit supersedes a pending one and retires the ack.
            commit_req <= 1'b1;
            ack_state  <= 1'b0;
        end else if (frame_start && commit_req) begin
            bank_state <= ~bank_state;
            commit_req <= 1'b0;
            ack_state  <= 1'b1;
        end
    end

    assign active_bank = bank_state;
    assign commit_ack  = ack_state;

    // -----------------------------------------------------------------
    // Descriptor writes with per-byte enable into the back bank.
    // -----------------------------------------------------------------
    always @(posedge clk) begin
        if (is_desc_wr) begin
            if (back_bank == 1'b0) begin
                if (wr_be[0]) desc0[desc_wa][7:0]   <= wr_data[7:0];
                if (wr_be[1]) desc0[desc_wa][15:8]  <= wr_data[15:8];
                if (wr_be[2]) desc0[desc_wa][23:16] <= wr_data[23:16];
                if (wr_be[3]) desc0[desc_wa][31:24] <= wr_data[31:24];
            end else begin
                if (wr_be[0]) desc1[desc_wa][7:0]   <= wr_data[7:0];
                if (wr_be[1]) desc1[desc_wa][15:8]  <= wr_data[15:8];
                if (wr_be[2]) desc1[desc_wa][23:16] <= wr_data[23:16];
                if (wr_be[3]) desc1[desc_wa][31:24] <= wr_data[31:24];
            end
        end
    end

    // -----------------------------------------------------------------
    // Glyph sequence writes (single byte, wr_be[0] is the byte enable).
    // -----------------------------------------------------------------
    always @(posedge clk) begin
        if (is_glyph_wr && wr_be[0]) begin
            if (back_bank == 1'b0)
                glyph0[glyph_wa] <= wr_data[7:0];
            else
                glyph1[glyph_wa] <= wr_data[7:0];
        end
    end

    // -----------------------------------------------------------------
    // Read ports: registered reads from the active bank.  When the bank
    // toggles on a frame boundary the in-flight read still returns data
    // from the old bank for one cycle; the renderer's round-robin
    // prefetch covers every slot again long before the first active
    // pixel of the new frame, so stale words are always overwritten.
    // -----------------------------------------------------------------
    reg [31:0] desc_rd_reg;
    reg [7:0]  glyph_rd_reg;

    always @(posedge clk) begin
        if (bank_state == 1'b0)
            desc_rd_reg <= desc0[desc_rd_addr];
        else
            desc_rd_reg <= desc1[desc_rd_addr];
    end

    always @(posedge clk) begin
        if (bank_state == 1'b0)
            glyph_rd_reg <= glyph0[glyph_rd_addr];
        else
            glyph_rd_reg <= glyph1[glyph_rd_addr];
    end

    assign desc_rd_data  = desc_rd_reg;
    assign glyph_rd_data = glyph_rd_reg;

    // SLOT_COUNT / GLYPH_DEPTH document the ABI v0 geometry (32 slots,
    // 512 glyph ids); the storage above is sized to exactly that maximum,
    // so the fixed address decoding in this module stays parameter-free.

endmodule
