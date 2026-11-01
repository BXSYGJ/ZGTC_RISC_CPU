`timescale 1ns/1ps
module bare_extraction_miter (
 input wire clk,rst_n,serial_rx,inject_bus_fault,
 input wire [7:0] gpio_input,
 output wire [63:0] mismatch,
 output wire [645:0] reference_frame,bare_frame,
 output wire serial_tx,maintenance_fault,trap_valid,trace_valid,trace_write,
 output wire i_request_fire,i_response_fire,d_request_fire,d_response_fire,maintenance_fire,
 output wire [31:0] status_code,trace_pc,
 output wire [63:0] cycle_count,retired_count
);
 GTP_GRS GRS_INST(.GRS_N(1'b1));
 reference_soc #(.ENABLE_M(1),.ENABLE_C(1),.ENABLE_PREDICTOR(1),.LOAD_USE_BUBBLE(1),.FAST_ICACHE_HIT(1),.FAST_DCACHE_READ(1),.FAST_DCACHE_WRITE(1),.FETCH_OVERLAP(1),.DATA_OVERLAP(1),.EARLY_D_REQUEST(1),.BTB_INDEX_BITS(8),.ICACHE_SET_BITS(9),.CACHE_SET_BITS(6),.ENABLE_CACHE(1),.MEMORY_ADDRESS_BITS(14),.CLOCK_HZ(3200),.BAUD(100),.INIT_FILE("firmware.hex")) reference_soc(
  .clk(clk),.rst_n(rst_n),.serial_rx(serial_rx),.gpio_input(gpio_input),
  .serial_tx(),.gpio_output(),.status_code(),.maintenance_fault(),
  .trace_valid(),.trace_pc(),.trace_instruction(),.trap_valid(),.trap_cause(),
  .cycle_count(),.retired_count());
 bare_environment #(.ENABLE_M(1),.ENABLE_C(1),.ENABLE_PREDICTOR(1),.LOAD_USE_BUBBLE(1),.FAST_ICACHE_HIT(1),.FAST_DCACHE_READ(1),.FAST_DCACHE_WRITE(1),.FETCH_OVERLAP(1),.DATA_OVERLAP(1),.EARLY_D_REQUEST(1),.BTB_INDEX_BITS(8),.ICACHE_SET_BITS(9),.CACHE_SET_BITS(6),.ENABLE_CACHE(1),.MEMORY_ADDRESS_BITS(14),.CLOCK_HZ(3200),.BAUD(100),.INIT_FILE("firmware.hex")) environment(
  .inject_bus_fault(inject_bus_fault),.clk(clk),.rst_n(rst_n),.serial_rx(serial_rx),.gpio_input(gpio_input),
  .serial_tx(),.gpio_output(),.status_code(),.maintenance_fault(),
  .trace_valid(),.trace_pc(),.trace_instruction(),.trap_valid(),.trap_cause(),
  .cycle_count(),.retired_count());
 assign mismatch[0]=(reference_soc.core.i_req_valid !== environment.core.i_req_valid);
 assign mismatch[1]=(reference_soc.core.i_req_ready !== environment.core.i_req_ready);
 assign mismatch[2]=(reference_soc.core.i_req_address !== environment.core.i_req_address);
 assign mismatch[3]=(reference_soc.core.i_req_pair_address !== environment.core.i_req_pair_address);
 assign mismatch[4]=(reference_soc.core.i_rsp_valid !== environment.core.i_rsp_valid);
 assign mismatch[5]=(reference_soc.core.i_rsp_ready !== environment.core.i_rsp_ready);
 assign mismatch[6]=(reference_soc.core.i_rsp_data !== environment.core.i_rsp_data);
 assign mismatch[7]=(reference_soc.core.i_rsp_pair_data !== environment.core.i_rsp_pair_data);
 assign mismatch[8]=(reference_soc.core.i_rsp_is_c !== environment.core.i_rsp_is_c);
 assign mismatch[9]=(reference_soc.core.i_rsp_pair_is_c !== environment.core.i_rsp_pair_is_c);
 assign mismatch[10]=(reference_soc.core.i_rsp_pair_valid !== environment.core.i_rsp_pair_valid);
 assign mismatch[11]=(reference_soc.core.i_rsp_error !== environment.core.i_rsp_error);
 assign mismatch[12]=(reference_soc.core.d_req_valid !== environment.core.d_req_valid);
 assign mismatch[13]=(reference_soc.core.d_req_ready !== environment.core.d_req_ready);
 assign mismatch[14]=(reference_soc.core.d_req_address !== environment.core.d_req_address);
 assign mismatch[15]=(reference_soc.core.d_req_data !== environment.core.d_req_data);
 assign mismatch[16]=(reference_soc.core.d_req_strobe !== environment.core.d_req_strobe);
 assign mismatch[17]=(reference_soc.core.d_req_write !== environment.core.d_req_write);
 assign mismatch[18]=(reference_soc.core.d_rsp_valid !== environment.core.d_rsp_valid);
 assign mismatch[19]=(reference_soc.core.d_rsp_ready !== environment.core.d_rsp_ready);
 assign mismatch[20]=(reference_soc.core.d_rsp_data !== environment.core.d_rsp_data);
 assign mismatch[21]=(reference_soc.core.d_rsp_error !== environment.core.d_rsp_error);
 assign mismatch[22]=(reference_soc.core.maintenance_valid !== environment.core.maintenance_valid);
 assign mismatch[23]=(reference_soc.core.maintenance_ready !== environment.core.maintenance_ready);
 assign mismatch[24]=(reference_soc.core.timer_value !== environment.core.timer_value);
 assign mismatch[25]=(reference_soc.core.irq_external !== environment.core.irq_external);
 assign mismatch[26]=(reference_soc.core.irq_software !== environment.core.irq_software);
 assign mismatch[27]=(reference_soc.core.irq_timer !== environment.core.irq_timer);
 assign mismatch[28]=(reference_soc.core.trace_valid !== environment.core.trace_valid);
 assign mismatch[29]=(reference_soc.core.trace_pc !== environment.core.trace_pc);
 assign mismatch[30]=(reference_soc.core.trace_instruction !== environment.core.trace_instruction);
 assign mismatch[31]=(reference_soc.core.trace_write !== environment.core.trace_write);
 assign mismatch[32]=(reference_soc.core.trace_rd !== environment.core.trace_rd);
 assign mismatch[33]=(reference_soc.core.trace_data !== environment.core.trace_data);
 assign mismatch[34]=(reference_soc.core.trap_valid !== environment.core.trap_valid);
 assign mismatch[35]=(reference_soc.core.trap_pc !== environment.core.trap_pc);
 assign mismatch[36]=(reference_soc.core.trap_cause !== environment.core.trap_cause);
 assign mismatch[37]=(reference_soc.core.trap_value !== environment.core.trap_value);
 assign mismatch[38]=(reference_soc.core.pipeline_valid !== environment.core.pipeline_valid);
 assign mismatch[39]=(reference_soc.core.cycle_count !== environment.core.cycle_count);
 assign mismatch[40]=(reference_soc.core.retired_count !== environment.core.retired_count);
 assign mismatch[41]=(reference_soc.serial_tx !== environment.serial_tx);
 assign mismatch[42]=(reference_soc.gpio_output !== environment.gpio_output);
 assign mismatch[43]=(reference_soc.status_code !== environment.status_code);
 assign mismatch[44]=(reference_soc.maintenance_fault !== environment.maintenance_fault);
 assign mismatch[45]=(reference_soc.mmio_req_valid !== environment.mmio_req_valid);
 assign mismatch[46]=(reference_soc.mmio_req_ready !== environment.mmio_req_ready);
 assign mismatch[47]=(reference_soc.mmio_rsp_valid !== environment.mmio_rsp_valid);
 assign mismatch[48]=(reference_soc.mmio_rsp_ready !== environment.mmio_rsp_ready);
 assign mismatch[49]=(reference_soc.mmio_rsp_data !== environment.mmio_rsp_data);
 assign mismatch[50]=(reference_soc.mmio_rsp_error !== environment.mmio_rsp_error);
 assign mismatch[63:51]=0;
 assign reference_frame={reference_soc.core.i_req_valid,reference_soc.core.i_req_ready,reference_soc.core.i_req_address,reference_soc.core.i_req_pair_address,reference_soc.core.i_rsp_valid,reference_soc.core.i_rsp_ready,reference_soc.core.i_rsp_data,reference_soc.core.i_rsp_pair_data,reference_soc.core.i_rsp_is_c,reference_soc.core.i_rsp_pair_is_c,reference_soc.core.i_rsp_pair_valid,reference_soc.core.i_rsp_error,reference_soc.core.d_req_valid,reference_soc.core.d_req_ready,reference_soc.core.d_req_address,reference_soc.core.d_req_data,reference_soc.core.d_req_strobe,reference_soc.core.d_req_write,reference_soc.core.d_rsp_valid,reference_soc.core.d_rsp_ready,reference_soc.core.d_rsp_data,reference_soc.core.d_rsp_error,reference_soc.core.maintenance_valid,reference_soc.core.maintenance_ready,reference_soc.core.timer_value,reference_soc.core.irq_external,reference_soc.core.irq_software,reference_soc.core.irq_timer,reference_soc.core.trace_valid,reference_soc.core.trace_pc,reference_soc.core.trace_instruction,reference_soc.core.trace_write,reference_soc.core.trace_rd,reference_soc.core.trace_data,reference_soc.core.trap_valid,reference_soc.core.trap_pc,reference_soc.core.trap_cause,reference_soc.core.trap_value,reference_soc.core.pipeline_valid,reference_soc.core.cycle_count,reference_soc.core.retired_count};
 assign bare_frame={environment.core.i_req_valid,environment.core.i_req_ready,environment.core.i_req_address,environment.core.i_req_pair_address,environment.core.i_rsp_valid,environment.core.i_rsp_ready,environment.core.i_rsp_data,environment.core.i_rsp_pair_data,environment.core.i_rsp_is_c,environment.core.i_rsp_pair_is_c,environment.core.i_rsp_pair_valid,environment.core.i_rsp_error,environment.core.d_req_valid,environment.core.d_req_ready,environment.core.d_req_address,environment.core.d_req_data,environment.core.d_req_strobe,environment.core.d_req_write,environment.core.d_rsp_valid,environment.core.d_rsp_ready,environment.core.d_rsp_data,environment.core.d_rsp_error,environment.core.maintenance_valid,environment.core.maintenance_ready,environment.core.timer_value,environment.core.irq_external,environment.core.irq_software,environment.core.irq_timer,environment.core.trace_valid,environment.core.trace_pc,environment.core.trace_instruction,environment.core.trace_write,environment.core.trace_rd,environment.core.trace_data,environment.core.trap_valid,environment.core.trap_pc,environment.core.trap_cause,environment.core.trap_value,environment.core.pipeline_valid,environment.core.cycle_count,environment.core.retired_count};
 assign serial_tx=environment.serial_tx;
 assign maintenance_fault=environment.maintenance_fault;
 assign status_code=environment.status_code;
 assign trap_valid=environment.core.trap_valid;
 assign trace_valid=environment.core.trace_valid;
 assign trace_write=environment.core.trace_write;
 assign trace_pc=environment.core.trace_pc;
 assign cycle_count=environment.core.cycle_count;
 assign retired_count=environment.core.retired_count;
 assign i_request_fire=environment.i_req_valid && environment.i_req_ready;
 assign i_response_fire=environment.i_rsp_valid && environment.i_rsp_ready;
 assign d_request_fire=environment.d_req_valid && environment.d_req_ready;
 assign d_response_fire=environment.d_rsp_valid && environment.d_rsp_ready;
 assign maintenance_fire=environment.maintenance_valid && environment.maintenance_ready;
endmodule
