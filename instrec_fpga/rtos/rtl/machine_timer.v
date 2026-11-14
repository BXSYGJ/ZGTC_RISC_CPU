// Free-running 64-bit machine timer in the 125 MHz core clock domain.
// Register words: 0=mtime low, 1=mtime high, 2=mtimecmp low, 3=mtimecmp high.
// write_valid is a one-cycle pulse from an accepted CPU data transaction.
// All registers support byte writes. mtime runs on edges without a nonzero
// strobe time write; a direct time write replaces the selected bytes and
// holds the remaining time bytes for that edge. mtimecmp resets to all ones.
`timescale 1ns/1ps
module machine_timer (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        write_valid,
    input  wire [1:0]  word_address,
    input  wire [31:0] write_data,
    input  wire [3:0]  write_strobe,
    output reg  [31:0] read_data,
    output wire [63:0] timer_value,
    output wire        timer_irq
);
    reg [63:0] mtime;
    reg [63:0] mtimecmp;
    wire write_time = write_valid && !word_address[1] && |write_strobe;
    wire write_compare = write_valid && word_address[1] && |write_strobe;

    function [31:0] merge_bytes;
        input [31:0] previous;
        input [31:0] incoming;
        input [3:0] strobes;
        integer lane;
        begin
            merge_bytes = previous;
            for (lane=0; lane<4; lane=lane+1) begin
                if (strobes[lane])
                    merge_bytes[lane*8 +: 8] = incoming[lane*8 +: 8];
            end
        end
    endfunction

    assign timer_value = mtime;
    assign timer_irq = (mtime >= mtimecmp);

    always @* begin
        case (word_address)
            2'd0: read_data = mtime[31:0];
            2'd1: read_data = mtime[63:32];
            2'd2: read_data = mtimecmp[31:0];
            2'd3: read_data = mtimecmp[63:32];
            default: read_data = 32'd0;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mtime <= 64'd0;
            mtimecmp <= 64'hffff_ffff_ffff_ffff;
        end else begin
            if (write_time) begin
                if (word_address[0])
                    mtime[63:32] <= merge_bytes(mtime[63:32], write_data, write_strobe);
                else
                    mtime[31:0] <= merge_bytes(mtime[31:0], write_data, write_strobe);
            end else begin
                mtime <= mtime + 64'd1;
            end
            if (write_compare) begin
                if (word_address[0])
                    mtimecmp[63:32] <= merge_bytes(mtimecmp[63:32], write_data, write_strobe);
                else
                    mtimecmp[31:0] <= merge_bytes(mtimecmp[31:0], write_data, write_strobe);
            end
        end
    end
endmodule
