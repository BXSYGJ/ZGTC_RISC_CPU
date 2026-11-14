// -----------------------------------------------------------------------------
// logits_snap - full logits snapshot registers behind MMIO window
//               0x8000_0030..0x8000_003C (INTERFACE_CONTRACTS_V0_20261104
//               section 3, "MMIO extension v0" draft; first RTL cut)
// -----------------------------------------------------------------------------
// Problem being fixed: the CPU used to read only the last probability event
// plus top1, which violates the master-plan requirement of a complete
// logits snapshot. This module latches the WHOLE result vector at once and
// exposes it through an indexed MMIO read port.
//
// Register map (decoded externally by rv32_cpu_subsys, strobes wired here):
//   0x8000_0030 W  LOGIT_IDX  idx_wen / idx_wdata[4:0]
//                 0..7 eight-class logits, 8..12 five-group activity,
//                 13 dominance, 14/15 spare
//   0x8000_0034 R  LOGIT_VAL  idx_q (combinational read of the shadow slot
//                 selected by the latched read pointer)
//   0x8000_0038 R  SNAP_META  meta_q = {valid_count, epoch, mode, frame}
//   0x8000_003C W  SNAP_CTRL  ctrl_wen / ctrl_wdata
//                 bit0: latch request (snapshot the live input bus)
//                 bit1: epoch clear / mode-switch event
//
// Input side (v0 choice: PARALLEL bus, see header of the port list):
//   logits_in carries SLOT_COUNT x 32-bit slots on one flat wire. Slot i
//   occupies logits_in[i*32 +: 32]. Slots 0..7 hold the eight-class int32
//   logits (native range), 8..12 the five-group activity (Q16 fixed-point
//   domain), 13 dominance, 14/15 spare. A serial 32b+idx variant was
//   rejected for v0 because the NPU result registers already exist as a
//   parallel vector, so a parallel latch is one cycle, wire-only, and
//   cannot interleave with a moving upstream state.
//
// Latch mechanism (one sentence): a latch fire (upstream latch_req pulse
// OR a CPU write of SNAP_CTRL[0]) copies ALL SLOT_COUNT shadow registers,
// the frame/mode/epoch tags and the valid count in the SAME clock edge
// from a single always block, so a snapshot is never half-new half-old.
//
// epoch semantics (v0, contract section 3):
//   * a successful latch stores epoch_in and sets valid_count = SLOT_COUNT
//     (snap_valid rises);
//   * a SNAP_CTRL[1] write is the mode-switch event: it stores epoch_in + 1
//     (modulo 256, the field is 8 bits) and clears valid_count to 0, so
//     snap_valid falls until the next latch of the new mode.
//   * KNOWN DEVIATION from the contract wording "clear old results after a
//     mode switch": v0 clears the VALID COUNT only and keeps the old slot
//     DATA readable (CPU may still inspect the previous snapshot; stale
//     data is fenced by snap_valid/valid_count == 0). Clearing the data
//     would make post-switch diagnosis impossible and buys nothing - the
//     reader already must check SNAP_META. TB scene S3 asserts the
//     keep-data behaviour explicitly.
//   * if SNAP_CTRL[1] and a latch request hit the same cycle (e.g. a write
//     of 0x3), the epoch clear WINS and the latch is dropped: a snapshot
//     taken in the cycle the mode switches is mode-ambiguous by
//     definition.
//
// Outputs for the rv32 integration (this module is plain MMIO plumbing):
//   idx_wen/idx_wdata and ctrl_wen/ctrl_wdata come from the address
//   decoder; idx_q and meta_q are combinational and go straight into the
//   mmio_rdata mux; snap_valid/snap_epoch report snapshot freshness.
//
// Coding: SV-2005 subset (no always_ff/always_comb/logic), registers in
// one always @(posedge clk or negedge rst_n) block, combinational outputs
// are plain assigns, pure ASCII comments, module name = file name.
// -----------------------------------------------------------------------------
module logits_snap #(
    // Number of shadow slots (address + width are derived from it).
    parameter [7:0] SLOT_COUNT = 8'd16
) (
    input  wire                 clk,           // core clock domain
    input  wire                 rst_n,         // async active-low reset
    // ---- live NPU-domain result bus (parallel, SLOT_COUNT x 32b) ----
    input  wire [SLOT_COUNT*32-1:0] logits_in, // slot i = logits_in[i*32 +: 32]
    input  wire [7:0]           frame_id_in,   // frame tag of the live vector
    input  wire [7:0]           mode_id_in,    // mode tag (0=eight-class, 1=group5)
    input  wire [7:0]           epoch_in,      // epoch announced upstream
    input  wire                 latch_req,     // one-cycle latch pulse (NPU done)
    // ---- MMIO write port (external decode, one-cycle strobes) ----
    input  wire                 idx_wen,       // LOGIT_IDX write strobe
    input  wire [31:0]          idx_wdata,     // LOGIT_IDX write data ([4:0] used)
    input  wire                 ctrl_wen,      // SNAP_CTRL write strobe
    input  wire [31:0]          ctrl_wdata,    // SNAP_CTRL write data ([1:0] used)
    // ---- MMIO read side + status ----
    output wire [31:0]          idx_q,         // LOGIT_VAL: shadow slot value
    output wire [31:0]          meta_q,        // SNAP_META: {valid,epoch,mode,frame}
    output wire                 snap_valid,    // 1 when valid_count != 0
    output wire [7:0]           snap_epoch     // current snapshot epoch
);

    // ------------------------------------------------------------------
    // Shadow registers (the snapshot)
    // ------------------------------------------------------------------
    reg [31:0]        snap_slots [0:SLOT_COUNT-1]; // latched result vector
    reg [7:0]         snap_frame;                  // latched frame_id tag
    reg [7:0]         snap_mode;                   // latched mode_id tag
    reg [7:0]         snap_epoch_r;                // latched epoch tag
    reg [7:0]         valid_count;                 // slots valid in snapshot
    reg [4:0]         rd_idx;                      // latched LOGIT_IDX pointer

    integer           i;                           // reset/latch loop variable

    // ------------------------------------------------------------------
    // Control decode (combinational)
    // ------------------------------------------------------------------
    wire latch_fire;   // snapshot request: upstream pulse or SNAP_CTRL[0]
    wire epoch_clr;    // mode-switch event: SNAP_CTRL[1]

    assign latch_fire = latch_req  | (ctrl_wen && ctrl_wdata[0]);
    assign epoch_clr  = ctrl_wen   && ctrl_wdata[1];

    // ------------------------------------------------------------------
    // Snapshot state (single always block -> same-edge atomic update)
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_idx       <= 5'd0;
            snap_frame   <= 8'd0;
            snap_mode    <= 8'd0;
            snap_epoch_r <= 8'd0;
            valid_count  <= 8'd0;
            for (i = 0; i < SLOT_COUNT; i = i + 1)
                snap_slots[i] <= 32'd0;
        end else begin
            // LOGIT_IDX: latch the read pointer (bits [4:0] only, the
            // remaining write bits are reserved and ignored).
            if (idx_wen)
                rd_idx <= idx_wdata[4:0];

            // Mode switch wins over a same-cycle latch request.
            if (epoch_clr) begin
                snap_epoch_r <= epoch_in + 8'd1;  // 8-bit wrap is intended
                valid_count  <= 8'd0;              // data kept (v0 deviation)
            end else if (latch_fire) begin
                for (i = 0; i < SLOT_COUNT; i = i + 1)
                    snap_slots[i] <= logits_in[i*32 +: 32];
                snap_frame   <= frame_id_in;
                snap_mode    <= mode_id_in;
                snap_epoch_r <= epoch_in;
                valid_count  <= SLOT_COUNT;
            end
        end
    end

    // ------------------------------------------------------------------
    // Read side (combinational)
    // ------------------------------------------------------------------
    assign idx_q      = snap_slots[rd_idx];
    assign meta_q     = {valid_count, snap_epoch_r, snap_mode, snap_frame};
    assign snap_valid = (valid_count != 8'd0);
    assign snap_epoch = snap_epoch_r;

endmodule
