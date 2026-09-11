`timescale 1ns/1ps
module burst_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0;
    reg [1:0] master_cmd_valid=0,master_cmd_write=0,master_w_valid=0,master_w_last=0,master_b_ready=0,master_r_ready=0;
    wire [1:0] master_cmd_ready,master_w_ready,master_b_valid,master_b_error,master_r_valid,master_r_last,master_r_error;
    reg [31:0] master_cmd_address[0:1],master_w_data[0:1];
    reg [7:0] master_cmd_length[0:1];
    wire [31:0] master_r_data[0:1];
    wire cmd_valid,cmd_write,w_valid,w_ready,w_last,b_valid,b_ready,b_error,r_valid,r_ready,r_last,r_error;
    wire [31:0] cmd_address,w_data,r_data;
    wire [7:0] cmd_length;
    wire ram_cmd_ready;
    reg command_gate=0;
    wire cmd_ready=ram_cmd_ready && command_gate;
    integer checks=0,cycles=0,grants=0;
    reg cmd_held=0;
    reg [31:0] held_address;
    reg [7:0] held_length;
    reg held_write;
    reg [31:0] random_state=32'h13579bdf;
    rv32_burst_arbiter arbiter(
        .clk(clk),.rst_n(rst_n),
        .a_cmd_valid(master_cmd_valid[0]),.a_cmd_ready(master_cmd_ready[0]),.a_cmd_write(master_cmd_write[0]),
        .a_cmd_address(master_cmd_address[0]),.a_cmd_length(master_cmd_length[0]),
        .a_w_valid(master_w_valid[0]),.a_w_ready(master_w_ready[0]),.a_w_data(master_w_data[0]),.a_w_last(master_w_last[0]),
        .a_b_valid(master_b_valid[0]),.a_b_ready(master_b_ready[0]),.a_b_error(master_b_error[0]),
        .a_r_valid(master_r_valid[0]),.a_r_ready(master_r_ready[0]),.a_r_data(master_r_data[0]),.a_r_last(master_r_last[0]),.a_r_error(master_r_error[0]),
        .b_cmd_valid(master_cmd_valid[1]),.b_cmd_ready(master_cmd_ready[1]),.b_cmd_write(master_cmd_write[1]),
        .b_cmd_address(master_cmd_address[1]),.b_cmd_length(master_cmd_length[1]),
        .b_w_valid(master_w_valid[1]),.b_w_ready(master_w_ready[1]),.b_w_data(master_w_data[1]),.b_w_last(master_w_last[1]),
        .b_b_valid(master_b_valid[1]),.b_b_ready(master_b_ready[1]),.b_b_error(master_b_error[1]),
        .b_r_valid(master_r_valid[1]),.b_r_ready(master_r_ready[1]),.b_r_data(master_r_data[1]),.b_r_last(master_r_last[1]),.b_r_error(master_r_error[1]),
        .cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_write(cmd_write),.cmd_address(cmd_address),.cmd_length(cmd_length),
        .w_valid(w_valid),.w_ready(w_ready),.w_data(w_data),.w_last(w_last),
        .b_valid(b_valid),.b_ready(b_ready),.b_error(b_error),.r_valid(r_valid),.r_ready(r_ready),.r_data(r_data),.r_last(r_last),.r_error(r_error)
    );
    rv32_burst_ram #(.ADDRESS_BITS(8),.BUFFER_BITS(2)) ram(
        .clk(clk),.rst_n(rst_n),.cmd_valid(cmd_valid && command_gate),.cmd_ready(ram_cmd_ready),
        .cmd_write(cmd_write),.cmd_address(cmd_address),.cmd_length(cmd_length),
        .w_valid(w_valid),.w_ready(w_ready),.w_data(w_data),.w_last(w_last),
        .b_valid(b_valid),.b_ready(b_ready),.b_error(b_error),.r_valid(r_valid),.r_ready(r_ready),.r_data(r_data),.r_last(r_last),.r_error(r_error)
    );
    task automatic check(input bit condition,input string label_text);
        begin
            checks=checks+1;
            if(!condition) $fatal(1,"FAIL burst %s cycle=%0d",label_text,cycles);
        end
    endtask
    task automatic command(input integer master,input bit writing,input [31:0] address,input [7:0] length_value);
        begin
            @(negedge clk); master_cmd_valid[master]=1; master_cmd_write[master]=writing;
            master_cmd_address[master]=address; master_cmd_length[master]=length_value;
            @(posedge clk); while(!master_cmd_ready[master]) @(posedge clk);
            @(negedge clk); master_cmd_valid[master]=0;
        end
    endtask
    task automatic write_burst(input integer master,input [31:0] address,input [31:0] pattern,input integer beats,input [7:0] length_value,input bit expected_error);
        integer beat_index;
        begin
            command(master,1,address,length_value);
            for(beat_index=0;beat_index<beats;beat_index=beat_index+1) begin
                @(negedge clk); master_w_valid[master]=1; master_w_data[master]=pattern+32'(beat_index);
                master_w_last[master]=beat_index==beats-1;
                @(posedge clk); while(!master_w_ready[master]) @(posedge clk);
                @(negedge clk); master_w_valid[master]=0;
            end
            @(posedge clk); while(!master_b_valid[master]) @(posedge clk);
            check(master_b_error[master]===expected_error,"write acknowledgment");
            repeat(3) begin
                @(posedge clk); check(master_b_valid[master] && master_b_error[master]===expected_error,"write acknowledgment backpressure");
            end
            @(negedge clk); master_b_ready[master]=1;
            @(posedge clk);
            @(negedge clk); master_b_ready[master]=0;
        end
    endtask
    task automatic read_burst(input integer master,input [31:0] address,input [31:0] pattern,input integer beats,input bit expected_error);
        integer beat_index;
        reg [31:0] held_response;
        begin
            command(master,0,address,8'(beats-1));
            for(beat_index=0;beat_index<beats;beat_index=beat_index+1) begin
                @(posedge clk); while(!master_r_valid[master]) @(posedge clk);
                check(master_r_error[master]===expected_error && master_r_last[master]===(beat_index==beats-1),"read flags");
                check(master_r_data[master]===(expected_error ? 32'b0 : pattern+32'(beat_index)),"read data routing");
                held_response=master_r_data[master];
                repeat(2) begin
                    @(posedge clk); check(master_r_valid[master] && master_r_data[master]===held_response,"read response backpressure");
                end
                @(negedge clk); master_r_ready[master]=1;
                @(posedge clk);
                @(negedge clk); master_r_ready[master]=0;
            end
        end
    endtask
    always @(negedge clk) begin
        random_state=random_state^(random_state<<13);
        random_state=random_state^(random_state>>17);
        random_state=random_state^(random_state<<5);
        command_gate=cycles>8 && random_state[0];
    end
    always @(posedge clk) begin
        if(rst_n) begin
            cycles=cycles+1;
            if(cmd_held) check(cmd_valid && cmd_address===held_address && cmd_length===held_length && cmd_write===held_write,"locked command under arbitration backpressure");
            cmd_held=cmd_valid && !cmd_ready; held_address=cmd_address; held_length=cmd_length; held_write=cmd_write;
            check(master_cmd_ready!=3 && master_b_valid!=3 && master_r_valid!=3,"responses belong to one master");
            if(cmd_valid && cmd_ready) begin
                if(grants<8) check(master_cmd_ready==(grants%2==0 ? 1 : 2),"round-robin fairness");
                grants=grants+1;
            end
            if(cycles>20000) $fatal(1,"Burst watchdog expired");
        end
    end
    initial begin
        master_cmd_address[0]=0; master_cmd_address[1]=0;
        master_cmd_length[0]=0; master_cmd_length[1]=0; master_w_data[0]=0; master_w_data[1]=0;
        #1; rst_n=1; #1; rst_n=0;
        repeat(3) @(negedge clk); rst_n=1;
        fork
            begin : writer_a
                integer transfer_index;
                for(transfer_index=0;transfer_index<4;transfer_index=transfer_index+1)
                    write_burst(0,32'(transfer_index*16),32'h11000000+32'(transfer_index*16),4,3,0);
            end
            begin : writer_b
                integer transfer_index;
                for(transfer_index=0;transfer_index<4;transfer_index=transfer_index+1)
                    write_burst(1,32'h80+32'(transfer_index*16),32'h22000000+32'(transfer_index*16),4,3,0);
            end
        join
        for(integer transfer_index=0;transfer_index<4;transfer_index=transfer_index+1) begin
            read_burst(0,32'(transfer_index*16),32'h11000000+32'(transfer_index*16),4,0);
            read_burst(1,32'h80+32'(transfer_index*16),32'h22000000+32'(transfer_index*16),4,0);
        end
        write_burst(0,0,32'hdead0000,2,3,1);
        read_burst(1,0,32'h11000000,4,0);
        write_burst(0,0,32'hdead0000,5,3,1);
        read_burst(1,0,32'h11000000,4,0);
        write_burst(0,2,32'hdead0000,4,3,1);
        read_burst(1,0,32'h11000000,4,0);
        write_burst(0,32'h400,32'hdead0000,4,3,1);
        read_burst(1,32'h400,0,4,1);
        write_burst(0,32'h100,32'h01234567,1,0,0);
        read_burst(1,32'h100,32'h01234567,1,0);
        $display("PASS burst checks=%0d grants=%0d",checks,grants);
        $finish;
    end
endmodule
