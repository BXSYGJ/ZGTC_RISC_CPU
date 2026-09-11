# Factored write/read collision forwarding

rv32_cache.sv changes only the synchronous writable forwarding predicates relative to the direct-array LRU candidate. Source identity and hardware parameters are in configuration.json.

Run scripts/test_cache_collision_forward.py. This keeps the original LRU/reset/reference checks and adds cycle-level collision/registered-flag equivalence,32 synchronous forwarding/writeback coverage configurations and ten compiled collision/data mutations.

The135 MHz seed1 physical implementation fails timing. Do not promote this candidate or combine its resource count with old CoreMark counters. See docs/CACHE_COLLISION_FORWARD.md and local source-bound audit files.
