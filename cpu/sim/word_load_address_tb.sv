`timescale 1ns/1ps
module word_load_address_tb;
    parameter integer LOAD_USE_BUBBLE=1;
    parameter integer EARLY_D_REQUEST=1;
    typedef struct packed {
        logic uses_rs1,uses_rs2,writes_rd;
        logic [31:0] immediate;
        logic [3:0] alu_op;
        logic alu_immediate;
        logic is_lui,is_auipc,is_branch,is_jal,is_jalr,is_load,is_store;
        logic is_fence,is_fence_i,is_csr,is_ecall,is_ebreak,is_mret,is_wfi,illegal;
    } decode_t;
    decode_t decoded;
    reg clk=0,rst_n=0,response_valid=0,response_error=0,request_ready=0;
    reg [31:0] response_data=0;
    reg [31:0] values[0:7];
    integer cases=0,bubbles=0,faults=0;
    rv32_core #(.LOAD_USE_BUBBLE(LOAD_USE_BUBBLE),.EARLY_D_REQUEST(EARLY_D_REQUEST)) dut(
        .clk(clk),.rst_n(rst_n),.i_req_ready(1'b0),.i_rsp_valid(1'b0),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(request_ready),.d_rsp_valid(response_valid),.d_rsp_data(response_data),.d_rsp_error(response_error),
        .maintenance_ready(1'b1),.timer_value(64'b0),.irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    function automatic [31:0] loaded(input [31:0] data,input integer format_code,input integer offset);
        reg [31:0] shifted;
        begin
            shifted=data>>(offset*8);
            case(format_code)
                0: loaded={{24{shifted[7]}},shifted[7:0]};
                1: loaded={{16{shifted[15]}},shifted[15:0]};
                2: loaded=shifted;
                4: loaded={24'b0,shifted[7:0]};
                5: loaded={16'b0,shifted[15:0]};
                default: loaded=0;
            endcase
        end
    endfunction
    task tick;
        begin clk=1; #1; clk=0; #1; end
    endtask
    task run_case(input integer format_code,input integer offset,input [31:0] data,
                  input integer displacement,input integer ready,input integer fault);
        reg [31:0] pointer,address;
        reg wait_expected;
        begin
            clk=0; rst_n=0; response_valid=0; response_error=0; request_ready=ready!=0; response_data=data;
            #1; rst_n=1; #1; rst_n=0; #1; rst_n=1; #1;
            decoded='0; decoded.is_load=1; decoded.uses_rs1=1; decoded.writes_rd=1; decoded.immediate=32'(displacement);
            dut.ex_decode=decoded; dut.ex_valid=1; dut.ex_pc=32'h100; dut.ex_prediction=32'h104;
            dut.ex_instruction=32'h00008303; dut.ex_rd=6; dut.ex_operand_a=32'h12345678;
            dut.mem_valid=1; dut.mem_load=1; dut.mem_writes=1; dut.mem_rd=1; dut.mem_sent=1;
            dut.mem_instruction=32'h00000083 | (32'(format_code)<<12); dut.mem_pc=32'h80;
            dut.mem_prediction=32'h84; dut.mem_next_pc=32'h84; dut.mem_address=32'(offset);
            dut.mem_funct3=3'(format_code); dut.mem_load_route=dut.decode_load_route(3'(format_code),2'(offset));
            dut.wb_valid=1; dut.wb_writes=1; dut.wb_rd=1; dut.wb_data=32'h98765432;
            pointer=loaded(data,format_code,offset); address=pointer+32'(displacement);
            wait_expected=LOAD_USE_BUBBLE!=0 && format_code!=2;
            #1;
            if(dut.ex_fire || dut.d_req_valid) $fatal(1,"FAIL word_load_address issued before response case=%0d",cases);
            response_valid=1; response_error=fault!=0; #1;
            if(fault!=0) begin
                if(!dut.mem_flush || !dut.trap_valid || dut.trap_cause!==32'd5 || dut.trap_value!==32'(offset) || dut.ex_fire || dut.d_req_valid)
                    $fatal(1,"FAIL word_load_address older fault priority case=%0d",cases);
                tick(); response_valid=0; response_error=0; #1;
                if(dut.ex_valid || dut.wb_valid) $fatal(1,"FAIL word_load_address fault survived case=%0d",cases);
                faults=faults+1;
            end else begin
                if(wait_expected) begin
                    if(!dut.load_use_wait || dut.ex_fire || dut.d_req_valid)
                        $fatal(1,"FAIL word_load_address missing subword bubble case=%0d",cases);
                    tick(); response_valid=0; response_data=~data; #1;
                    if(dut.mem_valid || !dut.trace_write || dut.trace_data!==pointer)
                        $fatal(1,"FAIL word_load_address lost pointer writeback case=%0d",cases);
                    bubbles=bubbles+1;
                end else if(dut.load_use_wait) $fatal(1,"FAIL word_load_address unexpected word bubble case=%0d",cases);
                if(!dut.ex_fire || dut.effective_address!==address || dut.d_req_valid!==(EARLY_D_REQUEST!=0))
                    $fatal(1,"FAIL word_load_address executing address case=%0d expected=%08x actual=%08x",cases,address,dut.effective_address);
                if(EARLY_D_REQUEST!=0 && dut.d_req_address!=={address[31:2],2'b0})
                    $fatal(1,"FAIL word_load_address aligned request case=%0d",cases);
                tick(); response_valid=0; #1;
                if(!dut.mem_valid || dut.mem_address!==address || dut.mem_sent!==(EARLY_D_REQUEST!=0 && ready!=0) || dut.mem_pc!==32'h100)
                    $fatal(1,"FAIL word_load_address captured request case=%0d",cases);
                if(!dut.mem_sent) begin
                    if(!dut.d_req_valid || dut.d_req_address!=={address[31:2],2'b0})
                        $fatal(1,"FAIL word_load_address pending request case=%0d",cases);
                    request_ready=1; tick();
                end
                response_valid=1; response_data=32'h78563412; #1;
                tick(); response_valid=0; #1;
                if(!dut.trace_write || dut.trace_pc!==32'h100 || dut.trace_rd!==5'd6 || dut.trace_data!==loaded(32'h78563412,0,int'(address[1:0])))
                    $fatal(1,"FAIL word_load_address final retirement case=%0d",cases);
            end
            cases=cases+1;
        end
    endtask
    initial begin
        values[0]=0; values[1]=32'hffffffff; values[2]=32'h80008080; values[3]=32'h7fff7f7f;
        values[4]=32'h01020304; values[5]=32'h80818283; values[6]=32'ha55aa55a; values[7]=32'h5aa55aa5;
        for(integer format_code=0;format_code<6;format_code=format_code+1)
            if(format_code!=3)
                for(integer offset=0;offset<4;offset=offset+1)
                    if((format_code!=2 || offset==0) && ((format_code!=1 && format_code!=5) || offset%2==0))
                        for(integer sample=0;sample<8;sample=sample+1)
                            for(integer displacement=0;displacement<2;displacement=displacement+1)
                                for(integer ready=0;ready<2;ready=ready+1)
                                    for(integer fault=0;fault<2;fault=fault+1)
                                        run_case(format_code,offset,values[sample],displacement*4,ready,fault);
        if(cases!=832 || faults!=416 || bubbles!=(LOAD_USE_BUBBLE!=0 ? 384 : 0))
            $fatal(1,"FAIL word_load_address coverage cases=%0d faults=%0d bubbles=%0d",cases,faults,bubbles);
        $display("PASS word_load_address cases=%0d faults=%0d bubbles=%0d bubble=%0d early=%0d",cases,faults,bubbles,LOAD_USE_BUBBLE,EARLY_D_REQUEST);
        $finish;
    end
endmodule
