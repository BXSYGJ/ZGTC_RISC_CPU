`timescale 1ns/1ps
module trap_value_tb;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    reg inject_interrupt=0;
    reg [31:0] injected_cause=0;
    reg d_rsp_valid=0,d_rsp_error=0;
    wire trap_valid;
    wire [31:0] trap_pc,trap_cause,trap_value;
    integer checks=0,bit_index;
    reg [31:0] pattern;
    rv32_core core (
        .clk(clk),.rst_n(rst_n),.i_req_ready(1'b0),.i_rsp_valid(1'b0),
        .i_rsp_data(32'b0),.i_rsp_error(1'b0),.d_req_ready(1'b1),
        .d_rsp_valid(d_rsp_valid),.d_rsp_data(32'h12345678),.d_rsp_error(d_rsp_error),
        .maintenance_ready(1'b1),.timer_value(64'b0),.irq_external(1'b0),
        .irq_software(1'b0),.irq_timer(1'b0),.trap_valid(trap_valid),
        .trap_pc(trap_pc),.trap_cause(trap_cause),.trap_value(trap_value)
    );
    task check(input condition,input string label_text);
        begin
            checks=checks+1;
            if(condition!==1'b1) $fatal(1,"trap_value %s",label_text);
        end
    endtask
    task reset_core;
        begin
            @(negedge clk); rst_n=0; inject_interrupt=0; d_rsp_valid=0; d_rsp_error=0;
            repeat(2) @(negedge clk);
            rst_n=1;
        end
    endtask
    task inject_execute(input [31:0] instruction_word,input [31:0] pc_value,
        input [31:0] operand_value,input fetch_error);
        begin
            core.id_instruction=instruction_word;
            #1;
            core.ex_decode=core.id_decode; core.ex_instruction=instruction_word;
            core.ex_pc=pc_value; core.ex_operand_a=operand_value; core.ex_operand_b=32'h5a5a5a5a;
            core.ex_error=fetch_error; core.ex_rd=instruction_word[11:7]; core.ex_valid=1;
            #1; check(core.ex_fire,"execute transfer accepted");
        end
    endtask
    task exception_case(input [31:0] instruction_word,input [31:0] pc_value,
        input [31:0] operand_value,input fetch_error,input [31:0] irq_cause,
        input [31:0] expected_cause,input [31:0] expected_value);
        integer stall_cycle;
        begin
            reset_core();
            inject_interrupt=irq_cause[31]; injected_cause=irq_cause;
            force core.mem_fire=1'b0;
            inject_execute(instruction_word,pc_value,operand_value,fetch_error);
            check(core.execute_exception && core.execute_cause===expected_cause,"execute cause priority");
            @(posedge clk); #1;
            check(core.mem_valid && core.mem_exception,"exception metadata captured");
            for(stall_cycle=0;stall_cycle<3;stall_cycle=stall_cycle+1) begin
                check(trap_pc===pc_value && trap_cause===expected_cause && trap_value===expected_value,
                    "registered exception value under stall");
                @(negedge clk);
                core.ex_pc=~pc_value; core.ex_instruction=~instruction_word;
                core.ex_operand_a=~operand_value; core.ex_error=~fetch_error;
                inject_interrupt=~inject_interrupt; injected_cause=32'hffffffff;
                @(posedge clk); #1;
            end
            @(negedge clk); release core.mem_fire; #1;
            check(trap_valid && trap_value===expected_value,"exception commit value");
            @(posedge clk); #1;
            check(!core.mem_valid,"exception consumed once");
            check(core.machine.mtval===expected_value && core.machine.mcause===expected_cause &&
                core.machine.mepc===(pc_value & 32'hfffffffc),"exception CSR capture");
        end
    endtask
    task access_fault_case(input store_access,input [31:0] address_value);
        integer stall_cycle;
        begin
            reset_core();
            inject_execute(store_access ? 32'h0020a023 : 32'h0000a183,32'h100,address_value,1'b0);
            check(!core.execute_exception,"aligned data access has no execute exception");
            @(posedge clk); #1;
            for(stall_cycle=0;stall_cycle<4;stall_cycle=stall_cycle+1) begin
                check(core.mem_valid && !trap_valid && trap_value===address_value,"pending access retains full address");
                @(negedge clk); core.ex_operand_a=~address_value; core.ex_pc=32'hffffffff;
                @(posedge clk); #1;
            end
            @(negedge clk); d_rsp_error=1; d_rsp_valid=1; #1;
            check(trap_valid && trap_cause===(store_access ? 32'd7 : 32'd5) && trap_value===address_value,
                "bus fault uses captured address");
            @(posedge clk); #1; check(!core.mem_valid,"bus fault consumed once");
            check(core.machine.mtval===address_value && core.machine.mcause===(store_access ? 32'd7 : 32'd5),
                "bus fault CSR capture");
        end
    endtask
    task pending_reset_case(input data_access);
        begin
            reset_core();
            force core.mem_fire=1'b0;
            inject_execute(data_access ? 32'h0000a183 : 32'hffffffff,32'h100,32'h80001000,1'b0);
            @(posedge clk); #1; check(core.mem_valid,"pending transaction before reset");
            @(negedge clk); rst_n=0; #1; release core.mem_fire; #1;
            check(!core.mem_valid && !trap_valid && core.machine.mtval==0,"reset cancels pending transaction");
            repeat(2) @(negedge clk); rst_n=1;
            repeat(2) @(negedge clk);
            check(!trap_valid && core.machine.mtval==0,"no stale trap after reset");
        end
    endtask
    initial begin
        force core.interrupt_pending=inject_interrupt;
        force core.interrupt_cause=injected_cause;
        for(bit_index=0;bit_index<32;bit_index=bit_index+1) begin
            pattern=32'h1 << bit_index;
            exception_case(32'h00008067,(pattern & 32'hfffffffc) | 32'h2,~pattern,1'b1,0,0,
                (pattern & 32'hfffffffc) | 32'h2);
            exception_case(32'hffffffff,pattern & 32'hfffffffc,0,1'b1,0,1,pattern & 32'hfffffffc);
            exception_case(pattern | 32'h7f,32'h100,0,1'b0,0,2,pattern | 32'h7f);
            exception_case(32'h00100073,pattern & 32'hfffffffc,0,1'b0,0,3,pattern & 32'hfffffffc);
            exception_case(32'h00008067,32'h100,pattern | 32'h3,1'b0,0,0,(pattern | 32'h3) & 32'hfffffffe);
            exception_case(32'h0000a183,32'h100,pattern | 32'h2,1'b0,0,4,pattern | 32'h2);
            exception_case(32'h0020a023,32'h100,pattern | 32'h2,1'b0,0,6,pattern | 32'h2);
            exception_case(32'h00009183,32'h100,pattern | 32'h1,1'b0,0,4,pattern | 32'h1);
            exception_case(32'h00209023,32'h100,pattern | 32'h1,1'b0,0,6,pattern | 32'h1);
            access_fault_case(1'b0,pattern & 32'hfffffffc);
            access_fault_case(1'b1,~pattern & 32'hfffffffc);
        end
        exception_case(32'h00000073,32'h100,32'hdeadbeef,1'b0,0,11,0);
        exception_case(32'hfff09173,32'h100,32'hdeadbeef,1'b0,0,2,32'hfff09173);
        exception_case(32'h0020006f,32'h80000100,0,1'b0,0,0,32'h80000102);
        exception_case(32'h00008067,32'h102,32'habcdef03,1'b1,32'h8000000b,32'h8000000b,0);
        exception_case(32'hffffffff,32'h102,32'habcdef03,1'b1,32'h80000003,32'h80000003,0);
        exception_case(32'h0020a023,32'h102,32'habcdef03,1'b1,32'h80000007,32'h80000007,0);
        exception_case(32'h00008067,32'h101,32'h100,1'b0,0,0,32'h101);
        exception_case(32'h0020006f,32'hfffffffc,0,1'b0,0,0,32'hfffffffe);
        pending_reset_case(1'b0); pending_reset_case(1'b1);
        reset_core(); #1; check(!trap_valid,"reset clears pending trap");
        $display("PASS trap_value checks=%0d",checks); $finish;
    end
    initial begin #200000; $fatal(1,"trap_value timeout"); end
endmodule
