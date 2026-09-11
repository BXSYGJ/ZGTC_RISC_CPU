CHANGES = [
    [
        "    wire [PATTERNS-1:0] pattern_prediction;",
        "    wire [PATTERNS-1:0] pattern_prediction;\n    wire [HISTORY_BITS-1:0] prior_history=history[update_index];\n    wire run_saturated=(prior_history | {1'b1,{(HISTORY_BITS-1){1'b0}}})=={HISTORY_BITS{1'b1}};\n    wire [HISTORY_BITS-1:0] next_history=prior_history[HISTORY_BITS-1]==update_taken ?\n        (run_saturated ? prior_history : prior_history+{{(HISTORY_BITS-1){1'b0}},1'b1}) :\n        {update_taken,{(HISTORY_BITS-1){1'b0}}};"
    ],
    [
        "history[update_index]<=update_conditional ? {{(HISTORY_BITS-1){1'b0}},update_taken} : {HISTORY_BITS{1'b0}};",
        "history[update_index]<=update_conditional ? {update_taken,{(HISTORY_BITS-1){1'b0}}} : {HISTORY_BITS{1'b0}};"
    ],
    [
        "history[update_index]<=(history[update_index] << 1) | {{(HISTORY_BITS-1){1'b0}},update_taken};",
        "history[update_index]<=next_history;"
    ]
]
