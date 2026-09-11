CHANGES = [
    [
        "    integer reset_index;",
        "    reg [31:0] register_valid;"
    ],
    [
        " : registers[id_rs1];",
        " : (register_valid[id_rs1] ? registers[id_rs1] : 32'd0);"
    ],
    [
        " : registers[id_rs2];",
        " : (register_valid[id_rs2] ? registers[id_rs2] : 32'd0);"
    ],
    [
        "            for(reset_index=0;reset_index<32;reset_index=reset_index+1) registers[reset_index]<=0;",
        "            register_valid<=0;"
    ],
    [
        "            if(trace_write) registers[wb_rd]<=wb_data;",
        "            if(trace_write) register_valid[wb_rd]<=1'b1;"
    ],
    [
        "    always @(posedge clk or negedge rst_n) begin\n        if(!rst_n) begin\n            muldiv_started<=0;",
        "    always @(posedge clk) begin\n        if(rst_n && trace_write) registers[wb_rd]<=wb_data;\n    end\n    always @(posedge clk or negedge rst_n) begin\n        if(!rst_n) begin\n            muldiv_started<=0;"
    ]
]
