`timescale 1ns/1ps
module tb_pacerv_local_timeout;
 reg clk=0,rst_n=0,request=0,response_ready=0,diag_valid=0;
 always #5 clk=~clk;
 wire request_ready,response_valid,response_error,cpu_fault,cpu_valid,cpu_read_ready;
 wire [31:0] response_data,cpu_mask;
 wire [36:0] cpu_cmd;
 wire [255:0] cpu_data;
 wire [3:0] c_wr,c_rv,c_done,c_abort;
 wire [255:0] c_data;
 wire m_valid,m_ready,active,share_fault;
 wire [36:0] m_cmd;
 wire [255:0] m_data;
 wire [31:0] m_mask;
 wire [1:0] owner;
 reg m_done=0,m_rvalid=0,running=0;
 integer age=0,received=0,diag_done=0,checks=0,grants=0;
 pace_cpu_ddr_bridge #(.REQ_TIMEOUT(12)) cpu(
  .clk(clk),.rst_n(rst_n),.ddr_ok(1'b1),.req_valid(request),.req_ready(request_ready),
  .req_address(32'h40000000),.req_write(1'b0),.req_data(32'd0),.req_strobe(4'd0),
  .rsp_valid(response_valid),.rsp_ready(response_ready),.rsp_data(response_data),.rsp_error(response_error),
  .m_cmd_valid(cpu_valid),.m_cmd(cpu_cmd),.m_wdata(cpu_data),.m_wstrb(cpu_mask),.m_rd_ready(cpu_read_ready),
  .m_wready(c_wr[3]),.m_rvalid(c_rv[3]),.m_rdata(c_data),.m_done(c_done[3]),.m_abort(c_abort[3]),.fault(cpu_fault));
 ddr3_m3_share share(
  .clk(clk),.rst_n(rst_n),.boot_done(1'b1),.c_valid({cpu_valid,1'b0,diag_valid,1'b0}),
  .c_cmd({cpu_cmd,37'd0,{1'b0,28'h0300000,8'd0},37'd0}),
  .c_wdata({cpu_data,768'd0}),.c_wstrb({cpu_mask,96'hffffffffffffffffffffffff}),
  .c_rd_ready({cpu_read_ready,1'b0,1'b1,1'b0}),.c_wready(c_wr),.c_rvalid(c_rv),
  .c_done(c_done),.c_abort(c_abort),.c_rdata(c_data),
  .m_valid(m_valid),.m_cmd(m_cmd),.m_wdata(m_data),.m_wstrb(m_mask),.m_rd_ready(m_ready),
  .m_wready(1'b0),.m_rvalid(m_rvalid),.m_rdata({8{32'h12345678}}),.m_done(m_done),.m_abort(1'b0),
  .fault(share_fault),.owner(owner),.active(active));
 task automatic check(input bit good,input string label);
  begin if(!good)$fatal(1,"%s",label);checks=checks+1;end
 endtask
 always @(negedge clk) begin
  if(!rst_n)begin age=0;m_done=0;m_rvalid=0;running=0;end
  else begin
   m_done=0;
   if(!running && m_valid)begin running=1;age=0;grants=grants+1;end
   else if(running)begin
    age=age+1;
    if(age==40)m_done=1;
    m_rvalid=age>=42 && received<grants;
    if(!active && age>42)begin running=0;m_rvalid=0;end
   end
  end
 end
 always @(posedge clk)if(rst_n)begin
  if(m_rvalid && m_ready)received=received+1;
  if(c_done[1])diag_done=diag_done+1;
 end
 initial begin
  repeat(4)@(negedge clk);rst_n=1;request=1;
  do @(posedge clk);while(!request_ready);
  @(negedge clk);request=0;
  wait(response_valid);@(negedge clk);
  check(response_error && cpu_fault,"local deadline returns CPU error");
  check(active && owner==3 && !share_fault,"timed-out CPU retains outstanding physical owner");
  response_ready=1;@(negedge clk);response_ready=0;diag_valid=1;
  wait(diag_done==1);@(negedge clk);diag_valid=0;
  wait(received==2 && !active);
  repeat(5)@(negedge clk);
  check(received==2 && grants==2,"late CPU result drained before diagnostic result");
  check(!active && !share_fault && cpu_fault,"diagnostic service survives CPU-only timeout");
  request=1;do @(posedge clk);while(!request_ready);@(negedge clk);request=0;
  wait(response_valid);check(response_error,"later CPU access returns sticky error");
  check(grants==2,"faulted CPU issues no new physical command");
  $display("PACERV_LOCAL_TIMEOUT PASS checks=%0d late_cpu_drain=1 subsequent_diag=1",checks);$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
