`timescale 1ns/1ps
// pace_cpu_ddr_bridge: single-outstanding CPU word bus to the shared DDR bus.
// Byte/halfword stores arrive as word-aligned data with four byte strobes.
// CPU APP: 40000000..400fffff -> DDR 00600000..006fffff (read/write).
// CPU OBS: 41000000..415fffff -> DDR 00000000..005fffff (legal reads only).
module pace_cpu_ddr_bridge #(
    parameter integer REQ_TIMEOUT = 1048576
) (
    input wire clk, rst_n, ddr_ok,
    input wire req_valid,
    output wire req_ready,
    input wire [31:0] req_address,
    input wire req_write,
    input wire [31:0] req_data,
    input wire [3:0] req_strobe,
    output wire rsp_valid,
    input wire rsp_ready,
    output wire [31:0] rsp_data,
    output wire rsp_error,
    output wire m_cmd_valid,
    output wire [36:0] m_cmd,
    output wire [255:0] m_wdata,
    output wire [31:0] m_wstrb,
    output wire m_rd_ready,
    input wire m_wready, m_rvalid,
    input wire [255:0] m_rdata,
    input wire m_done, m_abort,
    output reg fault
);
    localparam [1:0] IDLE=0, WAIT_DDR=1, RESPONSE=2;
    reg [1:0] state;
    reg [27:0] address_q;
    reg write_q;
    reg [31:0] data_q;
    reg [3:0] strobe_q;
    reg [2:0] word_q;
    reg done_seen, read_seen, write_seen;
    reg [31:0] read_q, wait_count;
    reg response_error;
    wire app_region = req_address >= 32'h40000000 && req_address <= 32'h400ffffc;
    wire obs_region = req_address >= 32'h41000000 && req_address <= 32'h415ffffc;
    wire [27:0] obs_address = {4'b0000,req_address[23:0]};
    wire obs_legal = (obs_address <= 28'h00c5ffc) ||
        (obs_address >= 28'h0100000 && obs_address <= 28'h01b7ffc) ||
        (obs_address >= 28'h0200000 && obs_address <= 28'h020fffc) ||
        (obs_address >= 28'h0300000 && obs_address <= 28'h030fffc) ||
        (obs_address >= 28'h0400000 && obs_address <= 28'h043fffc) ||
        (obs_address >= 28'h0440000 && obs_address <= 28'h045fffc);
    wire legal_request = req_address[1:0]==2'b00 &&
        (app_region || (obs_region && !req_write && obs_legal));
    wire [27:0] translated = app_region ? (28'h0600000 + {8'd0,req_address[19:0]}) : obs_address;
    wire complete = done_seen && (write_q ? write_seen : read_seen);
    wire local_timeout = REQ_TIMEOUT != 0 && wait_count >= REQ_TIMEOUT-1;
    assign req_ready = state==IDLE && ddr_ok;
    assign rsp_valid = state==RESPONSE;
    assign rsp_data = read_q;
    assign rsp_error = response_error;
    assign m_cmd_valid = state==WAIT_DDR && !done_seen && !fault;
    assign m_cmd = {write_q,address_q,8'd0};
    assign m_wdata = {{224{1'b0}},data_q} << {word_q,5'b0};
    assign m_wstrb = {28'd0,strobe_q} << {word_q,2'b0};
    // A local timeout answers the CPU and poisons future CPU operations.
    // The M3 owner retains any already captured command and drains its tail;
    // data_q/strobe_q are never overwritten while fault is latched.
    assign m_rd_ready = (state==WAIT_DDR && !read_seen) || fault;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE; address_q<=0; write_q<=0; data_q<=0; strobe_q<=0;
            word_q<=0; done_seen<=0; read_seen<=0; write_seen<=0;
            read_q<=0; wait_count<=0; response_error<=0; fault<=0;
        end else begin
            case(state)
                IDLE: if(req_valid && req_ready) begin
                    response_error<=0; read_q<=0;
                    if(!legal_request || fault || m_abort) begin
                        response_error<=1; state<=RESPONSE;
                        if(m_abort) fault<=1;
                    end else begin
                        address_q<={translated[27:5],5'd0};
                        word_q<=req_address[4:2]; write_q<=req_write;
                        data_q<=req_data; strobe_q<=req_strobe;
                        done_seen<=0; read_seen<=0; write_seen<=0;
                        wait_count<=0; state<=WAIT_DDR;
                    end
                end
                WAIT_DDR: begin
                    wait_count<=wait_count+1;
                    if(m_done) done_seen<=1;
                    if(m_wready) write_seen<=1;
                    if(m_rvalid && m_rd_ready) begin
                        read_q<=m_rdata >> {word_q,5'b0}; read_seen<=1;
                    end
                    // Error is inspected after the registered done edge too:
                    // the controller's timeout flags become visible after done.
                    if(m_abort || local_timeout) begin
                        response_error<=1; fault<=1; state<=RESPONSE;
                    end else if(complete) state<=RESPONSE;
                end
                RESPONSE: if(rsp_ready) state<=IDLE;
                default: state<=IDLE;
            endcase
        end
    end
endmodule
