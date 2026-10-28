// ---------------------------------------------------------------------------
// wdma.v -- weight DMA for the INT8 NPU (T-M2-02)
//
// Two streams per layer, both from DDR3 master 1:
//
//  1. Contract: bias/M/shift live after the weights in the same region.
//     They are read once at layer start into small on-chip RAMs, then
//     emitted per group as the 48-beat sequence conv_engine expects:
//       16 x bias (s32) -> 16 x M (s32) -> 16 x shift (u8/7-bit).
//     fc2 has only 8 channels; the group is zero-padded to 16 lanes.
//
//  2. Weights: a contiguous 32-byte beat stream cut into taps
//     (16 B conv/fc1, 8 B fc2). conv1 is the odd case: 27 taps = 432 B =
//     13.5 beats, so the last beat contributes one tap.
//
// Flow: contract read -> per group {48 contract beats, weight burst(s),
// tap emit} -> next group. A 16-beat FIFO absorbs the 2:1 rate difference
// between a 32-byte beat and a 16-byte tap, because the DDR3 IP cannot be
// back-pressured. w_data/w_valid are held until w_ready (conv/fc only
// accept during their MAC window).
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

    // 48-beat group contract toward conv_engine
    output reg          b_valid,
    output reg  signed [31:0] bias_s32,
    output reg          m_valid,
    output reg  signed [31:0] m_s32,
    output reg          s_valid,
    output reg  [6:0]   shift,

    output reg          busy,
    output reg          done
);

    // ---- layer geometry ----
    reg [27:0] wb, bb, mb, sb;
    reg [8:0]  cout;
    reg [15:0] grp_total, taps_per_grp;
    reg [7:0]  tap_bytes;

    always @* begin
        case (layer_id)
            4'd0: begin wb=28'd512;    bb=28'd944;    mb=28'd1136;   sb=28'd1328;
                         cout=9'd48;  grp_total=16'd3;  taps_per_grp=16'd9;    tap_bytes=8'd16; end
            4'd1: begin wb=28'd1376;   bb=28'd42848;  mb=28'd43232;  sb=28'd43616;
                         cout=9'd96;  grp_total=16'd6;  taps_per_grp=16'd432;  tap_bytes=8'd16; end
            4'd2: begin wb=28'd43712;  bb=28'd209600; mb=28'd210368; sb=28'd211136;
                         cout=9'd192; grp_total=16'd12; taps_per_grp=16'd864;  tap_bytes=8'd16; end
            4'd3: begin wb=28'd211328; bb=28'd653696; mb=28'd654720; sb=28'd655744;
                         cout=9'd256; grp_total=16'd16; taps_per_grp=16'd1728; tap_bytes=8'd16; end
            4'd4: begin wb=28'd656000; bb=28'd688768; mb=28'd689280; sb=28'd689792;
                         cout=9'd128; grp_total=16'd8;  taps_per_grp=16'd256;  tap_bytes=8'd16; end
            default: begin wb=28'd689920; bb=28'd690944; mb=28'd690976; sb=28'd691008;
                         cout=9'd8;  grp_total=16'd1;  taps_per_grp=16'd128;  tap_bytes=8'd8; end
        endcase
    end

    localparam [3:0] S_IDLE   = 4'd0;
    localparam [3:0] S_CB_CMD = 4'd1;
    localparam [3:0] S_CB_FIL = 4'd2;
    localparam [3:0] S_CM_CMD = 4'd3;
    localparam [3:0] S_CM_FIL = 4'd4;
    localparam [3:0] S_CS_CMD = 4'd5;
    localparam [3:0] S_CS_FIL = 4'd6;
    localparam [3:0] S_GRP    = 4'd7;
    localparam [3:0] S_TCMD   = 4'd8;
    localparam [3:0] S_TFIL   = 4'd9;
    localparam [3:0] S_TEMIT  = 4'd10;
    localparam [3:0] S_NEXT   = 4'd11;
    localparam [3:0] S_DONE   = 4'd12;
    reg [3:0] state;

    reg signed [31:0] bram [0:255];
    reg signed [31:0] mram [0:255];
    reg [7:0]         sram [0:255];

    // contract read bookkeeping
    reg [15:0] cfg_beats_left;
    reg [4:0]  cfg_cmd_beats;
    reg [27:0] cfg_addr;
    reg [8:0]  cfg_idx;      // element index inside the current contract

    // contract emit
    reg [5:0]  c_cnt;
    reg [15:0] grp_cnt;

    // weight stream
    reg [255:0] fifo [0:15];
    reg [4:0]   wr_ptr, rd_ptr, fifo_cnt;
    reg [15:0]  taps_left, beats_left;
    reg [4:0]   cmd_beats, emit_beats;
    reg [7:0]   sub;
    reg [15:0]  tap_in_grp;
    reg [27:0]  cur_addr;

    wire [255:0] beat_c = fifo[rd_ptr[3:0]];
    wire [31:0]  total_taps  = taps_per_grp * grp_total;
    wire [31:0]  total_bytes = total_taps * tap_bytes;
    wire [15:0]  total_beats = (total_bytes + 32'd31) >> 5;
    wire [4:0]   chunk = (cfg_beats_left > 16'd16) ? 5'd16 : cfg_beats_left[4:0];

    // FIFO write (never back-pressured by the IP).
    always @(posedge clk) begin
        if (rd_valid) fifo[wr_ptr[3:0]] <= rd_data;
    end

    // Contract RAM write: 8 x s32 for bias/M, 32 x u8 for shift.
    integer j;
    always @(posedge clk) begin
        if (rd_valid && (state == S_CB_FIL)) begin
            for (j = 0; j < 8; j = j + 1)
                bram[{cfg_idx[7:3], j[2:0]} + 0] <= rd_data[j*32 +: 32];
        end
        if (rd_valid && (state == S_CM_FIL)) begin
            for (j = 0; j < 8; j = j + 1)
                mram[{cfg_idx[7:3], j[2:0]}] <= rd_data[j*32 +: 32];
        end
        if (rd_valid && (state == S_CS_FIL)) begin
            for (j = 0; j < 32; j = j + 1)
                sram[{cfg_idx[7:3], 5'd0} + j] <= rd_data[j*8 +: 8];
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
            b_valid      <= 1'b0;
            m_valid      <= 1'b0;
            s_valid      <= 1'b0;
            busy         <= 1'b0;
            done         <= 1'b0;
            cfg_beats_left <= 16'd0;
            cfg_cmd_beats  <= 5'd0;
            cfg_addr       <= 28'd0;
            cfg_idx        <= 9'd0;
            c_cnt          <= 6'd0;
            grp_cnt        <= 16'd0;
            wr_ptr         <= 5'd0;
            rd_ptr         <= 5'd0;
            fifo_cnt       <= 5'd0;
            taps_left      <= 16'd0;
            beats_left     <= 16'd0;
            cmd_beats      <= 5'd0;
            emit_beats     <= 5'd0;
            sub            <= 8'd0;
            tap_in_grp     <= 16'd0;
            cur_addr       <= 28'd0;
        end else begin
            w_valid   <= 1'b0;
            grp_start <= 1'b0;
            b_valid   <= 1'b0;
            m_valid   <= 1'b0;
            s_valid   <= 1'b0;
            done      <= 1'b0;

            if (rd_valid) begin
                wr_ptr   <= wr_ptr + 5'd1;
                fifo_cnt <= fifo_cnt + 5'd1;
            end

            case (state)
                S_IDLE: begin
                    busy <= 1'b0;
                    if (start) begin
                        busy           <= 1'b1;
                        grp_cnt        <= 16'd0;
                        cfg_addr       <= bb;
                        cfg_idx        <= 9'd0;
                        cfg_beats_left <= (cout + 9'd7) >> 3;
                        state          <= S_CB_CMD;
                    end
                end

                // ---- bias ----
                S_CB_CMD: begin
                    cfg_cmd_beats <= chunk;
                    rd_cmd <= {1'b0, cfg_addr,
                               ((cfg_beats_left > 16'd16) ? 8'd15 : (cfg_beats_left[7:0] - 8'd1))};
                    rd_cmd_valid <= 1'b1;
                    state <= S_CB_FIL;
                end
                S_CB_FIL: begin
                    if (rd_done) begin
                        rd_cmd_valid   <= 1'b0;
                        cfg_addr       <= cfg_addr + {19'd0, cfg_cmd_beats, 5'd0};
                        cfg_beats_left <= cfg_beats_left - {11'd0, cfg_cmd_beats};
                        cfg_idx        <= cfg_idx + {4'd0, cfg_cmd_beats, 3'd0};
                        if (cfg_beats_left <= 16'd16) begin
                            cfg_addr <= mb;
                            cfg_idx  <= 9'd0;
                            cfg_beats_left <= (cout + 9'd7) >> 3;
                            state <= S_CM_CMD;
                        end else begin
                            state <= S_CB_CMD;
                        end
                    end
                end

                // ---- M ----
                S_CM_CMD: begin
                    cfg_cmd_beats <= chunk;
                    rd_cmd <= {1'b0, cfg_addr,
                               ((cfg_beats_left > 16'd16) ? 8'd15 : (cfg_beats_left[7:0] - 8'd1))};
                    rd_cmd_valid <= 1'b1;
                    state <= S_CM_FIL;
                end
                S_CM_FIL: begin
                    if (rd_done) begin
                        rd_cmd_valid   <= 1'b0;
                        cfg_addr       <= cfg_addr + {19'd0, cfg_cmd_beats, 5'd0};
                        cfg_beats_left <= cfg_beats_left - {11'd0, cfg_cmd_beats};
                        if (cfg_beats_left <= 16'd16) begin
                            cfg_addr <= sb;
                            cfg_idx  <= 9'd0;
                            cfg_beats_left <= (cout + 9'd31) >> 5;
                            state <= S_CS_CMD;
                        end else begin
                            state <= S_CM_CMD;
                        end
                    end
                end

                // ---- shift ----
                S_CS_CMD: begin
                    cfg_cmd_beats <= chunk;
                    rd_cmd <= {1'b0, cfg_addr,
                               ((cfg_beats_left > 16'd16) ? 8'd15 : (cfg_beats_left[7:0] - 8'd1))};
                    rd_cmd_valid <= 1'b1;
                    state <= S_CS_FIL;
                end
                S_CS_FIL: begin
                    if (rd_done) begin
                        rd_cmd_valid   <= 1'b0;
                        cfg_addr       <= cfg_addr + {19'd0, cfg_cmd_beats, 5'd0};
                        cfg_beats_left <= cfg_beats_left - {11'd0, cfg_cmd_beats};
                        cfg_idx        <= cfg_idx + {4'd1, 5'd0};   // +32 bytes
                        if (cfg_beats_left <= 16'd16) begin
                            c_cnt     <= 6'd0;
                            grp_cnt   <= 16'd0;
                            tap_in_grp<= 16'd0;
                            cur_addr  <= wb;
                            taps_left <= taps_per_grp;
                            beats_left<= (taps_per_grp * tap_bytes + 32'd31) >> 5;
                            wr_ptr    <= 5'd0;
                            rd_ptr    <= 5'd0;
                            fifo_cnt  <= 5'd0;
                            state     <= S_GRP;
                        end else begin
                            state <= S_CS_CMD;
                        end
                    end
                end

                // ---- 48-beat group contract ----
                S_GRP: begin
                    if (c_cnt == 6'd0) grp_start <= 1'b1;
                    if (c_cnt < 6'd16) begin
                        b_valid  <= 1'b1;
                        bias_s32 <= (grp_cnt * 16 + c_cnt[3:0] < cout)
                                    ? bram[grp_cnt * 16 + c_cnt[3:0]] : 32'sd0;
                    end else if (c_cnt < 6'd32) begin
                        m_valid  <= 1'b1;
                        m_s32    <= (grp_cnt * 16 + c_cnt[3:0] < cout)
                                    ? mram[grp_cnt * 16 + c_cnt[3:0]] : 32'sd0;
                    end else begin
                        s_valid  <= 1'b1;
                        shift    <= (grp_cnt * 16 + c_cnt[3:0] < cout)
                                    ? sram[grp_cnt * 16 + c_cnt[3:0]][6:0] : 7'd0;
                    end
                    c_cnt <= c_cnt + 6'd1;
                    if (c_cnt == 6'd47) state <= S_TCMD;
                end

                // ---- weight burst for this group ----
                S_TCMD: begin
                    if (beats_left == 16'd0) begin
                        state <= S_NEXT;
                    end else begin
                        cmd_beats <= (beats_left > 16'd16) ? 5'd16 : beats_left[4:0];
                        rd_cmd <= {1'b0, cur_addr,
                                   ((beats_left > 16'd16) ? 8'd15 : (beats_left[7:0] - 8'd1))};
                        rd_cmd_valid <= 1'b1;
                        state <= S_TFIL;
                    end
                end
                S_TFIL: begin
                    if (rd_done) begin
                        rd_cmd_valid <= 1'b0;
                        cur_addr     <= cur_addr + {19'd0, cmd_beats, 5'd0};
                        beats_left   <= beats_left - {11'd0, cmd_beats};
                        emit_beats   <= cmd_beats;
                        sub          <= 8'd0;
                        state        <= S_TEMIT;
                    end
                end
                S_TEMIT: begin
                    if (emit_beats != 5'd0 && taps_left != 16'd0) begin
                        if (tap_bytes == 8'd16)
                            w_data <= sub[0] ? beat_c[255:128] : beat_c[127:0];
                        else case (sub[1:0])
                            2'd0: w_data <= {64'd0, beat_c[63:0]};
                            2'd1: w_data <= {64'd0, beat_c[127:64]};
                            2'd2: w_data <= {64'd0, beat_c[191:128]};
                            default: w_data <= {64'd0, beat_c[255:192]};
                        endcase

                        w_valid <= 1'b1;
                        if (w_ready) begin
                            tap_in_grp <= (tap_in_grp + 16'd1 == taps_per_grp) ? 16'd0 : tap_in_grp + 16'd1;
                            taps_left  <= taps_left - 16'd1;
                            if ((tap_bytes == 8'd16 && sub == 8'd1) ||
                                (tap_bytes == 8'd8  && sub == 8'd3)) begin
                                sub        <= 8'd0;
                                rd_ptr     <= rd_ptr + 5'd1;
                                fifo_cnt   <= fifo_cnt - 5'd1;
                                emit_beats <= emit_beats - 5'd1;
                                if (taps_left == 16'd1) begin
                                    state <= S_NEXT;
                                end else if (emit_beats == 5'd1) begin
                                    state <= S_TCMD;
                                end
                            end else begin
                                sub <= sub + 8'd1;
                            end
                        end
                    end
                end

                S_NEXT: begin
                    if (grp_cnt + 16'd1 == grp_total) begin
                        state <= S_DONE;
                    end else begin
                        grp_cnt    <= grp_cnt + 16'd1;
                        tap_in_grp <= 16'd0;
                        taps_left  <= taps_per_grp;
                        beats_left <= (taps_per_grp * tap_bytes + 32'd31) >> 5;
                        cur_addr   <= cur_addr + (taps_per_grp * tap_bytes + 32'd31) / 32 * 32;
                        c_cnt      <= 6'd0;
                        state      <= S_GRP;
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