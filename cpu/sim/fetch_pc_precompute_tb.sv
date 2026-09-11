`timescale 1ns/1ps
module fetch_pc_precompute_tb;
    parameter integer PREDICTOR=1;
    parameter integer CHECK_INCREMENT=1;
    reg clk=0,rst_n=0;
    reg prediction_hit_value=0,predicted_taken_value=0;
    reg flush_value=0,barrier_value=0,active_value=0,complete_value=0;
    reg [31:0] target_value=0,redirect_value=0;
    reg [31:0] random_state=32'h76ad5213;
    reg [31:0] edges[0:15];
    integer checks=0;
    rv32_core #(.ENABLE_PREDICTOR(PREDICTOR)) dut(.clk(clk),.rst_n(rst_n),
        .i_req_ready(1'b0),.i_rsp_valid(1'b0),.i_rsp_data(32'b0),.i_rsp_error(1'b0),
        .d_req_ready(1'b0),.d_rsp_valid(1'b0),.d_rsp_data(32'b0),.d_rsp_error(1'b0),
        .maintenance_ready(1'b0),.timer_value(64'b0),
        .irq_external(1'b0),.irq_software(1'b0),.irq_timer(1'b0));
    task automatic check_case(input [31:0] pc_value,input [31:0] predicted_value,input integer mode);
        reg [31:0] sequential,expected_pc,expected_prediction;
        begin
            clk=0; dut.next_pc=pc_value; dut.fetch_prediction=32'hdeadbeef;
            target_value=predicted_value; redirect_value=pc_value ^ 32'h13572468;
            prediction_hit_value=mode[0]; predicted_taken_value=mode[1];
            flush_value=mode[2]; barrier_value=mode[3];
            active_value=mode[4]; complete_value=mode[5];
            sequential=pc_value+32'd4;
            expected_pc=pc_value; expected_prediction=32'hdeadbeef;
            if((!active_value || complete_value) && !flush_value && !barrier_value) begin
                expected_pc=(PREDICTOR!=0 && prediction_hit_value && predicted_taken_value) ? predicted_value : sequential;
                expected_prediction=expected_pc;
            end
            if(flush_value) expected_pc=redirect_value;
            #1;
            if(CHECK_INCREMENT!=0) begin : verify_increment
                if(dut.sequential_fetch_pc!==sequential) $fatal(1,"FAIL fetch_pc_precompute increment");
            end
            clk=1;
            #1;
            if(dut.next_pc!==expected_pc || dut.fetch_prediction!==expected_prediction)
                $fatal(1,"FAIL fetch_pc_precompute pc=%08x target=%08x mode=%0d expected=%08x/%08x actual=%08x/%08x",pc_value,predicted_value,mode,expected_pc,expected_prediction,dut.next_pc,dut.fetch_prediction);
            checks=checks+1;
            clk=0;
        end
    endtask
    initial begin
        force dut.prediction_hit=prediction_hit_value;
        force dut.predicted_taken=predicted_taken_value;
        force dut.predicted_target=target_value;
        force dut.mem_flush=flush_value;
        force dut.frontend_barrier=barrier_value;
        force dut.fetch_active=active_value;
        force dut.fetch_complete=complete_value;
        force dut.redirect_pc=redirect_value;
        #1; rst_n=1; #1; rst_n=0; #1; rst_n=1;
        edges[0]=0; edges[1]=1; edges[2]=2; edges[3]=3;
        edges[4]=32'hffffffff; edges[5]=32'hfffffffc; edges[6]=32'hfffffffd; edges[7]=32'hfffffffe;
        edges[8]=32'h000003ff; edges[9]=32'h0003ffff; edges[10]=32'h03ffffff; edges[11]=32'h7fffffff;
        edges[12]=32'h80000000; edges[13]=32'hffff0001; edges[14]=32'h55555555; edges[15]=32'haaaaaaaa;
        for(integer edge_index=0;edge_index<16;edge_index=edge_index+1)
            for(integer mode=0;mode<64;mode=mode+1) check_case(edges[edge_index],~edges[edge_index],mode);
        for(integer position=2;position<32;position=position+1)
            for(integer low=0;low<4;low=low+1)
                for(integer mode=0;mode<4;mode=mode+1)
                    check_case((32'd1<<position)-4+32'(low),32'h81234567,mode);
        for(integer sample=0;sample<10000;sample=sample+1) begin
            random_state=random_state ^ (random_state<<13);
            random_state=random_state ^ (random_state>>17);
            random_state=random_state ^ (random_state<<5);
            check_case(random_state,random_state ^ 32'h97afe541,sample%64);
        end
        if(checks!=11504) $fatal(1,"Incomplete PC precompute test coverage");
        $display("PASS fetch_pc_precompute checks=%0d predictor=%0d",checks,PREDICTOR);
        $finish;
    end
endmodule

