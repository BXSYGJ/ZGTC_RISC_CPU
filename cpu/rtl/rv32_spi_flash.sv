`timescale 1ns/1ps
// 1-bit SPI master controller for the on-board user QSPI Flash (U9, SPI1).
// Mode 0 (CPOL=0, CPHA=0), MSB-first. SCK is generated only while a byte
// transfer is active and idles low. SCK frequency = clk / CLK_DIV.
module rv32_spi_flash #(
    parameter integer CLK_DIV=4        // SCK period in clk cycles (>=2, even)
) (
    input wire clk,
    input wire rst_n,
    input wire cfg_cs,                 // 1 = flash selected (active low output)
    input wire start,                  // pulse to begin an 8-bit shift
    input wire [7:0] tx_data,
    output reg [7:0] rx_data,
    output wire busy,
    output wire spi_cs,                // active low
    output wire spi_sck,
    output wire spi_mosi,
    input wire spi_miso
);
    localparam integer HALF = (CLK_DIV < 2 ? 2 : CLK_DIV) >> 1;
    localparam [1:0] IDLE=0,SHIFT=1;
    reg state;
    reg [7:0] shift_out;
    reg [7:0] shift_in;
    reg [3:0] clk_cnt;
    reg sck_int;
    reg [2:0] bit_count;
    assign spi_cs = ~cfg_cs;
    assign spi_sck = sck_int;
    assign spi_mosi = shift_out[7];
    assign busy = state==SHIFT;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE; shift_out<=0; shift_in<=0; clk_cnt<=0; sck_int<=0;
            bit_count<=0; rx_data<=0;
        end else begin
            case(state)
                IDLE: begin
                    sck_int<=0; clk_cnt<=0;
                    if(start) begin
                        shift_out<=tx_data; shift_in<=0; bit_count<=0;
                        state<=SHIFT;
                    end
                end
                SHIFT: begin
                    if(clk_cnt==HALF[3:0]-1'b1) begin
                        clk_cnt<=0;
                        if(sck_int==1'b0) begin
                            // Rising edge: sample MISO.
                            sck_int<=1'b1;
                            shift_in<={shift_in[6:0],spi_miso};
                            if(bit_count==3'd7) begin
                                rx_data<={shift_in[6:0],spi_miso};
                                state<=IDLE; sck_int<=1'b0;
                            end else bit_count<=bit_count+1'b1;
                        end else begin
                            // Falling edge: advance MOSI to the next bit.
                            sck_int<=1'b0;
                            shift_out<={shift_out[6:0],1'b0};
                        end
                    end else clk_cnt<=clk_cnt+1'b1;
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
