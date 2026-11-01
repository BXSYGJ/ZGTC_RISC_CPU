// -----------------------------------------------------------------------------
// self_test - DDR3 pattern self-test over ddr3_ctrl_axi master port 3
//             (tasks.md T-M0-09, design.md Sec. 2.2.9 / Sec. 5.1,
//             REQ-MEM-005; contract C-SELFTEST@1 rules F1..F7)
// -----------------------------------------------------------------------------
// Writes a 4 KB pattern block into the DDR3 self-test region
// (base 0x0030_0000, Sec. 5.1 address map) and reads it back for a
// word-by-word compare. Pattern: 32-bit address-tagged words
// {25'h0, word_idx[6:0]} XOR DDR_PATTERN -> each 32-bit word is unique
// by index, so a stuck address line or a swapped beat fails loudly.
//
// Master port 3 interface (Sun's ddr3_ctrl_axi, integration-verified
// against src/ddr3/ddr3_ctrl_axi.v):
//   cmd        : m3_cmd = {wr, addr[27:0], len[7:0]} with cmd_valid[3]
//   write beats: m3_wdata[255:0] accepted on wready_beat[3] pulses
//   read data  : rd_data_3[255:0] with rd_valid[3], paced by rd_ready[3]
//   completion : done[3] single-cycle pulse (write completion, read
//                completion, or AXI watchdog abort)
// All bursts are fixed len=15 (16 beats x 32 B = 512 B per command).
//
// Dummy-write-before-read (REQ-MEM-003 hard rule) is enforced INSIDE
// ddr3_ctrl_axi (the adapter injects a masked dummy write before every
// read command); this module simply issues plain read commands and
// therefore performs no dummy write of its own (integration note: if
// the adapter's dummy-write policy changes, the read path here must be
// revisited - flagged as an integration alignment point).
//
// Transaction plan (bit-level self-check table):
//   write phase : 8 commands, addresses 0x300000 + i*512 (i=0..7),
//                 each a 16-beat burst of 32 B = 512 B; total 4 KB.
//                 Every 32-bit word w (index 0..1023, big-endian order
//                 inside each beat) = DDR_PATTERN ^ w, so each word is
//                 unique by index.
//
//   read phase  : 8 commands, same addresses/burst shape; every beat
//                 is compared word-wise against the regenerated
//                 expected pattern.
//   result      : st_done=1 on full pass; st_fail=1 + first failing
//                 byte address st_fail_addr[27:0] otherwise.
//   duration    : 16 x 512 B at DDR3 speed -> a few ms at most; the
//                 sys_ctrl watchdog budget for the whole test is 100 ms
//                 (2x margin over a worst-case latency-bound run).
//
// Robustness rules (root cause of the field symptom "DDR3 ERR
// @FFFFFFFF", where sys_ctrl timed out because neither st_done nor
// st_fail was ever raised):
//   * cmd_valid is a LEVEL held from issue until done (F1/F3). A single
//     cycle strobe is lost whenever the arbiter cannot grant it on that
//     exact cycle (a read command requires an empty read fifo, see
//     C-DDR3-CTRL-SEM@1 S6), which used to wedge the FSM forever.
//   * ST_WDATA tests wready_beat BEFORE done (F2). A normal write burst
//     raises the last wready_beat and done on the SAME cycle (S1/S2), so
//     the order must never be inverted or a healthy burst would be
//     reported as an abort.
//   * ST_RDATA tests rd_valid BEFORE done_q (F4). The read fifo count
//     only reflects a push on the next cycle (S5), hence the beat that
//     carries rlast is offered with rd_valid exactly one cycle after
//     done: done_q is that one-cycle delayed copy of done, and a done_q
//     with no rd_valid can only mean an AXI watchdog abort.
//   * st_done and st_fail are mutually exclusive and both stick in
//     ST_END until the next st_start (F6/F7).
//
// All logic runs in the core_clk (125 MHz) domain. Pattern generation
// and comparison are combinational functions of the command/beat
// indices so no pattern ROM is needed.
// -----------------------------------------------------------------------------
module self_test #(
    // 32-bit pattern seed: XORed into every word, keeps low-byte
    // uniqueness of the address-tagged pattern.
    parameter [31:0] DDR_PATTERN  = 32'h5A5A_00FF,
    // Self-test region base (byte address, Sec. 5.1 map: 0x0030_0000).
    parameter [27:0] SELFTEST_BASE = 28'h0030_0000
) (
    input  wire        clk,            // core_clk 125 MHz
    input  wire        rst_n,          // core-domain reset, sync release
    // control from sys_ctrl
    input  wire        st_start,       // one-cycle start request
    // ddr3_ctrl_axi master port 3 (integration alignment point)
    output reg         cmd_valid,      // maps to cmd_valid[3]
    output reg  [36:0] cmd,            // maps to m3_cmd = {wr,addr,len}
    output wire [255:0] wdata,         // maps to m3_wdata (combinational
                                       // beat data, valid whenever
                                       // wready_beat pulses)
    input  wire        wready_beat,    // maps to wready_beat[3]
    output reg         rd_ready,       // maps to rd_ready[3]
    input  wire [255:0] rd_data,       // maps to rd_data_3
    input  wire        rd_valid,       // maps to rd_valid[3]
    input  wire        done,           // maps to done[3]
    // status to sys_ctrl
    output reg         st_done,        // test completed with PASS
    output reg         st_fail,        // test completed with FAIL
    output reg  [27:0] st_fail_addr    // first failing byte address
);

    // ------------------------------------------------------------------
    // Pattern function: 32-bit word for word index w_idx (0..1023).
    // 8 words per beat, 16 beats per command, 8 commands -> 1024 words.
    // ------------------------------------------------------------------
    function [31:0] pat_word;
        input [9:0] w_idx;
        begin
            pat_word = DDR_PATTERN ^ {22'd0, w_idx};
        end
    endfunction

    // Command/address generation.
    localparam [3:0] BURST_LEN = 4'd15;   // fixed len=15 (16 beats)

    reg [2:0]  cmd_idx;    // command index 0..7
    reg [3:0]  beat_idx;   // beat index within burst 0..15
    reg [6:0]  wrd_idx;    // word base index within command 0,8,...,120
    reg [9:0]  exp_idx;    // running word index for compare (0..1023)


    // Byte address of the current command: base + cmd_idx*512 (F5).
    // The index is zero-extended to the full 28-bit address width before
    // the shift so the sum never relies on an implicit width truncation.
    wire [27:0] cmd_addr = SELFTEST_BASE + ({25'd0, cmd_idx} << 9);

    // Expected 256-bit beat during the read phase: 8 words for
    // word indices exp_idx .. exp_idx+7 (big-endian word order inside
    // the beat, matching the writer's packing).
    wire [255:0] exp_beat = {pat_word(exp_idx + 10'd7),
                              pat_word(exp_idx + 10'd6),
                              pat_word(exp_idx + 10'd5),
                              pat_word(exp_idx + 10'd4),
                              pat_word(exp_idx + 10'd3),
                              pat_word(exp_idx + 10'd2),
                              pat_word(exp_idx + 10'd1),
                              pat_word(exp_idx + 10'd0)};

    // Write beat data: word indices (cmd_idx*128) + wrd_idx + 0..7,
    // driven combinationally so the beat present on a wready_beat
    // pulse always matches the current beat counter.
    wire [9:0] wr_base = {cmd_idx, wrd_idx};


    assign wdata = {pat_word(wr_base + 10'd7),
                      pat_word(wr_base + 10'd6),
                      pat_word(wr_base + 10'd5),
                      pat_word(wr_base + 10'd4),
                      pat_word(wr_base + 10'd3),
                      pat_word(wr_base + 10'd2),
                      pat_word(wr_base + 10'd1),
                      pat_word(wr_base + 10'd0)};

    // ------------------------------------------------------------------
    // FSM: idle -> write commands -> read commands -> compare on the
    // fly -> done/fail.
    // ------------------------------------------------------------------
    localparam [2:0] ST_IDLE = 3'd0;
    localparam [2:0] ST_WCMD = 3'd1;
    localparam [2:0] ST_WDATA = 3'd2;
    localparam [2:0] ST_RCMD = 3'd3;
    localparam [2:0] ST_RDATA = 3'd4;
    localparam [2:0] ST_END  = 3'd5;

    reg [2:0] state;
    reg       done_q;   // done delayed by one cycle (read abort guard)

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= ST_IDLE;
            cmd_valid    <= 1'b0;
            cmd          <= 37'd0;
            rd_ready     <= 1'b1;    // always accept read beats
            cmd_idx      <= 3'd0;
            beat_idx     <= 4'd0;
            wrd_idx      <= 7'd0;
            exp_idx      <= 10'd0;
            done_q       <= 1'b0;
            st_done      <= 1'b0;
            st_fail      <= 1'b0;
            st_fail_addr <= 28'd0;
        end else begin
            // One-cycle delayed copy of done (F4). The read fifo count is
            // updated on the cycle after a push (S5), so the beat carrying
            // rlast appears with rd_valid exactly one cycle after done.
            done_q <= done;

            case (state)
                ST_IDLE: begin
                    if (st_start) begin
                        cmd_idx      <= 3'd0;
                        beat_idx     <= 4'd0;
                        wrd_idx      <= 7'd0;
                        exp_idx      <= 10'd0;
                        st_done      <= 1'b0;
                        st_fail      <= 1'b0;
                        st_fail_addr <= 28'd0;
                        state        <= ST_WCMD;
                    end
                end

                ST_WCMD: begin
                    // Issue write command i: addr base+i*512, len 15.
                    // cmd = {wr, addr[27:0], len[7:0]} = 37 bits exactly.
                    // cmd_valid is left high here and only cleared by the
                    // done pulse below (F1: hold the strobe until done).
                    cmd       <= {1'b1, cmd_addr, 8'd15};
                    cmd_valid <= 1'b1;
                    beat_idx  <= 4'd0;
                    wrd_idx   <= 7'd0;
                    state     <= ST_WDATA;
                end

                ST_WDATA: begin
                    // wdata is combinational and always presents the
                    // beat selected by beat_idx/wrd_idx; the counter
                    // advances on the wready_beat handshake pulse.
                    // wready_beat MUST be tested first (F2/S1/S2): the
                    // completing beat and done arrive on the same cycle.
                    if (wready_beat) begin
                        if (beat_idx == 4'd15) begin
                            if (cmd_idx == 3'd7) begin
                                cmd_idx <= 3'd0;
                                state   <= ST_RCMD;
                            end else begin
                                cmd_idx <= cmd_idx + 3'd1;
                                state   <= ST_WCMD;
                            end
                        end else begin
                            beat_idx <= beat_idx + 4'd1;
                            wrd_idx  <= wrd_idx + 7'd8;
                        end
                    end else if (done) begin
                        // done with no beat handshake while the burst is
                        // still short: the AXI watchdog aborted the write
                        // (or the address phase never handshook). Report
                        // the failure instead of waiting forever.
                        st_done      <= 1'b0;
                        st_fail      <= 1'b1;
                        st_fail_addr <= cmd_addr;
                        state        <= ST_END;
                    end
                end

                ST_RCMD: begin
                    // Issue read command i (dummy-write handled inside
                    // ddr3_ctrl_axi per REQ-MEM-003). cmd_valid is held
                    // until done (F3): a read grant needs an empty read
                    // fifo, so a one-cycle strobe can be dropped.
                    cmd       <= {1'b0, cmd_addr, 8'd15};
                    cmd_valid <= 1'b1;
                    exp_idx   <= {cmd_idx, 7'd0};
                    state     <= ST_RDATA;
                end

                ST_RDATA: begin
                    // Compare every beat on the fly. A command holds
                    // 16 beats of 8 words; the last beat of command i is
                    // recognized by exp_idx[6:0] == 120 (word index
                    // i*128 + 120 .. i*128 + 127).
                    // rd_valid is tested before done_q (F4): on a normal
                    // last beat both are high on the same cycle.
                    if (rd_valid) begin
                        if (rd_data != exp_beat) begin
                            // First failing beat: report its byte
                            // address (beat granularity; word position
                            // inside the beat is not resolved further).
                            st_done      <= 1'b0;
                            st_fail      <= 1'b1;
                            st_fail_addr <= cmd_addr;
                            state        <= ST_END;
                        end else if (exp_idx[6:0] == 7'd120) begin
                            // Last beat of the current command matched.
                            if (cmd_idx == 3'd7) begin
                                st_fail <= 1'b0;
                                st_done <= 1'b1;
                                state   <= ST_END;
                            end else begin
                                cmd_idx <= cmd_idx + 3'd1;
                                state   <= ST_RCMD;
                            end
                        end else begin
                            exp_idx <= exp_idx + 10'd8;
                        end
                    end else if (done_q) begin
                        // done arrived one cycle ago and still no beat is
                        // available: the read burst was aborted by the
                        // AXI watchdog (AR/S_R timeout, empty fifo).
                        st_done      <= 1'b0;
                        st_fail      <= 1'b1;
                        st_fail_addr <= cmd_addr;
                        state        <= ST_END;
                    end
                end

                ST_END: begin
                    // Terminal state: results held until the next
                    // st_start (KEY1 re-trigger path from sys_ctrl).
                    // st_done / st_fail are mutually exclusive (F7) and
                    // both sticky in this state (F6).
                    if (st_start) begin
                        cmd_idx      <= 3'd0;
                        beat_idx     <= 4'd0;
                        wrd_idx      <= 7'd0;
                        exp_idx      <= 10'd0;
                        st_done      <= 1'b0;
                        st_fail      <= 1'b0;
                        st_fail_addr <= 28'd0;
                        state        <= ST_WCMD;
                    end
                end

                default: state <= ST_IDLE;
            endcase

            // Hold cmd_valid from issue until done (F1/F3), then clear it
            // on the completion pulse so a finished command can never be
            // granted a second time. This assignment is last in the block
            // on purpose: done wins over any issue in the same cycle.
            if (done) begin
                cmd_valid <= 1'b0;
            end
        end
    end

endmodule