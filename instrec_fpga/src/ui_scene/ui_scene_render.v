// -----------------------------------------------------------------------------
// File    : ui_scene_render.v
// Module  : ui_scene_render
// Project : InstRec-FPGA (PG2L100H-6IFBG676, PDS 2022.2-SP6.4)
// Purpose : Scene raster renderer for the software-defined UI v0
//           (work package D, UI Scene ABI v0).
//
//           Generates a 640x360 (v0 small canvas, geometry equi-ratio to
//           1080p) scan timing with DE / HS / VS, and paints the active
//           scene bank described by the shadow slot registers:
//
//             TEXT : 16x32 pixels per character, glyph id from the glyph
//                    sequence RAM (glyph_ptr + char index), dot matrix from
//                    the 16x32 glyph ROM (4096 words, $readmemh).
//             BAR  : rectangle filled up to value/1000 of its width
//                    (fill test: x_local * 1000 < value * w, evaluated in
//                    32-bit arithmetic, same as the reference model).
//             RECT : solid colour fill.
//
//           Priority: the lowest slot index that covers the pixel wins
//           (equivalent to painting slots from the highest index down and
//           letting lower indices overwrite).  Inside the winning slot,
//           non-ink pixels (blank glyph dots, the unfilled part of a bar)
//           render black, matching the reference model exactly.
//
//           Four-stage pixel pipeline (same convention as ui_renderer):
//             stage 0 : scan counters -> slot selection and geometry
//             stage 1 : glyph sequence RAM address (synchronous read in
//                       ui_scene_table)
//             stage 2 : glyph id available -> glyph ROM address
//                       (synchronous read)
//             stage 3 : glyph bits available -> registered rgb output
//           rgb / de_out / hs_out / vs_out are all delayed by the same four
//           cycles, so they stay mutually aligned at the output.
//
//           Slot shadow registers: during blanking (!de of the timing
//           generator) a round-robin prefetch walks the 256 descriptor
//           words of the active bank through the one-cycle desc_rd port
//           (256 cycles per full refresh, one blank line already offers
//           160 cycles and the frame head offers 7200).  A frame boundary
//           bank toggle is therefore settled long before the first active
//           pixel is scanned; during active lines the shadow registers are
//           frozen, which keeps one frame internally consistent.
// -----------------------------------------------------------------------------

