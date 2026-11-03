`timescale 1ns/1ps
// Fixed-feature NPU probe testbench, derived from tb_npu_full_native.sv.
// Differences from the parent experiment:
//   * no in-TB golden value checks: every layer output is collected into
//     arrays and dumped with $writememh, the full-array comparison against
//     scripts/golden_pipeline.py happens Python-side (stronger than the
//     parent's per-value $fatal checks and it yields the snapshot files).
//   * feature source selected via +vec=N, dump directory via +outdir=...
//     so one Verilator build serves every probe vector.
// Kept from the parent: identical DUT instance, weight preload into the
// behavioural DDR3 model, layer-progress prints, timeout / native-DDR
// protocol / output-count fatals.
module tb_npu_probe;
reg clk=0; always #5 clk=~clk;
reg rst_n=0,start=0;
wire busy,done,timeout_flag,probs_valid,feat_en,cmd_v;
wire [31:0] cycles; wire [14:0] feat_a; wire [36:0] cmd;
wire [7:0] pct; wire [3:0] idx,top1;
reg [7:0] feat_d=0; wire [255:0] rd_data;
wire rd_valid,rd_done;
reg [7:0] weights[0:691039];
reg [7:0] feat_v0[0:16511],feat_v1[0:16511],feat_v2[0:16511],feat_v3[0:16511];
wire acv,acw,awv;wire [31:0] aca;wire [255:0] awd;
wire acr,awr,arv;wire [255:0] ard;
integer vec_sel=0;
string outdir;
npu_top dut(.clk(clk),.rst_n(rst_n),.start(start),.busy(busy),.done(done),.npu_cycles(cycles),.timeout_flag(timeout_flag),.feat_rd_addr(feat_a),.feat_rd_en(feat_en),.feat_rd_data(feat_d),.rd_cmd_valid(cmd_v),.rd_cmd(cmd),.rd_ready(1'b1),.rd_data(rd_data),.rd_valid(rd_valid),.rd_done(rd_done),.act_cmd_valid(acv),.act_cmd_write(acw),.act_cmd_addr(aca),.act_cmd_ready(acr),.act_wr_valid(awv),.act_wr_data(awd),.act_wr_ready(awr),.act_rd_valid(arv),.act_rd_data(ard),.probs_valid(probs_valid),.probs_pct(pct),.probs_idx(idx),.top1(top1));
always @(posedge clk) if(feat_en) begin
 case(vec_sel)
  0: feat_d<=feat_v0[feat_a];
  1: feat_d<=feat_v1[feat_a];
  2: feat_d<=feat_v2[feat_a];
  default: feat_d<=feat_v3[feat_a];
 endcase
end
integer prev=-1, prob_count=0;
always @(posedge clk) if(rst_n) begin
 if(dut.layer!=prev) begin $display("LAYER %0d cycle %0d",dut.layer,cycles); prev=dut.layer; end
 if(cycles!=0 && cycles%1000000==0) $display("PROGRESS %0d layer %0d",cycles,dut.layer);
 if(timeout_flag) $fatal(1,"timeout layer %0d",dut.layer);
end
// ---- layer collectors (same sampling points as the parent TB checks) ----
reg [7:0] dump_conv1[0:792575]; integer count_conv1=0;
reg [7:0] dump_conv2[0:396287]; integer count_conv2=0;
reg [7:0] dump_conv3[0:196607]; integer count_conv3=0;
reg [7:0] dump_conv4[0:65535];  integer count_conv4=0;
reg [7:0] dump_pool1[0:198143]; integer count_pool1=0;
reg [7:0] dump_pool2[0:98303];  integer count_pool2=0;
reg [7:0] dump_pool3[0:49151];  integer count_pool3=0;
reg [7:0] dump_pool4[0:16383];  integer count_pool4=0;
reg [31:0] dump_gap[0:255];     integer count_gap=0;
reg [7:0] dump_fc1[0:127];      integer count_fc1=0;
reg [7:0] dump_fc2[0:7];        integer count_fc2=0;reg [15:0] dump_probs[0:7];
always @(posedge clk) if(rst_n && dut.core_y_valid && dut.pool_y_ready && dut.layer==0) begin
 if(count_conv1<792576) dump_conv1[count_conv1]<=dut.core_y_u8;
 count_conv1=count_conv1+1;
end
always @(posedge clk) if(rst_n && dut.core_y_valid && dut.pool_y_ready && dut.layer==2) begin
 if(count_conv2<396288) dump_conv2[count_conv2]<=dut.core_y_u8;
 count_conv2=count_conv2+1;
end
always @(posedge clk) if(rst_n && dut.core_y_valid && dut.pool_y_ready && dut.layer==4) begin
 if(count_conv3<196608) dump_conv3[count_conv3]<=dut.core_y_u8;
 count_conv3=count_conv3+1;
end
always @(posedge clk) if(rst_n && dut.core_y_valid && dut.pool_y_ready && dut.layer==6) begin
 if(count_conv4<65536) dump_conv4[count_conv4]<=dut.core_y_u8;
 count_conv4=count_conv4+1;
end
always @(posedge clk) if(rst_n && dut.pool_p_valid && ((dut.pool_sel1 || dut.pool_sel3) ? dut.s0_in_ready : dut.pool_sel2 ? dut.s1_in_ready : 1'b1) && (dut.pool_sel1)) begin
 if(count_pool1<198144) dump_pool1[count_pool1]<=dut.pool_p_u8;
 count_pool1=count_pool1+1;
end
always @(posedge clk) if(rst_n && dut.pool_p_valid && ((dut.pool_sel1 || dut.pool_sel3) ? dut.s0_in_ready : dut.pool_sel2 ? dut.s1_in_ready : 1'b1) && (dut.pool_sel2)) begin
 if(count_pool2<98304) dump_pool2[count_pool2]<=dut.pool_p_u8;
 count_pool2=count_pool2+1;
end
always @(posedge clk) if(rst_n && dut.pool_p_valid && ((dut.pool_sel1 || dut.pool_sel3) ? dut.s0_in_ready : dut.pool_sel2 ? dut.s1_in_ready : 1'b1) && (dut.pool_sel3)) begin
 if(count_pool3<49152) dump_pool3[count_pool3]<=dut.pool_p_u8;
 count_pool3=count_pool3+1;
end
always @(posedge clk) if(rst_n && dut.pool_p_valid && ((dut.pool_sel1 || dut.pool_sel3) ? dut.s0_in_ready : dut.pool_sel2 ? dut.s1_in_ready : 1'b1) && (dut.pool_sel4)) begin
 if(count_pool4<16384) dump_pool4[count_pool4]<=dut.pool_p_u8;
 count_pool4=count_pool4+1;
end
always @(posedge clk) if(rst_n && dut.gap_we) begin
 if(count_gap<256) dump_gap[count_gap]<=dut.gap_wdata;
 count_gap=count_gap+1;
end
always @(posedge clk) if(rst_n && dut.fc1_y_valid) begin
 if(count_fc1<128) dump_fc1[count_fc1]<=dut.fc1_y;
 count_fc1=count_fc1+1;
end
always @(posedge clk) if(rst_n && dut.fc2_y_valid) begin
 if(count_fc2<8) dump_fc2[count_fc2]<=dut.fc2_y;
 count_fc2=count_fc2+1;
end
always @(posedge clk) if(probs_valid) begin
 dump_probs[idx]<=dut.sm_q16;
 prob_count=prob_count+1;
end
// ---- native DDR plumbing: aligner + m1 bridge + ctrl + behavioural model ----
wire weight_ready=1'b1;
wire [36:0] native_weight_cmd;wire aligned_valid,aligned_rdvalid,aligned_done;wire[255:0]aligned_data;
weight_read_aligner aligner(.clk(clk),.rst_n(rst_n),.up_valid(cmd_v),.up_cmd(cmd),.up_data(rd_data),.up_rd_valid(rd_valid),.up_done(rd_done),.dn_valid(aligned_valid),.dn_cmd(native_weight_cmd),.dn_data(aligned_data),.dn_rd_valid(aligned_rdvalid),.dn_done(aligned_done));

    wire [255:0] n_mwdata;
    wire n_mcmdvalid, n_mrdready;
    wire [36:0] n_mcmd;
    wire n_protocol_error, n_failed;
    wire [3:0] n_cmd_to_err;
    wire [3:0] n_cmd_valid = {2'b00,n_mcmdvalid,1'b0};
    wire [3:0] n_rd_ready = {2'b00,n_mrdready,1'b0};
    wire [3:0] n_wready_beat, n_done_vec, n_rd_valid_vec;
    wire [255:0] n_rd0, n_rd1, n_rd2, n_rd3;
    wire [31:0] n_wc0,n_wc1,n_wc2,n_wc3;
    wire [3:0] n_addr_err;
    wire n_to_err;
    wire [2:0] n_dbg;
    wire [7:0] n_wmiss;
    wire [27:0] n_awaddr,n_araddr;
    wire n_awap,n_arap,n_awvalid,n_arvalid,n_awready,n_arready;
    wire [3:0] n_awid,n_arid,n_awlen,n_arlen,n_rid;
    wire [255:0] n_axi_wdata,n_axi_rdata;
    wire [31:0] n_axi_wstrb;
    wire n_axi_wready,n_wlast,n_rvalid_axi,n_rlast;

    npu_m1_bridge n_bridge(
        .clk(clk),.rst_n(rst_n),.wgt_cmd_valid(aligned_valid),.wgt_cmd(native_weight_cmd),
        .wgt_rd_ready(weight_ready),.wgt_rd_data(aligned_data),.wgt_rd_valid(aligned_rdvalid),
        .wgt_done(aligned_done),.act_cmd_valid(acv),.act_cmd_write(acw),.act_cmd_addr(aca),
        .act_cmd_ready(acr),.act_wr_valid(awv),.act_wr_data(awd),
        .act_wr_ready(awr),.act_rd_valid(arv),.act_rd_data(ard),
        .m1_cmd_valid(n_mcmdvalid),.m1_cmd(n_mcmd),.m1_wdata(n_mwdata),
        .m1_rd_ready(n_mrdready),.m1_wready(n_wready_beat[1]),.m1_rdata(n_rd1),
        .m1_rvalid(n_rd_valid_vec[1]),.m1_done(n_done_vec[1]),.m1_abort(n_cmd_to_err[1] || n_addr_err[1]),
        .protocol_error(n_protocol_error),.transaction_failed(n_failed));

    ddr3_ctrl_axi #(.AXI_TO_LIMIT(64),.P3_QUOTA_TIMEOUT(32)) n_ctrl(
        .clk(clk),.rst_n(rst_n),.cmd_valid(n_cmd_valid),
        .m0_cmd(37'd0),.m1_cmd(n_mcmd),.m2_cmd(37'd0),.m3_cmd(37'd0),
        .m0_wdata(256'd0),.m1_wdata(n_mwdata),.m2_wdata(256'd0),.m3_wdata(256'd0),
        .wready_beat(n_wready_beat),.rd_ready(n_rd_ready),.rd_data_0(n_rd0),.rd_data_1(n_rd1),
        .rd_data_2(n_rd2),.rd_data_3(n_rd3),.rd_valid(n_rd_valid_vec),.done(n_done_vec),
        .wait_cnt_0(n_wc0),.wait_cnt_1(n_wc1),.wait_cnt_2(n_wc2),.wait_cnt_3(n_wc3),
        .addr_err(n_addr_err),.to_err(n_to_err),.cmd_to_err(n_cmd_to_err),.dbg_to_state(n_dbg),
        .wlast_miss_cnt(n_wmiss),.axi_awaddr(n_awaddr),.axi_awuser_ap(n_awap),.axi_awuser_id(n_awid),
        .axi_awlen(n_awlen),.axi_awvalid(n_awvalid),.axi_awready(n_awready),.axi_wdata(n_axi_wdata),
        .axi_wstrb(n_axi_wstrb),.axi_wready(n_axi_wready),.axi_wusero_id(4'd0),.axi_wusero_last(n_wlast),
        .axi_araddr(n_araddr),.axi_aruser_ap(n_arap),.axi_aruser_id(n_arid),.axi_arlen(n_arlen),
        .axi_arvalid(n_arvalid),.axi_arready(n_arready),.axi_rdata(n_axi_rdata),.axi_rid(n_rid),
        .axi_rlast(n_rlast),.axi_rvalid(n_rvalid_axi));

    ddr3_axi_model_full #(.MEM_BEATS(262144)) n_model(
        .clk(clk),.rst_n(rst_n),.s_awaddr(n_awaddr),.s_awvalid(n_awvalid),.s_awlen(n_awlen),
        .s_awuser_id(n_awid),.s_awready(n_awready),.s_wdata(n_axi_wdata),.s_wstrb(n_axi_wstrb),
        .s_wready(n_axi_wready),.s_wusero_last(n_wlast),.s_araddr(n_araddr),.s_arvalid(n_arvalid),
        .s_arlen(n_arlen),.s_aruser_id(n_arid),.s_arready(n_arready),.s_rdata(n_axi_rdata),
        .s_rid(n_rid),.s_rlast(n_rlast),.s_rvalid(n_rvalid_axi),.obs_aw_hs(),.obs_ar_hs(),
        .obs_wr_beats(),.obs_rd_beats(),.obs_len0_wr(),.obs_len0_wstrb0(),.obs_len0_wstrb1(),.obs_last_marker());


integer preload_i,preload_k;
initial begin
 #1; for(preload_i=0;preload_i<21595;preload_i=preload_i+1) begin
 for(preload_k=0;preload_k<32;preload_k=preload_k+1) n_model.mem[32768+preload_i][preload_k*8+:8]=weights[preload_i*32+preload_k];
 end
end
always @(posedge clk) if(rst_n && (n_protocol_error || n_failed || n_to_err || n_addr_err!=0 || dut.s0_error || dut.s1_error || dut.mux_error)) $fatal(1,"native DDR protocol error bridge=%b timeout=%b address=%b",n_protocol_error,n_to_err,n_addr_err);

// ---- main sequence: load assets, run one inference, dump snapshots ----
initial begin
 $readmemh("build/sim/npu_probe/assets/weights.hex",weights);
 $readmemh("build/sim/npu_probe/assets/feat_v0.hex",feat_v0);
 $readmemh("build/sim/npu_probe/assets/feat_v1.hex",feat_v1);
 $readmemh("build/sim/npu_probe/assets/feat_v2.hex",feat_v2);
 $readmemh("build/sim/npu_probe/assets/feat_v3.hex",feat_v3);
 if(!$value$plusargs("vec=%d",vec_sel)) vec_sel=0;
 case(vec_sel)
  0: outdir="build/sim/npu_probe/sine440";
  1: outdir="build/sim/npu_probe/zeros49";
  2: outdir="build/sim/npu_probe/rand20261104";
  default: outdir="build/sim/npu_probe/sine440_twolevel";
 endcase
 void'($value$plusargs("outdir=%s",outdir));
 $display("PROBE_START vec=%0d outdir=%s",vec_sel,outdir);
 repeat(5) @(negedge clk); rst_n=1;
 repeat(3) @(negedge clk); start=1; @(negedge clk); start=0;
 wait(done); @(negedge clk);
 if(prob_count!=8) $fatal(1,"bad probability count %0d",prob_count);
 if(count_conv1!=792576 || count_conv2!=396288 || count_conv3!=196608 || count_conv4!=65536) $fatal(1,"incomplete convolution outputs");
 if(count_pool1!=198144 || count_pool2!=98304 || count_pool3!=49152 || count_pool4!=16384) $fatal(1,"incomplete pool outputs");
 if(count_gap!=256 || count_fc1!=128 || count_fc2!=16) $fatal(1,"incomplete GAP/FC outputs %d %d %d",count_gap,count_fc1,count_fc2);
 $writememh($sformatf("%s/conv1.hex",outdir),dump_conv1);
 $writememh($sformatf("%s/conv2.hex",outdir),dump_conv2);
 $writememh($sformatf("%s/conv3.hex",outdir),dump_conv3);
 $writememh($sformatf("%s/conv4.hex",outdir),dump_conv4);
 $writememh($sformatf("%s/pool1.hex",outdir),dump_pool1);
 $writememh($sformatf("%s/pool2.hex",outdir),dump_pool2);
 $writememh($sformatf("%s/pool3.hex",outdir),dump_pool3);
 $writememh($sformatf("%s/pool4.hex",outdir),dump_pool4);
 $writememh($sformatf("%s/gap.hex",outdir),dump_gap);
 $writememh($sformatf("%s/fc1.hex",outdir),dump_fc1);
 $writememh($sformatf("%s/fc2.hex",outdir),dump_fc2);
 $writememh($sformatf("%s/probs.hex",outdir),dump_probs);
 $display("PROBE_DONE vec=%0d cycles=%0d top1=%0d",vec_sel,cycles,top1);
 $display("RESULT: PASS npu_probe vec=%0d cycles=%0d",vec_sel,cycles);
 $finish;
end
initial begin repeat(51000000) @(negedge clk);$fatal(1,"TB watchdog");end

endmodule
