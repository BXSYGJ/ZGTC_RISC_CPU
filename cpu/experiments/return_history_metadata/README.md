# Return classification stored in unused history bits

## Scope

This is an isolated predictor storage experiment, not an integrated CPU, physical implementation or new benchmark version. Its reference is `full_id_relation_mask1/rv32_btb.sv` (SHA256 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E). Candidate SHA256: `6E1B86520A18A36CBC8F5AE4ADA3568207660851EE794C8178879F5C44FB2030`. Four exact substitutions are recorded in `change-receipt.json`.

## Representation change

Conditional entries retain their complete dynamic history. Unconditional entries do not use conditional history for taken/not-taken prediction, so their history bit zero stores return classification instead of a separate return_entry array. Every trained unconditional update refreshes that bit. A conditional/unconditional type change already forces allocation in the unchanged predictor, initializing conditional history before it is used again. Other history bits are cleared for unconditional entries. Tags, target addresses, counters, allocation rules, stack behavior, reset/invalidation and prediction interfaces are unchanged.

The RTL removes ENTRIES dedicated return-classification bits while keeping all functionality. Actual LUT savings are not established: inference, packing and placement must be measured with the complete CPU and retained GPIO/UART/42-data/33-trigger/1024-sample ILA.

## Completed tests

Three test methods pass. The differential bench runs 12000 clock cycles per configuration, comparing outputs before and after each update (24000 output comparisons per configuration), plus valid-entry tags, targets, conditional histories and encoded return flags. It exercises type transitions at a repeatedly overwritten entry, allocation/collisions, same-address fetch/update, misaligned addresses, reset, invalidation, stack push/pop and return-target selection.

| Index bits | History bits | Stack depth | Conditional-entry checks | Unconditional-entry checks | Return-target observations |
|---:|---:|---:|---:|---:|---:|
| 4 | 1 | 0 | 66195 | 75660 | 0 |
| 4 | 1 | 1 | 66195 | 75660 | 2116 |
| 4 | 3 | 1 | 66195 | 75660 | 2116 |
| 4 | 4 | 2 | 66195 | 75660 | 2561 |
| 8 | 3 | 1 | 216852 | 230139 | 2123 |

Five compiled faults are rejected by prediction, history or return-encoding checks: incorrect flag source, skipping non-allocation refresh, wrong stored bit, applying return override to conditional entries, and corrupt conditional-history initialization. Exact source reconstruction confirms no other predictor changes.

## Remaining gates

Integrate with the unchanged timing-passing parent core and repeat source-bound whole-core/cache, short UART and independent ISA checks. Only a complete retained-ILA physical implementation can establish area or timing improvement. The ongoing parent long simulations and V1 implementation remain untouched.
