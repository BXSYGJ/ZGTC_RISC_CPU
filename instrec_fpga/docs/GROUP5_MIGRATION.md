# Five-group activity target correction (2026-11-02)

> RESUMED FOR ASSESSMENT (2026-11-02): the user now requests the five-group
> dominant result as the main output, alongside all five independent activity
> scores. Preserve the accepted eight-class board baseline. See
> GROUP5_REUSE_AND_CPU_ASSESSMENT_20261102.md and STATUS.md for the current plan.

The user identified simultaneous instrument-group activity as the originally
intended feature, previously deferred migration, and has now resumed it with dominance as the primary result.
If this migration is resumed, do not claim eight-class softmax probabilities
implement independent group activity.

## Frozen source of truth

- Training project: sibling `InstRec`, checkpoint `runs/group5_v3/best_model.pth`,
  epoch 22, `DualHeadInstrumentCNN`. SHA-256:
  `5ada8db602427af8b5c7ba01aa581f5852ebf2b884d94932c821fe44cf22b636`.
- Web backend also selects this checkpoint, not the IRMAS deployment assets.
- Hardware output order must preserve trained order:
  **strings, woodwinds, brass, percussion, keys**.
  UI labels: 弦乐、木管、铜管、打击乐、键盘/拨弦.
- Activity: five independent sigmoid outputs. Multiple groups can be active;
  values need not sum to one. They are model activity scores, not measured
  acoustic energy percentages.
- Separate dominance head: five logits, softmax, masked by predicted activity
  > 0.5 then renormalized; all zero when no group is active. Never substitute
  dominance for activity.
- Input is mono 44100 Hz, 66150-sample segment, normalized 64 x 130 Mel features.
  Training config's approximate duration is not the authoritative sample count;
  cache metadata and serving frontend explicitly specify 66150 samples.
- Frozen float state, complete model source, config, held-out features and both
  heads' outputs: `models/group5_v3_float_20261102/`. Manifest records hashes.
  `scripts/freeze_group5_reference.py` reproduces the read-only extraction.
  This is a float reference, **not quantized or deployed**.

## Required implementation and acceptance

1. Calibrate the correct checkpoint using training split features, fold BN,
   export per-layer integer contract and weight image with provenance. Evaluate
   INT8 vs float on held-out data; do not use the old model's zero points/scales.
2. Change feature window and normalization from 64 x 258 to 64 x 130. Verify
   reflect padding, raw-frame maximum before truncation, statistics, replay and
   page buffers against a new fixed-point golden reference.
3. CNN spatial widths become 130 -> 65 -> 32 -> 16 -> 8 after pooling;
   GAP consumes 4 x 8 per channel (32 rather than 64 values). Update replay,
   dimensions, counts, DDR layout and FC2 five-output scheduling coherently.
4. Implement independent activity sigmoid with its own integer contract.
   Preserve the optional separate dominance head assets; dominance is the primary displayed result, with activity retained alongside. Update CPU/MMIO/UART and five UI bars to carry group identity
   and activity without top1/normalization assumptions.
5. Verify full CPU + Mel + native NPU against new golden, including multi-active
   and no-active cases, different consecutive windows and reset/ACK behavior.
   Old 8-class PASS reports remain historical hardware evidence only.
6. Fix full-system timing violations before claiming stable delivery. Reuse RV,
   DDR and board-verified HDMI transport. One PDS at a time; board boot PASS is
   not inference PASS. External audio remains unconnected per user.

## Historical board note (superseded by STATUS.md)

Full diagnostic bitstream `489EF753...26F2E5EF` programs successfully and boots
RV32/MMIO/ISA plus DDR SELFTEST/DDROK, but has negative setup/recovery margins
and the legacy model geometry; weights were not uploaded. No five-group FPGA
inference has passed. Verified fixed-data display fallback remains on
`codex/display-demo`, SHA-256 `602AB321...E60A17C`.
