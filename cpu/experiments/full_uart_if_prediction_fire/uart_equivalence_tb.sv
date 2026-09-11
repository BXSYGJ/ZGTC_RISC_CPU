module uart_equivalence_tb;
    parameter integer CLOCK_HZ=3200;
    parameter integer BAUD=100;
    localparam integer DIVIDER=(CLOCK_HZ+BAUD/2)/BAUD;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,serial_rx=1,tx_valid=0,rx_ready=1;
    reg [7:0] tx_data=0;
    wire serial_tx,tx_ready,tx_busy,rx_valid,framing_error,overrun_error;
    wire [7:0] rx_data;
    wire reference_tx,reference_ready,reference_busy,reference_valid,reference_frame,reference_overrun;
    wire [7:0] reference_data;
    integer cycles=0,received=0,frames=0,overruns=0,byte_index,reset_bit;
    reg [31:0] random_state=32'h12345678;
    rv32_uart #(.CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD)) candidate(.*);
    rv32_uart_reference #(.CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD)) reference_uart(
        .clk(clk),.rst_n(rst_n),.serial_rx(serial_rx),.serial_tx(reference_tx),
        .tx_valid(tx_valid),.tx_ready(reference_ready),.tx_data(tx_data),.tx_busy(reference_busy),
        .rx_valid(reference_valid),.rx_ready(rx_ready),.rx_data(reference_data),
        .framing_error(reference_frame),.overrun_error(reference_overrun));
    always @(posedge clk) begin
        #1;
        cycles=cycles+1;
        if({serial_tx,tx_ready,tx_busy,rx_valid,rx_data,framing_error,overrun_error} !==
           {reference_tx,reference_ready,reference_busy,reference_valid,reference_data,reference_frame,reference_overrun})
            $fatal(1,"UART_MISMATCH cycle=%0d rx=%02x reference=%02x",cycles,rx_data,reference_data);
        if(rst_n) begin
            if(rx_valid && rx_ready) received=received+1;
            if(framing_error) frames=frames+1;
            if(overrun_error) overruns=overruns+1;
        end
    end
    task send_frame(input [7:0] value,input bit good_stop);
        integer bit_index;
        begin
            serial_rx=0; repeat(DIVIDER) @(negedge clk);
            for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin
                serial_rx=value[bit_index]; repeat(DIVIDER) @(negedge clk);
            end
            serial_rx=good_stop; repeat(DIVIDER) @(negedge clk);
            serial_rx=1; repeat(DIVIDER) @(negedge clk);
        end
    endtask
    initial begin
        #1; rst_n=1; #1; rst_n=0;
        repeat(4) @(negedge clk); rst_n=1;
        for(byte_index=0;byte_index<256;byte_index=byte_index+1) begin
            tx_data=byte_index; tx_valid=1;
            send_frame(byte_index,1);
        end
        if(received!=256) $fatal(1,"Missing exhaustive RX coverage: %0d",received);
        tx_valid=0; rx_ready=0;
        send_frame(8'h3c,1); send_frame(8'ha5,1);
        if(overruns==0) $fatal(1,"Missing overrun coverage");
        rx_ready=1;
        send_frame(8'h81,0);
        if(frames==0) $fatal(1,"Missing framing coverage");
        serial_rx=0; repeat(DIVIDER/4) @(negedge clk);
        serial_rx=1; repeat(DIVIDER*2) @(negedge clk);
        for(reset_bit=0;reset_bit<10;reset_bit=reset_bit+1) begin
            serial_rx=0; repeat(DIVIDER*(reset_bit+1)) @(negedge clk);
            #1; rst_n=0; #2;
            serial_rx=1; repeat(4) @(negedge clk); rst_n=1;
            repeat(DIVIDER*2) @(negedge clk); send_frame(8'h96,1);
        end
        repeat(20000) begin
            @(negedge clk);
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            serial_rx=random_state[0]; rx_ready=random_state[1];
            tx_valid=random_state[2]; tx_data=random_state[10:3];
        end
        $display("PASS uart_equivalence divider=%0d cycles=%0d received=%0d frame_errors=%0d overruns=%0d",DIVIDER,cycles,received,frames,overruns);
        $finish;
    end
endmodule
