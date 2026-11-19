# Combined bitstream: four-class physical input verification

Board bitstream SHA-256: `815a65940a95fe74c730a82263f09a73c17fc70d6bbf718b123753b00ab3a81b`.

Command: `python scripts/diagnose_live_pcm.py --classes 3,0,6,2 --label after_correct_stride`.

All four sources classify correctly and all eight integer logits match golden on the exact captured PCM, with zero playback underruns. Flute/clarinet/trumpet captured half 0; female singer captured half 1, using the correct 270336-byte physical slot stride. Every capture finishes unlocked. Input uses NICEHCK device 2, source digital gain 0 dB, endpoint volume/mute preserved.

Reversing each block of 16 samples again makes golden misclassify all four as class 7, completing the before/after causal comparison. The JSON field `golden_page_order_restored` retains its historical diagnostic name; on this already-fixed bitstream, that operation deliberately reintroduces the old defect.
