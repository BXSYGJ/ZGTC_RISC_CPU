`timescale 1ns/1ps
module regfile_valid_tb;
    reg clk=0,rst_n=1,trace_write=0;
    reg [4:0] wb_rd=0,id_rs1=0,id_rs2=0;
    reg [31:0] wb_data=0,random_state=32'h5f937ca1;
    wire [31:0] parent_a,parent_b,candidate_a,candidate_b;
    integer checks=0,cycles=0,resets=0,epoch,number,query,trial;
    parent_regfile reference_design(.clk(clk),.rst_n(rst_n),.trace_write(trace_write),.wb_rd(wb_rd),.id_rs1(id_rs1),.id_rs2(id_rs2),.wb_data(wb_data),.id_operand_a(parent_a),.id_operand_b(parent_b));
    candidate_regfile candidate_design(.clk(clk),.rst_n(rst_n),.trace_write(trace_write),.wb_rd(wb_rd),.id_rs1(id_rs1),.id_rs2(id_rs2),.wb_data(wb_data),.id_operand_a(candidate_a),.id_operand_b(candidate_b));
    task check;
        begin
            if(parent_a!==candidate_a || parent_b!==candidate_b)
                $fatal(1,"FAIL regfile_valid cycles=%0d reset=%0d ports=%0d/%0d expected=%h/%h actual=%h/%h",cycles,rst_n,id_rs1,id_rs2,parent_a,parent_b,candidate_a,candidate_b);
            checks=checks+1;
        end
    endtask
    task step;
        begin
            #1; check();
            clk=1; #1; check();
            clk=0; #1; check();
            cycles=cycles+1;
        end
    endtask
    task reset_now;
        begin
            trace_write=0; rst_n=0; #1; check();
            resets=resets+1;
            step();
            rst_n=1; #1; check();
        end
    endtask
    task next_random;
        begin
            random_state=random_state^(random_state<<13);
            random_state=random_state^(random_state>>17);
            random_state=random_state^(random_state<<5);
        end
    endtask
    initial begin
        reset_now();
        for(epoch=0;epoch<8;epoch=epoch+1) begin
            for(query=0;query<1024;query=query+1) begin
                id_rs1=query[4:0]; id_rs2=query[9:5]; trace_write=0; step();
            end
            for(number=1;number<32;number=number+1) begin
                wb_rd=number[4:0]; id_rs1=number[4:0]; id_rs2=number[4:0];
                next_random();
                case(epoch)
                    1: wb_data=32'hxxxxxxxx;
                    2: wb_data=32'hzzzzzzzz;
                    3: wb_data=32'h12xz34xz;
                    4: wb_data=0;
                    default: wb_data=random_state;
                endcase
                trace_write=1; step();
                trace_write=0; step();
            end
            for(query=0;query<1024;query=query+1) begin
                id_rs1=query[4:0]; id_rs2=query[9:5]; trace_write=0; step();
            end
            reset_now();
        end
        for(trial=0;trial<8192;trial=trial+1) begin
            next_random();
            wb_rd=random_state[4:0]; id_rs1=random_state[9:5]; id_rs2=random_state[14:10];
            trace_write=random_state[15] && wb_rd!=0;
            if(trial%7==0) id_rs1=wb_rd;
            if(trial%11==0) id_rs2=wb_rd;
            wb_data=trial%17==0 ? 32'hzx01xz10 : random_state;
            if(trial%257==0) reset_now();
            step();
        end
        reset_now();
        for(number=1;number<32;number=number+1) begin
            rst_n=0; resets=resets+1; trace_write=1; wb_rd=number[4:0];
            id_rs1=number[4:0]; id_rs2=0; wb_data=32'ha55ac33c;
            step();
            trace_write=0; step();
            rst_n=1; step();
            trace_write=1; wb_data=32'h0f0ff0f0; step();
            trace_write=0; step();
        end
        if(cycles<25000 || checks<75000 || resets!=73)
            $fatal(1,"FAIL regfile_valid insufficient coverage");
        $display("PASS regfile_valid cycles=%0d checks=%0d resets=%0d read_pairs=1024 data_includes_XZ=1",cycles,checks,resets);
        $finish;
    end
endmodule
