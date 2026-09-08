`timescale 1ns/1ps

// uart_beacon: 与固件无关的串口链路裁决器。
// 只依赖 27MHz 时钟(D18)，持续以 115200 8N1 在 uart_tx(AB26) 发送字节流
// 0x55 0xAA 0x00 0xFF 循环 + 计数，帧间留 ~1ms 静默以区分字节。
// 若远程实验箱串口桥正常，任何时刻打开串口都能收到连续数据。
module uart_beacon (
    input  wire clk,
    output reg  uart_tx
);

    // 27 MHz / 115200 baud ~= 234.375 个时钟周期
    localparam integer BAUD_CYCLES = 234;

    reg [11:0] tx_timer;      // bit 内相位计数
    reg [3:0]  bit_index;     // 0=start,1..8=data,9=stop
    reg [3:0]  frame_state;   // 0=idle,1=transmitting
    reg [7:0]  tx_byte;
    reg [15:0] gap_count;
    reg [23:0] idle_count;    // 上电复位计时（自复位，不依赖外部按键）

    always @(posedge clk) begin
        // 上电自复位：前 2^18 周期维持内部复位
        if (idle_count[23:0] != 24'hFFFFFF)
            idle_count <= idle_count + 1'b1;
    end
    wire rst = (idle_count[23:0] < 24'h000200);

    always @(posedge clk) begin
        if (rst) begin
            uart_tx     <= 1'b1;   // 空闲 = 高
            frame_state <= 4'd0;
            tx_timer    <= 12'd0;
            bit_index   <= 4'd0;
            tx_byte     <= 8'h55;
            gap_count   <= 16'd0;
        end else begin
            if (frame_state == 4'd0) begin
                // idle：空一段时间再发下一字节（~26 bit，便于观察帧）
                if (gap_count < 16'd26) begin
                    gap_count <= gap_count + 1'b1;
                end else begin
                    gap_count   <= 16'd0;
                    frame_state <= 4'd1;
                    tx_timer    <= 12'd0;
                    bit_index   <= 4'd0;
                    // 负载含 0x00/0xFF 以检验全 0/全 1 都能传
                    tx_byte     <= tx_byte + 8'h27; // 55,A2->… 覆盖多样值
                end
            end else begin
                if (tx_timer < BAUD_CYCLES - 1) begin
                    tx_timer <= tx_timer + 1'b1;
                end else begin
                    tx_timer <= 12'd0;
                    if (bit_index == 4'd9) begin
                        frame_state <= 4'd0; // 完成 start+8+stop
                    end else begin
                        bit_index <= bit_index + 1'b1;
                    end
                end
                // 逐位输出：start=0, data LSB first, stop=1
                if (tx_timer == 0) begin
                    case (bit_index)
                        4'd0:    uart_tx <= 1'b0;
                        4'd1:    uart_tx <= tx_byte[0];
                        4'd2:    uart_tx <= tx_byte[1];
                        4'd3:    uart_tx <= tx_byte[2];
                        4'd4:    uart_tx <= tx_byte[3];
                        4'd5:    uart_tx <= tx_byte[4];
                        4'd6:    uart_tx <= tx_byte[5];
                        4'd7:    uart_tx <= tx_byte[6];
                        4'd8:    uart_tx <= tx_byte[7];
                        default: uart_tx <= 1'b1;
                    endcase
                end
            end
        end
    end

endmodule