`timescale 1ns / 1ps

module ui_scene_render #(
    // Visible canvas (v0: 640x360, equi-ratio to 1920x1080).
    parameter [10:0] IMG_W        = 11'd640,
    parameter [10:0] IMG_H        = 11'd360,
    // Total scan geometry (blanking included).
    parameter [10:0] HTOTAL       = 11'd800,
    parameter [10:0] VTOTAL       = 11'd405,
    parameter [10:0] HSTART       = 11'd64,
    parameter [10:0] VSTART       = 11'd9,
    parameter [10:0] HSYNC_START  = 11'd16,
    parameter [10:0] HSYNC_END    = 11'd112,
    parameter [3:0]  VSYNC_LINES  = 4'd4,
    // Number of descriptor slots (ABI v0: 32).
    parameter [4:0]  SLOT_COUNT   = 5'd32
) (
    input  wire        clk,
    input  wire        rst_n,

    // Descriptor prefetch port (active bank, one-cycle read).
    output wire [7:0]  desc_rd_addr,
    input  wire [31:0] desc_rd_data,

    // Glyph sequence read port (active bank, one-cycle read).
    output wire [8:0]  glyph_rd_addr,
    input  wire [7:0]  glyph_rd_data,

    // Rendered video output (four-cycle aligned pixel pipeline).
    output reg  [23:0] rgb,
    output reg         de_out,
    output reg         hs_out,
    output reg         vs_out,

    // Single-cycle frame boundary marker (x == 0 && y == 0), feeds the
    // atomic bank switch in ui_scene_table.
    output wire        frame_start
);

    // -----------------------------------------------------------------
    // Scan timing generator.
    // -----------------------------------------------------------------
    reg [10:0] xc;
    reg [10:0] yc;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            xc <= 11'd0;
            yc <= 11'd0;
        end else if (xc == HTOTAL - 11'd1) begin
            xc <= 11'd0;
            yc <= (yc == VTOTAL - 11'd1) ? 11'd0 : (yc + 11'd1);
        end else begin
            xc <= xc + 11'd1;
        end
    end

    wire de_now = (xc >= HSTART) && (xc < HSTART + IMG_W) &&
                  (yc >= VSTART) && (yc < VSTART + IMG_H);
    wire hs_now = (xc >= HSYNC_START) && (xc < HSYNC_END);
    wire vs_now = (yc < {7'd0, VSYNC_LINES});
    assign frame_start = (xc == 11'd0) && (yc == 11'd0);

    // Canvas coordinates (origin at the first active pixel): all scene
    // geometry is specified in this 640x360 domain, not in scan
    // coordinates.  Outside the DE window the subtraction wraps, which
    // is harmless: those cycles are blanked at the output register.
    wire [10:0] img_x = xc - HSTART;
    wire [10:0] img_y = yc - VSTART;

    // -----------------------------------------------------------------
    // Slot shadow registers, refreshed from the active bank during
    // blanking via the round-robin prefetch below.
    // -----------------------------------------------------------------
    reg [31:0] slot_w0 [0:31];
    reg [31:0] slot_w1 [0:31];
    reg [31:0] slot_w2 [0:31];
    reg [31:0] slot_w3 [0:31];
    reg [31:0] slot_w4 [0:31];
    reg [31:0] slot_w5 [0:31];

    reg [7:0]  pref_cnt;
    reg [7:0]  pref_cnt_d;
    reg        pref_d;

    assign desc_rd_addr = pref_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pref_cnt   <= 8'd0;
            pref_cnt_d <= 8'd0;
            pref_d     <= 1'b0;
        end else begin
            pref_cnt   <= de_now ? pref_cnt : (pref_cnt + 8'd1);
            pref_cnt_d <= pref_cnt;
            pref_d     <= ~de_now;
        end
    end

    // pref_cnt_d addresses word (pref_cnt_d[2:0]) of slot
    // pref_cnt_d[7:3]; the table read data arrives one cycle later, in
    // the cycle where pref_d is still high (the read was issued while
    // blanking).  Data returned during active video is dropped.
    always @(posedge clk) begin
        if (pref_d) begin
            case (pref_cnt_d[2:0])
                3'd0: slot_w0[pref_cnt_d[7:3]] <= desc_rd_data;
                3'd1: slot_w1[pref_cnt_d[7:3]] <= desc_rd_data;
                3'd2: slot_w2[pref_cnt_d[7:3]] <= desc_rd_data;
                3'd3: slot_w3[pref_cnt_d[7:3]] <= desc_rd_data;
                3'd4: slot_w4[pref_cnt_d[7:3]] <= desc_rd_data;
                3'd5: slot_w5[pref_cnt_d[7:3]] <= desc_rd_data;
                default: ;
            endcase
        end
    end

    // -----------------------------------------------------------------
    // Stage 0 (combinational): per-slot coverage and winner selection.
    // -----------------------------------------------------------------
    wire [31:0] cov;

    genvar gi;
    generate
        for (gi = 0; gi < 32; gi = gi + 1) begin : g_slot_cov
            wire [12:0] slot_x0 = {1'b0, slot_w1[gi][11:0]};
            wire [12:0] slot_y0 = {1'b0, slot_w1[gi][23:12]};
            wire [12:0] slot_xe = slot_x0 + {1'b0, slot_w2[gi][11:0]};
            wire [12:0] slot_ye = slot_y0 + {1'b0, slot_w2[gi][23:12]};
            wire        slot_on = slot_w0[gi][16] && (slot_w0[gi][7:0] != 8'd0);
            assign cov[gi] = slot_on &&
                             ({2'd0, img_x} >= slot_x0) && ({2'd0, img_x} < slot_xe) &&
                             ({2'd0, img_y} >= slot_y0) && ({2'd0, img_y} < slot_ye);
        end
    endgenerate

    // Scan from the highest slot index down: later assignments win, so the
    // lowest covering slot index ends up selected (lowest = on top).
    reg        sel_found;
    reg [7:0]  sel_type;
    reg [11:0] sel_x;
    reg [11:0] sel_y;
    reg [11:0] sel_w;
    reg [11:0] sel_h;
    reg [23:0] sel_color;
    reg [15:0] sel_value;
    reg [8:0]  sel_gptr;

    integer si;
    always @* begin
        sel_found  = 1'b0;
        sel_type   = 8'd0;
        sel_x      = 12'd0;
        sel_y      = 12'd0;
        sel_w      = 12'd0;
        sel_h      = 12'd0;
        sel_color  = 24'd0;
        sel_value  = 16'd0;
        sel_gptr   = 9'd0;
        for (si = 31; si >= 0; si = si - 1) begin
            if (cov[si]) begin
                sel_found = 1'b1;
                sel_type  = slot_w0[si][7:0];
                sel_x     = slot_w1[si][11:0];
                sel_y     = slot_w1[si][23:12];
                sel_w     = slot_w2[si][11:0];
                sel_h     = slot_w2[si][23:12];
                sel_color = slot_w3[si][23:0];
                sel_value = slot_w4[si][15:0];
                sel_gptr  = slot_w5[si][8:0];
            end
        end
    end

    // Winner geometry (all offsets are inside the winner rectangle, so
    // the unsigned subtractions below never wrap).
    wire [11:0] dx        = {1'b0, img_x} - sel_x;
    wire [11:0] dy        = {1'b0, img_y} - sel_y;
    wire [7:0]  char_idx  = dx[11:4];
    wire [4:0]  glyph_row = dy[4:0];
    wire [3:0]  glyph_bit = 4'd15 - dx[3:0];

    // TEXT: only characters below the glyph-count value are rendered; the
    // glyph id index wraps modulo 512 like the 9-bit RAM address.
    wire text_sel  = (sel_type == 8'd1);
    wire text_on   = text_sel && ({1'b0, char_idx} < sel_value);
    wire [8:0] glyph_addr = sel_gptr + {1'b0, char_idx};

    // BAR: 32-bit product comparison, bit-exact with the reference model.
    wire bar_sel   = (sel_type == 8'd2);
    wire [31:0] bar_lhs = {20'd0, dx} * 32'd1000;
    wire [31:0] bar_rhs = {16'd0, sel_value} * {20'd0, sel_w};
    wire bar_fill  = bar_sel && (bar_lhs < bar_rhs);
    wire rect_sel  = (sel_type == 8'd3);

    // -----------------------------------------------------------------
    // Stage 1: winner parameters and glyph sequence RAM address.
    // -----------------------------------------------------------------
    reg        de_s1, hs_s1, vs_s1;
    reg [7:0]  type_s1;
    reg [23:0] color_s1;
    reg        bar_fill_s1;
    reg        text_on_s1;
    reg        rect_s1;
    reg [4:0]  row_s1;
    reg [3:0]  bit_s1;
    reg        found_s1;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            de_s1       <= 1'b0;
            hs_s1       <= 1'b0;
            vs_s1       <= 1'b0;
            type_s1     <= 8'd0;
            color_s1    <= 24'd0;
            bar_fill_s1 <= 1'b0;
            text_on_s1  <= 1'b0;
            rect_s1     <= 1'b0;
            row_s1      <= 5'd0;
            bit_s1      <= 4'd0;
            found_s1    <= 1'b0;
        end else begin
            de_s1       <= de_now;
            hs_s1       <= hs_now;
            vs_s1       <= vs_now;
            type_s1     <= sel_type;
            color_s1    <= sel_color;
            bar_fill_s1 <= bar_fill;
            text_on_s1  <= text_on;
            rect_s1     <= rect_sel;
            row_s1      <= glyph_row;
            bit_s1      <= glyph_bit;
            found_s1    <= sel_found;
        end
    end

    assign glyph_rd_addr = glyph_addr;

    // -----------------------------------------------------------------
    // Stage 2: glyph id from the table, glyph ROM address for the dot
    // matrix lookup (ROM read is registered, one cycle).
    // -----------------------------------------------------------------
    reg [4:0]  row_s2;
    wire [11:0] rom_addr = {glyph_rd_data[6:0], row_s2};

    reg        de_s2, hs_s2, vs_s2;
    reg [23:0] color_s2;
    reg        bar_fill_s2;
    reg        text_on_s2;
    reg        rect_s2;
    reg [3:0]  bit_s2;
    reg        found_s2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            de_s2       <= 1'b0;
            hs_s2       <= 1'b0;
            vs_s2       <= 1'b0;
            color_s2    <= 24'd0;
            bar_fill_s2 <= 1'b0;
            text_on_s2  <= 1'b0;
            rect_s2     <= 1'b0;
            bit_s2      <= 4'd0;
            found_s2    <= 1'b0;
            row_s2      <= 5'd0;
        end else begin
            de_s2       <= de_s1;
            hs_s2       <= hs_s1;
            vs_s2       <= vs_s1;
            color_s2    <= color_s1;
            bar_fill_s2 <= bar_fill_s1;
            text_on_s2  <= text_on_s1;
            rect_s2     <= rect_s1;
            bit_s2      <= bit_s1;
            found_s2    <= found_s1;
            row_s2      <= row_s1;
        end
    end

    reg [15:0] glyph_rom [0:4095];

    initial begin
        $readmemh("src/ui_scene/glyph16x32.hex", glyph_rom);
    end

    reg [15:0] rom_bits_s3;

    always @(posedge clk) begin
        rom_bits_s3 <= glyph_rom[rom_addr];
    end

    // -----------------------------------------------------------------
    // Stage 3: ink decision and the output register (fourth pipeline
    // stage for de / hs / vs keeps rgb and the control outputs aligned).
    // -----------------------------------------------------------------
    reg        de_s3, hs_s3, vs_s3;
    reg [23:0] color_s3;
    reg        bar_fill_s3;
    reg        text_on_s3;
    reg        rect_s3;
    reg [3:0]  bit_s3;
    reg        found_s3;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            de_s3       <= 1'b0;
            hs_s3       <= 1'b0;
            vs_s3       <= 1'b0;
            color_s3    <= 24'd0;
            bar_fill_s3 <= 1'b0;
            text_on_s3  <= 1'b0;
            rect_s3     <= 1'b0;
            bit_s3      <= 4'd0;
            found_s3    <= 1'b0;
        end else begin
            de_s3       <= de_s2;
            hs_s3       <= hs_s2;
            vs_s3       <= vs_s2;
            color_s3    <= color_s2;
            bar_fill_s3 <= bar_fill_s2;
            text_on_s3  <= text_on_s2;
            rect_s3     <= rect_s2;
            bit_s3      <= bit_s2;
            found_s3    <= found_s2;
        end
    end

    wire ink = found_s3 && (rect_s3 || bar_fill_s3 ||
                            (text_on_s3 && rom_bits_s3[bit_s3]));

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rgb    <= 24'd0;
            de_out <= 1'b0;
            hs_out <= 1'b0;
            vs_out <= 1'b0;
        end else begin
            rgb    <= ink ? color_s3 : 24'd0;
            de_out <= de_s3;
            hs_out <= hs_s3;
            vs_out <= vs_s3;
        end
    end

    // SLOT_COUNT documents the ABI v0 slot count; the coverage selection
    // above is unrolled for the fixed ABI v0 maximum of 32 slots.

endmodule
