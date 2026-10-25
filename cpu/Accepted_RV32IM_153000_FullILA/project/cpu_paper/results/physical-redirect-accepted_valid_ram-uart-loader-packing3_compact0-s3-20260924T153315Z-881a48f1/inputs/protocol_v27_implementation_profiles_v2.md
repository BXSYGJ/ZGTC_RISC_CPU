# v27 implementation-profile extension 2

Frozen before running `routing99`, 2026-09-20. This adds one profile to extension 1; it does not overwrite or relabel its unsupported `routing100` experiment.

The native run `physical-redirect-relaxed_banked_early-uart-loader-routing100-s1-20260919T222027Z-b6f097e9` completed synthesis, full-ILA validation and device mapping, then rejected `-slack_weight 100`. PDS diagnostic Flow-0186 explicitly reports the legal range as **10 through 99**. The earlier native help and manual described the integer option without this bound. Preserve the run as `integration_failed`; it supplies no placement or timing measurement. Repeating the identical invalid option across placement seeds would not test timing.

The new `routing99` profile specifies only `-slack_weight 99`, the reported upper legal bound. Default routing weight remains the documented 90. Start with `redirect-optimization-v27-r6/relaxed_banked_early` after the already launched `refine40` seed-1 run. Keep this routing factor separate from additional placement iterations. Native acceptance and complete reports remain required; no improvement is presumed from the higher weight.

All v27 and extension-1 requirements remain: unchanged 153 MHz clock and constraints, native PDS/ADS target, complete-system resources and full ILA; independent matched off/on/early implementations before promotion; seeds 1, 2, 3 in order and first-passing-seed selection; unchanged RTL and firmware identity checks; all failed or unsupported attempts retained. Adding this profile is not a new redirect algorithm or proof of hardware performance.
