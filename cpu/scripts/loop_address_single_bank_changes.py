CHANGES = [
  [
    "    localparam integer LOOP_ENTRIES=1<<LOOP_INDEX_BITS;",
    "    localparam integer LOOP_ENTRIES=1;"
  ],
  [
    "    genvar loop_index_bit;\n    generate for (loop_index_bit=0;loop_index_bit<LOOP_INDEX_BITS;loop_index_bit=loop_index_bit+1) begin: loop_index_wires\n        if (loop_index_bit+LOOP_INDEX_SHIFT<INDEX_BITS) begin: mapped\n            assign loop_fetch_index[loop_index_bit]=fetch_index[loop_index_bit+LOOP_INDEX_SHIFT];\n            assign loop_update_index[loop_index_bit]=update_index[loop_index_bit+LOOP_INDEX_SHIFT];\n        end else begin: unused_index\n            assign loop_fetch_index[loop_index_bit]=1'b0;\n            assign loop_update_index[loop_index_bit]=1'b0;\n        end\n    end endgenerate\n",
    "    assign loop_fetch_index={LOOP_INDEX_BITS{1'b0}};\n    assign loop_update_index={LOOP_INDEX_BITS{1'b0}};\n    wire loop_update_admitted;\n    generate if (LOOP_INDEX_SHIFT<INDEX_BITS) begin: admitted_bank\n        assign loop_update_admitted=!update_index[LOOP_INDEX_SHIFT];\n    end else begin: all_admitted\n        assign loop_update_admitted=1'b1;\n    end endgenerate\n"
  ],
  [
    "        end else if (train_update) begin\n            if (update_conditional && update_target[ADDRESS_BITS-1:2]<update_pc[ADDRESS_BITS-1:2]) begin",
    "        end else if (train_update && loop_update_admitted) begin\n            if (update_conditional && update_target[ADDRESS_BITS-1:2]<update_pc[ADDRESS_BITS-1:2]) begin"
  ]
]
