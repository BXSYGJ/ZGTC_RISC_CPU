`timescale 1ns/1ps
module tb_symphony_renderer;
    reg clk=0;
    always #3.367 clk=~clk;
    reg rst_n=0;
    reg [10:0] x=0,y=0;
    reg de=0,hs=0,vs=0;
    reg page_library=0;
    reg [3:0] filter_class=8;
    reg [5:0] selected_index=2;
    reg [6:0] item_count=64;
    wire [5:0] rd_index;
    wire rd_all;
    reg rd_valid=0,rd_bookmark=0;
    reg [2:0] rd_class=0;
    reg [7:0] rd_confidence=0;
    reg [31:0] rd_time_ms=0,rd_sequence=0;
    wire [23:0] rgb;
    wire de_out,hs_out,vs_out,frame_start;
    wire [10:0] wave_addr;
    wire [14:0] spec_addr;
    symphony_renderer dut(
        .pix_clk(clk),.rst_pix_n(rst_n),.pix_x(x),.pix_y(y),.pix_de(de),.pix_hs(hs),.pix_vs(vs),
        .wave_rd_addr(wave_addr),.wave_min(16'd0),.wave_max(16'd0),.wave_valid(1'b1),.mute_flag_sync(1'b0),
        .spec_ram_addr(spec_addr),.spec_ram_data(8'd0),.feature_ready(1'b1),.result_ready(1'b1),.class_idx(4'd7),
        .pct0(8'd2),.pct1(8'd1),.pct2(8'd1),.pct3(8'd3),.pct4(8'd2),.pct5(8'd1),.pct6(8'd3),.pct7(8'd87),
        .page_library(page_library),.filter_class(filter_class),.selected_index(selected_index),
        .item_count(item_count),.history_count(7'd64),.result_time_ms(32'd123456),.result_sequence(32'd128),
        .rd_index(rd_index),.rd_all(rd_all),.rd_valid(rd_valid),.rd_class(rd_class),.rd_confidence(rd_confidence),
        .rd_time_ms(rd_time_ms),.rd_sequence(rd_sequence),.rd_bookmark(rd_bookmark),
        .selected_valid(1'b1),.selected_class(3'd5),.selected_confidence(8'd81),.selected_time_ms(32'd120456),
        .selected_sequence(32'd126),.selected_bookmark(1'b0),
        .vsync_pulse(frame_start),.rgb(rgb),.de_out(de_out),.hs_out(hs_out),.vs_out(vs_out)
    );
    // Deliberate render fixture, not an audio classifier or board capture.
    // The hardware integration test separately uses the actual history state.
    always @(posedge clk)begin
        rd_valid<=item_count!=0;
        rd_class<=3'd7-rd_index[2:0];
        rd_confidence<=87-(rd_index%5)*3;
        rd_time_ms<=123456-rd_index*1500;
        rd_sequence<=128-rd_index;
        rd_bookmark<=rd_index%7==0;
    end
    reg [4:0] de_expected=0,hs_expected=0,vs_expected=0;
    integer x_expected[0:4];
    integer y_expected[0:4];
    integer pixel_count=0,clock_checks=0,samples=0;
    integer fd=0,frame,px,py,k;
    reg writing=0;
    always @(posedge clk)begin
        for(k=4;k>0;k=k-1)begin
            x_expected[k]=x_expected[k-1];y_expected[k]=y_expected[k-1];
        end
        x_expected[0]=x;y_expected[0]=y;
        de_expected={de_expected[3:0],de};
        hs_expected={hs_expected[3:0],hs};
        vs_expected={vs_expected[3:0],vs};
        #0.1;
        if(rst_n)begin
            clock_checks=clock_checks+1;
            if({de_out,hs_out,vs_out}!=={de_expected[4],hs_expected[4],vs_expected[4]})
                $fatal(1,"Video control alignment failed at clock %0d",clock_checks);
            if($isunknown(rgb))$fatal(1,"Unknown rendered pixel");
            if(!de_out&&rgb!==24'd0)$fatal(1,"Blanking pixel was not black");
            if(writing&&de_out)begin
                $fwrite(fd,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
                pixel_count=pixel_count+1;
                if(x_expected[4]==10&&y_expected[4]==500)begin
                    if(rgb!==24'h18332e)$fatal(1,"Sidebar color mismatch");samples=samples+1;
                end
                if(x_expected[4]==1900&&y_expected[4]==500)begin
                    if(rgb!==24'hf4f6ef)$fatal(1,"Canvas color mismatch");samples=samples+1;
                end
            end
        end
    end
    initial begin
        for(k=0;k<5;k=k+1)begin x_expected[k]=0;y_expected[k]=0;end
        repeat(8)@(negedge clk);
        rst_n=1;
        repeat(80)@(negedge clk);
        for(frame=0;frame<4;frame=frame+1)begin
            page_library=frame==1||frame==2;
            filter_class=frame>=2?4'd5:4'd8;
            item_count=frame==2?7'd0:7'd64;
            selected_index=2;
            repeat(80)@(negedge clk);
            if(frame==0)fd=$fopen("guide.ppm","wb");
            else if(frame==1)fd=$fopen("library.ppm","wb");
            else if(frame==2)fd=$fopen("library_empty.ppm","wb");
            else fd=$fopen("guide_filter.ppm","wb");
            if(fd==0)$fatal(1,"Could not create native screenshot");
            $fwrite(fd,"P6\n# Native RTL render fixture; not board/audio inference\n1920 1080\n255\n");
            pixel_count=0;writing=1;
            for(py=0;py<1125;py=py+1)begin
                for(px=0;px<2200;px=px+1)begin
                    @(negedge clk);x=px;y=py;de=px<1920&&py<1080;
                    hs=px>=2008&&px<2052;vs=py>=1084&&py<1089;
                end
            end
            @(negedge clk);de=0;hs=0;vs=0;
            repeat(8)@(negedge clk);
            writing=0;$fclose(fd);
            if(pixel_count!=2073600)$fatal(1,"Visible pixel count mismatch %0d",pixel_count);
            $display("NATIVE_FRAME_PASS page=%0d pixels=%0d",frame,pixel_count);
        end
        if(samples!=8)$fatal(1,"Sample count mismatch");
        $display("NATIVE_SYMPHONY_RENDER_PASS frames=4 visible_pixels=8294400 checked_video_clocks=%0d latency=5 fixture_only=1",clock_checks);
        $finish;
    end
endmodule
