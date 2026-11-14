`timescale 1ns/1ps
// Exercise the real frozen probability CDC and its isolated event extension.
module tb_symphony_commit;
    reg core_clk = 0, pix_clk = 0;
    always #4 core_clk = ~core_clk;
    always #3 pix_clk = ~pix_clk;
    reg core_rst_n = 0, pix_rst_n = 0;
    reg probs_valid = 0, frame_start = 0;
    reg [7:0] probs_pct = 0;
    reg [3:0] probs_idx = 0, top1 = 0;
    wire [7:0] p0,p1,p2,p3,p4,p5,p6,p7;
    wire ready;
    wire [3:0] class_out;
    integer update_count = 0;
    integer checks = 0;
`ifdef HAS_FRAME_UPDATE
    wire frame_update;
    reg last_update = 0;
`endif
    bars_data dut (
        .core_clk(core_clk), .core_rst_n(core_rst_n),
        .probs_valid(probs_valid), .probs_pct(probs_pct),
        .probs_idx(probs_idx), .top1(top1),
        .pix_clk(pix_clk), .pix_rst_n(pix_rst_n), .frame_start(frame_start),
        .pct0(p0), .pct1(p1), .pct2(p2), .pct3(p3),
        .pct4(p4), .pct5(p5), .pct6(p6), .pct7(p7),
        .frame_ready(ready), .frame_class(class_out)
`ifdef HAS_FRAME_UPDATE
        , .frame_update(frame_update)
`endif
    );
`ifdef HAS_FRAME_UPDATE
    always @(negedge pix_clk) begin
        if (!pix_rst_n) last_update = 0;
        else begin
            if (frame_update) begin
                if (last_update) $fatal(1,"frame_update exceeded one pixel clock");
                update_count = update_count + 1;
            end
            last_update = frame_update;
        end
    end
`endif
    task check_snapshot;
        input integer base;
        input integer cls;
        begin
            checks = checks + 1;
            if ({p7,p6,p5,p4,p3,p2,p1,p0} !==
                {8'(base+7),8'(base+6),8'(base+5),8'(base+4),
                 8'(base+3),8'(base+2),8'(base+1),8'(base)})
                $fatal(1,"incoherent or wrong probability snapshot base=%0d",base);
            if (class_out !== cls[3:0] || ready !== 1'b1)
                $fatal(1,"class/ready did not accompany the probabilities");
        end
    endtask
    task send_result;
        input integer base;
        input integer cls;
        integer i;
        begin
            for (i=0; i<8; i=i+1) begin
                @(negedge core_clk);
                probs_valid = 1;
                probs_idx = i;
                probs_pct = base+i;
                top1 = cls;
            end
            @(negedge core_clk); probs_valid = 0;
            repeat(16) @(negedge pix_clk);
        end
    endtask
    task commit_frame;
        begin
            @(negedge pix_clk); frame_start = 1;
            @(negedge pix_clk); frame_start = 0;
            repeat(3) @(negedge pix_clk);
        end
    endtask
    initial begin
        repeat(5) @(negedge pix_clk);
        core_rst_n=1; pix_rst_n=1;
        repeat(8) @(negedge pix_clk);
        if (ready !== 0 || {p7,p6,p5,p4,p3,p2,p1,p0} !== 64'b0)
            $fatal(1,"reset did not produce an empty result");
        // An incomplete inference must not become a visible snapshot.
        @(negedge core_clk); probs_valid=1; probs_idx=0; probs_pct=77;
        @(negedge core_clk); probs_valid=0;
        repeat(16) @(negedge pix_clk);
        commit_frame();
        if (ready !== 0) $fatal(1,"incomplete result became visible");
        send_result(10,2);
        if (ready !== 0) $fatal(1,"result became visible outside frame_start");
        commit_frame(); check_snapshot(10,2);
        send_result(20,2);
        check_snapshot(10,2);
        commit_frame(); check_snapshot(20,2);
        // Sticky ready and an unchanged class cannot identify this second event.
        send_result(30,6);
        check_snapshot(20,2);
        commit_frame(); check_snapshot(30,6);
        repeat(5) begin commit_frame(); check_snapshot(30,6); end
`ifdef HAS_FRAME_UPDATE
        if (update_count !== 3) $fatal(1,"expected exactly 3 event pulses, got %0d", update_count);
        $display("MODIFIED_PASS coherent_snapshots=3 repeated_class_events=2 update_pulses=3 idle_frames=5 checks=%0d",checks);
`else
        $display("BASELINE_PASS coherent_snapshots=3 repeated_class_events=2 sticky_ready=1 idle_frames=5 checks=%0d",checks);
`endif
        $finish;
    end
    initial begin #100000; $fatal(1,"test timeout"); end
endmodule
