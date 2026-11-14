`timescale 1ns/1ps
// ddr3_m3_share: clients are 0 boot, 1 diagnostic, 2 feature export, 3 CPU.
// Boot owns the port until boot_done. Afterwards transactions are round-robin.
// Each command valid must return low before that client can issue again.
module ddr3_m3_share (
    input wire clk, rst_n, boot_done,
    input wire [3:0] c_valid,
    input wire [147:0] c_cmd,
    input wire [1023:0] c_wdata,
    input wire [127:0] c_wstrb,
    input wire [3:0] c_rd_ready,
    output wire [3:0] c_wready, c_rvalid, c_done, c_abort,
    output wire [255:0] c_rdata,
    output wire m_valid,
    output wire [36:0] m_cmd,
    output wire [255:0] m_wdata,
    output wire [31:0] m_wstrb,
    output wire m_rd_ready,
    input wire m_wready, m_rvalid,
    input wire [255:0] m_rdata,
    input wire m_done, m_abort,
    output reg fault,
    output reg [1:0] owner,
    output reg active
);
    reg [36:0] cmd_q;
    reg done_seen;
    reg [4:0] reads_left;
    reg [3:0] armed;
    reg [1:0] next_owner;
    reg choose_valid;
    reg [1:0] chosen;
    integer offset;
    reg [1:0] candidate;
    wire delivered = m_rvalid && m_rd_ready;
    wire finished = active && done_seen && reads_left==0;
    wire [3:0] owner_bit = 4'b0001 << owner;
    always @* begin
        choose_valid=0; chosen=0; candidate=0;
        if(!boot_done) begin
            choose_valid=c_valid[0] && armed[0]; chosen=0;
        end else begin
            for(offset=0;offset<4;offset=offset+1) begin
                candidate=next_owner+offset;
                if(!choose_valid && c_valid[candidate] && armed[candidate]) begin
                    choose_valid=1; chosen=candidate;
                end
            end
        end
    end
    assign m_valid = active && !done_seen && !fault && !m_abort;
    assign m_cmd = cmd_q;
    assign m_wdata = c_wdata[owner*256 +: 256];
    assign m_wstrb = c_wstrb[owner*32 +: 32];
    assign m_rd_ready = active && (fault || m_abort || c_rd_ready[owner]);
    assign c_wready = active && !fault && !m_abort && m_wready ? owner_bit : 4'd0;
    assign c_rvalid = active && !fault && !m_abort && m_rvalid ? owner_bit : 4'd0;
    assign c_rdata = m_rdata;
    // Preserve the legacy raw command-completion edge (in particular, final
    // write-ready and done coincide). Ownership and read routing remain locked
    // independently until finished, after every queued read beat is consumed.
    // CPU bridge separately joins raw done with its captured data/error state.
    assign c_done = active && !fault && (m_done || m_abort) ? owner_bit : 4'd0;
    assign c_abort = fault ? 4'hf : (active && m_abort ? owner_bit : 4'd0);
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            active<=0; owner<=0; cmd_q<=0; done_seen<=0; reads_left<=0;
            armed<=4'hf; next_owner<=1; fault<=0;
        end else begin
            // A held valid belongs to the just-completed command. It cannot
            // be regranted even if a client consumes done a cycle later.
            armed<=armed | ~c_valid;
            if(!active && !fault) begin
                if(choose_valid) begin
                    active<=1; owner<=chosen; cmd_q<=c_cmd[chosen*37 +: 37];
                    armed[chosen]<=0; done_seen<=0;
                    reads_left<=c_cmd[chosen*37+36] ? 0 :
                        {1'b0,c_cmd[chosen*37 +: 4]}+1;
                    if(c_cmd[chosen*37 +: 8]>15) fault<=1;
                end
            end else if(active) begin
                if(m_done) done_seen<=1;
                if(delivered && reads_left!=0) reads_left<=reads_left-1;
                if(m_abort) begin fault<=1; active<=0; end
                else if(finished && !fault) begin
                    active<=0; next_owner<=owner+1;
                end
            end
        end
    end
endmodule
