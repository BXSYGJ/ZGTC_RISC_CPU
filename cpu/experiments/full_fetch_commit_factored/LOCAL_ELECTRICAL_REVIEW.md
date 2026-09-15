# Local asynchronous-I/O review: 153 MHz fetch factoring

September 11, 2026. This is a bounded synthesized-input review, not electrical signoff or permission to program a board.

## Current evidence

All three complete-ILA native images pass timing at 153 MHz, 9502 total LUT, 5079 FF and +0.021 ns setup slack. Each retains 42 data channels, 33 trigger channels and 1024-sample depth. Benchmark and scope images share all twenty physical source files and the complete CPU configuration; their firmware roles are checked explicitly.

audit_fetch_async.py --include-application binds each native input netlist to the completed PDS invocation, current CPU source and corresponding firmware. The unchanged reference structural checker is pinned by SHA256 E3D786523AE68796A45B7E503DB7DED314B067C18FBB66C6C2F89EAFB1D78513. Six regression methods exercise the current performance netlist, rejecting bypassed stages, extra first-stage logic/assign fanout, wrong clock and missing UART module.

| Full-ILA image | Synthesized input netlist SHA256 |
| --- | --- |
| fetch-commit-seed1-native-wb | 7226207B2EDA5DF39E9AC0E7840415FEE28E1CE81C01B9AA79D3F275BDAB9C89 |
| fetch-commit-v1-seed1 | 7C4CEF5FD7FEB9335F8B93F2969D1050633C475F0AE039EEC475AE341A51D6E7 |
| fetch-commit-scope-seed1 | 4D99213889215D77479EF8217B54DCA38A7CEAC28F39D66D2FA65550C64EF756 |

All three pass checks of UART rx_meta -> rx_sync, GPIO gpio_meta[0] -> gpio_sync[0], GPIO gpio_meta[1] -> gpio_sync[1], and reset_pipe[0] -> reset_pipe[1]. The expected primitive type, clock, reset/preset, direct data connection and absence of additional first-stage named-port/assign fanout are verified. Receipt: build/async-structure-all-images.json.

## Limits and open gates

This check examines the synthesized input to ILA implementation, not post-route synchronizer placement, whole-design CDC, metastability MTBF or complete reset recovery/removal safety. The broader raw-input consumer/hierarchy audit from the older 151.2 MHz version is not silently inherited by this candidate.

The actual PDS results still report unset SCBV. Board revision, configuration mode, VCCIOCFG, VCCIOL4/VCCIOL5 and the physical SCBV connection must be established from the applicable board evidence before electrical signoff. No voltage, strap or timing exception is guessed.

The source-bound scope runtime and full-ILA application qualification pass in build/local-application-qualification.json; the bounded timeout test uses explicit 64-bit counter jumps, not thirty continuously simulated seconds. No new board validation is claimed. The user's remote-board gate and the accepted DC90363D board baseline remain unchanged.
