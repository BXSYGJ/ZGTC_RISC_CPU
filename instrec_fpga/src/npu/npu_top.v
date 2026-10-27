// ---------------------------------------------------------------------------
// npu_top.v -- NPU layer sequencer skeleton (T-M2-06)
//
// Layer order (design.md 4.6):
//   conv1 -> pool1 -> conv2 -> pool2 -> conv3 -> pool3 -> conv4 -> pool4
//   -> gap -> fc1 -> fc2 -> done
//
// This file currently provides the control shell only: the layer sequence,
// busy/done handshake, npu_cycles counter and the REQ-REL-002 timeout flag.
// The datapath modules (conv_engine / pool_engine / gap_unit / fc_engine)
// and wdma are instantiated in the next integration step; the per-layer
// start/done wires below are the attachment points.
//
// Budget: 200 ms at 125 MHz = 25,000,000 cycles. timeout_flag latches when
// the measured npu_cycles exceeds 2x that (50,000,000), per REQ-REL-002.
// ---------------------------------------------------------------------------

module npu_top (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        start,          // pulse from sys_ctrl (weights loaded)
    output reg         busy,
    output reg         done,           // pulse after fc2
    output reg  [31:0] npu_cycles,
    output reg         timeout_flag,   // sticky, cleared by reset

    output reg  [3:0]  layer_id,       // current layer index (0..10)
    output reg         layer_start,    // pulse: datapath layer begin
    input  wire        layer_done      // pulse: datapath layer finished
);

    localparam [3:0] L_CONV1 = 4'd0;
    localparam [3:0] L_POOL1 = 4'd1;
    localparam [3:0] L_CONV2 = 4'd2;
    localparam [3:0] L_POOL2 = 4'd3;
    localparam [3:0] L_CONV3 = 4'd4;
    localparam [3:0] L_POOL3 = 4'd5;
    localparam [3:0] L_CONV4 = 4'd6;
    localparam [3:0] L_POOL4 = 4'd7;
    localparam [3:0] L_GAP   = 4'd8;
    localparam [3:0] L_FC1   = 4'd9;
    localparam [3:0] L_FC2   = 4'd10;
    localparam [3:0] L_DONE  = 4'd11;

    localparam [31:0] TIMEOUT_CYCLES = 32'd50_000_000;  // 2 x 200 ms @125 MHz

    reg [3:0] state;
    reg [1:0] wait_cnt;   // small settle delay between layers

    wire last_layer = (layer_id == L_FC2);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= L_CONV1;
            busy         <= 1'b0;
            done         <= 1'b0;
            npu_cycles   <= 32'd0;
            timeout_flag <= 1'b0;
            layer_id     <= L_CONV1;
            layer_start  <= 1'b0;
            wait_cnt     <= 2'd0;
        end else begin
            layer_start <= 1'b0;
            done        <= 1'b0;

            if (timeout_flag == 1'b0 && npu_cycles >= TIMEOUT_CYCLES)
                timeout_flag <= 1'b1;

            if (!busy) begin
                if (start) begin
                    busy       <= 1'b1;
                    state      <= L_CONV1;
                    layer_id   <= L_CONV1;
                    npu_cycles <= 32'd0;
                    layer_start<= 1'b1;
                    wait_cnt   <= 2'd0;
                end
            end else begin
                npu_cycles <= npu_cycles + 32'd1;

                if (wait_cnt != 2'd0) begin
                    wait_cnt <= wait_cnt - 2'd1;
                    if (wait_cnt == 2'd1) begin
                        layer_start <= 1'b1;
                    end
                end else if (layer_done) begin
                    if (last_layer) begin
                        busy  <= 1'b0;
                        done  <= 1'b1;
                        state <= L_DONE;
                    end else begin
                        layer_id <= layer_id + 4'd1;
                        state    <= layer_id + 4'd1;
                        wait_cnt <= 2'd1;   // one idle beat, then pulse start
                    end
                end
            end
        end
    end

endmodule