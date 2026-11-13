`timescale 1ns/1ps
module tb_pacerv_shared_ddr;
 reg clk=0,rst_n=0,boot_done=0;
 always #5 clk=~clk;
 reg req_valid=0,req_write=0,rsp_ready=0;
 reg [31:0] req_address=0,req_data=0;
 reg [3:0] req_strobe=0;
 wire req_ready,rsp_valid,rsp_error,bridge_fault;
 wire [31:0] rsp_data;
 wire cpu_valid,cpu_ready,cpu_rvalid,cpu_done,cpu_abort;
 wire [36:0] cpu_cmd;
 wire [255:0] cpu_data;
 wire [31:0] cpu_mask;
 reg [2:0] clients=0,clients_ready=0;
 reg [110:0] clients_cmd=0;
 reg [767:0] clients_data=0;
 reg [2:0] other_valid=0,other_ready=0;
 reg [110:0] other_cmd=0;
 reg [767:0] other_wdata=0;
 wire [255:0] other_rdata[0:2];
 wire [3:0] c_wready,c_rvalid,c_done,c_abort;
 wire [255:0] c_rdata;
 wire m_valid,m_rd_ready,m_wready,m_rvalid,m_done,m_abort,share_fault,share_active;
 wire [1:0] owner;
 wire [36:0] m_cmd;
 wire [255:0] m_wdata;
 wire [31:0] m_wstrb;
 wire [3:0] d_done,d_rvalid,d_wready,addr_err,cmd_to_err;
 wire [255:0] d_rdata;
 wire [27:0] awaddr,araddr;
 wire [3:0] awlen,arlen,awid,arid;
 wire awvalid,arvalid,awready,arready,wready,rvalid,rlast;
 wire [255:0] wdata,rdata;
 wire [31:0] wstrb;
 wire ap0,ap1;
 reg stall_aw=0;
 integer checks=0,cmd_count=0,byte_checks=0,diag_beats=0;
 integer audio_writes=0,activation_checks=0,mel_beats=0,cpu_wait=0,max_cpu_wait=0;
 pace_cpu_ddr_bridge #(.REQ_TIMEOUT(2000)) cpu(
  .clk(clk),.rst_n(rst_n),.ddr_ok(1'b1),
  .req_valid(req_valid),.req_ready(req_ready),.req_address(req_address),.req_write(req_write),
  .req_data(req_data),.req_strobe(req_strobe),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),
  .rsp_data(rsp_data),.rsp_error(rsp_error),.fault(bridge_fault),
  .m_cmd_valid(cpu_valid),.m_cmd(cpu_cmd),.m_wdata(cpu_data),.m_wstrb(cpu_mask),
  .m_rd_ready(cpu_ready),.m_wready(c_wready[3]),.m_rvalid(c_rvalid[3]),.m_rdata(c_rdata),
  .m_done(c_done[3]),.m_abort(c_abort[3]));
 ddr3_m3_share share(
  .clk(clk),.rst_n(rst_n),.boot_done(boot_done),
  .c_valid({cpu_valid,clients}),.c_cmd({cpu_cmd,clients_cmd}),.c_wdata({cpu_data,clients_data}),
  .c_wstrb({cpu_mask,96'hffffffffffffffffffffffff}),.c_rd_ready({cpu_ready,clients_ready}),
  .c_wready(c_wready),.c_rvalid(c_rvalid),.c_done(c_done),.c_abort(c_abort),.c_rdata(c_rdata),
  .m_valid(m_valid),.m_cmd(m_cmd),.m_wdata(m_wdata),.m_wstrb(m_wstrb),.m_rd_ready(m_rd_ready),
  .m_wready(d_wready[3]),.m_rvalid(d_rvalid[3]),.m_rdata(d_rdata),.m_done(d_done[3]),
  .m_abort(cmd_to_err[3]|addr_err[3]),.fault(share_fault),.owner(owner),.active(share_active));
 ddr3_ctrl_axi #(.M3_MASK_ENABLE(1),.AXI_TO_LIMIT(32),.P3_QUOTA_TIMEOUT(16)) ctrl(
  .clk(clk),.rst_n(rst_n),.cmd_valid({m_valid,other_valid}),
  .m0_cmd(other_cmd[0+:37]),.m1_cmd(other_cmd[37+:37]),.m2_cmd(other_cmd[74+:37]),.m3_cmd(m_cmd),
  .m0_wdata(other_wdata[0+:256]),.m1_wdata(other_wdata[256+:256]),.m2_wdata(other_wdata[512+:256]),
  .m3_wdata(m_wdata),.m3_wstrb(m_wstrb),
  .wready_beat(d_wready),.rd_ready({m_rd_ready,other_ready}),
  .rd_data_0(other_rdata[0]),.rd_data_1(other_rdata[1]),.rd_data_2(other_rdata[2]),
  .rd_data_3(d_rdata),.rd_valid(d_rvalid),
  .done(d_done),.addr_err(addr_err),.cmd_to_err(cmd_to_err),
  .axi_awaddr(awaddr),.axi_awuser_ap(ap0),.axi_awuser_id(awid),.axi_awlen(awlen),
  .axi_awvalid(awvalid),.axi_awready(awready),.axi_wdata(wdata),.axi_wstrb(wstrb),
  .axi_wready(wready),.axi_wusero_id(4'd3),.axi_wusero_last(last_hold!=0),
  .axi_araddr(araddr),.axi_aruser_ap(ap1),.axi_aruser_id(arid),.axi_arlen(arlen),
  .axi_arvalid(arvalid),.axi_arready(arready),.axi_rdata(rdata),.axi_rid(4'd3),
  .axi_rlast(rlast),.axi_rvalid(rvalid));
 // Sparse logical addresses are never truncated. Pango address is a word
 // index: >>3 converts it into a 32-byte memory-beat index.
 reg [255:0] mem[0:229375];
 reg [31:0] rng=32'h12345678;
 integer wr_left=0,rd_left=0,wr_index=0,rd_index=0,last_hold=0,i,b;
 assign awready = !stall_aw && wr_left==0 && rng[0];
 assign wready = wr_left!=0 && rng[1];
 assign arready = rd_left==0 && rng[2];
 assign rvalid = rd_left!=0 && (rng[3] || rng[4]);
 assign rlast = rd_left==1;
 assign rdata = mem[rd_index];
 always @(posedge clk) begin
  if(!rst_n) begin wr_left<=0;rd_left<=0;last_hold<=0;rng<=32'h12345678;end
  else begin
   if(m_valid && !d_done[3])cpu_wait<=cpu_wait+1;
   else begin if(cpu_wait>max_cpu_wait)max_cpu_wait<=cpu_wait;cpu_wait<=0;end
   rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
   if(last_hold!=0) last_hold<=last_hold-1;
   if(awvalid && awready) begin
    if(awaddr[2:0]!=0 || (awaddr>>3)>229375) $fatal(1,"write address geometry");
    wr_index<=awaddr>>3;wr_left<=awlen+1;cmd_count<=cmd_count+1;
   end
   if(wready) begin
    for(b=0;b<32;b=b+1) if(wstrb[b]) mem[wr_index][b*8+:8]<=wdata[b*8+:8];
    wr_index<=wr_index+1;wr_left<=wr_left-1;
    if(wr_left==1) last_hold<=4;
   end
   if(arvalid && arready) begin
    if(araddr[2:0]!=0 || (araddr>>3)>229375) $fatal(1,"read address geometry");
    rd_index<=araddr>>3;rd_left<=arlen+1;
   end
   if(rvalid) begin rd_left<=rd_left-1;rd_index<=rd_index+1;end
  end
 end
 task automatic check(input bit good,input string label);
  begin if(!good) $fatal(1,"%s",label); checks=checks+1;end
 endtask
 task automatic master_write(input integer client,input [27:0] a,input [31:0] value);
  begin
   @(negedge clk);other_cmd[client*37+:37]={1'b1,a,8'd0};
   other_wdata[client*256+:256]={8{value}};other_valid[client]=1;
   do @(posedge clk);while(!d_done[client]);
   @(negedge clk);other_valid[client]=0;
   repeat(2)@(negedge clk);
  end
 endtask
 task automatic master_read(input integer client,input [27:0] a,input integer beats,input [31:0] value);
  integer count;
  reg done_seen;
  begin
   @(negedge clk);other_cmd[client*37+:37]={1'b0,a,8'(beats-1)};
   other_valid[client]=1;other_ready[client]=0;count=0;done_seen=0;
   while(!done_seen || count<beats) begin
    @(negedge clk);other_ready[client]=rng[client+8] || rng[client+12];
    @(posedge clk);
    if(d_done[client])begin done_seen=1;other_valid[client]=0;end
    if(d_rvalid[client] && other_ready[client])begin
     check(other_rdata[client]==={8{value}},"concurrent master read payload");count=count+1;
    end
   end
   @(negedge clk);other_valid[client]=0;other_ready[client]=0;
   if(client==2)mel_beats=mel_beats+count;
   else activation_checks=activation_checks+count;
   repeat(2)@(negedge clk);
  end
 endtask
 task automatic cpu_access(input [31:0] a,input bit w,input [31:0] d,input [3:0] s,
                 input bit expected_error,output reg [31:0] result);
  reg [31:0] held;
  reg held_error;
  begin
   @(negedge clk);req_address=a;req_write=w;req_data=d;req_strobe=s;req_valid=1;
   do @(posedge clk); while(!req_ready);
   @(negedge clk);req_valid=0;
   while(!rsp_valid) @(negedge clk);
   held=rsp_data;held_error=rsp_error;
   repeat(3) begin
    @(negedge clk);check(rsp_valid && rsp_data===held && rsp_error===held_error,"held CPU response");
   end
   check(held_error===expected_error,"CPU response error");result=held;
   rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;
  end
 endtask
 reg [31:0] expected[0:15];
 reg [31:0] result,new_data;
 reg [3:0] mask;
 integer t,k,before_cmds;
 initial begin
  for(i=0;i<229376;i=i+1) mem[i]={8{32'h5aa55aa5}};
  for(i=0;i<16;i=i+1) expected[i]=32'h5aa55aa5;
  repeat(5) @(negedge clk);rst_n=1;
  // CPU remains queued while the boot owner is active.
  fork
   begin cpu_access(32'h40000000,0,0,0,0,result);check(result==32'h5aa55aa5,"boot-held CPU read");end
   begin
    repeat(10) @(negedge clk);check(!m_valid,"boot excludes CPU before done");boot_done=1;
   end
  join
  fork
  begin : concurrent_audio
   integer a;
   for(a=0;a<32;a=a+1)begin master_write(0,28'h0010000+a*32,32'ha0000000+a);audio_writes=audio_writes+1;end
  end
  begin : concurrent_activation
   integer a;
   for(a=0;a<8;a=a+1)begin
    master_write(1,28'h0401000+a*32,32'hb0000000+a);
    master_read(1,28'h0401000+a*32,1,32'hb0000000+a);
   end
  end
  begin : concurrent_mel
   integer a;
   for(a=0;a<4;a=a+1)master_read(2,28'h0020000+a*512,16,32'h5aa55aa5);
  end
  begin : concurrent_cpu
  for(t=0;t<64;t=t+1) begin
   k=t%16;new_data=32'h10203040^(t*32'h01030709);mask=(t%15)+1;
   cpu_access(32'h40000000+k*4,1,new_data,mask,0,result);
   for(b=0;b<4;b=b+1) if(mask[b]) expected[k][b*8+:8]=new_data[b*8+:8];
   cpu_access(32'h40000000+k*4,0,0,0,0,result);
   check(result===expected[k],"masked write/read word");byte_checks=byte_checks+4;
  end
  end
  join
  check(audio_writes==32 && activation_checks==8 && mel_beats==64,"all physical masters complete");
  check(max_cpu_wait<1000,"CPU receives quota service under three-master traffic");
  for(k=0;k<32;k=k+1)begin
   cpu_access(32'h41010000+k*32,0,0,0,0,result);
   check(result==32'ha0000000+k,"audio DDR checksum word survives CPU traffic");
  end
  for(k=0;k<16;k=k+1) begin
   cpu_access(32'h40000000+k*4,0,0,0,0,result);check(result===expected[k],"adjacent words preserved");
  end
  before_cmds=cmd_count;
  cpu_access(32'h40000001,0,0,0,1,result);
  cpu_access(32'h40100000,0,0,0,1,result);
  cpu_access(32'h410c6000,0,0,0,1,result);
  cpu_access(32'h41460000,0,0,0,1,result);
  cpu_access(32'h41000000,1,32'hffffffff,15,1,result);
  cpu_access(32'h41400000,1,32'hffffffff,15,1,result);
  check(cmd_count==before_cmds,"illegal accesses issue no DDR command");
  cpu_access(32'h41400000,0,0,0,0,result);check(result==32'h5aa55aa5,"read-only activation");
  cpu_access(32'h41000000,0,0,0,0,result);check(result==32'h5aa55aa5,"read-only PCM");
  cpu_access(32'h400ffffc,1,32'hcafebabe,15,0,result);
  cpu_access(32'h400ffffc,0,0,0,0,result);check(result==32'hcafebabe,"last APP word");
  cpu_access(32'h410c5ffc,0,0,0,0,result);check(result==32'h5aa55aa5,"last PCM word");
  cpu_access(32'h411b7ffc,0,0,0,0,result);check(result==32'h5aa55aa5,"last weights word");
  cpu_access(32'h4120fffc,0,0,0,0,result);check(result==32'h5aa55aa5,"last spectrum word");
  cpu_access(32'h4130fffc,0,0,0,0,result);check(result==32'h5aa55aa5,"last self-test word");
  cpu_access(32'h4143fffc,0,0,0,0,result);check(result==32'h5aa55aa5,"last activation A word");
  cpu_access(32'h4145fffc,0,0,0,0,result);check(result==32'h5aa55aa5,"last activation B word");
  // Diagnostic reader withholds all upstream ready until IP done arrives.
  // CPU simultaneously waits. Ownership must stay diagnostic through drain.
  @(negedge clk);clients_cmd[37+:37]={1'b0,28'h0300000,8'd7};clients[1]=1;
  fork
   begin cpu_access(32'h40000008,0,0,0,0,result);check(result===expected[2],"CPU behind diagnostic drain");end
   begin
    wait(d_done[3]);@(negedge clk);
    repeat(8) begin @(negedge clk);check(share_active && owner==1,"owner locked after IP done");end
    clients_ready[1]=1;
    while(diag_beats<8) begin @(posedge clk);if(c_rvalid[1] && clients_ready[1])diag_beats=diag_beats+1;end
    @(negedge clk);clients[1]=0;clients_ready[1]=0;
   end
  join
  check(diag_beats==8,"all diagnostic beats delivered");
  repeat(12) @(negedge clk);check(!share_active && !m_valid,"held valid not duplicated");
  check(addr_err==0 && cmd_to_err==0,"legal transactions stay error free");
  stall_aw=1;
  cpu_access(32'h40000000,0,0,0,1,result);
  check(bridge_fault && share_fault && cmd_to_err[3],"sticky timeout propagates");
  before_cmds=cmd_count;
  cpu_access(32'h40000000,1,0,15,1,result);
  check(cmd_count==before_cmds,"faulted port rejects later command");
  $display("PACERV_SHARED_DDR PASS checks=%0d masked_bytes=%0d diagnostic_beats=%0d audio_writes=%0d activation_reads=%0d mel_beats=%0d max_cpu_wait=%0d",checks,byte_checks,diag_beats,audio_writes,activation_checks,mel_beats,max_cpu_wait);
  $finish;
 end
 initial begin #20000000;$fatal(1,"global timeout");end
endmodule
