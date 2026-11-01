# Corrected WDMA parameter RAM equivalence (2026-11-01)

Persistent experiment assets are in `sim/experiments/wdma_parameter_ram/`.
The runner freshly passed six layers for 350,000 cycles each while comparing
read commands, weight and parameter handshakes/data, group-start, busy and
done under randomized DDR response gaps and ready stalls:

```text
layer 0: commands=195, weights=1672, contracts=9216, groups=192
layer 1: commands=2691, weights=82290, contracts=9216, groups=192
layer 2: commands=5094, weights=161493, contracts=9072, groups=189
layer 3: commands=5147, weights=163283, contracts=4608, groups=96
layer 4: commands=67, weights=2034, contracts=3072, groups=8
layer 5: commands=5, weights=128, contracts=24, groups=1
RESULT: PASS (6 layers bounded cycle equivalence; not functional correctness)
```

Raw log: `build/sim/wdma_parameter_ram_experiment/run.log`.
The persistent runner and RTL snapshots have no dependency on ignored build
sources or copied image data. The test uses an address-derived synthetic DDR
pattern and randomized command/ready timing.

An earlier WDMA wide-RAM test showed equivalence against the unmodified
original, whose parameter loader and channel index were themselves defective.
That evidence did not establish corrected parameter addressing. The current
test compares corrected scalar WDMA (including repaired per-beat parameter
indexing and stream handshake) against a corrected wide candidate. Wide write
indices are bias/M `cfg_idx[7:3]` (M bank offset 32) and shift `cfg_idx[7:5]`;
read indices use `pa[8:3]` for bias/M and `pa[7:5]` for shift, with lane and
table select captured on the same edge to retain the one-cycle contract read.

The wide candidate source SHA-256 is
`160B0D7F0C0A86E046469964F329F93007DE04E9D7CAA8F90660A6E7F949A732`.
This equivalence test makes no resource-saving claim. The candidate has not
been synthesized, so RAM inference, FF/LUT reduction, timing and routing are
unverified. Full conv1 golden validation is separate.
