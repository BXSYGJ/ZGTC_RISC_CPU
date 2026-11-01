# Pure core preparation: source boundary and external service

Read-only assessment, 2026-11-01. No bare-core implementation or physical build is created by this assessment. The local ILA waveform handoff is complete: `README.md`, `WAVEFORM_ANALYSIS.json`, and `RENDERER_VERIFICATION.json` in this directory describe the nine actual local RTL windows.

The appropriate pure RTL DUT is the selected release's `rv32_core`, with all existing ports exposed. It already contains the RVC frontend and expander, predictor/return stack, decoder, register file and pipeline, machine CSRs and 64-bit cycle/retired counters, interrupts/exceptions, and the complete enabled multiply/divide unit. Adding another frontend around it would duplicate functionality. Caches, backing RAM, arbiters, uncached bridges, MMIO, UART, GPIO, timer generation, PLL and ILA remain outside this DUT.

## Exact source closure and parameters

For each release, obtain its own source RTL directory from that release's `waveforms/WAVEFORM_MANIFEST.json` `source_inputs` entry named `rv32_core.sv`. These are the exact hashed snapshots used for the accepted local recordings; do not mix files between releases. The transitive RTL closure contains exactly these eight source files:

```
rv32_core.sv
rv32_rvc_frontend.sv
rv32_rvc_expand.sv
rv32_decode.sv
rv32_alu.sv
rv32_muldiv.sv
rv32_btb.sv
rv32_machine.sv
```

The seven child modules instantiate no additional `rv32_*` modules. Preserve each file byte-for-byte. A wrapper may pass every existing input/output through and set parameters, without changing execution logic.

| Parameter | Original_155250 | H3_Base_145125 | H3_Retained_145125 |
| --- | ---: | ---: | ---: |
| RESET_VECTOR | 0 | 0 | 0 |
| ENABLE_M / ENABLE_C / ENABLE_PREDICTOR | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| FETCH_ADDRESS_BITS / BTB_ADDRESS_BITS | 16 / 16 | 16 / 16 | 16 / 16 |
| BTB_INDEX_BITS | 8 | 8 | 8 |
| EARLY_D_REQUEST / FETCH_OVERLAP / LOAD_USE_BUBBLE | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| RETAIN_MUL_ELIGIBILITY | parameter absent | parameter absent | 1 (existing default) |
| Initial physical target | 155.25 MHz | 145.125 MHz | 145.125 MHz |

The 16-bit instruction/tag address parameters reproduce the parent SoC's `MEMORY_ADDRESS_BITS=14` word memory plus two byte bits. Data request addresses remain 32 bits and permit external MMIO. Changing either address parameter to 32 is a distinct configuration requiring fresh area/timing and range behavior checks; it does not preserve the existing area boundary.

Original exports 616 port bits including clock and reset; both H3 versions export 648 because they add `i_req_pair_address[31:0]`. Preserve all outputs: requests and response-ready, maintenance, complete retirement trace, trap PC/cause/value, five pipeline-valid bits, and both full 64-bit counters. Preserve all input error, ready/valid, pair, timer64 and interrupt bits. A constant timer or interrupt connection in the synthesized wrapper would specialize away part of the machine CSR/interrupt implementation.

## Existing experiments have two different meanings

`D:/AAAFPGA/ZGTC_RISC_CPU/cpu/experiments/peripheral_partition` is explicitly a **NoMmioPeripherals** system. `rv32_bare_sim.sv` instantiates `rv32_soc` with `ENABLE_CACHE(1)`, I-cache set bits 9, D-cache set bits 6 and backing RAM. `run_bare_pds.ps1` passes `-CacheEnabled 1`. Its PDS shell observes only low retired-counter bits on LEDs. The 7756-LUT, 144-MHz route and 157.5-MHz runtime are separate artifacts, as the existing documentation already records. Neither qualifies any of the three newly isolated cacheless cores.

The useful parts of `qualify_bare_pair.py` are its joins: identical firmware, exact RTL hashes, identical frequency, raw native resource/timing reports, complete CRC output and duration before computing `iterations * clock_hz / cycles`, `iterations * 1e6 / cycles`, and division by the actual area denominator. A new service-contract identity must be added to these joins. Do not transplant its cached runtime or claimed score.

The existing paper's `research/micpro-submission-20261003/manuscript/generated/bare_core_tables.tex` describes a different historical, genuinely cache-excluding timing fixture. H3 baseline/tightened rows report 150/165 MHz, 4771/4838 LUT and 1500 FF; R153 baseline/tightened rows report 160/170 MHz, 4405/4351 LUT and 1522/1511 FF. It retains four APMs, zero DRM, one GPLL and 0.150-ns uncertainty. These historical values are source-specific context. They are not fresh measurements of Original155.25 or the retained-eligibility token core, and the table contains no isolated-core CoreMark measurement.

## External memory service contract

