`timescale 1ns/1ps

module blink_top #(
    parameter integer COUNT_MAX = 13_500_000
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       key,
    output reg  [7:0] led
);

    reg [25:0] counter;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            counter <= 26'd0;
            led     <= 8'b0000_0001;
        end else if (counter == COUNT_MAX - 1) begin
            counter <= 26'd0;
            if (key)
                led <= {led[6:0], led[7]};
            else
                led <= {led[0], led[7:1]};
        end else begin
            counter <= counter + 1'b1;
        end
    end

endmodule
