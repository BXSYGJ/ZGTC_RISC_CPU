`timescale 1ns/1ps
module cached_core_tb;
    parameter integer PREDICTOR=1;
    parameter integer ICACHE_SET_BITS=0;
    parameter integer CACHE_SETS=1;
    parameter integer ENABLE_CACHE=1;
    parameter integer LOAD_USE_BUBBLE=0;
    parameter integer FAST_ICACHE_HIT=0;
    parameter integer FAST_DCACHE_READ=0;
    parameter integer FAST_DCACHE_WRITE=0;
    parameter integer FETCH_OVERLAP=0;
    parameter integer DATA_OVERLAP=0;
    parameter integer EARLY_D_REQUEST=0;
    parameter integer BTB_INDEX_BITS=4;
    localparam integer MEMORY_ADDRESS_BITS=ICACHE_SET_BITS==10 ? 13 : 12;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0;
    wire i_req_valid,i_req_ready,i_rsp_valid,i_rsp_ready,i_rsp_error;
    wire d_req_valid,d_req_ready,d_req_write,d_rsp_valid,d_rsp_ready,d_rsp_error;
    wire [31:0] i_req_address,i_rsp_data,d_req_address,d_req_data,d_rsp_data;
    wire [3:0] d_req_strobe;
    wire maintenance_valid,maintenance_ready,memory_maintenance_ready,memory_maintenance_error;
    reg final_flush=0;
    wire mmio_req_valid,mmio_req_write,mmio_rsp_ready;
    wire [31:0] mmio_req_address,mmio_req_data;
    wire [3:0] mmio_req_strobe;
    reg mmio_req_ready=0,mmio_rsp_valid=0,mmio_rsp_error=0;
    reg [31:0] mmio_rsp_data=0;
    wire [31:0] i_hit_count,i_miss_count,d_hit_count,d_miss_count,d_writeback_count;
    reg [63:0] timer_value=0;
    reg irq_external=0,irq_software=0,irq_timer=0;
    wire trace_valid,trace_write,trap_valid;
    wire [31:0] trace_pc,trace_instruction,trace_data,trap_pc,trap_cause,trap_value;
    wire [4:0] trace_rd,pipeline_valid;
    wire [63:0] cycle_count,retired_count;
    reg mmio_pending=0,mmio_write=0,passed=0;
    reg [31:0] mmio_address,mmio_data;
    reg [3:0] mmio_strobe;
    reg [31:0] random_state=32'h12345678;
    reg i_held=0,d_held=0;
    reg [31:0] held_i_address,held_d_address,held_d_data;
    reg [3:0] held_d_strobe;
    reg held_d_write;
    integer delay_cycles=0,checks=0,cycles=0,trap_count=0,success_wait=0,trace_file;
    integer memory_forward_count=0,load_forward_count=0;
    integer load_wait_count=0,wb_load_forward_count=0,zero_offset_forward_count=0;
    integer fetch_outstanding=0,overlap_count=0;
    string firmware,trace_path,memory_path;
    assign maintenance_ready=memory_maintenance_ready && !final_flush;
    rv32_core #(.BTB_ADDRESS_BITS(MEMORY_ADDRESS_BITS+2),.BTB_INDEX_BITS(BTB_INDEX_BITS),.EARLY_D_REQUEST(EARLY_D_REQUEST),.FETCH_OVERLAP(FETCH_OVERLAP),.ENABLE_PREDICTOR(PREDICTOR),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE)) core(.*);
    rv32_memory_system #(.MEMORY_ADDRESS_BITS(MEMORY_ADDRESS_BITS),.DATA_OVERLAP(DATA_OVERLAP),.ICACHE_SET_BITS(ICACHE_SET_BITS),.CACHE_SET_BITS(CACHE_SETS),.ENABLE_CACHE(ENABLE_CACHE),.FETCH_OVERLAP(FETCH_OVERLAP),.FAST_DCACHE_WRITE(FAST_DCACHE_WRITE),.FAST_DCACHE_READ(FAST_DCACHE_READ),.FAST_ICACHE_HIT(FAST_ICACHE_HIT)) memory_system(
        .clk(clk),.rst_n(rst_n),
        .i_req_valid(i_req_valid),.i_req_ready(i_req_ready),.i_req_address(i_req_address),
        .i_rsp_valid(i_rsp_valid),.i_rsp_ready(i_rsp_ready),.i_rsp_data(i_rsp_data),.i_rsp_error(i_rsp_error),
        .d_req_valid(d_req_valid),.d_req_ready(d_req_ready),.d_req_address(d_req_address),.d_req_write(d_req_write),
        .d_req_data(d_req_data),.d_req_strobe(d_req_strobe),.d_rsp_valid(d_rsp_valid),.d_rsp_ready(d_rsp_ready),.d_rsp_data(d_rsp_data),.d_rsp_error(d_rsp_error),
        .maintenance_valid(maintenance_valid || final_flush),.maintenance_ready(memory_maintenance_ready),.maintenance_error(memory_maintenance_error),
        .mmio_req_valid(mmio_req_valid),.mmio_req_ready(mmio_req_ready),.mmio_req_address(mmio_req_address),.mmio_req_write(mmio_req_write),
        .mmio_req_data(mmio_req_data),.mmio_req_strobe(mmio_req_strobe),.mmio_rsp_valid(mmio_rsp_valid),.mmio_rsp_ready(mmio_rsp_ready),.mmio_rsp_data(mmio_rsp_data),.mmio_rsp_error(mmio_rsp_error),
        .i_hit_count(i_hit_count),.i_miss_count(i_miss_count),.d_hit_count(d_hit_count),.d_miss_count(d_miss_count),.d_writeback_count(d_writeback_count)
    );
    task check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL cached_core %s cycle=%0d pc=%08x",label_text,cycles,trace_pc);
        end
    endtask
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware");
        if(!$value$plusargs("trace=%s",trace_path)) $fatal(1,"Missing trace path");
        if(!$value$plusargs("memory_out=%s",memory_path)) $fatal(1,"Missing memory output path");
        if($value$plusargs("seed=%h",random_state)) begin end
        trace_file=$fopen(trace_path,"w");
        if(!trace_file) $fatal(1,"Cannot open trace output");
        #1; rst_n=1;
        $readmemh(firmware,memory_system.ram.memory,0,4095);
        #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
    end
    always @(negedge clk) begin
        if(rst_n) begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            mmio_req_ready=!mmio_pending && !mmio_rsp_valid && random_state[0];
        end
    end
    always @(posedge clk) begin
        if(rst_n) begin
            cycles=cycles+1; timer_value<=timer_value+1;
            if(i_rsp_valid && i_rsp_ready) begin
                check(fetch_outstanding==1,"fetch response has exactly one outstanding request");
                fetch_outstanding=fetch_outstanding-1;
            end
            if(i_req_valid && i_req_ready) fetch_outstanding=fetch_outstanding+1;
            check(fetch_outstanding>=0 && fetch_outstanding<=1,"single outstanding fetch invariant");
            if(i_req_valid && i_req_ready && i_rsp_valid && i_rsp_ready) overlap_count=overlap_count+1;
            if(i_held) check(i_req_valid && i_req_address===held_i_address,"held fetch request");
            if(d_held) check(d_req_valid && d_req_address===held_d_address && d_req_data===held_d_data && d_req_strobe===held_d_strobe && d_req_write===held_d_write,"held data request");
            i_held=i_req_valid && !i_req_ready; held_i_address=i_req_address;
            d_held=d_req_valid && !d_req_ready; held_d_address=d_req_address; held_d_data=d_req_data; held_d_strobe=d_req_strobe; held_d_write=d_req_write;
            if(mmio_req_valid && mmio_req_ready) begin
                check(!mmio_pending,"one MMIO transaction");
                mmio_pending<=1; mmio_address<=mmio_req_address; mmio_data<=mmio_req_data; mmio_strobe<=mmio_req_strobe; mmio_write<=mmio_req_write;
                delay_cycles<=int'(random_state[3:1]);
            end
            if(mmio_pending && !mmio_rsp_valid) begin
                if(delay_cycles==0) begin
                    mmio_rsp_valid<=1; mmio_rsp_error<=0;
                    if(mmio_address==32'h10000000 && mmio_write) begin
                        check(mmio_data==32'hcafe0001 && mmio_strobe==15,"firmware success signature"); passed<=1;
                    end else if(mmio_address==32'h10000004 && mmio_write) irq_timer<=mmio_data[0];
                    else mmio_rsp_error<=1;
                end else delay_cycles<=delay_cycles-1;
            end
            if(mmio_rsp_valid && mmio_rsp_ready) begin mmio_rsp_valid<=0; mmio_pending<=0; end
            if(trace_valid) begin
                $fdisplay(trace_file,"R %08x %08x %0d %0d %08x",trace_pc,trace_instruction,trace_write,trace_rd,trace_data);
                check(!trace_write || trace_rd!=0,"x0 invariant");
            end
            if(trap_valid) begin
                trap_count=trap_count+1;
                $fdisplay(trace_file,"T %08x %08x %08x",trap_pc,trap_cause,trap_value);
                check(trap_count<=13,"bounded trap count");
            end
            if(core.ex_fire && core.wb_valid && core.wb_writes && core.wb_rd!=0 && core.wb_instruction[6:0]==7'h03 &&
                ((core.ex_decode.uses_rs1 && core.ex_rs1==core.wb_rd) || (core.ex_decode.uses_rs2 && core.ex_rs2==core.wb_rd)))
                wb_load_forward_count=wb_load_forward_count+1;
            if(core.ex_valid && core.load_use_wait && core.mem_fire && !core.mem_flush) begin
                load_wait_count=load_wait_count+1;
                check(!core.ex_fire && !((core.ex_decode.is_branch && core.ex_instruction[14:13]==0) || (core.ex_decode.is_load && core.ex_decode.immediate==0)),"non-bypass consumer held on load completion");
            end
            if(core.ex_fire && core.mem_valid && core.mem_writes && core.mem_rd!=0 &&
                ((core.ex_decode.uses_rs1 && core.ex_rs1==core.mem_rd) || (core.ex_decode.uses_rs2 && core.ex_rs2==core.mem_rd))) begin
                memory_forward_count=memory_forward_count+1;
                if(core.mem_load) begin
                    load_forward_count=load_forward_count+1;
                    check((core.ex_decode.is_branch && core.ex_instruction[14:13]==0) || (core.ex_decode.is_load && core.ex_decode.immediate==0),"only BEQ/BNE or zero-offset load may bypass a MEM load");
                    if(core.ex_decode.is_load) begin
                        zero_offset_forward_count=zero_offset_forward_count+1;
                        check(core.effective_address===core.mem_value,"zero-offset dependent load uses current memory result");
                    end
                end
            end
            if(memory_maintenance_ready) check(!memory_maintenance_error,"cache maintenance success");
            if(passed) begin
                success_wait=success_wait+1;
                if(success_wait==12) final_flush<=1;
            end
            if(final_flush && memory_maintenance_ready) begin
                if(FETCH_OVERLAP!=0 && ENABLE_CACHE!=0) check(overlap_count>0,"overlapping request and response exercised");
                check(trap_count==13 && !irq_timer,"all traps handled and interrupt acknowledged");
                check(memory_system.ram.memory[2048]==32'hbeefaaff,"dirty data reaches RAM");
                if(ENABLE_CACHE!=0) check(i_hit_count>0 && i_miss_count>0 && d_hit_count>0 && d_miss_count>0 && d_writeback_count>0,"I/D cache paths exercised");
                else check(i_hit_count==0 && i_miss_count==0 && d_hit_count==0 && d_miss_count==0 && d_writeback_count==0,"cache bypass counters zero");
                check(LOAD_USE_BUBBLE!=0 && load_wait_count>0 && wb_load_forward_count>0 && load_forward_count>0 && zero_offset_forward_count>0,"selective equality and zero-offset bypass coverage");
                $display("PASS cached_core checks=%0d cycles=%0d traps=%0d I=%0d/%0d D=%0d/%0d WB=%0d forwarding=%0d load_forwarding=%0d sets_bits=%0d predictor=%0d",checks,cycle_count,trap_count,i_hit_count,i_miss_count,d_hit_count,d_miss_count,d_writeback_count,memory_forward_count,load_forward_count,CACHE_SETS,PREDICTOR);
                $fclose(trace_file); $writememh(memory_path,memory_system.ram.memory); $finish;
            end
            if(cycles>100000) $fatal(1,"Cached core watchdog expired PC=%08x",trace_pc);
        end
    end
    always @(posedge clk) if(rst_n && core.ex_valid) begin
        if(core.ex_muldiv && core.execute_common_exception!==core.execute_exception)
            $fatal(1,"M exception qualification differs from canonical exception");
        if((core.ex_decode.is_load || core.ex_decode.is_store) && core.execute_data_exception!==core.execute_exception)
            $fatal(1,"Data exception qualification differs from canonical exception");
    end
endmodule