All request/response acceptance occurs on the rising edge when valid and ready are both one. Use ordered responses, one outstanding I request and one outstanding D request, and permit a new request on the same edge that consumes the prior response when the core offers it. Never generate an unsolicited response. A zero-cycle response to a newly accepted request is inappropriate: the core records the pending/sent flag at that acceptance edge and consumes the response later.

| Interface | Required behavior outside the DUT |
| --- | --- |
| I demand | Capture the full aligned `i_req_address` on acceptance. Return the demanded little-endian 32-bit word and matching error. Hold valid/data/error until `i_rsp_ready`. The frontend can discard a wrong-path result after redirect; it still expects the outstanding response to drain. |
| I C metadata | `i_rsp_is_c[0] = data[1:0] != 2'b11`; `i_rsp_is_c[1] = data[17:16] != 2'b11`. Apply the same rule to pair data. Metadata must describe the actual returned halfwords, not ELF instruction boundaries. Illegal compressed encodings remain the expander's responsibility. |
| I companion | Capture H3 `i_req_pair_address` on the same edge as demand, and return that word only when valid and in range. Original's legacy companion is `{request_address[31:3],1'b1,2'b0}` and is useful for the lower word of an 8-byte pair. Do not impose this formula on H3, whose companion is the following 32-bit word. Set pair-valid to zero when a separate fault would be needed: the interface has no separate pair-error input. Preserve full-width carry/range checks near the end of memory. |
| D demand | Capture aligned address, write flag, shifted write data and four byte strobes. For a write, apply exactly the enabled byte lanes once. Return a completion response for stores as well as loads. Hold response until `d_rsp_ready`; error must represent a real unsupported/faulting access. Apply unsigned/signed load extension in the core, not in the memory model. |
| Concurrency/order | Allow independent I and D service; define simultaneous same-address fetch/write semantics. A deterministic read-before-write service with ordered D stores and a fence.i barrier is practical. Returning stale prefetched instruction buffers before fence.i is expected; do not repair core state externally. |
| fence.i | Assert `maintenance_ready` only after earlier accepted stores are visible and pending reads are drained or have a specified coherent snapshot. With cacheless external RAM this may be a one-edge barrier after the drain. Keep the existing core frontend/predictor invalidation behavior intact. |
| Timer/IRQ | Timer64 and external/software/timer interrupt inputs belong to the environment. Benchmark runs can drive inactive IRQs; separate functional tests must exercise the preserved logic. |

The request-valid ports need not act as cancel-safe speculative queues. The current frontend can change a request selection during redirect, and the service must sample fields only when accepted. Retain normal valid/data stability assertions on responses. Track request counts and acknowledgements to catch repeated stores or dropped wrong-path reads.

## Recommended measurement sequence

1. **Identical existing services outside the DUT.** Build a simulation-only environment using each release's existing `rv32_memory_system`, RAM/native timing models and `rv32_peripherals`, connected to the new bare DUT exactly as `rv32_soc` connects them. Preserve H3's snapshot early-read hook (`snapshot_pre_read = d_req_valid && d_req_ready && !d_req_write`, word index `d_req_address[4:2] ^ 3'd4`), performance-config bits and counters, maintenance-fault gate, accelerated UART configuration, firmware and reset timing. The environment is omitted from the core synthesis file list. Compare the complete per-edge retirement tuple, trap tuple, all requests/handshakes, cycle and retired counters against the selected unmodified full SoC. This should prove extraction preserves behavior, including the actual historical memory service; it does not prove a standalone memory-independent score.

2. **Fresh standalone external-RAM experiment.** Feasible implementation: two independent one-entry registered I/D response queues, minimum one full edge from request acceptance to response consumption, a unified 64-KiB byte-addressed RAM initialized from the same image, real byte stores, correct C predecode and pair address, explicit coherent maintenance barrier. Keep identical latency/throughput/pair-availability/error and deterministic backpressure rules across all three cores. Begin with single-word I delivery (`pair_valid=0`) and then a separately named pair-enabled profile. Run CRC and trace checks before full performance measurement. This service avoids caches but is an ideal external-memory assumption, not a board-memory timing claim.

3. **Firmware for the direct service.** The existing V0 program requires its real UART/status/performance MMIO path. To retain exactly that ELF, keep the existing peripheral module or a cycle-faithful external bus service outside the DUT; acknowledge stores and return genuine status/snapshot values. Do not report fabricated cache counters or use a permanently-ready UART. A standalone cacheless benchmark is cleaner with a fresh no-MMIO port that starts automatically, reads `mcycle/minstret` through high/low/high coherent reads, writes CRC/text/counts into ordinary external RAM after timing, executes the required maintenance barrier and publishes a final RAM status. Its newly compiled ELF/hash/layout is a distinct measurement; compare all three with the same port/toolchain/seeds.

For each profile report fresh cycles, retired instructions, CRCs, configured clock and observed duration, I/D requests and response waits, pair successes, and the exact service JSON/hash. CoreMark/MHz depends on this service. A core-only area denominator paired with cached services should be labeled **core area with explicitly external cached-system services**; it is not the whole-system CoreMark/LUT. The standalone one-cycle profile is a conditional pure-core efficiency result. Frequency must come from the same core source/parameters and a declared physical boundary.

