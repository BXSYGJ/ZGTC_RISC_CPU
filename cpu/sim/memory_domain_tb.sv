`timescale 1ns/1ps
module memory_domain_tb #(
    parameter integer ENABLE_CACHE=1,
    parameter integer DATA_OVERLAP=1
);
    reg clk=0,rst_n=1,d_req_valid=0;
    reg [31:0] d_req_address=0;
    reg [31:0] random_state=32'h91ac406d;
    reg [27:0] lower_address;
    reg expected_mmio;
    wire d_req_ready;
    integer checks=0,ram_cases=0,mmio_cases=0;
    rv32_memory_system #(.MEMORY_ADDRESS_BITS(6),.CACHE_SET_BITS(1),.ENABLE_CACHE(ENABLE_CACHE),.DATA_OVERLAP(DATA_OVERLAP)) dut(
        .clk(clk),.rst_n(rst_n),.i_req_valid(1'b0),.i_req_address(32'b0),.i_rsp_ready(1'b1),
        .d_req_valid(d_req_valid),.d_req_ready(d_req_ready),.d_req_address(d_req_address),.d_req_write(1'b0),.d_req_data(32'h12345678),.d_req_strobe(4'hf),.d_rsp_ready(1'b0),
        .maintenance_valid(1'b0),.mmio_req_ready(1'b0),.mmio_rsp_valid(1'b0),.mmio_rsp_data(32'b0),.mmio_rsp_error(1'b0));
    task automatic probe(input integer upper,input integer sample);
        begin
            clk=0; rst_n=0; d_req_valid=0; #1;
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
            case(sample)
                0: lower_address=0;
                1: lower_address=28'hfffffff;
                2: lower_address=28'h1000000;
                3: lower_address=28'h8000000;
                4: lower_address=28'h000ffff;
                5: lower_address=28'h0010000;
                6: lower_address=28'h0fff000;
                7: lower_address=28'h0fffffe;
                default: lower_address=random_state[27:0];
            endcase
            d_req_address={4'(upper),lower_address};
            expected_mmio=upper!=0;
            d_req_valid=1; rst_n=1; #1;
            if(dut.request_mmio!==expected_mmio || !d_req_ready || dut.cache_req_valid[1]!==!expected_mmio)
                $fatal(1,"FAIL memory_domain request owner upper=%0d sample=%0d",upper,sample);
            if(!expected_mmio && dut.cache_req_address[1]!==d_req_address)
                $fatal(1,"FAIL memory_domain accepted RAM address changed upper=%0d sample=%0d",upper,sample);
            clk=1; #1;
            if(!dut.data_active || dut.data_mmio!==expected_mmio || dut.mmio_request_pending!==expected_mmio)
                $fatal(1,"FAIL memory_domain registered owner upper=%0d sample=%0d",upper,sample);
            if(expected_mmio && dut.mmio_request_address!==d_req_address)
                $fatal(1,"FAIL memory_domain MMIO payload truncated upper=%0d sample=%0d",upper,sample);
            if(expected_mmio) mmio_cases=mmio_cases+1; else ram_cases=ram_cases+1;
            checks=checks+1;
        end
    endtask
    initial begin
        for(integer upper=0;upper<16;upper=upper+1)
            for(integer sample=0;sample<64;sample=sample+1) probe(upper,sample);
        if(checks!=1024 || ram_cases!=64 || mmio_cases!=960) $fatal(1,"FAIL memory_domain coverage");
        $display("PASS memory_domain checks=%0d ram=%0d mmio=%0d cache=%0d overlap=%0d",checks,ram_cases,mmio_cases,ENABLE_CACHE,DATA_OVERLAP);
        $finish;
    end
endmodule
