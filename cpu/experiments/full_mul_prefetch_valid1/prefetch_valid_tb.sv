`timescale 1ns/1ps
module prefetch_valid_tb;
    parameter integer RESPONSE_DELAY=16;
    parameter integer PREDICTOR=1;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    wire i_req_valid,i_rsp_ready,d_req_valid,d_rsp_ready,d_req_write,maintenance_valid;
    wire [31:0] i_req_address,d_req_address,d_req_data;
    wire [3:0] d_req_strobe;
    wire i_req_ready=!i_rsp_valid;
    wire d_req_ready=!d_rsp_valid && !response_pending;
    reg i_rsp_valid=0,d_rsp_valid=0,response_pending=0;
    reg [31:0] i_rsp_data=0;
    wire i_rsp_error=0,d_rsp_error=0,maintenance_ready=1;
    wire [31:0] d_rsp_data=0;
    wire irq_external=0,irq_software=0,irq_timer=0;
    wire [63:0] timer_value=0;
    wire trace_valid,trace_write,trap_valid;
    wire [31:0] trace_pc,trace_instruction,trace_data,trap_pc,trap_cause,trap_value;
    wire [4:0] trace_rd,pipeline_valid;
    wire [63:0] cycle_count,retired_count;
    reg [31:0] memory[0:16383];
    reg [31:0] expected[0:6];
    integer delay_remaining=0,stores=0,multiplies=0,expired=0,success_wait=0;
    integer available=0,fallback=0;
    reg passed=0;
    string firmware;
    rv32_core #(.BTB_INDEX_BITS(8),.BTB_ADDRESS_BITS(16),.ENABLE_PREDICTOR(PREDICTOR),
        .EARLY_D_REQUEST(1),.FETCH_OVERLAP(1),.ENABLE_M(1),.LOAD_USE_BUBBLE(1)) core(.*);
    initial begin
        if(!$value$plusargs("firmware=%s",firmware)) $fatal(1,"Missing firmware");
        $readmemh(firmware,memory);
        expected[0]=63; expected[1]=0; expected[2]=0; expected[3]=0; expected[4]=99; expected[5]=117; expected[6]=0;
        #1; rst_n=1; #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
    end
    always @(posedge clk) if(rst_n) begin
        if(i_rsp_valid && i_rsp_ready) i_rsp_valid<=0;
        if(i_req_valid && i_req_ready) begin
            if(i_req_address[31:16]!=0 || i_req_address[1:0]!=0) $fatal(1,"Instruction address");
            i_rsp_valid<=1; i_rsp_data<=memory[i_req_address[15:2]];
        end
        if(d_rsp_valid && d_rsp_ready) d_rsp_valid<=0;
        if(d_req_valid && d_req_ready) begin
            if(!d_req_write || d_req_strobe!=15) $fatal(1,"Unexpected data request");
            if(d_req_address==32'h10000000 && d_req_data==7 && !passed) passed=1;
            else $fatal(1,"FAIL prefetch_valid unexpected store");
            response_pending<=1; delay_remaining<=RESPONSE_DELAY;
        end else if(response_pending) begin
            if(delay_remaining==0) begin response_pending<=0; d_rsp_valid<=1; end
            else delay_remaining<=delay_remaining-1;
        end
        if(trap_valid) $fatal(1,"Unexpected trap");
        if(trace_valid && trace_instruction[6:0]==7'h33 && trace_instruction[31:25]==1 && trace_instruction[14:12]==0) begin
            if(multiplies>=7 || !trace_write || trace_data!==expected[multiplies])
                $fatal(1,"FAIL prefetch_valid retired multiply ordinal=%0d data=%08x",multiplies,trace_data);
            multiplies=multiplies+1;
        end
        if(passed) begin
            success_wait=success_wait+1;
            if(success_wait==64) begin
                if(multiplies!=7 || available<2 || fallback<3) $fatal(1,"FAIL prefetch_valid missing coverage available=%0d fallback=%0d",available,fallback);
                $display("PASS prefetch_valid delay=%0d predictor=%0d available=%0d fallback=%0d multiplies=%0d",RESPONSE_DELAY,PREDICTOR,available,fallback,multiplies);
                $finish;
            end
        end
        if(cycle_count>5000) $fatal(1,"watchdog");
    end
    always @(posedge clk) if(rst_n) begin
        if(core.id_fire && core.id_instruction[6:0]==7'h33 && core.id_instruction[31:25]==1 && core.id_instruction[14:12]==0) begin
            if(core.id_rs1==0 || core.id_rs2==0 || !core.id_register_a_valid || !core.id_register_b_valid) fallback=fallback+1;
        end
        if(core.mul_precompute) begin
            available=available+1;
            if(core.id_rs1==0 || core.id_rs2==0 || core.mul_id_operand_a!==core.id_operand_a || core.mul_id_operand_b!==core.id_operand_b)
                $fatal(1,"FAIL prefetch_valid unsafe raw operands");
        end
    end
    always @(posedge clk) if(rst_n && core.mul_precomputed && !core.ex_fire) begin
        expired=expired+1;
        #1;
        if(core.mul_precomputed!==1'b0) $fatal(1,"FAIL expired marker retained");
    end
endmodule

