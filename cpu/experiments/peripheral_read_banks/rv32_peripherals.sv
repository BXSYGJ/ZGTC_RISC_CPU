`timescale 1ns/1ps
module rv32_peripherals #(
    parameter integer CLOCK_HZ=27000000,
    parameter integer BAUD=115200
) (
    input wire clk,
    input wire rst_n,
    input wire [287:0] performance_values,
    input wire [31:0] performance_config,
    input wire req_valid,
    output wire req_ready,
    input wire [31:0] req_address,
    input wire req_write,
    input wire [31:0] req_data,
    input wire [3:0] req_strobe,
    output reg rsp_valid,
    input wire rsp_ready,
    output reg [31:0] rsp_data,
    output reg rsp_error,
    input wire serial_rx,
    output wire serial_tx,
    input wire [7:0] gpio_input,
    output reg [7:0] gpio_output,
    output wire irq_external,
    output reg irq_software,
    output reg irq_timer,
    output reg [63:0] timer_value,
    output reg [31:0] status_code
);
    localparam [31:0] STATUS=32'h10000000,VERSION=32'h10000004,
        UART_DATA=32'h10000100,UART_STATUS=32'h10000104,UART_CONTROL=32'h10000108,UART_ERRORS=32'h1000010c,
        GPIO_OUTPUT=32'h10000200,GPIO_INPUT=32'h10000204,GPIO_ENABLE=32'h10000208,GPIO_PENDING=32'h1000020c,
        TIME_LOW=32'h10000300,TIME_HIGH=32'h10000304,COMPARE_LOW=32'h10000308,COMPARE_HIGH=32'h1000030c,SOFTWARE_IRQ=32'h10000310;
    reg [7:0] gpio_meta,gpio_sync,gpio_previous,gpio_enable,gpio_pending;
    reg [1:0] uart_control,uart_errors;
    reg [63:0] timer_compare;
    reg [287:0] performance_snapshot;
    reg [31:0] snapshot_sequence;
    wire uart_tx_ready,uart_tx_valid,uart_tx_busy,uart_rx_ready,uart_rx_valid,framing_error,overrun_error;
    wire [7:0] uart_tx_data,uart_rx_data,rx_fifo_data;
    wire tx_fifo_ready,rx_fifo_valid,rx_fifo_pop;
    wire [4:0] tx_count,rx_count;
    wire [31:0] write_mask={{8{req_strobe[3]}},{8{req_strobe[2]}},{8{req_strobe[1]}},{8{req_strobe[0]}}};
    wire uart_write=req_write && req_address==UART_DATA && req_strobe[0];
    wire request_fire=req_valid && req_ready;
    wire [7:0] pending_clear=(request_fire && req_write && req_address==GPIO_PENDING) ? req_data[7:0] & write_mask[7:0] : 8'b0;
    wire [1:0] errors_clear=(request_fire && req_write && req_address==UART_ERRORS) ? req_data[1:0] & write_mask[1:0] : 2'b0;
    wire uart_idle=tx_count==0 && !uart_tx_busy;
    assign req_ready=!rsp_valid && (!uart_write || tx_fifo_ready);
    assign rx_fifo_pop=request_fire && !req_write && req_address==UART_DATA && rx_fifo_valid;
    assign irq_external=(|(gpio_pending & gpio_enable)) || (uart_control[0] && rx_fifo_valid) || (uart_control[1] && uart_idle);
    (* syn_keep=1 *) wire [63:0] timer_incremented=timer_value+1'b1;
    reg [63:0] timer_value_next,timer_compare_next;
    always @* begin
        timer_value_next=timer_incremented;
        timer_compare_next=timer_compare;
        if(request_fire && req_write) begin
            case(req_address)
                TIME_LOW: timer_value_next={timer_value[63:32],(timer_value[31:0] & ~write_mask) | (req_data & write_mask)};
                TIME_HIGH: timer_value_next={(timer_value[63:32] & ~write_mask) | (req_data & write_mask),timer_value[31:0]};
                COMPARE_LOW: timer_compare_next[31:0]=(timer_compare[31:0] & ~write_mask) | (req_data & write_mask);
                COMPARE_HIGH: timer_compare_next[63:32]=(timer_compare[63:32] & ~write_mask) | (req_data & write_mask);
                default: begin end
            endcase
        end
    end
    (* syn_keep=1 *) wire timer_upper_equal=timer_value_next[63:32]==timer_compare_next[63:32];
    (* syn_keep=1 *) wire timer_upper_greater=timer_value_next[63:32]>timer_compare_next[63:32];
    (* syn_keep=1 *) wire timer_lower_at_least=timer_value_next[31:0]>=timer_compare_next[31:0];
    wire timer_interrupt_next=timer_upper_greater || (timer_upper_equal && timer_lower_at_least);
    rv32_fifo tx_fifo(.clk(clk),.rst_n(rst_n),.in_valid(request_fire && uart_write),.in_ready(tx_fifo_ready),.in_data(req_data[7:0]),
        .out_valid(uart_tx_valid),.out_ready(uart_tx_ready),.out_data(uart_tx_data),.count(tx_count));
    rv32_fifo rx_fifo(.clk(clk),.rst_n(rst_n),.in_valid(uart_rx_valid),.in_ready(uart_rx_ready),.in_data(uart_rx_data),
        .out_valid(rx_fifo_valid),.out_ready(rx_fifo_pop),.out_data(rx_fifo_data),.count(rx_count));
    rv32_uart #(.CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD)) uart(.clk(clk),.rst_n(rst_n),.serial_rx(serial_rx),.serial_tx(serial_tx),
        .tx_valid(uart_tx_valid),.tx_ready(uart_tx_ready),.tx_data(uart_tx_data),.tx_busy(uart_tx_busy),
        .rx_valid(uart_rx_valid),.rx_ready(uart_rx_ready),.rx_data(uart_rx_data),.framing_error(framing_error),.overrun_error(overrun_error));
    reg [31:0] decoded_read_data;
    reg decoded_read_error;
    always @* begin
        decoded_read_data=0; decoded_read_error=0;
        case(req_address[31:11])
            21'h20000: begin
                case(req_address[10:8])
                    3'd0: begin
                        case(req_address[7:0])
                            8'h00: decoded_read_data=status_code;
                            8'h04: decoded_read_data=32'h00010000;
                            default: decoded_read_error=1;
                        endcase
                    end
                    3'd1: begin
                        case(req_address[7:0])
                            8'h00: decoded_read_data=rx_fifo_valid ? {24'b0,rx_fifo_data} : 32'hffffffff;
                            8'h04: decoded_read_data={26'b0,uart_errors[1],uart_errors[0],(rx_count==16),rx_fifo_valid,uart_idle,tx_fifo_ready};
                            8'h08: decoded_read_data={30'b0,uart_control};
                            8'h0c: decoded_read_data={30'b0,uart_errors};
                            default: decoded_read_error=1;
                        endcase
                    end
                    3'd2: begin
                        case(req_address[7:0])
                            8'h00: decoded_read_data={24'b0,gpio_output};
                            8'h04: decoded_read_data={24'b0,gpio_sync};
                            8'h08: decoded_read_data={24'b0,gpio_enable};
                            8'h0c: decoded_read_data={24'b0,gpio_pending};
                            default: decoded_read_error=1;
                        endcase
                    end
                    3'd3: begin
                        case(req_address[7:0])
                            8'h00: decoded_read_data=timer_value[31:0];
                            8'h04: decoded_read_data=timer_value[63:32];
                            8'h08: decoded_read_data=timer_compare[31:0];
                            8'h0c: decoded_read_data=timer_compare[63:32];
                            8'h10: decoded_read_data={31'b0,irq_software};
                            default: decoded_read_error=1;
                        endcase
                    end
                    3'd4: begin
                        case(req_address[7:0])
                            8'h00: decoded_read_data=snapshot_sequence;
                            8'h04: decoded_read_data=performance_config;
                            8'h10: decoded_read_data=performance_snapshot[31:0];
                            8'h14: decoded_read_data=performance_snapshot[63:32];
                            8'h18: decoded_read_data=performance_snapshot[95:64];
                            8'h1c: decoded_read_data=performance_snapshot[127:96];
                            8'h20: decoded_read_data=performance_snapshot[159:128];
                            8'h24: decoded_read_data=performance_snapshot[191:160];
                            8'h28: decoded_read_data=performance_snapshot[223:192];
                            8'h2c: decoded_read_data=performance_snapshot[255:224];
                            8'h30: decoded_read_data=performance_snapshot[287:256];
                            default: decoded_read_error=1;
                        endcase
                    end
                    default: decoded_read_error=1;
                endcase
            end
            default: decoded_read_error=1;
        endcase
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            rsp_valid<=0; rsp_data<=0; rsp_error<=0; gpio_output<=0; status_code<=0;
            gpio_meta<=0; gpio_sync<=0; gpio_previous<=0; gpio_enable<=0; gpio_pending<=0;
            performance_snapshot<=0; snapshot_sequence<=0;
            uart_control<=0; uart_errors<=0; timer_value<=0; timer_compare<=64'hffffffffffffffff; irq_software<=0; irq_timer<=0;
        end else begin
            gpio_meta<=gpio_input; gpio_sync<=gpio_meta; gpio_previous<=gpio_sync;
            gpio_pending<=(gpio_pending & ~pending_clear) | (gpio_sync & ~gpio_previous);
            uart_errors<=(uart_errors & ~errors_clear) | {overrun_error,framing_error};
            timer_value<=timer_value_next; timer_compare<=timer_compare_next; irq_timer<=timer_interrupt_next;
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            if(request_fire) begin
                rsp_valid<=1; rsp_error<=0; rsp_data<=0;
                if(req_address[1:0]!=0) rsp_error<=1;
                else if(req_write) begin
                    case(req_address)
                        STATUS: status_code<=(status_code & ~write_mask) | (req_data & write_mask);
                        UART_DATA: begin end
                        UART_CONTROL: uart_control<=(uart_control & ~write_mask[1:0]) | (req_data[1:0] & write_mask[1:0]);
                        UART_ERRORS,GPIO_PENDING: begin end
                        GPIO_OUTPUT: gpio_output<=(gpio_output & ~write_mask[7:0]) | (req_data[7:0] & write_mask[7:0]);
                        GPIO_ENABLE: gpio_enable<=(gpio_enable & ~write_mask[7:0]) | (req_data[7:0] & write_mask[7:0]);
                        TIME_LOW,TIME_HIGH,COMPARE_LOW,COMPARE_HIGH: begin end
                        SOFTWARE_IRQ: if(req_strobe[0]) irq_software<=req_data[0];
                        32'h10000400: if(req_strobe[0] && req_data[0]) begin
                            performance_snapshot<=performance_values;
                            snapshot_sequence<=snapshot_sequence+1'b1;
                        end
                        default: rsp_error<=1;
                    endcase
                end else begin
                    rsp_data<=decoded_read_data;
                    rsp_error<=decoded_read_error;
                end
            end
        end
    end
endmodule
