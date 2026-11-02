`timescale 1ns/1ps
// Pixel-domain frame export. PLL is replaced by a simulation clock stub;
// all renderer, overlay, timing, pin output and demo source RTL is real.
module tb_ui_frame;
    reg clk=0;
    always #3.367 clk=~clk;
    reg rst_n=0;
    wire [7:0] led;
    wire uart_tx,scl,pclk,de,hs,vs,hrst;
    wire [23:0] rgb;
    tri1 sda;
    integer fd;
    integer pixels=0;
    reg capture=0;
    reg last_vs=0;
    top_ui_demo dut(.clk(clk),.rst_n(rst_n),.key1_n(1'b0),.led(led),
      .uart_tx(uart_tx),.hdmi_rst_n(hrst),.iic_tx_scl(scl),.iic_tx_sda(sda),
      .vout_clk(pclk),.vout_de(de),.vout_hs(hs),.vout_vs(vs),.vout_data(rgb));
    always @(posedge pclk) begin
      if (rst_n && dut.rst_pix_n && !dut.raw_video) begin
        if (vs && !last_vs && !capture) begin
          fd=$fopen("build/sim/ui_frame/frame.ppm","wb");
          if(!fd) $fatal(1,"cannot create frame.ppm");
          $fwrite(fd,"P6\n1920 1080\n255\n");
          capture=1;
        end
        if(capture && de) begin
          $fwrite(fd,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
          pixels=pixels+1;
          if(pixels==2073600) begin
            $fclose(fd);
            $display("RESULT: PASS exported actual UI RTL frame, %0d pixels",pixels);
            $finish;
          end
        end
        last_vs=vs;
      end
    end
    initial begin repeat(8) @(negedge clk);rst_n=1;end
    initial begin #50000000; $fatal(1,"frame export timeout");end
endmodule

module pll(input wire clkin1,output wire clkout0,output wire clkout1,output wire lock);
    assign clkout0=clkin1;
    assign clkout1=clkin1;
    assign lock=1'b1;
endmodule
