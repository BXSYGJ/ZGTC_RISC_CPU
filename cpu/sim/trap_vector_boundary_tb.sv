`timescale 1ns/1ps
module trap_vector_boundary_tb;
    parameter integer ENABLE_M=0;
    reg clk=0,rst_n=0,retire=0,irq_external=0,irq_software=0,irq_timer=0;
    reg [63:0] timer_value=64'h13579bdf2468ace0;
    reg [11:0] read_address=12'h305,write_address=12'h305;
    reg read_write_intent=0,write_valid=0,trap_enter=0,return_from_trap=0;
    reg [31:0] write_data=0,trap_pc=0,trap_cause=0,trap_value=0;
    wire [31:0] read_data,return_pc,trap_target,interrupt_cause;
    wire read_illegal,interrupt_pending;
    wire [63:0] cycle_count,retired_count;
    reg [31:0] base_value,expected_mtvec,expected_target,random_state=32'h951ca073;
    reg [31:0] signature=0;
    integer checks=0,overflows=0,direct_cases=0,vectored_cases=0;
    rv32_machine #(.ENABLE_M(ENABLE_M)) machine(.*);
    task tick;
        begin clk=0; #1; clk=1; #1; clk=0; #1; end
    endtask
    function automatic [31:0] next_random(input [31:0] value);
        reg [31:0] mixed;
        begin
            mixed=value^(value<<13); mixed=mixed^(mixed>>17);
            next_random=mixed^(mixed<<5);
        end
    endfunction
    initial begin
        #1; rst_n=1; #1; rst_n=0; #1; rst_n=1;
        for(integer sample=0;sample<576;sample=sample+1) begin
            if(sample<32) base_value=(32'h1<<sample)-4;
            else if(sample<64) base_value=~(32'h1<<(sample-32));
            else if(sample<320) base_value=((sample-64)<<24) | 32'h00fffffc;
            else begin random_state=next_random(random_state); base_value=random_state; end
            base_value=base_value & 32'hfffffffc;
            for(integer mode=0;mode<4;mode=mode+1) begin
                write_data=base_value | mode; write_valid=1; retire=sample[0]; tick(); write_valid=0;
                expected_mtvec=base_value | (mode==1 ? 32'd1 : 32'd0);
                if(read_illegal || read_data!==expected_mtvec)
                    $fatal(1,"FAIL trap_vector_boundary CSR mode normalization sample=%0d mode=%0d",sample,mode);
                for(integer interrupt_flag=0;interrupt_flag<2;interrupt_flag=interrupt_flag+1)
                    for(integer cause=0;cause<32;cause=cause+1) begin
                        trap_cause=(interrupt_flag!=0 ? 32'h80000000 : 0) | (random_state & 32'h7fffffe0) | cause;
                        expected_target=base_value;
                        if(mode==1 && interrupt_flag!=0) begin
                            expected_target=base_value+cause*4;
                            vectored_cases=vectored_cases+1;
                            if(expected_target<base_value) overflows=overflows+1;
                        end else direct_cases=direct_cases+1;
                        #1;
                        if(trap_target!==expected_target || trap_target[1:0]!==2'b00)
                            $fatal(1,"FAIL trap_vector_boundary target sample=%0d mode=%0d cause=%08x expected=%08x actual=%08x",sample,mode,trap_cause,expected_target,trap_target);
                        signature={signature[30:0],signature[31]}^trap_target^trap_cause;
                        checks=checks+1;
                    end
                irq_external=sample[0]; irq_software=sample[1]; irq_timer=sample[2];
                tick();
            end
        end
        if(checks!=147456 || direct_cases!=129024 || vectored_cases!=18432 || overflows==0)
            $fatal(1,"FAIL trap_vector_boundary missing coverage checks=%0d direct=%0d vector=%0d overflow=%0d",checks,direct_cases,vectored_cases,overflows);
        $display("PASS trap_vector_boundary checks=%0d direct=%0d vector=%0d overflow=%0d signature=%08x m=%0d",checks,direct_cases,vectored_cases,overflows,signature,ENABLE_M);
        $finish;
    end
endmodule
