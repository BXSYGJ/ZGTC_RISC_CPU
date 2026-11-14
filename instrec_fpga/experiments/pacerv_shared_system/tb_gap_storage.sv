`timescale 1ns/1ps
module tb_gap_storage;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst_n = 0, layer_start = 0, y_valid = 0;
    reg [7:0] y_u8 = 0, raddr = 0;
    wire [15:0] rdata, wdata;
    wire done, we;
    wire [7:0] waddr;
    gap_unit dut(.clk(clk), .rst_n(rst_n), .layer_start(layer_start),
        .y_valid(y_valid), .y_u8(y_u8), .g_raddr(raddr), .g_rdata(rdata),
        .gap_done(done), .gap_we(we), .gap_waddr(waddr), .gap_wdata(wdata));
    integer sums[0:255];
    integer expected[0:255];
    integer frame, k, channel, spatial, value, q, rem_value;
    integer writes = 0, total_writes = 0, done_count = 0;
    always @(posedge clk) begin
        if (rst_n && we) begin
            if (writes >= 256 || waddr !== writes[7:0] || wdata !== expected[writes])
                $fatal(1, "GAP output frame=%0d channel=%0d address=%0d got=%0d expected=%0d",
                    frame, writes, waddr, wdata, expected[writes]);
            writes = writes + 1;
            total_writes = total_writes + 1;
        end
        if (rst_n && done) done_count = done_count + 1;
    end
    initial begin
        repeat (3) @(negedge clk);
        rst_n = 1;
        for (frame = 0; frame < 3; frame = frame + 1) begin
            for (channel = 0; channel < 256; channel = channel + 1) sums[channel] = 0;
            writes = 0;
            @(negedge clk); layer_start = 1;
            @(negedge clk); layer_start = 0;
            for (k = 0; k < 16384; k = k + 1) begin
                channel = ((k / 256) % 16) * 16 + (k % 16);
                spatial = (k / 4096) * 16 + ((k / 16) % 16);
                if (frame == 0) value = (k * 17 + (k / 16) * 3) % 256;
                else if (frame == 1) value = (channel % 8) + (spatial < 32 ? 0 : 1);
                else value = 255;
                sums[channel] = sums[channel] + value;
                if (k % 11 == 0) begin
                    y_valid = 0;
                    @(negedge clk);
                end
                y_valid = 1; y_u8 = value[7:0];
                @(negedge clk);
            end
            y_valid = 0;
            for (channel = 0; channel < 256; channel = channel + 1) begin
                q = sums[channel] / 64;
                rem_value = sums[channel] % 64;
                if (rem_value > 32 || (rem_value == 32 && q % 2 == 1)) q = q + 1;
                expected[channel] = q;
            end
            wait(done);
            repeat (2) @(negedge clk);
            if (writes != 256) $fatal(1, "Incomplete GAP result frame");
            for (channel = 0; channel < 256; channel = channel + 1) begin
                raddr = channel[7:0];
                @(posedge clk); #1;
                if (rdata !== expected[channel]) $fatal(1, "GAP synchronous result read mismatch");
                @(negedge clk);
            end
        end
        if (total_writes != 768 || done_count != 3) $fatal(1, "GAP completion count");
        $display("GAP_STORAGE_PASS frames=3 outputs=768 readbacks=768 stalls=1 rounding_ties=1 maximum=255");
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "GAP storage timeout");
    end
endmodule
