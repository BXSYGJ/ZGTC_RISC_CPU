`timescale 1ns/1ps
module cache_valid_banks_tb;
    parameter integer SET_BITS=6;
    parameter integer READ_ONLY=0;
    localparam integer SETS=1<<SET_BITS;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,sample_ready=0,r_valid=0,r_last=0,r_error=0,failed=0;
    reg [31:0] req_address=0,random_state=32'h9b13d8e7;
    reg [2*SETS-1:0] valid_pattern=0,pattern_work=0;
    reg [3:0] driven_state=0;
    reg [SET_BITS:0] driven_victim=0;
    reg [1:0] driven_beat=0;
    reg expected0=0,expected1=0;
    integer checks=0,samples=0,holds=0,fill0=0,fill1=0,rejected=0,priority_checks=0;
    integer trial_index,line_index,set_index;
    rv32_cache #(.ADDRESS_BITS(24),.SET_BITS(SET_BITS),.WORD_BITS(2),.READ_ONLY(READ_ONLY)) cache(
        .clk(clk),.rst_n(rst_n),.req_address(req_address),.req_valid(1'b0),.req_write(1'b0),
        .req_data(32'b0),.req_strobe(4'b0),.rsp_ready(1'b0),.flush_valid(1'b0),
        .cmd_ready(1'b0),.w_ready(1'b0),.b_valid(1'b0),.b_error(1'b0),
        .r_valid(r_valid),.r_data(32'b0),.r_last(r_last),.r_error(r_error));
    rv32_cache_reference #(.ADDRESS_BITS(24),.SET_BITS(SET_BITS),.WORD_BITS(2),.READ_ONLY(READ_ONLY)) reference(
        .clk(clk),.rst_n(rst_n),.req_address(req_address),.req_valid(1'b0),.req_write(1'b0),
        .req_data(32'b0),.req_strobe(4'b0),.rsp_ready(1'b0),.flush_valid(1'b0),
        .cmd_ready(1'b0),.w_ready(1'b0),.b_valid(1'b0),.b_error(1'b0),
        .r_valid(r_valid),.r_data(32'b0),.r_last(r_last),.r_error(r_error));
    task advance_random;
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
        end
    endtask
    task step;
        begin
            @(posedge clk);
            if(!rst_n) begin expected0=0; expected1=0; end
            else if(sample_ready) begin
                set_index=int'(req_address[SET_BITS+3:4]);
                expected0=valid_pattern[set_index]; expected1=valid_pattern[SETS+set_index];
                samples=samples+1;
                if(driven_state==6 && r_valid && r_last && driven_beat==3 && !r_error && !failed)
                    priority_checks=priority_checks+1;
            end else if(driven_state==6 && r_valid && r_last && driven_beat==3 && !r_error && !failed) begin
                if(driven_victim[SET_BITS]) begin expected1=1; fill1=fill1+1; end
                else begin expected0=1; fill0=fill0+1; end
            end else begin
                holds=holds+1;
                if(driven_state==6) rejected=rejected+1;
            end
            #1;
            checks=checks+1;
            if({cache.lookup_valid1,cache.lookup_valid0}!=={expected1,expected0})
                $fatal(1,"FAIL valid_banks candidate check=%0d set=%0d expected=%b%b actual=%b%b",checks,set_index,expected1,expected0,cache.lookup_valid1,cache.lookup_valid0);
            if({reference.lookup_valid1,reference.lookup_valid0}!=={expected1,expected0})
                $fatal(1,"FAIL valid_banks reference check=%0d",checks);
            @(negedge clk);
        end
    endtask
    initial begin
        force cache.valid=valid_pattern; force reference.valid=valid_pattern;
        force cache.state=driven_state; force reference.state=driven_state;
        force cache.victim=driven_victim; force reference.victim=driven_victim;
        force cache.beat=driven_beat; force reference.beat=driven_beat;
        force cache.fill_failed=failed; force reference.fill_failed=failed;
        force cache.req_ready=sample_ready; force reference.req_ready=sample_ready;
        step(); rst_n=1;
        for(trial_index=0;trial_index<32*SETS;trial_index=trial_index+1) begin
            for(line_index=0;line_index<2*SETS;line_index=line_index+1) begin
                advance_random(); pattern_work[line_index]=random_state[0];
            end
            valid_pattern=pattern_work;
            req_address=32'(trial_index%SETS)<<4; sample_ready=1;
            driven_state=0; r_valid=0; r_last=0; r_error=0; failed=0; step();
            advance_random(); req_address=random_state; sample_ready=0; step();
            driven_state=6; r_valid=1; r_last=1; driven_beat=3;
            driven_victim=(SET_BITS+1)'(trial_index%2)<<SET_BITS; step();
            r_error=1; step();
        end
        for(trial_index=0;trial_index<16384;trial_index=trial_index+1) begin
            advance_random(); req_address=random_state;
            sample_ready=random_state[0]; driven_state=random_state[1] ? 6 : 0;
            driven_victim=(SET_BITS+1)'(random_state>>2); driven_beat=random_state[3:2];
            r_valid=random_state[4]; r_last=random_state[5]; r_error=random_state[6]; failed=random_state[7];
            valid_pattern={valid_pattern[2*SETS-2:0],random_state[8]};
            rst_n=(trial_index%257)!=0; step();
        end
        if(samples<32*SETS || holds<32*SETS || fill0<16*SETS || fill1<16*SETS || rejected<32*SETS || priority_checks==0)
            $fatal(1,"FAIL valid_banks coverage");
        $display("PASS valid_banks checks=%0d sets=%0d readonly=%0d samples=%0d holds=%0d fill0=%0d fill1=%0d rejected=%0d priority=%0d",checks,SET_BITS,READ_ONLY,samples,holds,fill0,fill1,rejected,priority_checks);
        $finish;
    end
    initial begin #20000000; $fatal(1,"FAIL valid_banks watchdog"); end
endmodule
