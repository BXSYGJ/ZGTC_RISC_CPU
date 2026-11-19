# 2026-11-19 UI bitstream board regression

- Branch/source at test start: `wrapup-working`, `ee17951e`, clean checkout.
- Bitstream: `build/instrec-latest.sbit`, 3791112 bytes, SHA-256 `C1269438352120FA11B83AA280E9224FD8EB8A04FB458E4476C997B1715040F1`.
- Build: `20261119-145948-caf76016`, setup WNS -0.861 ns, hold WHS +0.056 ns. Timing is not closed.
- FTDI was initially absent; user reconnected it. Flash succeeded on attempt 1: `The done bit is 1`, `COMMAND[Program] execute successfully, takes 3.6 secs.`
- Weight upload: COM5, `scripts/outputs/medley_48k/weights_image.bin`, 691040 bytes, SHA-256 `3d5d9bbccc806ecf4eabe072c255630aa70cd034ee82e0484307c6233b2ddab8`, 2700 frames, `WOK CFE5A709`.
- Sequential invocation for each sample: `python scripts/inject_audio.py --port COM5 --wav D:/0000/111/001/Pango/InstRec/data/demo/sample_N_NAME.wav --golden --keep-lock`.
- Each upload: 264192 bytes, 1032 frames, zero retransmissions. All eight board logit vectors match golden exactly.
- Argmax sequence: `0,1,2,0,4,5,6,7`. Label accuracy 7/8; flute is also class 0 in golden.
- `board_top1` in results.json is host argmax of UART logits. It is not a direct read of the softmax top1 register or HDMI display. Screen switching and KEY2 clear await user observation.
- Flash safety regression: `python -m pytest -q tests/test_board_flash_safety.py`, 16 passed.
- No audio volume changes. Final audio-writer lock retained for screen review. No active PDS build/configuration process; reusable JTAG server retained without termination.

The sample text files retain script output except per-frame progress lines. This README records flash/upload tool observations; raw flash output was not separately captured.

## Follow-up observation and hardware top1

User confirmed normal display and successful KEY2 history clearing, but initially reported no visible switching. A follow-up replay injected clarinet then piano without resetting the board. Both uploads had zero retransmissions; CPU UART telemetry reported actual hardware `NPU top1=0` then `NPU top1=4`, matching the returned logits. Raw telemetry is retained in `top1_recheck.json`. This establishes hardware top1 changes across runs; HDMI switching still awaits user feedback from the replay. The final retained window is now piano, with audio writer locked.
