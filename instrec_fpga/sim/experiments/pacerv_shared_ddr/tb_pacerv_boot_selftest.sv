`timescale 1ns/1ps
module tb_pacerv_boot_selftest;
 reg clk=0,rst_n=0,start=0,diag=0,cpu=0;
 always #5 clk=~clk;
 wire st_valid,st_ready,st_done,st_fail;
 wire [36:0] st_cmd;
 wire [255:0] st_data;
 wire [27:0] fail_address;
 wire [3:0] cw,cr,cd,ca,dw,dr,dd,addr_error,timeout_error;
 wire [255:0] data,ddr_data;
 wire mv,mready,fault,active;
 wire [1:0] owner;
 wire [36:0] command;
 wire [255:0] write_data;
 wire [31:0] mask;
 wire [27:0] awaddr,araddr;
 wire [3:0] awlen,arlen,awid,arid,rid,wid;
 wire awvalid,arvalid,awready,arready,wready,rvalid,rlast,wlast;
 wire [255:0] wdata,rdata;
 wire [31:0] wstrb;
 integer boot_writes=0,boot_reads=0,diag_reads=0,cpu_reads=0;
 self_test boot(.clk(clk),.rst_n(rst_n),.st_start(start),.cmd_valid(st_valid),.cmd(st_cmd),
  .wdata(st_data),.wready_beat(cw[0]),.rd_ready(st_ready),.rd_data(data),.rd_valid(cr[0]),
  .done(cd[0]),.st_done(st_done),.st_fail(st_fail),.st_fail_addr(fail_address));
 ddr3_m3_share share(.clk(clk),.rst_n(rst_n),.boot_done(st_done&&!st_fail),
  .c_valid({cpu,1'b0,diag,st_valid}),
  .c_cmd({{1'b0,28'h0600000,8'd0},37'd0,{1'b0,28'h0300000,8'd7},st_cmd}),
  .c_wdata({768'd0,st_data}),.c_wstrb(128'hffffffffffffffffffffffffffffffff),
  .c_rd_ready({1'b1,1'b0,1'b1,st_ready}),.c_wready(cw),.c_rvalid(cr),.c_done(cd),.c_abort(ca),.c_rdata(data),
  .m_valid(mv),.m_cmd(command),.m_wdata(write_data),.m_wstrb(mask),.m_rd_ready(mready),
  .m_wready(dw[3]),.m_rvalid(dr[3]),.m_rdata(ddr_data),.m_done(dd[3]),
  .m_abort(timeout_error[3]|addr_error[3]),.fault(fault),.owner(owner),.active(active));
 ddr3_ctrl_axi #(.M3_MASK_ENABLE(1)) ctrl(.clk(clk),.rst_n(rst_n),.cmd_valid({mv,3'd0}),
  .m0_cmd(37'd0),.m1_cmd(37'd0),.m2_cmd(37'd0),.m3_cmd(command),
  .m0_wdata(256'd0),.m1_wdata(256'd0),.m2_wdata(256'd0),.m3_wdata(write_data),.m3_wstrb(mask),
  .wready_beat(dw),.rd_ready({mready,3'd0}),.rd_data_3(ddr_data),.rd_valid(dr),.done(dd),
  .addr_err(addr_error),.cmd_to_err(timeout_error),
  .axi_awaddr(awaddr),.axi_awuser_id(awid),.axi_awlen(awlen),.axi_awvalid(awvalid),.axi_awready(awready),
  .axi_wdata(wdata),.axi_wstrb(wstrb),.axi_wready(wready),.axi_wusero_id(wid),.axi_wusero_last(wlast),
  .axi_araddr(araddr),.axi_aruser_id(arid),.axi_arlen(arlen),.axi_arvalid(arvalid),.axi_arready(arready),
  .axi_rdata(rdata),.axi_rid(rid),.axi_rlast(rlast),.axi_rvalid(rvalid));
 ddr3_axi_model memory(.clk(clk),.rst_n(rst_n),.s_awaddr(awaddr),.s_awvalid(awvalid),.s_awlen(awlen),
  .s_awuser_id(awid),.s_awready(awready),.s_wdata(wdata),.s_wstrb(wstrb),.s_wready(wready),
  .s_wusero_last(wlast),.s_araddr(araddr),.s_arvalid(arvalid),.s_arlen(arlen),.s_aruser_id(arid),
  .s_arready(arready),.s_rdata(rdata),.s_rid(rid),.s_rlast(rlast),.s_rvalid(rvalid));
 // The model has no write-ID output; this test uses physical master 3.
 assign wid=4'd3;
 always @(posedge clk)if(rst_n)begin
  if(cw[0])boot_writes=boot_writes+1;
  if(cr[0]&&st_ready)boot_reads=boot_reads+1;
  if(cr[1])diag_reads=diag_reads+1;
  if(cr[3])cpu_reads=cpu_reads+1;
  if(st_fail)$fatal(1,"real boot self-test failed address=%h",fail_address);
 end
 initial begin
  repeat(5)@(negedge clk);rst_n=1;start=1;
  @(negedge clk);start=0;cpu=1;diag=1;
  wait(st_done);@(negedge clk);
  if(boot_writes!=128||boot_reads!=128)$fatal(1,"4KiB boot read/write count");
  wait(cpu_reads==1&&diag_reads==8);@(negedge clk);cpu=0;diag=0;
  repeat(8)@(negedge clk);
  if(fault||addr_error||timeout_error||active)$fatal(1,"post-boot arbitration status");
  $display("PACERV_BOOT_SELFTEST PASS boot_bytes=4096 write_beats=%0d read_beats=%0d diag_beats=%0d cpu_beats=%0d",boot_writes,boot_reads,diag_reads,cpu_reads);$finish;
 end
 initial begin #2000000;$fatal(1,"boot test timeout");end
endmodule
