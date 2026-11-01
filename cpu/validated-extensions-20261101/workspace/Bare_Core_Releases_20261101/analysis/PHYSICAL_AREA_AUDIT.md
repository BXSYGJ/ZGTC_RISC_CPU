# Final pure-core physical area audit

All three final PDS routes pass all timing tables at their configured targets. Native setup uncertainty is 0.200 ns, satisfying the requested minimum 0.150 ns. The eight RTL files and complete wrapper parameters join the fresh extraction tests and completed original SoC source simulations.

| Core | Target MHz | Setup WNS ns | Native hierarchy LUT/RAM | Actual core slots incl. generated overhead | Native core FF | Core APM | Core distributed RAM slots |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| Original_155250 | 155.25 | +0.176 | 3859 | 4028–4031 | 1543 | 4 | 312 |
| H3_Base_145125 | 145.125 | +0.047 | 3892 | 4095–4107 | 1528 | 4 | 246 |
| H3_Retained_145125 | 145.125 | +0.019 | 3923 | 4143–4147 | 1554 | 4 | 246 |

The physical core interval counts unique exported LUT/RAM slots plus constants used exclusively by core cells. Its upper end assigns every shared or unexported LUT slot to the core. Distributed RAM is already included in the LUT/RAM count and is shown separately for clarity. Caches, backing RAM, MMIO, UART, GPIO, memory arbiters, PLL and ILA are outside the DUT. Register-file/predictor RAM and all multiply/divide APMs are inside it.

| Final total reconciliation | Core-exclusive LUT/RAM | Fixture-exclusive LUT/RAM | Shared LUT | Global-only LUT | Native device LUT/RAM | Native core + fixture FF |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Original_155250 | 4028 | 355 | 1 | 2 | 4386 | 1543 + 1232 = 2775 |
| H3_Base_145125 | 4095 | 391 | 11 | 1 | 4498 | 1528 + 1298 = 2826 |
| H3_Retained_145125 | 4143 | 403 | 1 | 3 | 4550 | 1554 + 1296 = 2850 |

No fixture estimate or fitted packed-macro LUT weight enters these sums. Each generated constant has its actual LUT INIT, physical slot and downstream consumer graph recorded. Every final device LUT total is the exact sum of the listed categories. Global-only slots remain unattributed and are included in the conservative core upper bound.

The physical simulation export omits four native packed core registers in Base and one in Retained. Their exact packed owner/output names are recorded and restore the authoritative native FF total. Every other exported FF joins its packed owner. The Retained native hierarchy convention counts 3923 core LUT/RAM slots while its unique physical export has 3925; both representations remain visible. Physical bounds use the unique exported slots. No equality is manufactured between these conventions.

All 64 `mcycle` and all 64 `minstret` physical FF bits are individually present in every export. Separate frontend, RVC expander, predictor, return-stack, decoder, ALU, machine CSR/exception/interrupt, multiply/divide and register-file RAM cones remain. Exact source identity preserves the full functional configuration; physical cone presence is an additional structural check.

Execution efficiency remains conditional on the explicitly external original cached-system service. The fresh bare-wrapper qualification ran 2M edges per baseline and real rollback; the completed 6000-iteration figures belong to the exact original SoC source simulations joined through source/configuration/firmware identity. The scan fixture provides physical controllability/observability and is excluded from the core-only area. These are local RTL/PDS results, without hardware measurements.

The JSON links each immutable build-specific area inventory, feature receipt, stable physical manifest, extraction qualification and completed source-reference receipt by SHA256. Native reports, final primitive exports, source copies and parameter contracts were reopened during this aggregate audit.
