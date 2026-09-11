`timescale 1ns/1ps
module fifo_equivalence_tb;
    parameter integer WIDTH=8;
    parameter integer DEPTH_BITS=4;
    localparam integer DEPTH=1<<DEPTH_BITS;
    reg clk=0,rst_n=0,in_valid=0,out_ready=0;
    reg [WIDTH-1:0] in_data=0;
    wire in_ready,out_valid,reference_ready,reference_valid;
    wire [WIDTH-1:0] out_data,reference_data;
    wire [DEPTH_BITS:0] count,reference_count;
    integer cycle_index,seed=32'h4712733,full_exchanges=0,full_seen=0,empty_seen=0,reset_count=0,unknown_controls=0;
    rv32_fifo #(.WIDTH(WIDTH),.DEPTH_BITS(DEPTH_BITS)) candidate(.*);
    rv32_fifo_reference #(.WIDTH(WIDTH),.DEPTH_BITS(DEPTH_BITS)) reference_dut(
        .clk(clk),.rst_n(rst_n),.in_valid(in_valid),.in_ready(reference_ready),.in_data(in_data),
        .out_valid(reference_valid),.out_ready(out_ready),.out_data(reference_data),.count(reference_count));
    always #5 clk=~clk;
    task check;
        begin
            if({count,in_ready,out_valid,out_data} !== {reference_count,reference_ready,reference_valid,reference_data})
                $fatal(1,"FIFO_MISMATCH cycle=%0d candidate=%h reference=%h",cycle_index,count,reference_count);
        end
    endtask
    function automatic control_value(input integer choice);
        case(choice & 3)
            0: control_value=0;
            1: control_value=1;
            2: control_value=1'bx;
            3: control_value=1'bz;
        endcase
    endfunction
    initial begin
        #1; rst_n=1; #1; rst_n=0; #1; check();
        for(cycle_index=0;cycle_index<32768;cycle_index=cycle_index+1) begin
            @(negedge clk);
            rst_n=(cycle_index%2048)!=0;
            if(!rst_n) reset_count=reset_count+1;
            in_data=$random(seed);
            if(cycle_index%(4*DEPTH)<DEPTH+2) begin in_valid=1; out_ready=0; end
            else if(cycle_index%(4*DEPTH)<2*DEPTH+2) begin in_valid=1; out_ready=1; end
            else begin in_valid=0; out_ready=1; end
            if(cycle_index>=8192 && cycle_index<16384) begin in_valid=$random(seed); out_ready=$random(seed); end
            if(cycle_index>=16384 && cycle_index<24576) begin
                in_valid=control_value(cycle_index); out_ready=control_value(cycle_index>>2);
                if((cycle_index%32)==0) in_data={WIDTH{1'bx}};
                if((cycle_index%32)==1) in_data={WIDTH{1'bz}};
                unknown_controls=unknown_controls+1;
            end
            #1; check();
            if(count===DEPTH) full_seen=full_seen+1;
            if(count===0) empty_seen=empty_seen+1;
            if(count===DEPTH && in_valid===1'b1 && out_ready===1'b1) full_exchanges=full_exchanges+1;
            @(posedge clk); #1; check();
        end
        if(full_seen==0 || empty_seen==0 || full_exchanges==0 || reset_count!=16 || unknown_controls==0)
            $fatal(1,"FIFO coverage incomplete");
        $display("PASS fifo_equivalence width=%0d depth_bits=%0d cycles=%0d full_exchange=%0d resets=%0d unknown=%0d",WIDTH,DEPTH_BITS,cycle_index,full_exchanges,reset_count,unknown_controls);
        $finish;
    end
endmodule
