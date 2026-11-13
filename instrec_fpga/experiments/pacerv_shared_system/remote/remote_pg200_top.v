`timescale 1ns/1ps
// PG200 physical-DDR integration scope. The competing accelerator is a pattern
// traffic generator; it exercises the shared controller without audio wiring.
module remote_pg200_top #(
    parameter PROG_HEX = "remote_prog.hex",
    parameter integer UART_DIV = 1085
) (
    input wire board_clk27, ref_clk_p, ref_clk_n, resetn,
    output wire uart_tx,
    output wire [7:0] led,
    output wire mem_cs_n, mem_rst_n, mem_ck, mem_ck_n, mem_cke,
    output wire mem_ras_n, mem_cas_n, mem_we_n, mem_odt,
    output wire [14:0] mem_a,
    output wire [2:0] mem_ba,
    inout wire [3:0] mem_dqs, mem_dqs_n,
    inout wire [31:0] mem_dq,
    output wire [3:0] mem_dm
);
    wire clk, rst_n, init_done, pll_lock, cpd_lock;
    // Remote programming cannot press KEY0. Assert a real startup reset using
    // the independent board oscillator, then let the IP synchronize release.
    reg [9:0] power_on_count = 10'd0;
    always @(posedge board_clk27 or negedge resetn) begin
        if (!resetn) power_on_count <= 10'd0;
        else if (!(&power_on_count)) power_on_count <= power_on_count + 1'b1;
    end
    wire boot_resetn = resetn && (&power_on_count);
    wire [27:0] awaddr, araddr;
    wire awap, arap, awvalid, arvalid, awready, arready;
    wire [3:0] awid, arid, awlen, arlen, wid, rid;
    wire [255:0] wdata, rdata;
    wire [31:0] wstrb;
    wire wready, wlast, rlast, rvalid;
    ddr3_wrapper ddr3_wrapper (
        .ref_clk_p(ref_clk_p), .ref_clk_n(ref_clk_n), .resetn(boot_resetn),
        .core_clk(clk), .core_clk_rst_n(rst_n), .ddr_init_done(init_done),
        .pll_lock(pll_lock), .ddrphy_cpd_lock(cpd_lock),
        .axi_awaddr(awaddr), .axi_awuser_ap(awap), .axi_awuser_id(awid),
        .axi_awlen(awlen), .axi_awvalid(awvalid), .axi_awready(awready),
        .axi_wdata(wdata), .axi_wstrb(wstrb), .axi_wready(wready),
        .axi_wusero_id(wid), .axi_wusero_last(wlast),
        .axi_araddr(araddr), .axi_aruser_ap(arap), .axi_aruser_id(arid),
        .axi_arlen(arlen), .axi_arvalid(arvalid), .axi_arready(arready),
        .axi_rdata(rdata), .axi_rid(rid), .axi_rlast(rlast), .axi_rvalid(rvalid),
        .mem_cs_n(mem_cs_n), .mem_rst_n(mem_rst_n), .mem_ck(mem_ck),
        .mem_ck_n(mem_ck_n), .mem_cke(mem_cke), .mem_ras_n(mem_ras_n),
        .mem_cas_n(mem_cas_n), .mem_we_n(mem_we_n), .mem_odt(mem_odt),
        .mem_a(mem_a), .mem_ba(mem_ba), .mem_dqs(mem_dqs),
        .mem_dqs_n(mem_dqs_n), .mem_dq(mem_dq), .mem_dm(mem_dm)
    );

    reg boot_started;
    wire boot_start = init_done && !boot_started;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) boot_started <= 0;
        else if (init_done) boot_started <= 1;
    end
    wire boot_done, boot_fail, boot_cmd_valid, boot_rd_ready;
    wire [27:0] boot_fail_addr;
    wire [36:0] boot_cmd;
    wire [255:0] boot_wdata;
    wire [3:0] cwready, crvalid, cdone, cabort;
    wire [255:0] crdata;
    self_test boot_test (
        .clk(clk), .rst_n(rst_n), .st_start(boot_start),
        .cmd_valid(boot_cmd_valid), .cmd(boot_cmd), .wdata(boot_wdata),
        .wready_beat(cwready[0]), .rd_ready(boot_rd_ready),
        .rd_data(crdata), .rd_valid(crvalid[0]), .done(cdone[0]),
        .st_done(boot_done), .st_fail(boot_fail), .st_fail_addr(boot_fail_addr)
    );

    wire accel_start, accel_done, accel_fail, accel_cmd_valid, accel_rd_ready;
    wire [36:0] accel_cmd;
    wire [255:0] accel_wdata;
    wire [27:0] accel_fail_addr;
    wire [3:0] ctrl_wready, ctrl_rvalid, ctrl_done;
    wire [255:0] ctrl_rdata0, ctrl_rdata1, ctrl_rdata2, ctrl_rdata3;
    self_test #(.SELFTEST_BASE(28'h0010000)) competing_master (
        .clk(clk), .rst_n(rst_n), .st_start(accel_start),
        .cmd_valid(accel_cmd_valid), .cmd(accel_cmd), .wdata(accel_wdata),
        .wready_beat(ctrl_wready[0]), .rd_ready(accel_rd_ready),
        .rd_data(ctrl_rdata0), .rd_valid(ctrl_rvalid[0]), .done(ctrl_done[0]),
        .st_done(accel_done), .st_fail(accel_fail), .st_fail_addr(accel_fail_addr)
    );
    reg accel_busy, accel_done_q, accel_fail_q;
    reg [31:0] accel_cycles;
    wire accel_done_event = accel_done && !accel_done_q;
    wire accel_fail_event = accel_fail && !accel_fail_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            accel_busy<=0; accel_cycles<=0; accel_done_q<=0; accel_fail_q<=0;
        end else begin
            accel_done_q<=accel_done; accel_fail_q<=accel_fail;
            if (accel_start) begin accel_busy<=1; accel_cycles<=0; end
            else if (accel_done_event || accel_fail_event) accel_busy<=0;
            else if (accel_busy) accel_cycles<=accel_cycles+1'b1;
        end
    end

    wire dd_valid, dd_ready, dd_write, dr_valid, dr_ready, dr_error;
    wire [31:0] dd_address, dd_data, dr_data;
    wire [3:0] dd_strobe;
    wire cpu_cmd_valid, cpu_rd_ready, bridge_fault;
    wire [36:0] cpu_cmd;
    wire [255:0] cpu_wdata;
    wire [31:0] cpu_wstrb;
    wire share_valid, share_rd_ready, share_fault, share_active;
    wire [1:0] share_owner;
    wire [36:0] share_cmd;
    wire [255:0] share_wdata;
    wire [31:0] share_wstrb;
    wire to_err;
    wire [3:0] addr_err, cmd_to_err;
    wire [2:0] timeout_state;
    wire [7:0] last_misses;
    wire [31:0] wait0, wait1, wait2, wait3;
    wire cpu_uart_valid, cpu_uart_ready, cpu_alive, cpu_trap;
    wire uart_raw_ready;
    reg uart_accept_hold;
    // Match the production UART adapter: registered ready stays high for the
    // first busy edge, so acknowledge exactly one FIFO byte per acceptance.
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) uart_accept_hold<=0;
        else if(!uart_raw_ready) uart_accept_hold<=0;
        else if(cpu_uart_valid && !uart_accept_hold) uart_accept_hold<=1;
    end
    assign cpu_uart_ready=uart_raw_ready && !uart_accept_hold;
    wire [7:0] cpu_uart_data, cpu_led;
    wire [31:0] trap_cause;
    wire [31:0] ddr_status = {boot_fail_addr[15:0],4'd0,addr_err,
        1'b0,cpd_lock,pll_lock,init_done,share_fault,bridge_fault,to_err,boot_fail};
    rv32_cpu_subsys #(.ENABLE_M(1),.ENABLE_C(1),.ENABLE_PREDICTOR(1),
        .PROG_HEX(PROG_HEX)) cpu (
        .clk(clk), .rst_n(rst_n), .npu_busy(accel_busy),
        .npu_done(accel_done_event), .npu_timeout(accel_fail_event),
        .npu_probs_valid(accel_done_event), .npu_probs_pct(8'd100),
        .npu_probs_idx(4'd0), .npu_top1(4'd0), .npu_cycles(accel_cycles),
        .ddr_ok(init_done && boot_done),
        .ddr_err(boot_fail || to_err || (|addr_err) || bridge_fault || share_fault),
        .ddr_sts(ddr_status), .uart_valid(cpu_uart_valid), .uart_data(cpu_uart_data),
        .uart_ready(cpu_uart_ready), .cpu_led(cpu_led), .cpu_alive(cpu_alive),
        .cpu_trap(cpu_trap), .cpu_trap_cause(trap_cause), .npu_soft_start(accel_start),
        .dd_req_valid(dd_valid), .dd_req_ready(dd_ready), .dd_req_address(dd_address),
        .dd_req_write(dd_write), .dd_req_data(dd_data), .dd_req_strobe(dd_strobe),
        .dd_rsp_valid(dr_valid), .dd_rsp_ready(dr_ready),
        .dd_rsp_data(dr_data), .dd_rsp_error(dr_error)
    );
    uart_tx #(.BAUD_DIV(UART_DIV)) uart (
        .clk(clk), .rst_n(rst_n), .byte_wvalid(cpu_uart_valid && !uart_accept_hold),
        .byte_wdata(cpu_uart_data), .byte_wready(uart_raw_ready), .uart_txd(uart_tx)
    );
    assign led = cpu_led | {cpu_trap,boot_fail,to_err,share_fault,bridge_fault,3'b000};
    pace_cpu_ddr_bridge bridge (
        .clk(clk), .rst_n(rst_n), .ddr_ok(init_done && boot_done),
        .req_valid(dd_valid), .req_ready(dd_ready), .req_address(dd_address),
        .req_write(dd_write), .req_data(dd_data), .req_strobe(dd_strobe),
        .rsp_valid(dr_valid), .rsp_ready(dr_ready), .rsp_data(dr_data), .rsp_error(dr_error),
        .m_cmd_valid(cpu_cmd_valid), .m_cmd(cpu_cmd), .m_wdata(cpu_wdata),
        .m_wstrb(cpu_wstrb), .m_rd_ready(cpu_rd_ready), .m_wready(cwready[3]),
        .m_rvalid(crvalid[3]), .m_rdata(crdata), .m_done(cdone[3]),
        .m_abort(cabort[3]), .fault(bridge_fault)
    );
    ddr3_m3_share share (
        .clk(clk), .rst_n(rst_n), .boot_done(boot_done || boot_fail),
        .c_valid({cpu_cmd_valid,2'b00,boot_cmd_valid}),
        .c_cmd({cpu_cmd,74'd0,boot_cmd}),
        .c_wdata({cpu_wdata,512'd0,boot_wdata}),
        .c_wstrb({cpu_wstrb,64'd0,32'hffffffff}),
        .c_rd_ready({cpu_rd_ready,2'b00,boot_rd_ready}),
        .c_wready(cwready), .c_rvalid(crvalid), .c_done(cdone), .c_abort(cabort),
        .c_rdata(crdata), .m_valid(share_valid), .m_cmd(share_cmd),
        .m_wdata(share_wdata), .m_wstrb(share_wstrb), .m_rd_ready(share_rd_ready),
        .m_wready(ctrl_wready[3]), .m_rvalid(ctrl_rvalid[3]), .m_rdata(ctrl_rdata3),
        .m_done(ctrl_done[3]), .m_abort(cmd_to_err[3]),
        .fault(share_fault), .owner(share_owner), .active(share_active)
    );
    ddr3_ctrl_axi #(.M3_MASK_ENABLE(1'b1), .AXI_USER_AP(1'b0)) controller (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid({share_valid,2'b00,accel_cmd_valid}),
        .m0_cmd(accel_cmd), .m1_cmd(37'd0), .m2_cmd(37'd0), .m3_cmd(share_cmd),
        .m0_wdata(accel_wdata), .m1_wdata(256'd0), .m2_wdata(256'd0),
        .m3_wdata(share_wdata), .m3_wstrb(share_wstrb), .wready_beat(ctrl_wready),
        .rd_ready({share_rd_ready,2'b00,accel_rd_ready}),
        .rd_data_0(ctrl_rdata0), .rd_data_1(ctrl_rdata1),
        .rd_data_2(ctrl_rdata2), .rd_data_3(ctrl_rdata3),
        .rd_valid(ctrl_rvalid), .done(ctrl_done),
        .wait_cnt_0(wait0), .wait_cnt_1(wait1), .wait_cnt_2(wait2), .wait_cnt_3(wait3),
        .addr_err(addr_err), .to_err(to_err), .cmd_to_err(cmd_to_err),
        .dbg_to_state(timeout_state), .wlast_miss_cnt(last_misses),
        .axi_awaddr(awaddr), .axi_awuser_ap(awap), .axi_awuser_id(awid),
        .axi_awlen(awlen), .axi_awvalid(awvalid), .axi_awready(awready),
        .axi_wdata(wdata), .axi_wstrb(wstrb), .axi_wready(wready),
        .axi_wusero_id(wid), .axi_wusero_last(wlast),
        .axi_araddr(araddr), .axi_aruser_ap(arap), .axi_aruser_id(arid),
        .axi_arlen(arlen), .axi_arvalid(arvalid), .axi_arready(arready),
        .axi_rdata(rdata), .axi_rid(rid), .axi_rlast(rlast), .axi_rvalid(rvalid)
    );
endmodule
