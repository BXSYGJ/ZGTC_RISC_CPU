`timescale 1ns/1ps
module coremark_tb;
    parameter integer ENABLE_M=0;
    parameter integer ENABLE_PREDICTOR=1;
    parameter integer LOAD_USE_BUBBLE=0;
    parameter integer FAST_ICACHE_HIT=0;
    parameter integer FAST_DCACHE_READ=0;
    parameter integer FAST_DCACHE_WRITE=0;
    parameter integer FETCH_OVERLAP=0;
    parameter integer DATA_OVERLAP=0;
    parameter integer EARLY_D_REQUEST=0;
    parameter integer BTB_INDEX_BITS=4;
    parameter integer ICACHE_SET_BITS=0;
    parameter integer CACHE_SET_BITS=4;
    parameter integer ENABLE_CACHE=1;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,serial_rx=1;
    reg [7:0] gpio_input=0;
    wire serial_tx,maintenance_fault,trace_valid,trap_valid;
    wire [7:0] gpio_output;
    wire [31:0] status_code,trace_pc,trace_instruction,trap_cause;
    wire [63:0] cycle_count,retired_count;
    integer cycles=0,uart_file;
    string firmware,uart_path;
    string profile_path;
    integer profile_file,profile_cycles=0,profile_retired=0;
    integer profile_counts[0:16383];
    integer profile_events[0:11];
    reg profile_enabled=0,profile_active=0,profile_started=0,profile_finished=0;
    reg [31:0] profile_start,profile_stop;
    initial begin
        if($value$plusargs("profile=%s",profile_path)) begin
            profile_enabled=1;
            if(!$value$plusargs("profile_start=%h",profile_start) || !$value$plusargs("profile_stop=%h",profile_stop))
                $fatal(1,"Missing profile symbol boundaries");
            if(profile_start==profile_stop || profile_start[1:0]!=0 || profile_stop[1:0]!=0)
                $fatal(1,"Invalid profile boundaries");
            profile_file=$fopen(profile_path,"w");
            if(!profile_file) $fatal(1,"Cannot open profile output");
            for(integer address_index=0;address_index<16384;address_index=address_index+1) profile_counts[address_index]=0;
            for(integer event_index=0;event_index<12;event_index=event_index+1) profile_events[event_index]=0;
        end
    end
    rv32_soc #(.DATA_OVERLAP(DATA_OVERLAP),.BTB_INDEX_BITS(BTB_INDEX_BITS),.EARLY_D_REQUEST(EARLY_D_REQUEST),.ENABLE_M(ENABLE_M),.CLOCK_HZ(3200),.BAUD(100),.ENABLE_PREDICTOR(ENABLE_PREDICTOR),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.FETCH_OVERLAP(FETCH_OVERLAP),.FAST_DCACHE_WRITE(FAST_DCACHE_WRITE),.FAST_DCACHE_READ(FAST_DCACHE_READ),.FAST_ICACHE_HIT(FAST_ICACHE_HIT),.ICACHE_SET_BITS(ICACHE_SET_BITS),.CACHE_SET_BITS(CACHE_SET_BITS),.ENABLE_CACHE(ENABLE_CACHE)) soc(.*);
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware");
        if(!$value$plusargs("uart=%s",uart_path)) $fatal(1,"Missing UART log");
        uart_file=$fopen(uart_path,"w");
        if(!uart_file) $fatal(1,"Cannot open UART log");
        #1; rst_n=1; $readmemh(firmware,soc.memory_system.ram.memory);
        #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
        wait(status_code==32'hc0100000);
        @(negedge clk); serial_rx=0; repeat(32) @(negedge clk);
        for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin
            serial_rx=(8'h47 >> bit_index)&1; repeat(32) @(negedge clk);
        end
        serial_rx=1;
    end
    initial begin : uart_monitor
        reg [7:0] observed;
        forever begin
            @(negedge serial_tx);
            if(rst_n) begin
                #160; if(serial_tx!==0) $fatal(1,"UART start");
                for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin #320; observed[bit_index]=serial_tx; end
                #320; if(serial_tx!==1) $fatal(1,"UART stop");
                $fwrite(uart_file,"%c",observed);
                $write("%c",observed);
            end
        end
    end
    always @(negedge clk) if(rst_n) begin
        cycles=cycles+1;
        if(profile_enabled) begin
            if(trace_valid && trace_pc==profile_start) begin
                if(profile_started) $fatal(1,"Profile start executed more than once");
                profile_started=1;
                profile_active=1;
            end
            if(profile_active) begin
                if(trace_valid && trace_pc==profile_stop) begin
                    profile_active=0;
                    profile_finished=1;
                end else begin
                    profile_cycles=profile_cycles+1;
                    if(trace_valid) profile_events[10]=profile_events[10]+1;
                    else profile_events[11]=profile_events[11]+1;
                    if(soc.core.mem_fire && soc.core.mem_branch && !soc.core.mem_fault) begin
                        case(soc.core.mem_instruction[6:0])
                            7'h63: begin
                                profile_events[0]=profile_events[0]+1;
                                if(soc.core.mem_next_pc!=soc.core.mem_prediction) profile_events[1]=profile_events[1]+1;
                            end
                            7'h6f: begin
                                profile_events[2]=profile_events[2]+1;
                                if(soc.core.mem_next_pc!=soc.core.mem_prediction) profile_events[3]=profile_events[3]+1;
                            end
                            7'h67: begin
                                profile_events[4]=profile_events[4]+1;
                                if(soc.core.mem_next_pc!=soc.core.mem_prediction) profile_events[5]=profile_events[5]+1;
                            end
                            default: $fatal(1,"Unknown control-flow opcode");
                        endcase
                    end
                    if(soc.core.mem_valid && soc.core.mem_access && !soc.core.mem_fire) profile_events[6]=profile_events[6]+1;
                    if(soc.core.ex_valid && soc.core.ex_muldiv && !soc.core.muldiv_valid && !soc.core.execute_exception) profile_events[7]=profile_events[7]+1;
                    if(soc.core.fetch_active && soc.core.fetch_sent && !soc.core.i_rsp_valid) profile_events[8]=profile_events[8]+1;
                    if(!soc.core.if_valid && !soc.core.id_valid && !soc.core.ex_valid) profile_events[9]=profile_events[9]+1;
                    if(trace_valid) begin
                        if(trace_pc[31:16]!=0 || trace_pc[1:0]!=0) $fatal(1,"Profile PC out of executable RAM");
                        profile_counts[trace_pc[15:2]]=profile_counts[trace_pc[15:2]]+1;
                        profile_retired=profile_retired+1;
                    end
                end
            end
        end
        if(trap_valid||maintenance_fault) $fatal(1,"CoreMark trap PC=%08x cause=%08x",trace_pc,trap_cause);
        if(status_code==32'hc0100001) begin
            if(profile_enabled) begin
                if(!profile_started || !profile_finished || profile_active) $fatal(1,"Incomplete profile window");
                $fwrite(profile_file,"WINDOW start=%08x stop=%08x cycles=%0d retired=%0d\n",profile_start,profile_stop,profile_cycles,profile_retired);
                $fwrite(profile_file,"EVENTS branch_resolutions=%0d branch_redirects=%0d jal_resolutions=%0d jal_redirects=%0d jalr_resolutions=%0d jalr_redirects=%0d memory_wait_cycles=%0d muldiv_wait_cycles=%0d fetch_wait_cycles=%0d frontend_empty_cycles=%0d retiring_cycles=%0d nonretiring_cycles=%0d\n",profile_events[0],profile_events[1],profile_events[2],profile_events[3],profile_events[4],profile_events[5],profile_events[6],profile_events[7],profile_events[8],profile_events[9],profile_events[10],profile_events[11]);
                for(integer address_index=0;address_index<16384;address_index=address_index+1)
                    if(profile_counts[address_index]!=0) $fwrite(profile_file,"%08x %0d\n",address_index*4,profile_counts[address_index]);
                $fclose(profile_file);
            end
            $fclose(uart_file);
            $display("PASS CoreMark simulation finished cycles=%0d retired=%0d",cycles,retired_count);
            $finish;
        end
        if(cycles>50000000) $fatal(1,"CoreMark simulation timeout PC=%08x",trace_pc);
    end
endmodule
