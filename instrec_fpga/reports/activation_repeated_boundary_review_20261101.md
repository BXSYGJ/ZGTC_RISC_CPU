# Activation and repeated-inference boundary review

Scope: production RTL corresponding to frozen snapshot `20261101-215059`.
No production interface or fault behavior changes are included in this review.

## Existing evidence

- Two complete native-controller inferences without reset pass every conv,
  pool, GAP, FC and softmax comparison. Both use the same feature frame.
- The abstract two-client activation mux directed test covers contention,
  command stalls, write ownership, immediate and delayed read responses.
- Dynamic row-store tests cover all three real geometries and output stalls;
  their DDR model returns delayed read data.

## Concrete remaining boundaries

1. Different frames without reset: same-frame repetition could hide retained
   values. `run_snapshot_native.py --production --ab-inputs` adds frame B as
   `255-A`, recomputes independent golden arrays, reloads them only before the
   second start, and preserves DUT and native DDR state. It writes a separate
   `npu_production_native_ab` run and hashed `ab_golden_manifest.json`.
   This A/B run passed: 16512 changed feature bytes, both frames complete in
   31141202 cycles, all conv/pool/GAP/FC/softmax values exact and all output
   counts complete. The FC accumulators differ between A and B, confirming
   changed data propagated through the network. Log:
   `build/sim/npu_production_native_ab_20261101-215059/run.log`.
   This closes the same-value repetition gap for this specific pair of frames,
   not arbitrary fault/reset sequencing.
2. Internal error visibility: `npu_top` observes `s0_error`, `s1_error` and
   `mux_error` only as internal wires. The native TB makes these fatal, but
   the production timeout/fault status does not aggregate these wires.
   Unexpected activation R traffic therefore lacks immediate software-visible
   error status. This review does not change that interface contract.
3. Recovery: bridge abort enters sticky `FAULT`; row stores have reset but no
   abort input. Reset recovery must be tested, and restart after an error
   without reset must not be claimed. No automatic retry is implemented.
4. Start sequencing: a row store samples start only in IDLE. Busy-time start,
   held start, and reset during outstanding abstract read/write transactions
   need directed tests if those cases become supported integration behavior.
5. Zero-latency R reaches the row-store implementation, but the full-geometry
   row-store TB uses delayed responses. Direct immediate-R and duplicate or
   unexpected-R tests remain distinct from mux immediate-R coverage.
6. Actual top arbitration with concurrent loader/audio/Mel/self-test traffic,
   physical DDR PHY, CDC, routing/timing and board operation remain outside
   these native compute tests.

## Resource gate

The frozen production candidate synthesized, but the mapping summary is over
capacity: LUT 115473/66600 (173.38%), registers 133439/133200 (100.18%),
DRM 88.5/155, APM 92/240. Evidence is
`build/resource_gate/native-20261101-215404-522126/synthesize/run.log`, Mapping
Summary. This is not a routable result or a bitstream. Isolated narrow row-store
mapping probes are managed separately and do not establish full-design fit.
