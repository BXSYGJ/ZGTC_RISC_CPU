`timescale 1ns/1ps
module core_tb;
    parameter integer PREDICTOR=1;
    parameter integer EARLY_D_REQUEST=0;
    parameter integer BTB_INDEX_BITS=4;
    parameter integer LOAD_USE_BUBBLE=0;
    parameter integer POISON_INVALID_DATA=0;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0;
    wire i_req_valid,i_rsp_ready,d_req_valid,d_rsp_ready,d_req_write,maintenance_valid;
    reg i_req_ready=0,i_rsp_valid=0,i_rsp_error=0;
    reg d_req_ready=0,d_rsp_valid=0,d_rsp_error=0,maintenance_ready=0;
    wire [31:0] i_req_address,d_req_address,d_req_data;
    wire [3:0] d_req_strobe;
    reg [31:0] i_rsp_data=0,d_rsp_data=0;
    reg [63:0] timer_value=0;
    reg irq_external=0,irq_software=0,irq_timer=0;
    wire trace_valid,trace_write,trap_valid;
    wire [31:0] trace_pc,trace_instruction,trace_data,trap_pc,trap_cause,trap_value;
    wire [4:0] trace_rd,pipeline_valid;
    wire [63:0] cycle_count,retired_count;
    reg [31:0] memory[0:4095];
    reg i_pending=0,d_pending=0;
    reg [31:0] i_address=0,d_address=0,d_data=0;
    reg [3:0] d_strobe=0;
    reg d_write=0;
    integer i_delay=0,d_delay=0,checks=0,trap_count=0,cycles=0,byte_index,trace_file;
    integer success_wait=0;
    integer early_accepted=0,early_fallback=0;
    integer poisoned_load_waits=0,poisoned_load_faults=0;
    reg passed=0;
    reg [31:0] random_state=32'h12345678;
    reg i_held=0,d_held=0;
    reg [31:0] held_i_address,held_d_address,held_d_data;
    reg [3:0] held_d_strobe;
    reg held_d_write;
    string firmware,trace_path,memory_path;
    rv32_core #(.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.BTB_INDEX_BITS(BTB_INDEX_BITS),.EARLY_D_REQUEST(EARLY_D_REQUEST),.ENABLE_PREDICTOR(PREDICTOR)) core(.*);
    task check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL core %s cycle=%0d pc=%08x",label_text,cycles,trace_pc);
        end
    endtask
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware image");
        if(!$value$plusargs("trace=%s",trace_path)) $fatal(1,"Missing trace path");
        if(!$value$plusargs("memory_out=%s",memory_path)) $fatal(1,"Missing memory output path");
        if($value$plusargs("seed=%h",random_state)) begin end
        $readmemh(firmware,memory);
        trace_file=$fopen(trace_path,"w");
        if(!trace_file) $fatal(1,"Cannot open trace output");
        #1; rst_n=1; #1; rst_n=0;
        repeat(4) @(negedge clk);
        rst_n=1;
    end
    always @(negedge clk) begin
        if(rst_n) begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            i_req_ready=!i_pending && !i_rsp_valid && random_state[0];
            d_req_ready=!d_pending && !d_rsp_valid && random_state[1];
            maintenance_ready=random_state[2];
            if(POISON_INVALID_DATA!=0 && !d_rsp_valid) begin
                d_rsp_data=random_state;
                d_rsp_error=random_state[3];
            end
        end
    end
    always @(posedge clk) begin
        if(rst_n) begin
            cycles=cycles+1;
            timer_value<=timer_value+1;
            if(core.mem_valid && core.mem_writes) check(!core.mem_store,"store never qualifies for register forwarding");
            if(POISON_INVALID_DATA!=0 && core.mem_valid && core.mem_load && !core.mem_exception && core.ex_valid) begin
                if(!d_rsp_valid) begin
                    check(!core.ex_fire && !core.early_data_request,"invalid load response cannot execute or issue a younger request");
                    if(core.mem_rd!=0 && core.mem_writes && LOAD_USE_BUBBLE==0) begin
                        if(core.ex_decode.uses_rs1 && core.ex_rs1==core.mem_rd) begin
                            check(core.forwarded_a===core.mem_value,"load operand A selection independent of response qualification");
                            poisoned_load_waits=poisoned_load_waits+1;
                        end
                        if(core.ex_decode.uses_rs2 && core.ex_rs2==core.mem_rd) begin
                            check(core.forwarded_b===core.mem_value,"load operand B selection independent of response qualification");
                            poisoned_load_waits=poisoned_load_waits+1;
                        end
                    end
                end else if(d_rsp_error) begin
                    check(!core.ex_fire && !core.early_data_request,"faulted load cannot execute a younger instruction");
                    poisoned_load_faults=poisoned_load_faults+1;
                end
            end
            if(core.early_data_request) begin
                check(core.ex_fire && !core.execute_exception && !core.mem_flush,"early request is committed to MEM without exception or flush");
                check(!(core.mem_valid && core.mem_access && !core.mem_sent),"early request does not displace an older request");
                if(d_req_ready) early_accepted=early_accepted+1;
                else early_fallback=early_fallback+1;
            end
            if(i_held) check(i_req_valid && i_req_address===held_i_address,"instruction request stability");
            if(d_held) check(d_req_valid && d_req_address===held_d_address && d_req_data===held_d_data &&
                d_req_strobe===held_d_strobe && d_req_write===held_d_write,"data request stability");
            i_held=i_req_valid && !i_req_ready;
            held_i_address=i_req_address;
            d_held=d_req_valid && !d_req_ready;
            held_d_address=d_req_address; held_d_data=d_req_data; held_d_strobe=d_req_strobe; held_d_write=d_req_write;
            if(i_req_valid && i_req_ready) begin
                check(!i_pending,"one outstanding instruction request");
                i_pending<=1; i_address<=i_req_address; i_delay<=int'(random_state[5:3]);
            end
            if(i_pending && !i_rsp_valid) begin
                if(i_delay==0) begin
                    i_rsp_valid<=1; i_rsp_error<=i_address>=16384;
                    i_rsp_data<=i_address<16384 ? memory[i_address[13:2]] : 0;
                end else i_delay<=i_delay-1;
            end
            if(i_rsp_valid && i_rsp_ready) begin i_rsp_valid<=0; i_pending<=0; end
            if(d_req_valid && d_req_ready) begin
                check(!d_pending,"one outstanding data request");
                d_pending<=1; d_address<=d_req_address; d_data<=d_req_data;
                d_strobe<=d_req_strobe; d_write<=d_req_write;
                d_delay<=(POISON_INVALID_DATA!=0 && !d_req_write ? 24 : 0)+int'(random_state[8:6]);
            end
            if(d_pending && !d_rsp_valid) begin
                if(d_delay==0) begin
                    d_rsp_valid<=1; d_rsp_data<=0; d_rsp_error<=0;
                    if(d_address==32'h10000000 && d_write) begin
                        check(d_data==32'hcafe0001 && d_strobe==15,"firmware success signature");
                        passed<=1;
                    end else if(d_address==32'h10000004 && d_write) begin
                        irq_timer<=d_data[0];
                    end else if(d_address<16384) begin
                        d_rsp_data<=memory[d_address[13:2]];
                        if(d_write) begin
                            for(byte_index=0;byte_index<4;byte_index=byte_index+1)
                                if(d_strobe[byte_index]) memory[d_address[13:2]][byte_index*8+:8]<=d_data[byte_index*8+:8];
                        end
                    end else d_rsp_error<=1;
                end else d_delay<=d_delay-1;
            end
            if(d_rsp_valid && d_rsp_ready) begin d_rsp_valid<=0; d_pending<=0; end
            if(trace_valid) begin
                $fdisplay(trace_file,"R %08x %08x %0d %0d %08x",trace_pc,trace_instruction,trace_write,trace_rd,trace_data);
                check(!trace_write || trace_rd!=0,"x0 write suppressed");
            end
            if(trap_valid) begin
                trap_count=trap_count+1;
                $fdisplay(trace_file,"T %08x %08x %08x",trap_pc,trap_cause,trap_value);
                check(trap_count<=13,"bounded exception count");
            end
            if(passed) begin
                success_wait=success_wait+1;
                if(success_wait==12) begin
                    check(trap_count==13,"all exceptions and timer interrupt observed");
                    check(memory[2048]==32'hbeefaaff,"byte strobes and fault suppression");
                    check(!irq_timer,"interrupt acknowledged");
                    if(POISON_INVALID_DATA!=0 && LOAD_USE_BUBBLE==0) begin
                        check(poisoned_load_waits>0,"poisoned dependent load coverage");
                        check(poisoned_load_faults>0,"poisoned pending load fault coverage");
                        $display("POISONED_LOAD_WAITS=%0d FAULTS=%0d",poisoned_load_waits,poisoned_load_faults);
                    end
                    if(EARLY_D_REQUEST!=0) begin
                        check(early_accepted>0,"early request accepted coverage");
                        check(early_fallback>0,"early request fallback coverage");
                        $display("EARLY_DATA accepted=%0d fallback=%0d",early_accepted,early_fallback);
                    end
                    check(link_push_observations>0,"return-stack link pushes exercised");
                $display("LINK pushes=%0d",link_push_observations);
                $display("PASS core checks=%0d traps=%0d cycles=%0d retired=%0d predictor=%0d",checks,trap_count,cycle_count,retired_count,PREDICTOR);
                    $fclose(trace_file);
                    $writememh(memory_path,memory);
                    $finish;
                end
            end
            if(cycles>60000) $fatal(1,"Core watchdog expired pc=%08x pipeline=%b",trace_pc,pipeline_valid);
        end
    end
    wire [5:0] observed_mem_classes={core.mem_branch,core.mem_load,core.mem_store,core.mem_fence_i,core.mem_csr,core.mem_mret};
    always @(posedge clk) if(rst_n) begin
        check((observed_mem_classes & (observed_mem_classes-6'b000001)) === 6'b0,"exclusive memory-stage instruction classes");
        check(core.predictor.update_valid === (core.mem_fire && core.mem_branch && !core.mem_fault),"specialized predictor training");
        check(core.predictor.invalidate === (core.mem_fire && core.mem_fence_i && !core.mem_fault),"specialized predictor invalidation");
        check(core.machine.write_valid === (core.mem_fire && core.mem_csr && core.mem_csr_write && !core.mem_fault),"specialized CSR commit");
        check(core.machine.return_from_trap === (core.mem_fire && core.mem_mret && !core.mem_fault),"specialized MRET commit");
    end
    integer link_push_observations=0;
    always @(posedge clk) begin
        if (rst_n && core.stack_commit && core.stack_call_hint) begin
            link_push_observations=link_push_observations+1;
            if (core.mem_result!==(core.mem_pc+32'd4))
                $fatal(1,"FAIL return_stack_link committed link differs from PC+4");
        end
    end
endmodule
