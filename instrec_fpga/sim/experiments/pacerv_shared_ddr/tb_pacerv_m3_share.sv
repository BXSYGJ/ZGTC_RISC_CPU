`timescale 1ns/1ps
module tb_pacerv_m3_share;
 reg clk=0,rst_n=0,boot_done=0;
 always #5 clk=~clk;
 reg [3:0] c_valid=0,c_ready=0;
 reg [147:0] c_cmd=0;
 wire [3:0] c_wr,c_rv,c_done,c_abort;
 wire [255:0] c_data;
 wire valid,ready,active,fault;
 wire [1:0] owner;
 wire [36:0] cmd;
 wire [255:0] wdata;
 wire [31:0] mask;
 reg running=0,done=0,abort_now=0,rvalid=0;
 integer age=0,left=0,grants=0,completed=0,checks=0,i;
 reg [3:0] served=0;
 reg [31:0] rng=32'hcafe1234;
 ddr3_m3_share dut(
  .clk(clk),.rst_n(rst_n),.boot_done(boot_done),.c_valid(c_valid),.c_cmd(c_cmd),
  .c_wdata(1024'd0),.c_wstrb(128'hffffffffffffffffffffffffffffffff),.c_rd_ready(c_ready),
  .c_wready(c_wr),.c_rvalid(c_rv),.c_done(c_done),.c_abort(c_abort),.c_rdata(c_data),
  .m_valid(valid),.m_cmd(cmd),.m_wdata(wdata),.m_wstrb(mask),.m_rd_ready(ready),
  .m_wready(1'b0),.m_rvalid(rvalid),.m_rdata({254'd0,owner}),.m_done(done),.m_abort(abort_now),
  .fault(fault),.owner(owner),.active(active));
 task check(input bit good,input string label);
  begin if(!good)$fatal(1,"%s",label);checks=checks+1;end
 endtask
 always @(negedge clk) begin
  if(!rst_n) begin running=0;done=0;rvalid=0;age=0;left=0;rng=32'hcafe1234;end
  else begin
   rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};c_ready=rng[7:4];
   done=0;
   if(!running && valid) begin running=1;age=0;left=2;grants=grants+1;end
   else if(running) begin
    age=age+1;
    if(age==2)done=1;
    rvalid=age>=4 && left!=0;
    if(left==0 && !active)begin running=0;rvalid=0;end
   end
  end
 end
 always @(posedge clk) if(rst_n) begin
  if(rvalid && ready)left=left-1;
  if(c_done!=0 && !abort_now)check(c_done==(4'b0001<<owner),"raw done routes only to its owner");
  if(dut.finished && !abort_now) begin
   check(!served[owner],"held client valid issued once");
   check(left==0,"read data drained before client done");
   served[owner]=1;completed=completed+1;
  end
 end
 initial begin
  for(i=0;i<4;i=i+1)c_cmd[i*37+:37]={1'b0,28'h0300000,8'd1};
  repeat(4)@(negedge clk);rst_n=1;c_valid=15;
  wait(completed==1);@(negedge clk);
  check(served==1 && grants==1,"boot monopolizes port before done");
  repeat(10)@(negedge clk);check(grants==1,"held boot valid is not a new command");
  boot_done=1;
  wait(completed==4);repeat(20)@(negedge clk);
  check(served==15 && grants==4,"all four held requests receive fair service once");
  c_valid=0;repeat(3)@(negedge clk);c_valid=8;
  wait(active && owner==3);@(negedge clk);abort_now=1;
  #1;check(c_abort[3] && c_done==8,"abort terminates only its owner");
  @(negedge clk);abort_now=0;
  check(fault && c_abort==15 && !valid,"abort remains fatal until reset");
  $display("PACERV_M3_SHARE PASS checks=%0d fair_clients=4 original_grants=4",checks);
  $finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