## PDS preservation and timing boundary

The installed `D:/PDS_2022.2-SP6.4/doc/User_Constraint_Editor_User_Guide.pdf`, section 2.3.5, printed pages 100–101, documents a real virtual-IO attribute. Example lines for an area-only direct top are:

```tcl
create_clock -name {core_clk} [get_ports {clk}] -period {6.441224}
define_attribute {p:i_req_valid} {PAP_IS_VIRTUAL_IO} {TRUE}
define_attribute {p:i_req_address[0]} {PAP_IS_VIRTUAL_IO} {TRUE}
define_attribute {p:i_rsp_data[0]} {PAP_IS_VIRTUAL_IO} {TRUE}
define_attribute {p:cycle_count[63]} {PAP_IS_VIRTUAL_IO} {TRUE}
```

Enumerate **every** nonclock port bit in the generated FDC, not just these examples, and keep the actual clock pin and clock constraint physical. Remove LOC, VCCIO, IOSTANDARD and other IO attributes from virtual ports. The guide states virtual IO does not participate in placement/routing and supports simple PNR only. Crucially, its next-page continuation explicitly excludes MPNR, timing analysis/reports and bitstream generation. Use virtual IO for CLM/resource assessment only; do not treat its timing as frequency acceptance. `PAP_IO_NONE` in an old Vex `bare.fdc` coexists with physical LOC attributes and is not the documented virtual-IO setting.

For a frequency-qualified routed fixture, a low-pin scan wrapper provides concrete controllability/observability: hold a complete input shadow/shift register, atomically update all core input registers; capture every core output into a shift register, and shift every bit out. Clock the core from the requested physical target; retain all error/IRQ/timer input bits as scan-controlled variables. No memory or peripheral belongs inside the DUT. Keep wrapper and core hierarchy distinguishable and request a detailed dev_map resource report. Report core hierarchy LUT/FF/APM/DRM, wrapper resources and total separately; boundary registers/scan muxes are actual area overhead. Constrain internal paths and explicit boundary register paths; do not exempt real execution paths to obtain a passing frequency. A literal full-port top would need 616/648 IO bits and is not practical for the package.

The installed ADS guide section 5.9, printed page 77, distinguishes `syn_hier="fixed"` (preserve hierarchy and prohibit cross-boundary optimization) from `syn_hier="hard"` (preserve hierarchy but permit constant propagation). Exact FDC form is `define_attribute {v:rv32_core} syn_hier {fixed}`. Apply the same boundary policy to all three cores. PDS's implementation settings document `dev_map -detail` for per-module resource reporting. The existing PG2L200H native map report confirms 400 available physical IO, below the 616/648 full interface bits.

A detailed synthesis/dev_map hierarchy table alone is not a post-route count. Export or query the final routed primitive instances, assign each to the preserved core/fixture/clock hierarchy by provenance, and sum the exact native resource classes. Include tool-created duplicate cells assigned to the core cone. Reconcile their sum with the final total resource report; list shared or unattributed cells separately instead of subtracting an estimated fixture cost. Compare pre-map and post-route register/counter/predictor/muldiv presence. If PDS flattens or moves cells across a boundary despite the intended hierarchy setting, report total fixture resources and the actual supported attribution stage until a defensible final partition is available.

An output XOR/signature is a weaker preservation boundary than captured scan bits: dependencies can algebraically cancel, equivalent outputs can merge, and it does not provide independent visibility of every bit. A shift/capture chain exposes each output bit separately and a scan-controlled input shadow exposes all core inputs without constant specialization. A core clock enable or stepping fixture must preserve a real generated clock/clocking primitive and its timing relationships; a raw combinational clock gate would introduce a different clock network. Treat scan controls as fixture controls, not benchmark execution stalls.

The installed `ADS_Synthesis_User_Guide.pdf`, section 5.14, printed page 90, warns that `syn_noprune` only preserves an instance through synthesis: an unconnected instance can still disappear during dev_map. `syn_keep`/`syn_preserve` attributes are supplementary, not an observability substitute. Validate the mapped/routed netlist: all intended ports remain represented, the register file and stage state are present, BTB/RAS and RVC cones exist, both counter bits 63 remain connected, all CSR/interrupt error paths survive, and the complete multiply/divide cone remains. Explicitly verify no cache, main RAM, UART/peripheral/PLL/ILA hierarchy entered the core resource denominator. Inferred RAM used by the register file or predictor belongs to the core and must be counted if the tool chooses that mapping; do not demand zero DRM by suppressing legitimate implementation.

A passing extraction test with unchanged external services establishes functional identity. A new direct-memory run establishes service-specific execution efficiency. A real untrimmed PDS route establishes frequency and core resource use. These are three complementary measurements with separate, hash-bound receipts.
