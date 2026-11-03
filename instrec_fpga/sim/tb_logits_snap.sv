// ---------------------------------------------------------------------------
// tb_logits_snap.sv -- MMIO logits snapshot testbench (contract section 3)
//
// DUT: src/ctrl/logits_snap.v (16-slot parallel latch, indexed MMIO read).
//
// Scenes (each one must end with "SCENE n PASS"):
//   S1  basic latch/read: 16 distinct slot values (int32 boundary sweep),
//       SNAP_CTRL[0] latch, per-index readback via LOGIT_IDX/LOGIT_VAL,
//       SNAP_META frame/mode/epoch/valid_count fields.
//   S2  atomicity: half of the live bus changes before the latch; the
//       shadow registers of ALL 16 slots must already hold the new values
//       at the FIRST negedge after the latching posedge (sampled through
//       hierarchical u_dut.snap_slots[*], case runs with --public), plus
//       the normal readback path.
//   S3  epoch clear: SNAP_CTRL[1] write -> epoch = epoch_in + 1,
//       valid_count = 0, snap_valid falls; v0 keeps the old slot DATA
//       readable (documented deviation from "clear old results").
//   S4  overwrite: a second full-bus latch (driven through latch_req, the
//       upstream NPU-done trigger path) replaces every slot.
//   S5  group5/dominance slots 8..13 latch and read back; untouched slots
//       keep their values; LOGIT_IDX only uses bits [4:0].
//
// PASS line: "RESULT: PASS tb_logits_snap" (run_sim.py contract).
// ---------------------------------------------------------------------------
`timescale 1ns/1ps

module tb_logits_snap;

    localparam integer CLK_HALF = 5;          // 100 MHz

    reg clk   = 1'b0;
    reg rst_n = 1'b0;
    always #(CLK_HALF) clk = ~clk;

    // -----------------------------------------------------------------
    // DUT connections
    // -----------------------------------------------------------------
    reg  [511:0] logits_in   = 512'd0;
    reg  [7:0]   frame_id_in = 8'd0;
    reg  [7:0]   mode_id_in  = 8'd0;
    reg  [7:0]   epoch_in    = 8'd0;
    reg          latch_req   = 1'b0;
    reg          idx_wen     = 1'b0;
    reg  [31:0]  idx_wdata   = 32'd0;
    reg          ctrl_wen    = 1'b0;
    reg  [31:0]  ctrl_wdata  = 32'd0;

    wire [31:0] idx_q;
    wire [31:0] meta_q;
    wire        snap_valid;
    wire [7:0]  snap_epoch;

    logits_snap #(
        .SLOT_COUNT (8'd16)
    ) u_dut (
        .clk         (clk),
        .rst_n       (rst_n),
        .logits_in   (logits_in),
        .frame_id_in (frame_id_in),
        .mode_id_in  (mode_id_in),
        .epoch_in    (epoch_in),
        .latch_req   (latch_req),
        .idx_wen     (idx_wen),
        .idx_wdata   (idx_wdata),
        .ctrl_wen    (ctrl_wen),
        .ctrl_wdata  (ctrl_wdata),
        .idx_q       (idx_q),
        .meta_q      (meta_q),
        .snap_valid  (snap_valid),
        .snap_epoch  (snap_epoch)
    );

    // -----------------------------------------------------------------
    // Bookkeeping
    // -----------------------------------------------------------------
    integer errors     = 0;
    integer checks     = 0;
    integer scene_base = 0;
    integer i          = 0;
    integer mm         = 0;
    reg [31:0] v       = 32'd0;
    reg [31:0] m       = 32'd0;

    reg [31:0] exp_cur [0:15];   // expected shadow content (mirrors the bus)

    task automatic check;
        input [511:0] name;
        input         ok;
        begin
            checks = checks + 1;
            if (ok) $display("CHECK PASS: %0s", name);
            else begin
                errors = errors + 1;
                $display("CHECK FAIL: %0s", name);
            end
        end
    endtask

    task automatic scene_end;
        input integer sc;
        begin
            if (errors == scene_base) $display("SCENE %0d PASS", sc);
            else $display("SCENE %0d FAIL", sc);
        end
    endtask

    // -----------------------------------------------------------------
    // MMIO-style drivers (stimulus on negedge, one-cycle strobes)
    // -----------------------------------------------------------------
    task automatic wr_idx;         // LOGIT_IDX write
        input [31:0] d;
        begin
            @(negedge clk);
            idx_wdata = d;
            idx_wen   = 1'b1;
            @(negedge clk);
            idx_wen   = 1'b0;
        end
    endtask

    task automatic wr_ctrl;        // SNAP_CTRL write
        input [31:0] d;
        begin
            @(negedge clk);
            ctrl_wdata = d;
            ctrl_wen   = 1'b1;
            @(negedge clk);
            ctrl_wen   = 1'b0;
        end
    endtask

    task automatic pulse_latch;    // upstream latch_req pulse (NPU done)
        begin
            @(negedge clk);
            latch_req = 1'b1;
            @(negedge clk);
            latch_req = 1'b0;
        end
    endtask

    task automatic rd_val;         // LOGIT_VAL read (settled at negedge)
        output [31:0] val;
        begin
            @(negedge clk);
            val = idx_q;
        end
    endtask

    task automatic rd_meta;        // SNAP_META read (settled at negedge)
        output [31:0] val;
        begin
            @(negedge clk);
            val = meta_q;
        end
    endtask

    // -----------------------------------------------------------------
    // Main sequence
    // -----------------------------------------------------------------
    initial begin
        $display("=== tb_logits_snap start ===");
        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        repeat (2) @(negedge clk);

        // ================= S1: basic latch / read =================
        scene_base = errors;
        rd_meta(m);
        check("S1 reset: valid_count is 0", m[31:24] === 8'd0);
        check("S1 reset: snap_valid low", snap_valid === 1'b0);

        // int32 boundary sweep + Q16 group5 domain + dominance + spare
        exp_cur[0]  = 32'hFFFF_FFC7;   // -57  (measured eight-class min)
        exp_cur[1]  = 32'h0000_0000;   // 0
        exp_cur[2]  = 32'h0000_00A9;   // 169  (measured eight-class max)
        exp_cur[3]  = 32'h1234_5678;
        exp_cur[4]  = 32'h8000_0000;   // INT32_MIN
        exp_cur[5]  = 32'h7FFF_FFFF;   // INT32_MAX
        exp_cur[6]  = 32'hFFFF_FFFF;   // -1
        exp_cur[7]  = 32'h0000_0064;   // 100
        exp_cur[8]  = 32'h0001_8000;   // Q16 1.5 (group5 activity domain)
        exp_cur[9]  = 32'h0000_8000;   // Q16 0.5
        exp_cur[10] = 32'h0000_0000;   // Q16 0.0
        exp_cur[11] = 32'h0002_8000;   // Q16 2.5
        exp_cur[12] = 32'h0000_0001;   // Q16 1 LSB
        exp_cur[13] = 32'hFFFF_0000;   // dominance, negative-domain sample
        exp_cur[14] = 32'hDEAD_BEEF;   // spare
        exp_cur[15] = 32'hCAFE_F00D;   // spare
        for (i = 0; i < 16; i = i + 1)
            logits_in[i*32 +: 32] = exp_cur[i];
        frame_id_in = 8'hA5;
        mode_id_in  = 8'h03;
        epoch_in    = 8'd2;

        wr_ctrl(32'h0000_0001);        // SNAP_CTRL[0]: latch request
        mm = 0;
        for (i = 0; i < 16; i = i + 1) begin
            wr_idx(i);
            rd_val(v);
            if (v !== exp_cur[i]) begin
                mm = mm + 1;
                $display("  S1 slot %0d: got %08h expected %08h",
                         i, v, exp_cur[i]);
            end
        end
        check("S1 all 16 slots read back exactly", mm == 0);
        rd_meta(m);
        check("S1 meta frame_id == 0xA5",  m[7:0]   === 8'hA5);
        check("S1 meta mode_id == 3",      m[15:8]  === 8'h03);
        check("S1 meta epoch == 2",        m[23:16] === 8'd2);
        check("S1 meta valid_count == 16", m[31:24] === 8'd16);
        check("S1 snap_valid high", snap_valid === 1'b1);
        check("S1 snap_epoch == 2",  snap_epoch === 8'd2);
        scene_end(1);

        // ================= S2: atomic latch =================
        scene_base = errors;
        // change HALF of the live bus (slots 0..7), keep 8..15 as-is
        for (i = 0; i < 8; i = i + 1) begin
            exp_cur[i] = 32'h5555_0000 + i * 32'h0010_0000;
            logits_in[i*32 +: 32] = exp_cur[i];
        end
        // before the latch the shadow must still hold the old slot 0
        wr_idx(32'd0);
        rd_val(v);
        check("S2 slot0 still old value before latch", v === 32'hFFFF_FFC7);

        // fire the latch and sample the shadow immediately after the edge
        @(negedge clk);
        ctrl_wdata = 32'h0000_0001;
        ctrl_wen   = 1'b1;
        @(posedge clk);               // latching edge (all slots at once)
        @(negedge clk);               // first sample point after the edge
        ctrl_wen = 1'b0;
        mm = 0;
        for (i = 0; i < 16; i = i + 1)
            if (u_dut.snap_slots[i] !== exp_cur[i]) begin
                mm = mm + 1;
                $display("  S2 slot %0d: shadow %08h expected %08h",
                         i, u_dut.snap_slots[i], exp_cur[i]);
            end
        check("S2 atomic: all 16 shadow slots new in the latch cycle", mm == 0);

        // normal readback path: 0..7 new, 8..15 unchanged bus values
        mm = 0;
        for (i = 0; i < 16; i = i + 1) begin
            wr_idx(i);
            rd_val(v);
            if (v !== exp_cur[i]) mm = mm + 1;
        end
        check("S2 readback: slots 0..7 new, 8..15 bus values", mm == 0);
        scene_end(2);

        // ================= S3: epoch clear =================
        scene_base = errors;
        epoch_in = 8'd9;
        wr_ctrl(32'h0000_0002);        // SNAP_CTRL[1]: mode-switch event
        rd_meta(m);
        check("S3 epoch == epoch_in + 1 == 10", m[23:16] === 8'd10);
        check("S3 valid_count cleared to 0",    m[31:24] === 8'd0);
        check("S3 snap_valid low after clear",  snap_valid === 1'b0);
        check("S3 snap_epoch == 10",            snap_epoch === 8'd10);
        // v0 semantics: valid is cleared, DATA is kept (documented deviation)
        wr_idx(32'd3);
        rd_val(v);
        check("S3 old slot 3 data still readable", v === exp_cur[3]);
        wr_idx(32'd11);
        rd_val(v);
        check("S3 old slot 11 data still readable", v === exp_cur[11]);
        scene_end(3);

        // ================= S4: new snapshot overwrites =================
        scene_base = errors;
        for (i = 0; i < 16; i = i + 1) begin
            exp_cur[i] = 32'h7000_0000 + i * 32'h0101_0101;
            logits_in[i*32 +: 32] = exp_cur[i];
        end
        frame_id_in = 8'h5C;
        mode_id_in  = 8'd1;
        epoch_in    = 8'd10;
        pulse_latch;                   // upstream latch_req trigger path
        mm = 0;
        for (i = 0; i < 16; i = i + 1) begin
            wr_idx(i);
            rd_val(v);
            if (v !== exp_cur[i]) mm = mm + 1;
        end
        check("S4 second latch overwrites all 16 slots", mm == 0);
        rd_meta(m);
        check("S4 meta frame_id == 0x5C", m[7:0]   === 8'h5C);
        check("S4 meta mode_id == 1",     m[15:8]  === 8'd1);
        check("S4 meta epoch == 10",      m[23:16] === 8'd10);
        check("S4 meta valid_count == 16", m[31:24] === 8'd16);
        check("S4 snap_valid high again", snap_valid === 1'b1);
        scene_end(4);

        // ================= S5: group5 / dominance slots =================
        scene_base = errors;
        // slots 8..13 (five-group activity + dominance) get new values
        for (i = 8; i < 14; i = i + 1) begin
            exp_cur[i] = 32'h0003_0000 + (i - 8) * 32'h0002_0000;
            logits_in[i*32 +: 32] = exp_cur[i];
        end
        frame_id_in = 8'hD1;
        epoch_in    = 8'd11;
        wr_ctrl(32'h0000_0001);        // CPU-triggered latch
        mm = 0;
        for (i = 8; i < 14; i = i + 1) begin
            wr_idx(i);
            rd_val(v);
            if (v !== exp_cur[i]) begin
                mm = mm + 1;
                $display("  S5 slot %0d: got %08h expected %08h",
                         i, v, exp_cur[i]);
            end
        end
        check("S5 group5/dominance slots 8..13 latch and read back", mm == 0);
        // untouched slots keep the previous snapshot values
        mm = 0;
        for (i = 0; i < 8; i = i + 1) begin
            wr_idx(i);
            rd_val(v);
            if (v !== exp_cur[i]) mm = mm + 1;
        end
        wr_idx(32'd14);
        rd_val(v);
        if (v !== exp_cur[14]) mm = mm + 1;
        wr_idx(32'd15);
        rd_val(v);
        if (v !== exp_cur[15]) mm = mm + 1;
        check("S5 untouched slots (0..7, 14, 15) unchanged", mm == 0);
        rd_meta(m);
        check("S5 meta frame_id == 0xD1",  m[7:0]   === 8'hD1);
        check("S5 meta epoch == 11",       m[23:16] === 8'd11);
        check("S5 meta valid_count == 16", m[31:24] === 8'd16);
        // LOGIT_IDX only uses bits [4:0]: upper write bits are ignored
        wr_idx(32'hFFFF_FFF9);         // low 5 bits decode to index 9
        rd_val(v);
        check("S5 LOGIT_IDX uses [4:0] only (upper bits ignored)",
              v === exp_cur[9]);
        scene_end(5);

        // -----------------------------------------------------------------
        $display("=== tb_logits_snap done: %0d checks, %0d errors ===",
                 checks, errors);
        if (errors == 0) begin
            $display("TB_LOGITS_SNAP: PASS");
            $display("RESULT: PASS tb_logits_snap");
            $finish;
        end else begin
            $display("TB_LOGITS_SNAP: FAIL");
            $display("RESULT: FAIL tb_logits_snap (%0d errors)", errors);
            $fatal(1, "tb_logits_snap failed");
        end
    end

    initial begin : watchdog
        #(10ms);
        $display("ERROR: tb_logits_snap watchdog (errors=%0d)", errors);
        $fatal(1, "tb_logits_snap timeout");
    end

endmodule
