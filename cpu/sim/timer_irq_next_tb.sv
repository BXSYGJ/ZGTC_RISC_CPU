`timescale 1ns/1ps
module timer_irq_next_tb;
    reg clk=0,rst_n=1;
    reg req_valid=0,req_write=0,rsp_ready=1;
    reg [31:0] req_address=0,req_data=0;
    reg [3:0] req_strobe=0;
    wire [1:0] req_ready,rsp_valid,rsp_error,serial_tx,irq_external,irq_software,irq_timer;
    wire [31:0] rsp_data [0:1],status_code [0:1];
    wire [7:0] gpio_output [0:1];
    wire [63:0] timer_value [0:1];
    reg [63:0] corners [0:15];
    reg [31:0] random_state=32'h53ea9217;
    reg [63:0] previous_timer=0;
    reg previous_irq=0;
    integer cycles=0,resets=0,irq_rises=0,irq_falls=0,wraps=0;
    rv32_peripherals_parent #(.CLOCK_HZ(3200),.BAUD(100)) parent_dut(
        .clk(clk),.rst_n(rst_n),.performance_values(288'b0),.performance_config(32'b0),
        .req_valid(req_valid),.req_ready(req_ready[0]),.req_address(req_address),.req_write(req_write),.req_data(req_data),.req_strobe(req_strobe),
        .rsp_valid(rsp_valid[0]),.rsp_ready(rsp_ready),.rsp_data(rsp_data[0]),.rsp_error(rsp_error[0]),
        .serial_rx(1'b1),.serial_tx(serial_tx[0]),.gpio_input(8'b0),.gpio_output(gpio_output[0]),
        .irq_external(irq_external[0]),.irq_software(irq_software[0]),.irq_timer(irq_timer[0]),.timer_value(timer_value[0]),.status_code(status_code[0])
    );
    rv32_peripherals #(.CLOCK_HZ(3200),.BAUD(100)) candidate_dut(
        .clk(clk),.rst_n(rst_n),.performance_values(288'b0),.performance_config(32'b0),
        .req_valid(req_valid),.req_ready(req_ready[1]),.req_address(req_address),.req_write(req_write),.req_data(req_data),.req_strobe(req_strobe),
        .rsp_valid(rsp_valid[1]),.rsp_ready(rsp_ready),.rsp_data(rsp_data[1]),.rsp_error(rsp_error[1]),
        .serial_rx(1'b1),.serial_tx(serial_tx[1]),.gpio_input(8'b0),.gpio_output(gpio_output[1]),
        .irq_external(irq_external[1]),.irq_software(irq_software[1]),.irq_timer(irq_timer[1]),.timer_value(timer_value[1]),.status_code(status_code[1])
    );
    task check_outputs;
        begin
            if({req_ready[0],rsp_valid[0],rsp_error[0],rsp_data[0],serial_tx[0],gpio_output[0],irq_external[0],irq_software[0],irq_timer[0],timer_value[0],status_code[0]} !==
               {req_ready[1],rsp_valid[1],rsp_error[1],rsp_data[1],serial_tx[1],gpio_output[1],irq_external[1],irq_software[1],irq_timer[1],timer_value[1],status_code[1]} || parent_dut.timer_compare!==candidate_dut.timer_compare)
                $fatal(1,"FAIL timer_irq_next cycle=%0d address=%h timer=%h/%h compare=%h/%h irq=%b/%b",cycles,req_address,timer_value[0],timer_value[1],parent_dut.timer_compare,candidate_dut.timer_compare,irq_timer[0],irq_timer[1]);
        end
    endtask
    task step;
        begin
            #1;check_outputs();#3;clk=1;#1;check_outputs();
            if(previous_irq===0 && irq_timer[0]===1) irq_rises=irq_rises+1;
            if(previous_irq===1 && irq_timer[0]===0) irq_falls=irq_falls+1;
            if(previous_timer===64'hffffffffffffffff && timer_value[0]===64'b0) wraps=wraps+1;
            previous_irq=irq_timer[0];previous_timer=timer_value[0];
            cycles=cycles+1;#4;clk=0;#1;
        end
    endtask
    task reset_pair;
        begin
            req_valid=0;req_write=0;rsp_ready=1;req_address=0;req_data=0;req_strobe=0;
            rst_n=0;#1;check_outputs();rst_n=1;#1;
            previous_irq=0;previous_timer=0;resets=resets+1;
        end
    endtask
    task write_register(input [31:0] address,input [31:0] data,input [3:0] strobe);
        begin
            req_valid=1;req_write=1;req_address=address;req_data=data;req_strobe=strobe;rsp_ready=1;
            #1;if(req_ready!==2'b11) $fatal(1,"FAIL timer_irq_next fixture request not ready");
            step();req_valid=0;req_write=0;step();
        end
    endtask
    task randomize_state;
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
        end
    endtask
    initial begin
        reset_pair();
        corners[0]=0;corners[1]=1;corners[2]=64'hffffffffffffffff;corners[3]=64'hfffffffffffffffc;
        corners[4]=64'h00000000ffffffff;corners[5]=64'h0000000100000000;corners[6]=64'h0000000100000001;
        corners[7]=64'h7fffffff00000000;corners[8]=64'h8000000000000000;corners[9]=64'h7fffffffffffffff;
        corners[10]=64'h80000000ffffffff;corners[11]=64'hffffffff00000000;corners[12]=64'h0000000080000000;
        corners[13]=64'h000000007fffffff;corners[14]=64'h55555555aaaaaaaa;corners[15]=64'haaaaaaaa55555555;
        for(integer value_index=0;value_index<16;value_index=value_index+1)
            for(integer compare_index=0;compare_index<16;compare_index=compare_index+1) begin
                write_register(32'h1000030c,corners[compare_index][63:32],15);
                write_register(32'h10000308,corners[compare_index][31:0],15);
                write_register(32'h10000304,corners[value_index][63:32],15);
                write_register(32'h10000300,corners[value_index][31:0],15);
                repeat(8) step();
            end
        for(integer strobe_index=0;strobe_index<16;strobe_index=strobe_index+1)
            for(integer address_index=0;address_index<4;address_index=address_index+1) begin
                randomize_state();
                write_register(32'h10000300+address_index*4,random_state,strobe_index[3:0]);
                repeat(2) step();
            end
        for(integer sample_index=0;sample_index<4096;sample_index=sample_index+1) begin
            randomize_state();req_valid=random_state[0];req_write=random_state[1];rsp_ready=random_state[2];
            req_address=32'h10000300+{26'b0,random_state[7:4],2'b0};req_strobe=random_state[11:8];
            randomize_state();req_data=random_state;
            case(sample_index%32)
                0:req_valid=1'bx;
                1:req_write=1'bz;
                2:rsp_ready=1'bx;
                3:req_address[0]=1'bx;
                4:req_address[1:0]=2'b11;
                5:req_strobe[0]=1'bx;
                default:begin end
            endcase
            step();
        end
        for(integer sample_index=0;sample_index<64;sample_index=sample_index+1) begin
            reset_pair();
            write_register(32'h1000030c,0,15);
            write_register(32'h10000308,32'h80000000,15);
            write_register(32'h10000304,{31'b0,sample_index[0]},15);
            randomize_state();req_data=random_state;req_data[sample_index%32]=sample_index[5] ? 1'bz : 1'bx;
            write_register(32'h10000300,req_data,15);
            repeat(2) step();
        end
        if(cycles!=9088 || resets!=65 || irq_rises==0 || irq_falls==0 || wraps==0) $fatal(1,"FAIL timer_irq_next incomplete coverage cycles=%0d resets=%0d",cycles,resets);
        $display("PASS timer_irq_next cycles=%0d resets=%0d irq_rises=%0d irq_falls=%0d wraps=%0d",cycles,resets,irq_rises,irq_falls,wraps);
        $finish;
    end
endmodule
