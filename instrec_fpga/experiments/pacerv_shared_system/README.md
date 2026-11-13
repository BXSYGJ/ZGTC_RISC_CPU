# PaceRV core in the shared audio system

## Integration

The five-stage H3 Base execution core replaces the small control core inside
`instrec_top`. The system keeps one DDR3 controller, one UART transmitter, one
audio front end, one NPU and one display pipeline. CPU code and its small stack
use local single-cycle boot ROM and RAM; application buffers use the system DDR.
The original H3 release and the original InstRec firmware remain frozen.

CPU features enabled by this integration are RV32IMC, the branch predictor,
overlapped instruction fetch and early data requests. The H3 release's cache
hierarchy is replaced by the existing system's local boot storage and a new
uncached shared-DDR data interface. Performance and timing are measured again
for this implementation.

## Address and ownership contract

| CPU byte address | Access | Destination |
| --- | --- | --- |
| `0x00000000..0x00001fff` | instruction/read | 8 KiB boot ROM |
| `0x20000000..0x20001fff` | read/write | 8 KiB CPU local RAM |
| `0x40000000..0x400fffff` | read/write | DDR physical `0x00600000..0x006fffff` |
| `0x41000000..0x415fffff` | read, valid subregions only | existing DDR physical `0..0x005fffff` |
| `0x80000000..` | MMIO, explicit registers | existing shared UART, NPU/status and LEDs |

The read-only observation alias permits software to inspect the PCM, weight,
feature and activation regions without overwriting accelerator-owned data.
Software reads a completed buffer after its producer commits it. Concurrent
producer updates can produce a changing view; the alias itself does not create
a snapshot. Gaps and writes to the observation alias return an access error.

CPU transfers are one aligned 32-byte DDR beat. Word selection and byte strobes
preserve the CPU's byte/halfword/word semantics. The Pango IP receives word
addresses (`byte_address >> 2`). A single locked M3 subarbiter serves boot
self-test, diagnostics, feature export and CPU accesses. Read ownership lasts
through both controller completion and consumption of every returned beat.
Post-boot arbitration rotates among active clients. The existing controller's
M3 quota continues to protect progress against M0/M1/M2 traffic.

## Evidence stages

1. Freeze original source hashes; run original firmware and DDR regressions.
2. Run the same firmware on PaceRV, followed by RV32IMC-specific and DDR tests.
3. Test production DDR control with masked writes, delayed read consumption,
   competing clients, rejected addresses and explicit error propagation.
4. Compile and map the complete PG2L100H audio top. Record resources and timing
   from the new source manifest.
5. Qualify the complete PG2L100H implementation using all ten timing summaries,
   frozen input hashes and the generated bitstream. Per the latest user
   instruction, remote-board testing is no longer an acceptance gate.

The remote board harness and the 100Pro+ audio top have separate build manifests.
Their results identify the actual device and tested peripherals.
The remote harness is retained as a separate experiment; current delivery
targets the 100Pro+ complete system and local PDS qualification.

## Original baseline

Git baseline: `852f067db4a4a710f5355e3ab311f035ced5b48d` (XSY).
`capture_baseline.py` reproduces the original input copies from Git and checks
their hashes. `BASELINE_MANIFEST.json` identifies the exact files.

Original native-Icarus CPU/firmware test: all C1-C10 checks passed. The fixed
integer workload reports `cycles=460012 inst=180008 acc=0xf2d8888b`.
The focused pre-integration Python regression passed 53 tests, and the existing
79 Verilog `.v` files passed the repository syntax-policy checker.

Commands and detailed results will be recorded in `VERIFICATION.txt` as each
stage completes. Large generated databases stay under `build/pacerv_shared_system`.

## Registered system paths

MMIO data is sampled alongside local memory and held by registered channel
occupancy. Activation commands capture their owner and address before the
downstream handshake. The registered text-selector and font pipeline aligns RGB and video control
to the same seven-clock latency.

The production activation-mux regression passed 24 mixed read/write transactions,
including immediate and delayed reads. Five full 1080p dashboard frames match
the original rasters exactly (10,368,000 pixels and 2,000 bar checks). The complete
native NPU still matches every golden layer and completes in 31,152,093 cycles.
The same-stream CPU loop remains at 180,016 cycles.

Reproduce the added checks with
`python sim/experiments/pacerv_integration/run_activation_mux.py` and
`python sim/experiments/pacerv_integration/run_dashboard_equivalence.py`.

## Current clock candidate

The selected build inputs use a real 109.375 MHz system clock and matching
875 Mbps DDR IP, generated-clock constraints, UART divisors and audio timing
constants. The pixel clock remains 148.5 MHz and I2S capture remains 48 kHz.
The complete physical build is still being qualified; `docs/STATUS.md` identifies
its current run and acceptance state.

Physical-rate audio simulation checks both 125 MHz and 109.375 MHz for two
complete windows. Each stable second window contains 132,096 real stereo frames
in exact order, with no injected frames, overflow or write timeout. Startup
has one injected frame at either clock. DDR completion in this test is a
512-cycle behavioural response. The full native NPU test independently
checks exact arithmetic and firmware control. See
`docs/AUDIO_FREQUENCY_IMPACT_20261114.md` for the latency comparison and evidence.
