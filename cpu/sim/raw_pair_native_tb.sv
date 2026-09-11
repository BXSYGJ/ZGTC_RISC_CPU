`timescale 1ns/1ps
module raw_pair_native_tb;
    reg [31:0] forwarded_a=0,forwarded_b=0,id_operand_a=0,id_operand_b=0;
    reg id_fire=0;
    wire [1:0] relation;
    reg [31:0] selected_a,selected_b;
    integer sample_index,select_index,checks=0;
    raw_native_compare candidate(.forwarded_a(forwarded_a),.forwarded_b(forwarded_b),.id_operand_a(id_operand_a),.id_operand_b(id_operand_b),.id_fire(id_fire),.relation(relation));
    initial begin
        for(sample_index=0;sample_index<8192;sample_index=sample_index+1) begin
            forwarded_a=$random; forwarded_b=$random; id_operand_a=$random; id_operand_b=$random;
            case(sample_index%4)
                0: forwarded_b=forwarded_a;
                1: id_operand_b=id_operand_a;
                2: begin forwarded_a=32'hffffffff; forwarded_b=0; id_operand_a=0; id_operand_b=32'hffffffff; end
                default: begin end
            endcase
            for(select_index=0;select_index<2;select_index=select_index+1) begin
                id_fire=select_index[0]; selected_a=id_fire ? id_operand_a : forwarded_a; selected_b=id_fire ? id_operand_b : forwarded_b;
                #1;
                if(relation!=={selected_a==selected_b,selected_a<selected_b})
                    $fatal(1,"FAIL raw native relation select=%b a=%h b=%h relation=%b",id_fire,selected_a,selected_b,relation);
                checks=checks+1;
            end
        end
        $display("PASS raw native unsigned equality checks=%0d",checks);
        $finish;
    end
endmodule
