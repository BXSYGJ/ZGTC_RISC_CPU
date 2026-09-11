# LRU storage experiment

Isolated alternatives to the DB55CBF5 synchronous-writable cache. Production RTL is not replaced.

- rv32_cache.sv: first reset-free array with expanded observation aliases; rejected by strict mixed-reset lint and 135 MHz timing.
- rv32_cache_async_guard.sv: consistent asynchronous guard, expanded aliases; strict lint passes but native LRU still uses 576 flip-flops.
- rv32_cache_direct_array.sv: direct indexed array, no RTL observation aliases; native LRU maps into 576 bits of single-port LUT RAM. Seeds1/7/5 all miss135 MHz timing.
- rv32_cache_readonly_ram.sv: I-cache-only RAM attempt; rejected procedural reset loop by PDS and large-geometry Verilator.
- rv32_cache_readonly_generated.sv: compatible generated D-cache reset flops plus I-cache RAM; complete functional tests pass, seed1 misses135 MHz timing. The earlier rejected sized-cast source is retained in its frozen PDS build.
- configuration.json, async_guard.json, direct_array.json: immutable candidate input identities and hardware parameters.

Run scripts/test_cache_lru_storage.py with --candidate direct_array or --candidate async_guard. The default is direct_array. See docs/CACHE_LRU_STORAGE.md for source hashes, failed attempts, regression coverage and source-bound measurements. Do not combine baseline long-run counters with candidate resources or claim hardware validation from local simulation.
