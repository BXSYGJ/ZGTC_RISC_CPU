`timescale 1ns/1ps
module tb_ui_session;
    reg core_clk=0, pix_clk=0, rst=0;
    always #5 core_clk=~core_clk;
    always #7 pix_clk=~pix_clk;
    reg [3:0] keys=15;
    reg wr=0, frame_start=0;
    reg [8:0] addr=0;
    reg [31:0] data=0;
    wire [31:0] events, meta;
    wire [511:0] rows;
    wire [63:0] probs;
    wire busy;
    ui_session_bridge #(.CORE_HZ(1000)) dut (
        .core_clk(core_clk), .core_rst_n(rst), .keys_n(keys), .key_events(events),
        .write_en(wr), .write_addr(addr), .write_data(data), .busy(busy),
        .pix_clk(pix_clk), .pix_rst_n(rst), .frame_start(frame_start),
        .view_rows(rows), .view_probs(probs), .view_meta(meta)
    );
    task store(input [8:0] a, input [31:0] d);
        @(negedge core_clk); wr=1; addr=a; data=d;
        @(negedge core_clk); wr=0;
    endtask
    task frame;
        repeat(5) @(negedge pix_clk);
        frame_start=1; @(negedge pix_clk); frame_start=0;
        repeat(5) @(negedge core_clk);
    endtask
    initial begin
        repeat(5) @(negedge core_clk); rst=1;
        store('h100,'h12345678); store('h13c,'h87654321);
        store('h058,'h801); store('h05c,'h11223344); store('h060,'h55667788);
        store('h068,1);
        if (!busy || meta!=0) $fatal(1,"Snapshot must wait for a frame");
        store('h100,'hdeadbeef); store('h058,0); store('h068,1);
        frame();
        if (busy || meta!='h801 || rows[31:0]!='h12345678 || rows[511:480]!='h87654321 || probs!=64'h5566778811223344)
            $fatal(1,"Busy write corrupted atomic snapshot");
        store('h058,1); store('h068,1);
        if(meta!='h801) $fatal(1,"Mid-frame view change");
        frame(); if(meta!=1) $fatal(1,"Second snapshot missing");
        // Bounce never becomes a UI event.
        keys=14; repeat(5) @(negedge core_clk); keys=15;
        repeat(30) @(negedge core_clk);
        if(events) $fatal(1,"Bounce generated a key event");
        keys=14; repeat(100) @(negedge core_clk); keys=15;
        repeat(30) @(negedge core_clk);
        if(events!=1) $fatal(1,"Short key action missing");
        keys=14; repeat(700) @(negedge core_clk);
        if(events!='h10001) $fatal(1,"Long press missing or repeated");
        keys=15; repeat(40) @(negedge core_clk);
        if(events!='h10001) $fatal(1,"Long release also generated short action");
        keys=7; repeat(100) @(negedge core_clk); keys=15;
        repeat(30) @(negedge core_clk);
        if(events!='h11001) $fatal(1,"KEY4 not routed independently");
        $display("RESULT: PASS ui_session frame CDC, busy protection and key gestures");
        $finish;
    end
    initial begin #1000000; $fatal(1,"Watchdog"); end
endmodule
