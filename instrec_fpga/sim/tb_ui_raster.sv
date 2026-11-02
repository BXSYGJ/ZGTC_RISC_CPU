`timescale 1ns/1ps
module tb_ui_raster;
    reg clk=0;
    always #3.367 clk=~clk;
    reg rst_n=0;
    wire hs,vs,de,ohs,ovs,ode,vpulse;
    wire [11:0] x,y;
    wire [10:0] addr;
    wire [23:0] rgb;
    reg [3:0] dh=0,dv=0,dd=0;
    integer cycles=0,active=0,h_edges=0,v_edges=0;
    reg last_h=0,last_v=0;
    sync_vg #(.X_BITS(12),.Y_BITS(12),.V_TOTAL(1125),.V_FP(4),.V_BP(36),
      .V_SYNC(5),.V_ACT(1080),.H_TOTAL(2200),.H_FP(88),.H_BP(148),
      .H_SYNC(44),.H_ACT(1920)) timing(.clk(clk),.rstn(rst_n),
      .vs_out(vs),.hs_out(hs),.de_out(de),.x_act(x),.y_act(y));
    ui_renderer ui(.pix_clk(clk),.rst_pix_n(rst_n),.pix_x(x[10:0]),.pix_y(y[10:0]),
      .pix_de(de),.pix_hs(hs),.pix_vs(vs),.wave_rd_addr(addr),
      .wave_min(16'hF000),.wave_max(16'h1000),.wave_valid(1'b1),
      .mute_flag_sync(1'b0),.vsync_pulse(vpulse),.spec_rgb(24'h000000),
      .spec_on(1'b0),.text_rgb(24'h000000),.text_on(1'b0),
      .bars_rgb(24'h000000),.bars_on(1'b0),.rgb(rgb),.de_out(ode),.hs_out(ohs),.vs_out(ovs));
    always @(posedge clk) begin
      if (!rst_n) begin dh<=0;dv<=0;dd<=0;end
      else begin dh<={dh[2:0],hs};dv<={dv[2:0],vs};dd<={dd[2:0],de};end
    end
    always @(negedge clk) begin
      if(rst_n) begin
        cycles=cycles+1;
        if (ohs!==dh[3] || ovs!==dv[3] || ode!==dd[3])
          $fatal(1,"UI controls mismatch cycle=%0d hs=%b/%b vs=%b/%b de=%b/%b",cycles,ohs,dh[3],ovs,dv[3],ode,dd[3]);
        if (ode) active=active+1;
        if (ohs && !last_h) h_edges=h_edges+1;
        if (ovs && !last_v) v_edges=v_edges+1;
        last_h=ohs;last_v=ovs;
      end
    end
    initial begin
      repeat(8) @(negedge clk);
      rst_n=1;
      repeat(4950010) @(negedge clk);
      $display("RESULT: PASS full 1080p raster cycles=%0d active=%0d HS=%0d VS=%0d",cycles,active,h_edges,v_edges);
      $finish;
    end
endmodule
