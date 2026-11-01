`timescale 1ns/1ps
module scan_fixture_tb;
    reg clk=0; always #5 clk=~clk;
    reg fixture_reset_n=0,scan_in=0,scan_shift=0,scan_update=0,scan_capture=0;
    wire scan_out;
    bare_core_scan_top uut(.clk(clk),.fixture_reset_n(fixture_reset_n),.scan_in(scan_in),.scan_shift(scan_shift),.scan_update(scan_update),.scan_capture(scan_capture),.scan_out(scan_out));
    localparam integer N=176, M=471;
    reg [N-1:0] pattern,previous;
    reg [M-1:0] captured;
    integer trial,k;
    initial begin
        previous=0;
        repeat(3) @(negedge clk); fixture_reset_n=1;
        for(trial=0;trial<N+3;trial=trial+1) begin
            pattern=0;
            if(trial<N) pattern[trial]=1;
            else if(trial==N) pattern={N{1'b1}};
            else if(trial==N+1) for(k=0;k<N;k=k+1) pattern[k]=(k%2);
            @(negedge clk); scan_shift=1;
            for(k=N-1;k>=0;k=k-1) begin
                scan_in=pattern[k]; @(posedge clk); #1;
                if(uut.active_inputs!==previous) $fatal(1,"Active core inputs changed without scan_update");
                @(negedge clk);
            end
            scan_shift=0; scan_update=1; @(posedge clk); #1;
            if(uut.active_inputs!==pattern) $fatal(1,"Input scan/update mismatch");
            if(uut.core_boundary.rst_n!==pattern[0]) $fatal(1,"Core input port mismatch: rst_n");
            if(uut.core_boundary.i_req_ready!==pattern[1]) $fatal(1,"Core input port mismatch: i_req_ready");
            if(uut.core_boundary.i_rsp_valid!==pattern[2]) $fatal(1,"Core input port mismatch: i_rsp_valid");
            if(uut.core_boundary.i_rsp_data!==pattern[34:3]) $fatal(1,"Core input port mismatch: i_rsp_data");
            if(uut.core_boundary.i_rsp_pair_data!==pattern[66:35]) $fatal(1,"Core input port mismatch: i_rsp_pair_data");
            if(uut.core_boundary.i_rsp_is_c!==pattern[68:67]) $fatal(1,"Core input port mismatch: i_rsp_is_c");
            if(uut.core_boundary.i_rsp_pair_is_c!==pattern[70:69]) $fatal(1,"Core input port mismatch: i_rsp_pair_is_c");
            if(uut.core_boundary.i_rsp_pair_valid!==pattern[71]) $fatal(1,"Core input port mismatch: i_rsp_pair_valid");
            if(uut.core_boundary.i_rsp_error!==pattern[72]) $fatal(1,"Core input port mismatch: i_rsp_error");
            if(uut.core_boundary.d_req_ready!==pattern[73]) $fatal(1,"Core input port mismatch: d_req_ready");
            if(uut.core_boundary.d_rsp_valid!==pattern[74]) $fatal(1,"Core input port mismatch: d_rsp_valid");
            if(uut.core_boundary.d_rsp_data!==pattern[106:75]) $fatal(1,"Core input port mismatch: d_rsp_data");
            if(uut.core_boundary.d_rsp_error!==pattern[107]) $fatal(1,"Core input port mismatch: d_rsp_error");
            if(uut.core_boundary.maintenance_ready!==pattern[108]) $fatal(1,"Core input port mismatch: maintenance_ready");
            if(uut.core_boundary.timer_value!==pattern[172:109]) $fatal(1,"Core input port mismatch: timer_value");
            if(uut.core_boundary.irq_external!==pattern[173]) $fatal(1,"Core input port mismatch: irq_external");
            if(uut.core_boundary.irq_software!==pattern[174]) $fatal(1,"Core input port mismatch: irq_software");
            if(uut.core_boundary.irq_timer!==pattern[175]) $fatal(1,"Core input port mismatch: irq_timer");
            previous=pattern;
            @(negedge clk); scan_update=0; scan_capture=1; captured=uut.core_outputs;
            @(posedge clk); #1;
            if(uut.output_shift!==captured) $fatal(1,"Parallel output capture mismatch");
            @(negedge clk); scan_capture=0; scan_shift=1;
            for(k=0;k<M;k=k+1) begin
                if(scan_out!==captured[k]) $fatal(1,"Serial output observation mismatch");
                @(posedge clk); #1; @(negedge clk);
            end
            scan_shift=0;
        end
        $display("SCAN_FIXTURE_PASS patterns=%0d input_bits=%0d output_bits=%0d",N+3,N,M);
        $finish;
    end
endmodule
