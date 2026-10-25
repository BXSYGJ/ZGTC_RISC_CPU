# v27 implementation-profile extension 1

Frozen before running these profiles, 2026-09-20. The v27 correctness, 153 MHz clock, full ILA, firmware, target device, resource accounting and hardware-promotion requirements remain mandatory.

Native `pnr -help` on Windows PDS 2022.2-SP6.4 for PG2L200H confirmed the `-slack_weight` and `-refineplacement_iteration` integer options. Evidence: `results/pds-pnr-options-20260919T215923Z-af049e02`, including executable hash, exact command, native output and installed manual hash. The manual lists defaults of 90 and 20 respectively. Neither help nor the inspected manual specifies numeric ranges. A rejected setting is an integration failure, not evidence of timing performance.

Predeclared profiles, each a separate implementation factor:

| Profile | Explicit additional PNR options | Hypothesis |
| --- | --- | --- |
| default | None | Existing default implementation control |
| routing100 | `-slack_weight 100` | Greater timing weight may reduce routing-dominated setup paths |
| refine40 | `-refineplacement_iteration 40` | More detailed-placement iterations may improve placement convergence |

No clock/IO constraint, cache geometry, RTL, synthesis option or ILA reduction accompanies these profiles. Do not silently enable options unavailable for Logos2. Report actual tool acceptance, timing, complete-system resources, elapsed runtime and every failed cell; an accepted command does not prove that it improved implementation.

Start with `redirect-optimization-v27-r6/relaxed_banked_early`: its default seed 1 has 9,459 LUT and -0.678 ns setup slack, providing useful area headroom while failing timing. Test routing100 before refine40. Within each profile retain the v27 seed order 1, 2, 3 and first-passing-seed selection; do not select a favorable resource result after measurement. Before promoting any profile-dependent gain, independently implement matched off/on/early controls with the same profile, tool, constraints, firmware and seed rule. Existing simulation evidence can be reused only after verifying unchanged RTL and firmware identities.

Any combination or additional profile needs a new versioned extension declared before its outcome. A profile change is not a new redirect algorithm, and successful timing alone cannot qualify a benchmark or resource-efficiency claim.
