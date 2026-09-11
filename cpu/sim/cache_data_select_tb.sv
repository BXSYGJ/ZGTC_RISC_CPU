`timescale 1ns/1ps
module cache_data_select_tb;
    reg reset_n;
    reg select_way,forward0,forward1;
    reg [31:0] payload0,payload1,payload_forward;
    reg [31:0] expected;
    integer controls,pattern,checks;
    rv32_cache #(.SET_BITS(1),.READ_ONLY(0)) cache (
        .clk(1'b0),.rst_n(reset_n),.req_valid(1'b0),.req_address(32'b0),
        .req_write(1'b0),.req_data(32'b0),.req_strobe(4'b0),.rsp_ready(1'b0),
        .flush_valid(1'b0),.cmd_ready(1'b0),.w_ready(1'b0),.b_valid(1'b0),
        .b_error(1'b0),.r_valid(1'b0),.r_data(32'b0),.r_last(1'b0),.r_error(1'b0)
    );
    initial begin
        reset_n=0; checks=0;
        #1; reset_n=1;
        force cache.hit1=select_way;
        force cache.synchronous_writable.forward_way0=forward0;
        force cache.synchronous_writable.forward_way1=forward1;
        force cache.synchronous_writable.read_way0=payload0;
        force cache.synchronous_writable.read_way1=payload1;
        force cache.synchronous_writable.forward_data=payload_forward;
        for(controls=0;controls<8;controls=controls+1) begin
            {select_way,forward0,forward1}=controls[2:0];
            for(pattern=0;pattern<104;pattern=pattern+1) begin
                payload0=0; payload1=0; payload_forward=0;
                if(pattern<32) payload0=32'b1<<pattern;
                else if(pattern<64) payload1=32'b1<<(pattern-32);
                else if(pattern<96) payload_forward=32'b1<<(pattern-64);
                else case(pattern)
                    96: begin payload0=32'hffffffff; payload1=32'haaaaaaaa; payload_forward=32'h55555555; end
                    97: begin payload0=32'haaaaaaaa; payload1=32'h55555555; payload_forward=32'hffffffff; end
                    98: begin payload0=32'h55555555; payload1=32'hffffffff; payload_forward=32'haaaaaaaa; end
                    99: begin payload0=32'h01234567; payload1=32'h89abcdef; payload_forward=32'h76543210; end
                    100: payload0=32'hxxxxxxxx;
                    101: payload1=32'hxxxxxxxx;
                    102: payload_forward=32'hxxxxxxxx;
                    103: begin payload0=32'hxxxxxxxx; payload1=32'hxxxxxxxx; payload_forward=32'hxxxxxxxx; end
                    default: $fatal(1,"Unexpected pattern");
                endcase
                expected=select_way ? (forward1 ? payload_forward : payload1) : (forward0 ? payload_forward : payload0);
                #1;
                if(cache.current_word!==expected) $fatal(1,"FAIL data mux controls=%0d pattern=%0d",controls,pattern);
                checks=checks+1;
            end
        end
        if(checks!=832) $fatal(1,"Missing data selector cases");
        $display("PASS isolated data selector cases=%0d control_combinations=8 walking_bits=96 unknown_patterns=4",checks);
        $finish;
    end
endmodule
