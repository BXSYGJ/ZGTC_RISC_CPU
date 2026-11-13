`timescale 1ns/1ps
// Independent 27 MHz UART reports transitions of the differential reference.
// No CPU, DDR controller or external DDR transactions are present.
module pg200_clock_probe #(
    parameter integer MEASURE_TICKS = 270000,
    parameter integer PRINT_TICKS = 27000000,
    parameter integer UART_DIV = 234
) (
    input wire board_clk27, ref_clk_p, ref_clk_n, resetn,
    output wire uart_tx
);
    wire ref_single, ref_clk;
    GTP_INBUFDS ref_input (.O(ref_single),.I(ref_clk_p),.IB(ref_clk_n));
    GTP_CLKBUFG ref_buffer (.CLKOUT(ref_clk),.CLKIN(ref_single));
    reg [7:0] ref_div = 0;
    always @(posedge ref_clk) ref_div <= ref_div + 1'b1;
    reg [9:0] por_count = 0;
    always @(posedge board_clk27 or negedge resetn) begin
        if(!resetn) por_count<=0;
        else if(!(&por_count)) por_count<=por_count+1'b1;
    end
    wire local_resetn = &por_count;
    reg [2:0] ref_sync=0;
    always @(posedge board_clk27) ref_sync<={ref_sync[1:0],ref_div[7]};
    wire ref_transition = ref_sync[2] ^ ref_sync[1];
    reg [31:0] measure_tick, edge_count, measured_edges;
    reg [31:0] print_tick, frame_edges;
    reg [4:0] character;
    reg sending, draining, tx_accept_hold;
    wire byte_ready;
    reg [7:0] byte_data;
    wire [3:0] nibble = (frame_edges >> ((19-character)*4)) & 4'hf;
    always @* begin
        if(character>=12 && character<=19)
            byte_data = nibble<10 ? 8'd48+nibble : 8'd55+nibble;
        else case(character)
            0:byte_data="P"; 1:byte_data="G"; 2:byte_data="2";
            3:byte_data="0"; 4:byte_data="0"; 5:byte_data="_";
            6:byte_data="R"; 7:byte_data="E"; 8:byte_data="F";
            9:byte_data=" "; 10:byte_data="E"; 11:byte_data="=";
            20:byte_data=" "; 21:byte_data="R"; 22:byte_data="=";
            23:byte_data=resetn ? "1" : "0";
            24:byte_data=13; default:byte_data=10;
        endcase
    end
    always @(posedge board_clk27 or negedge local_resetn) begin
        if(!local_resetn) begin
            measure_tick<=0; edge_count<=0; measured_edges<=0;
            print_tick<=PRINT_TICKS-1; frame_edges<=0;
            character<=0; sending<=0; draining<=0; tx_accept_hold<=0;
        end else begin
            if(!byte_ready) tx_accept_hold<=0;
            else if(sending && !tx_accept_hold) tx_accept_hold<=1;
            if(measure_tick==MEASURE_TICKS-1) begin
                measure_tick<=0;
                measured_edges<=edge_count+ref_transition;
                edge_count<=0;
            end else begin
                measure_tick<=measure_tick+1'b1;
                if(ref_transition) edge_count<=edge_count+1'b1;
            end
            if(sending && byte_ready && !tx_accept_hold) begin
                if(character==25) begin sending<=0; draining<=1; end
                else character<=character+1'b1;
            end else if(draining && byte_ready) begin
                draining<=0; print_tick<=PRINT_TICKS-1;
            end else if(!sending && !draining) begin
                if(print_tick==0) begin
                    sending<=1; character<=0; frame_edges<=measured_edges;
                end else print_tick<=print_tick-1'b1;
            end
        end
    end
    uart_tx #(.BAUD_DIV(UART_DIV)) transmitter (
        .clk(board_clk27),.rst_n(local_resetn),.byte_wvalid(sending && !tx_accept_hold),
        .byte_wdata(byte_data),.byte_wready(byte_ready),.uart_txd(uart_tx)
    );
endmodule
