// ---------------------------------------------------------------------------
// feat_dump: pack the Mel feature bytes emitted by feat_copy_engine into
// 32-byte DDR beats and write them to a reserved DDR region.
//
// Why: the only way to read back the complete 64 x 258 Mel feature from the
// board is to land it in DDR (the Mel bank itself is private to mel_engine and
// the NPU reads it directly).  Replacing the UI spectrum cache
// (feat_page_buf, 16,512 x 8 bits double-banked ~= 14.7 DRM18K) with a DDR
// image both enables the readback and frees the DRM headroom that
// place-and-route needs at 95% utilisation.
//
// Datapath: feat_copy_engine streams one byte per cycle (dst_we/dst_addr/
// dst_data).  This module collects 32 consecutive bytes into a 256-bit beat
// and issues one single-beat write command (len = 0) at
// DDR_BASE + (dst_addr >> 5) * 32.  16,512 bytes = 516 commands.
//
// The normal processing path is untouched: this module only consumes the copy
// stream that used to feed the (now disabled) spectrum cache.
// ---------------------------------------------------------------------------
`timescale 1ns / 1ps

module feat_dump #(
    parameter [27:0] DDR_BASE = 28'h0020_0000,  // reserved 64 KB region
    parameter integer BEATS    = 516            // 16512 / 32
) (
    input  wire        clk,
    input  wire        rst_n,

    // ---- byte stream from feat_copy_engine ------------------------------
    input  wire        src_we,
    input  wire [14:0] src_addr,
    input  wire [7:0]  src_data,
    input  wire        copy_done,

    // ---- DDR3 master-3 write port (single-beat commands) ----------------
    output reg         m3_cmd_valid,
    output reg  [36:0] m3_cmd,
    output reg  [255:0] m3_wdata,
    input  wire        m3_done,

    // ---- status ---------------------------------------------------------
    output reg         busy,
    output reg         dump_done
);

    // Byte packer: 256-bit beat, byte i at [i*8 +: 8].
    reg [255:0] beat_buf;
    reg         beat_ready;     // beat_buf holds a complete 32-byte beat
    reg [13:0]  beat_idx;       // 0..BEATS-1 in flight
    reg [13:0]  beat_cnt;       // beats accepted so far

    localparam [1:0] F_IDLE = 2'd0;   // waiting for bytes / beats
    localparam [1:0] F_REQ  = 2'd1;   // command presented, waiting done
    localparam [1:0] F_LAST = 2'd2;   // final beat in flight

    reg [1:0] state;

    assign busy = (state != F_IDLE) || beat_ready;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            beat_buf      <= 256'd0;
            beat_ready    <= 1'b0;
            beat_idx      <= 14'd0;
            beat_cnt      <= 14'd0;
            state         <= F_IDLE;
            m3_cmd_valid  <= 1'b0;
            m3_cmd        <= 37'd0;
            m3_wdata      <= 256'd0;
            dump_done     <= 1'b0;
        end else begin
            dump_done <= 1'b0;

            // ---- byte packing (independent of the write state machine) ----
            if (src_we && !beat_ready) begin
                // Byte address inside the 32-byte beat is src_addr[4:0]; a
                // full beat is complete when the low five bits wrap to 0
                // after byte 31.
                beat_buf[src_addr[4:0]*8 +: 8] <= src_data;
                if (src_addr[4:0] == 5'd31) begin
                    beat_ready <= 1'b1;
                    beat_cnt   <= beat_cnt + 14'd1;
                end
            end

            case (state)
                F_IDLE: begin
                    m3_cmd_valid <= 1'b0;
                    if (beat_ready) begin
                        m3_cmd       <= {1'b1,  // write
                                         DDR_BASE + {beat_idx[13:0], 5'b00000},
                                         8'd0};  // len = 0 -> one 32-byte beat
                        m3_wdata     <= beat_buf;
                        m3_cmd_valid <= 1'b1;
                        beat_ready   <= 1'b0;
                        state        <= F_REQ;
                    end
                end
                F_REQ: begin
                    if (m3_done) begin
                        m3_cmd_valid <= 1'b0;
                        beat_idx     <= beat_idx + 14'd1;
                        if (beat_cnt >= BEATS) begin
                            dump_done <= 1'b1;
                            state     <= F_IDLE;
                        end else begin
                            state <= F_IDLE;
                        end
                    end
                end
                default: state <= F_IDLE;
            endcase

            // Clear the packer at the end of a copy pass so the next window
            // starts aligned.
            if (copy_done && state == F_IDLE && !beat_ready) begin
                beat_idx <= 14'd0;
                beat_cnt <= 14'd0;
            end
        end
    end

endmodule