CHANGES = [
    [
        "    wire [31:0] id_operand_a=(trace_write && wb_rd==id_rs1) ? wb_data : (register_valid[id_rs1] ? registers[id_rs1] : 32'd0);",
        "    (* syn_maxfan=16 *) wire id_register_a_valid=register_valid[id_rs1];\n    (* syn_maxfan=16 *) wire id_register_b_valid=register_valid[id_rs2];\n    wire [31:0] id_operand_a=(trace_write && wb_rd==id_rs1) ? wb_data : (id_register_a_valid ? registers[id_rs1] : 32'd0);"
    ],
    [
        "    wire [31:0] id_operand_b=(trace_write && wb_rd==id_rs2) ? wb_data : (register_valid[id_rs2] ? registers[id_rs2] : 32'd0);",
        "    wire [31:0] id_operand_b=(trace_write && wb_rd==id_rs2) ? wb_data : (id_register_b_valid ? registers[id_rs2] : 32'd0);"
    ]
]
