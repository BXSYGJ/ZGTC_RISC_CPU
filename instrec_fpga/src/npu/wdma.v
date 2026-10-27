// ---------------------------------------------------------------------------
// wdma.v -- weight DMA for the INT8 NPU (T-M2-02)
//
// Reads a whole layer's weight region from DDR3 master 1 as a contiguous
// 32-byte beat stream and cuts it into taps:
//   conv/fc1 tap = 16 B (16 lanes)   fc2 tap = 8 B (8 lanes)
// Layer regions start 32-byte aligned, so a beat carries 2 taps (16 B) or
// 4 taps (8 B). conv1 is the only odd case: 27 taps = 432 B = 13.5 beats,
// so the last beat contributes a single tap (the upper half is not
// emitted).
//
// Flow: issue an AXI read command of up to 16 beats (the controller's
// burst limit), fill a 16-beat FIFO while rd_valid streams, then emit the
// buffered taps one per cycle. The FIFO absorbs the 2:1 rate difference
// between a 32-byte beat and a 16-byte tap; the DDR3 IP cannot be
// back-pressured, so buffering is mandatory.
//
// Group boundary: grp_start pulses on the first tap of each group, derived
// from the global tap counter and the per-layer taps-per-group.
//
// Contract stream (bias/M/shift) is still an attachment point: it lives in
// the same region after the weights and will be added with npu_top.
// ---------------------------------------------------------------------------

