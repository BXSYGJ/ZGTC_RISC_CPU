`timescale 1ns/1ps
module tb_audio_page_order;
    reg clk=0;
    always #4 clk=~clk;
    reg rst=0;
    wire rd_en;
    reg [31:0] rd_data=0;
    reg rd_valid=0;
    integer cycle=0, sample_number=0, commands=0;
    wire empty = cycle % 64 != 0 || sample_number >= 64;
    wire cmd_valid;
    wire [36:0] cmd;
    wire [255:0] data;
    reg done=0, seen=0;
    wire tick, mute, wave_valid, mute_sync;
    wire [15:0] win, err, wave_min, wave_max;
    wire [31:0] freeze_cycles;
    wire [17:0] page_count, done_count;
    audio_sink dut (
        .clk(clk), .rst_n(rst), .fifo_rd_en(rd_en), .fifo_rd_data(rd_data),
        .fifo_rd_valid(rd_valid), .fifo_empty(empty), .diag_lock(1'b0), .sd_idle(1'b0),
        .m0_cmd_valid(cmd_valid), .m0_cmd(cmd), .m0_wdata(data), .m0_done(done),
        .win_tick(tick), .win_id(win), .mute_flag(mute), .err_cnt(err),
        .freeze_cycles(freeze_cycles), .page_cnt_lat(page_count), .done_cnt_lat(done_count),
        .pix_clk(clk), .vsync_pulse(1'b0), .wave_rd_addr(11'd0),
        .wave_min(wave_min), .wave_max(wave_max), .wave_valid(wave_valid), .mute_flag_sync(mute_sync)
    );
    always @(posedge clk) begin
        cycle <= cycle+1;
        rd_valid <= rst && rd_en && !empty;
        if (rst && rd_en && !empty) begin
            rd_data <= {sample_number[15:0], sample_number[15:0] ^ 16'h8000};
            sample_number <= sample_number+1;
        end
        done <= 0;
        if (!cmd_valid) seen <= 0;
        if (rst && cmd_valid && !seen) begin
            for (integer lane=0; lane<16; lane=lane+1) begin
                if (data[lane*16 +: 16] !== (((commands/2)*16+lane) ^ ((commands%2) ? 16'h8000 : 0)))
                    $fatal(1,"PCM page chronology reversed/corrupt cmd=%0d lane=%0d got=%0d",commands,lane,data[lane*16 +: 16]);
            end
            if (cmd[35:8] != ((commands%2 ? 28'h84000 : 0) + (commands/2)*32))
                $fatal(1,"PCM page address wrong");
            seen <= 1; done <= 1; commands <= commands+1;
        end
    end
    initial begin
        repeat(4) @(negedge clk); rst=1;
        wait(commands==8);
        repeat(10) @(negedge clk);
        $display("RESULT: PASS audio_page_order four stereo pages, ascending little-endian samples");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"Audio page order watchdog");
    end
endmodule
