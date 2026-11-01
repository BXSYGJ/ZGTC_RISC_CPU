`timescale 1ns/1ps
module bare_core_scan_top (
    input wire clk, fixture_reset_n, scan_in, scan_shift, scan_update, scan_capture,
    output wire scan_out
);
    localparam integer INPUT_BITS=176;
    localparam integer OUTPUT_BITS=439;
    (* syn_preserve=1 *) reg [INPUT_BITS-1:0] input_shift, active_inputs;
    (* syn_preserve=1 *) reg [OUTPUT_BITS-1:0] output_shift;
    wire [OUTPUT_BITS-1:0] core_outputs;
    assign scan_out=output_shift[0];
    always @(posedge clk or negedge fixture_reset_n) begin
        if(!fixture_reset_n) begin input_shift<=0; active_inputs<=0; output_shift<=0; end
        else begin
            if(scan_shift) input_shift<={input_shift[INPUT_BITS-2:0],scan_in};
            if(scan_update) active_inputs<=input_shift;
            if(scan_capture) output_shift<=core_outputs;
            else if(scan_shift) output_shift<={1'b0,output_shift[OUTPUT_BITS-1:1]};
        end
    end
    (* syn_hier="fixed", syn_noprune=1 *) rv32_bare_core core_boundary (
        .clk(clk),
        .rst_n(active_inputs[0]),
        .i_req_valid(core_outputs[0]),
        .i_req_ready(active_inputs[1]),
        .i_req_address(core_outputs[32:1]),
        .i_rsp_valid(active_inputs[2]),
        .i_rsp_ready(core_outputs[33]),
        .i_rsp_data(active_inputs[34:3]),
        .i_rsp_pair_data(active_inputs[66:35]),
        .i_rsp_is_c(active_inputs[68:67]),
        .i_rsp_pair_is_c(active_inputs[70:69]),
        .i_rsp_pair_valid(active_inputs[71]),
        .i_rsp_error(active_inputs[72]),
        .d_req_valid(core_outputs[34]),
        .d_req_ready(active_inputs[73]),
        .d_req_address(core_outputs[66:35]),
        .d_req_data(core_outputs[98:67]),
        .d_req_strobe(core_outputs[102:99]),
        .d_req_write(core_outputs[103]),
        .d_rsp_valid(active_inputs[74]),
        .d_rsp_ready(core_outputs[104]),
        .d_rsp_data(active_inputs[106:75]),
        .d_rsp_error(active_inputs[107]),
        .maintenance_valid(core_outputs[105]),
        .maintenance_ready(active_inputs[108]),
        .timer_value(active_inputs[172:109]),
        .irq_external(active_inputs[173]),
        .irq_software(active_inputs[174]),
        .irq_timer(active_inputs[175]),
        .trace_valid(core_outputs[106]),
        .trace_pc(core_outputs[138:107]),
        .trace_instruction(core_outputs[170:139]),
        .trace_write(core_outputs[171]),
        .trace_rd(core_outputs[176:172]),
        .trace_data(core_outputs[208:177]),
        .trap_valid(core_outputs[209]),
        .trap_pc(core_outputs[241:210]),
        .trap_cause(core_outputs[273:242]),
        .trap_value(core_outputs[305:274]),
        .pipeline_valid(core_outputs[310:306]),
        .cycle_count(core_outputs[374:311]),
        .retired_count(core_outputs[438:375])
    );
endmodule
