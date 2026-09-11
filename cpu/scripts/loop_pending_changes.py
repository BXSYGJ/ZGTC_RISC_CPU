CHANGES = [
  [
    "    reg loop_direction [0:LOOP_ENTRIES-1];",
    "    reg loop_direction [0:LOOP_ENTRIES-1];\n    reg loop_ahead_direction [0:LOOP_ENTRIES-1];"
  ],
  [
    "    wire loop_use=loop_fetch_match && loop_confidence[loop_fetch_index][1];",
    "    wire loop_use=loop_fetch_match && loop_confidence[loop_fetch_index][1];\n    wire loop_pending_taken=!invalidate && train_update && update_conditional && update_taken &&\n        update_target<update_pc && loop_update_match && loop_fetch_index==loop_update_index;"
  ],
  [
    "                    loop_direction[loop_update_index]<=1;\n                end else if (update_taken) begin",
    "                    loop_direction[loop_update_index]<=1;\n                    loop_ahead_direction[loop_update_index]<=0;\n                end else if (update_taken) begin"
  ],
  [
    "                        loop_overflow[loop_update_index]<=1;\n                        loop_confidence[loop_update_index]<=0;\n                        loop_direction[loop_update_index]<=0;",
    "                        loop_overflow[loop_update_index]<=1;\n                        loop_confidence[loop_update_index]<=0;\n                        loop_direction[loop_update_index]<=0;\n                        loop_ahead_direction[loop_update_index]<=0;"
  ],
  [
    "                        loop_direction[loop_update_index]<=(loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-1){1'b0}},1'b1})<loop_trip[loop_update_index];",
    "                        loop_direction[loop_update_index]<=(loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-1){1'b0}},1'b1})<loop_trip[loop_update_index];\n                        loop_ahead_direction[loop_update_index]<=({1'b0,loop_count[loop_update_index]}+{{(LOOP_COUNT_BITS-1){1'b0}},2'b10})<{1'b0,loop_trip[loop_update_index]};"
  ],
  [
    "                        loop_direction[loop_update_index]<=0;\n                    end else begin\n                        loop_trip[loop_update_index]<=loop_count[loop_update_index];",
    "                        loop_direction[loop_update_index]<=0;\n                        loop_ahead_direction[loop_update_index]<=0;\n                    end else begin\n                        loop_trip[loop_update_index]<=loop_count[loop_update_index];"
  ],
  [
    "                        loop_direction[loop_update_index]<=1;\n                        if (loop_trip[loop_update_index]==loop_count[loop_update_index]) begin",
    "                        loop_direction[loop_update_index]<=1;\n                        loop_ahead_direction[loop_update_index]<=loop_count[loop_update_index]>1;\n                        if (loop_trip[loop_update_index]==loop_count[loop_update_index]) begin"
  ],
  [
    "(loop_use ? loop_direction[loop_fetch_index] : pattern_prediction[history[fetch_index]])",
    "(loop_use ? (loop_pending_taken ? loop_ahead_direction[loop_fetch_index] : loop_direction[loop_fetch_index]) : pattern_prediction[history[fetch_index]])"
  ]
]
