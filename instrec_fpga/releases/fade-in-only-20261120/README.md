# Immediate exit, 500 ms entry

Full build `20261120-095218-68abd3cb`, source `7f9a01ea` (functional change `4b185e07`). All six stages passed; source hashes remained unchanged. Firmware: 4556 bytes, RV32I.

Each inference immediately clears the old displayed probabilities and switches the class. New probabilities enter over 25 ticks of 20 ms. Raw records, latest-eight history and the existing two-page UI are preserved.

SHA-256: `de44df48c127cb2c2fb4b6705ce1356901a0d15361f83d9d8b4273f38d5cfabc`.

Final report: core setup -1.402 ns (834 endpoints); pixel setup -0.132 ns (1 endpoint); hold slow +0.017 ns, fast +0.007 ns. Timing is not closed. The intermediate after-hold-fix summary differs; the archived final `timing.rtr` is the release report.

Host animation/record tests: 2 passed. Actual CPU simulation passed, including immediate clear/class switch and the 500 ms endpoint. Evidence: `../../reports/ui_fade_in_only_20261120/`.

Programming and board validation status are recorded in `manifest.json`. Previous verified release: `../session-ui-20261119/`.

## Board retry result

Programming succeeded (done=1); medley_48k weights returned WOK CFE5A709. User confirmed immediate exit and 500 ms entry. Live inference remained unlocked.

The 90-second run produced 33 events, zero playback underruns, but only 6/16 nominal settled predictions were correct. A clarinet capture had PCM standard deviation 6.976 versus 3041.502 in the previous normal run. Hardware logits exactly matched integer golden on that captured PCM. Input level/connection requires investigation; classification acceptance has not passed. Endpoint volume was not changed.
