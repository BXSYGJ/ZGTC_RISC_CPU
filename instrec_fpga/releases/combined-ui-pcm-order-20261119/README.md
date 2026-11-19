# Combined live PCM order and UI candidate, 2026-11-19

**Build verified; not yet programmed on the board.** FTDI/JTAG is offline, while COM5 remains available. The old bitstream is still running. Do not interpret prior board tests as acceptance of this new file.

- Build: `20261119-203050-b39cb1ee`, source commit `0ed10615`, all six stages OK, source hashes unchanged, zero unrouted nets.
- SHA-256: `815a65940a95fe74c730a82263f09a73c17fc70d6bbf718b123753b00ab3a81b`.
- Timing: core setup -1.062 ns (446 failing endpoints); pixel setup +0.038 ns; hold +0.074 ns slow / +0.046 ns fast. **Timing is not closed.** Full report: `timing.rtr`.
- Post-route resources: 34453 LUT, 40326 FF, 90 APM, 130/155 DRM.

Included changes:

1. Live PCM page order fixed on both channels: oldest sample in little-endian DDR lane 0. The previous RTL reversed every 16 samples and corrupted the spectrum.
2. CPU firmware interpolates confidence over 500 ms, 25 updates at 20 ms intervals. CPU owns the arithmetic; HDMI consumes complete snapshots.
3. Latest eight inference distributions shown as stacked relative columns, oldest left and newest right, with an eight-class color legend. Animation updates do not create history records.
4. KEY2 clears history with 20 ms debounce.

Validation already completed: 471 Python tests passed / 26 skipped; 80 RTL files with zero lexical violations; actual firmware, history eviction/clear, full 1080p raster, audio page chronology and audio-chain simulations passed. The page-order test fails against the former RTL and passes with this file's source. Old-board captures of flute/clarinet/trumpet/female singer classify correctly in golden after restoring only the 16-sample page order; raw capture logits match the old board exactly. Evidence: `../../reports/live_audio_20261119/`.

After physically reconnecting JTAG, run from `instrec_fpga/`:

```powershell
python scripts/flash_bitstream.py --sbit releases/combined-ui-pcm-order-20261119/instrec_top.sbit
python scripts/weight_upload.py --port COM5 --image scripts/outputs/medley_48k/weights_image.bin
python scripts/diagnose_live_pcm.py --classes 3,0,6,2 --label after
```

Then verify a low-level 2000 Hz tone, the complete `demo_90s_8class.wav` real-time run, confidence transitions, eight-result eviction and KEY2 on the HDMI screen. Keep NICEHCK endpoint volume/mute unchanged. Every diagnostic capture must release `U` in `finally`; leave live input unlocked after testing. The flash helper now resolves explicit relative paths before handing them to cdt_cfg.
