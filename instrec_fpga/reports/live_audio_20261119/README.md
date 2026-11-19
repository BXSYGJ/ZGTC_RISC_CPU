# Live audio chronology defect and combined UI fix, 2026-11-19

## Reproduction on the board

The user's source is `D:/0000/111/001/Pango/InstRec/data/demo/demo_90s_8class.wav`, with its adjacent timeline. This is different from the eight `sample_N` files tested earlier. The timeline uses selected training clips and reports successful FP32/INT8 checks on interior windows.

One interior 132096-sample window per segment was checked with the actual medley_48k integer golden contract and weight image. All eight classified correctly, including flute. See `clean_golden.json`. This is an eight-window check, not a reproduction of every 50 ms sliding window in the author's validation.

Playback explicitly selected waveOut device 2, `NICEHCK HiFi Audio`. A 2000 Hz tone with digital amplitude 0.08 was played without changing endpoint volume or mute. After settling, the completed PCM half was locked and 8192 samples were read with CRC checks. The board was unlocked in a `finally` block. Playback underruns: zero.

- Raw capture: peak 1001.95 Hz; strong components near 4001.95 and 7001.95 Hz.
- Reversing each group of 16 samples offline: peak 1998.05 Hz, with normal neighboring FFT leakage bins.
- Error over the expected 24-sample period: std 3574.04 LSB before reversal; 2.24 LSB after reversal.
- Sample raw PCM, metadata and device information: `tone_2khz.raw`, `tone_2khz.json`.

## Root cause

`audio_sink.v` formerly appended each incoming sample at the least significant end of its 256-bit page shift register. After 16 samples, lane 0 held the newest sample, lane 15 the oldest. DDR readback, serial PCM injection and the mel reader use chronological little-endian 16-bit lanes. Thus live audio alone was reversed inside every 16-sample block. This changes spectral content; it is not a simple sample-rate error and must not be treated with a global 2x pitch correction.

The new RTL inserts each new sample at the most significant end, placing the oldest at lane 0 when the page fills. Both left and archived right channels are corrected. The dedicated ramp test fails against the former RTL with `cmd=0 lane=0 got=15`, then passes with the fix over four stereo pages. Original failing log retained in `audio_page_order_before.txt`; post-fix evidence will be added after verification.

Earlier STATUS notes assigning a similar half-frequency symptom to wiring or the PCM1808 module did not test this page-order defect. They must not be used to rule out the live audio RTL path.

Four actual music captures on the old board bitstream close the causal chain:

| Source class | Board top1 | Golden on raw capture | Golden after restoring page order |
|---|---:|---:|---:|
| Flute (3) | 7 | 7, logits identical to board | 3 |
| Clarinet (0) | 7 | 7, logits identical to board | 0 |
| Trumpet (6) | 7 | 7, logits identical to board | 6 |
| Female singer (2) | 7 | 7, logits identical to board | 2 |

Only the order of the same captured samples was changed in the last column; no gain, model, feature contract or weight changes were applied. See `before_class_captures.json` and the four `before_classN.raw` files. Every playback used NICEHCK device 2, gain 0 dB, zero underruns, and every capture ended unlocked. The reusable `scripts/diagnose_live_pcm.py` reproduces the controlled comparison and writes a unique report directory.

## Combined UI behavior

- Firmware reads an atomic complete eight-lane NPU percentage snapshot using a sequence counter.
- CPU performs 25 interpolation steps at 20 ms intervals, reaching the new confidence target in 500 ms at 125 MHz. Retargeting starts at the current displayed value. This implements the user's clarified 0.5 second time interval, not the earlier ambiguous EMA coefficient 0.5.
- CPU normalizes each raw inference vector to 100 percent using cumulative rounding and publishes cumulative boundaries once per inference.
- Display history retains the latest eight results, oldest left and newest right. Every column is one stacked eight-class confidence distribution, using a fixed class legend. Animation ticks do not create history entries.
- KEY2 clears history. Its former debounce arithmetic was also corrected to an actual 20 ms interval.
- Shared streaming playback preserves endpoint volume/mute instead of forcing full waveOut volume.

## Build and verification state

The UI-only build `20261119-201437-1effbbdb` was deliberately interrupted during synthesis to include the newly discovered audio fix. **No bitstream was produced by that run.** Its files remain under `build/pds/`; the existing board bitstream was not replaced.

Before the audio fix, final UI verification passed `rv_cpu`, `history_tracker`, `dashboard_ui`; Python regression was 470 passed / 26 skipped. The CPU simulation runs the actual firmware for the entire 500 ms animation, checks 25 publication ticks and one independent history vector. A full 1080p raster checks proportional stacking, legend colors and video alignment. Post-audio-fix verification and combined build/board results are recorded as they complete.

Post-fix verification: `audio_page_order` PASS, `audio_chain` PASS, Python 471 passed / 26 skipped, 80 RTL files with zero lexical violations. Combined full build `20261119-203050-b39cb1ee` started from commit `0ed10615`; board verification remains pending. PNG previews in this directory are actual RTL simulation rasters, not board photographs.
