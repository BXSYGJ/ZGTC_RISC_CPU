`timescale 1ns/1ps
module muldiv_core_tb;
    parameter integer LOAD_USE_BUBBLE=0;
    parameter integer FETCH_OVERLAP=0;
    parameter integer EARLY_D_REQUEST=0;
    parameter integer BTB_INDEX_BITS=4;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    wire i_req_valid,i_rsp_ready,d_req_valid,d_rsp_ready,d_req_write,maintenance_valid;
    wire [31:0] i_req_address,d_req_address,d_req_data;
    wire [3:0] d_req_strobe;
    wire i_req_ready=!i_rsp_valid;
    wire d_req_ready=!d_rsp_valid;
    reg i_rsp_valid=0,d_rsp_valid=0;
    reg [31:0] i_rsp_data=0;
    wire i_rsp_error=0,d_rsp_error=0,maintenance_ready=1;
    wire [31:0] d_rsp_data=0;
    reg irq_external=0;
    wire irq_software=0,irq_timer=0;
    wire [63:0] timer_value=0;
    wire trace_valid,trace_write,trap_valid;
    wire [31:0] trace_pc,trace_instruction,trace_data,trap_pc,trap_cause,trap_value;
    wire [4:0] trace_rd,pipeline_valid;
    wire [63:0] cycle_count,retired_count;
    reg [31:0] memory[0:16383];
    reg [31:0] interrupt_pc;
    integer interrupt_delay,delay_remaining,checks=0,interrupts=0,retires_at_target=0,success_wait=0;
    reg triggered=0,delaying=0,passed=0;
    string firmware;
    rv32_core #(.BTB_INDEX_BITS(BTB_INDEX_BITS),.EARLY_D_REQUEST(EARLY_D_REQUEST),.FETCH_OVERLAP(FETCH_OVERLAP),.ENABLE_M(1),.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE)) core(.*);
    initial begin
        if(!$value$plusargs("firmware=%s",firmware) || !$value$plusargs("irq_pc=%h",interrupt_pc) ||
           !$value$plusargs("irq_delay=%d",interrupt_delay)) $fatal(1,"Missing interrupt test parameters");
        if(interrupt_delay<0 || interrupt_delay>30) $fatal(1,"Invalid interrupt delay");
        $readmemh(firmware,memory);
        #1; rst_n=1; #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
    end
    always @(negedge clk) if(rst_n) begin
        if(!triggered && core.ex_pc==interrupt_pc && (core.muldiv_started ||
           (core.multiply_divide.unit.FAST_LOW_MUL!=0 && core.ex_valid && core.ex_muldiv &&
            core.ex_instruction[14:12]==0 && core.ex_can_fire))) begin
            triggered=1; delaying=1; delay_remaining=interrupt_delay;
        end
        if(delaying) begin
            if(delay_remaining==0) begin irq_external=1; delaying=0; end
            else delay_remaining=delay_remaining-1;
        end
        if(interrupts!=0) irq_external=0;
    end
    always @(posedge clk) if(rst_n) begin
        if(i_rsp_valid && i_rsp_ready) i_rsp_valid<=0;
        if(i_req_valid && i_req_ready) begin
            if(i_req_address[31:16]!=0 || i_req_address[1:0]!=0) $fatal(1,"Unexpected instruction address");
            i_rsp_valid<=1; i_rsp_data<=memory[i_req_address[15:2]];
        end
        if(d_rsp_valid && d_rsp_ready) d_rsp_valid<=0;
        if(d_req_valid && d_req_ready) begin
            if(!d_req_write || d_req_strobe!=15 || d_req_address!=32'h10000000 || d_req_data!=32'hcafe0001)
                $fatal(1,"Interrupted muldiv program failed address=%08x data=%08x",d_req_address,d_req_data);
            if(passed) $fatal(1,"Duplicate success");
            passed<=1; d_rsp_valid<=1;
        end
        if(trap_valid) begin
            if(trap_cause!=32'h8000000b || trap_pc!=interrupt_pc || trap_value!=0 || interrupts!=0 || retires_at_target!=0)
                $fatal(1,"Interrupt was not precise cause=%08x pc=%08x",trap_cause,trap_pc);
            interrupts=interrupts+1; checks=checks+1;
        end
        if(trace_valid && trace_pc==interrupt_pc) begin
            if(interrupts!=1) $fatal(1,"Canceled M operation retired before handler");
            retires_at_target=retires_at_target+1;
            if(retires_at_target!=1) $fatal(1,"M operation retired twice after restart");
            checks=checks+1;
        end
        if(passed) begin
            success_wait=success_wait+1;
            if(success_wait==20) begin
                if(interrupts!=1 || retires_at_target!=1 || !triggered || delaying) $fatal(1,"Missing interrupt coverage");
                $display("PASS muldiv_core checks=%0d irq_pc=%08x delay=%0d loadbubble=%0d",checks,interrupt_pc,interrupt_delay,LOAD_USE_BUBBLE);
                $finish;
            end
        end
        if(cycle_count>20000) $fatal(1,"Interrupted M operation deadlocked");
    end
    always @(posedge clk) if(rst_n && core.ex_valid) begin
        if(core.ex_muldiv && core.execute_common_exception!==core.execute_exception)
            $fatal(1,"M exception qualification differs from canonical exception");
        if((core.ex_decode.is_load || core.ex_decode.is_store) && core.execute_data_exception!==core.execute_exception)
            $fatal(1,"Data exception qualification differs from canonical exception");
    end
endmodule