module wdma (
    input  wire         clk,
    input  wire         rst_n,

    input  wire         start,
    input  wire [3:0]   layer_id,

    output reg          rd_cmd_valid,
    output reg  [36:0]  rd_cmd,
    input  wire         rd_ready,
    input  wire [255:0] rd_data,
    input  wire         rd_valid,
    input  wire         rd_done,

    output reg          w_valid,
    output reg  [127:0] w_data,
    input  wire         w_ready,

    output reg          grp_start,

    output reg          busy,
    output reg          done
);

    // ---- Layer geometry (from the verified image layout) ----
    reg [27:0] w_base;
    reg [15:0] grp_total;
    reg [15:0] taps_per_grp;
    reg [7:0]  tap_bytes;

    always @* begin
        case (layer_id)
            4'd0: begin w_base = 28'd512;    grp_total = 16'd3;  taps_per_grp = 16'd9;    tap_bytes = 8'd16; end
            4'd1: begin w_base = 28'd1376;   grp_total = 16'd6;  taps_per_grp = 16'd432;  tap_bytes = 8'd16; end
            4'd2: begin w_base = 28'd43712;  grp_total = 16'd12; taps_per_grp = 16'd864;  tap_bytes = 8'd16; end
            4'd3: begin w_base = 28'd211328; grp_total = 16'd16; taps_per_grp = 16'd1728; tap_bytes = 8'd16; end
            4'd4: begin w_base = 28'd656000; grp_total = 16'd8;  taps_per_grp = 16'd256;  tap_bytes = 8'd16; end
            default: begin w_base = 28'd689920; grp_total = 16'd1; taps_per_grp = 16'd128; tap_bytes = 8'd8; end
        endcase
    end

    localparam [2:0] S_IDLE = 3'd0;
    localparam [2:0] S_CMD  = 3'd1;
    localparam [2:0] S_FILL = 3'd2;
    localparam [2:0] S_EMIT = 3'd3;
    localparam [2:0] S_NEXT = 3'd4;
    localparam [2:0] S_DONE = 3'd5;
    reg [2:0] state;

    // 16-beat (512 B) read FIFO.
    reg [255:0] fifo [0:15];
    reg [4:0]   wr_ptr;
    reg [4:0]   rd_ptr;
    reg [4:0]   fifo_cnt;

    reg [15:0] grp_cnt;
    reg [31:0] tap_cnt;
    reg [27:0] cur_addr;
    reg [15:0] taps_left;
    reg [15:0] beats_left;    // beats in the whole layer
    reg [4:0]  cmd_beats;     // beats in the current command (<=16)
    reg [4:0]  emit_beats;    // beats buffered for the emitter
    reg [7:0]  sub;           // sub-tap index inside a beat
    reg [15:0]  tap_in_grp;

    wire [31:0] total_taps  = taps_per_grp * grp_total;
    wire [31:0] total_bytes = total_taps * tap_bytes;
    wire [15:0] total_beats = (total_bytes + 32'd31) >> 5;

    // FIFO is a register array; a combinational read is a 16:1 mux, small
    // enough for LUTRAM and avoids one extra pipeline stage.
    wire [255:0] beat_c = fifo[rd_ptr[3:0]];
    wire         grp_first = (tap_in_grp == 16'd0);

    // FIFO write (DDR3 read side, never back-pressured).
    always @(posedge clk) begin
        if (rd_valid) begin
            fifo[wr_ptr[3:0]] <= rd_data;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= S_IDLE;
            rd_cmd_valid <= 1'b0;
            rd_cmd       <= 37'd0;
            w_valid      <= 1'b0;
            w_data       <= 128'd0;
            grp_start    <= 1'b0;
            busy         <= 1'b0;
            done         <= 1'b0;
            tap_cnt      <= 32'd0;
            cur_addr     <= 28'd0;
            taps_left    <= 16'd0;
            beats_left   <= 16'd0;
            cmd_beats    <= 5'd0;
            emit_beats   <= 5'd0;
            sub          <= 8'd0;
            wr_ptr       <= 5'd0;
            rd_ptr       <= 5'd0;
            fifo_cnt     <= 5'd0;
            tap_in_grp   <= 16'd0;
        end else begin
            w_valid   <= 1'b0;
            grp_start <= 1'b0;
            done      <= 1'b0;

            if (rd_valid) begin
                wr_ptr   <= wr_ptr + 5'd1;
                fifo_cnt <= fifo_cnt + 5'd1;
            end

            case (state)
                S_IDLE: begin
                    busy <= 1'b0;
                    if (start) begin
                        busy       <= 1'b1;
                        tap_cnt    <= 32'd0;
                        cur_addr   <= w_base;
                        taps_left  <= taps_per_grp * grp_total;
                        beats_left <= total_beats;
                        tap_in_grp <= 16'd0;
                        wr_ptr     <= 5'd0;
                        rd_ptr     <= 5'd0;
                        fifo_cnt   <= 5'd0;
                        state      <= S_CMD;
                    end
                end

                S_CMD: begin
                    if (beats_left == 16'd0) begin
                        state <= S_DONE;
                    end else begin
                        cmd_beats    <= (beats_left > 16'd16) ? 5'd16 : beats_left[4:0];
                        rd_cmd       <= {1'b0, cur_addr,
                                         ((beats_left > 16'd16) ? 8'd15 : (beats_left[7:0] - 8'd1))};
                        rd_cmd_valid <= 1'b1;
                        state        <= S_FILL;
                    end
                end

                S_FILL: begin
                    // Wait for the burst to finish; rd_valid fills the FIFO.
                    if (rd_done) begin
                        rd_cmd_valid <= 1'b0;
                        cur_addr     <= cur_addr + {19'd0, cmd_beats, 5'd0};
                        beats_left   <= beats_left - {11'd0, cmd_beats};
                        emit_beats   <= cmd_beats;
                        sub          <= 8'd0;
                        state        <= S_EMIT;
                    end
                end

                S_EMIT: begin
                    if (emit_beats != 5'd0 && taps_left != 16'd0) begin
                        // 16-byte taps: sub 0 -> low half, 1 -> high half.
                        // 8-byte taps: sub 0..3 -> four quarters, zero
                        // extended into the 16-lane word for fc_engine.
                        if (tap_bytes == 8'd16) begin
                            w_data <= sub[0] ? beat_c[255:128] : beat_c[127:0];
                        end else begin
                            case (sub[1:0])
                                2'd0: w_data <= {64'd0, beat_c[63:0]};
                                2'd1: w_data <= {64'd0, beat_c[127:64]};
                                2'd2: w_data <= {64'd0, beat_c[191:128]};
                                default: w_data <= {64'd0, beat_c[255:192]};
                            endcase
                        end

                        w_valid <= 1'b1;
                        // Hold w_data/w_valid until the consumer accepts the
                        // tap; conv_engine only asserts w_ready during its
                        // MAC window, so unconditional advancement would
                        // silently drop taps.
                        if (w_ready) begin
                            if (grp_first) grp_start <= 1'b1;
                            tap_cnt   <= tap_cnt + 32'd1;
                            taps_left <= taps_left - 16'd1;

                            if (tap_in_grp + 16'd1 == taps_per_grp)
                                tap_in_grp <= 16'd0;
                            else
                                tap_in_grp <= tap_in_grp + 16'd1;

                            if ((tap_bytes == 8'd16 && sub == 8'd1) ||
                                (tap_bytes == 8'd8  && sub == 8'd3)) begin
                                sub        <= 8'd0;
                                rd_ptr     <= rd_ptr + 5'd1;
                                fifo_cnt   <= fifo_cnt - 5'd1;
                                emit_beats <= emit_beats - 5'd1;
                                if (taps_left == 16'd1)
                                    state <= S_DONE;
                                else if (emit_beats == 5'd1)
                                    state <= S_CMD;
                            end else begin
                                sub <= sub + 8'd1;
                            end
                        end
                    end
                end

                S_DONE: begin
                    busy  <= 1'b0;
                    done  <= 1'b1;
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule