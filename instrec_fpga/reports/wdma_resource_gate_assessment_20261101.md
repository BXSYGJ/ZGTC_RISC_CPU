# WDMA scalar/wide resource gate assessment (2026-11-01)

The wide parameter RAM candidate has a substantial measured resource benefit. The gate evidence does not support calling aggregate DRM capacity the dominant routing bottleneck, or dismissing the wide implementation as valueless. It also does not establish successful placement, routing, timing, or hardware operation.

## Device-map results

These numbers are the final dev_map table, not the slightly larger pre-map synthesis totals. Capacity is LUT 66,600 / FF 133,200 / DRM 155 / APM 240.

| Frozen input | LUT | FF | DRM | APM |
|---|---:|---:|---:|---:|
| Original routed baseline | 35,840 | 53,845 | 80.5 | 90 |
| Corrected scalar gate | 40,206 | 53,718 | 80.5 | 90 |
| Corrected wide gate | 29,409 | 33,211 | 88.5 | 90 |

Wide versus corrected scalar removes 10,797 LUT (26.85%) and 20,507 FF (38.18%), at a cost of 8 DRM. Wide versus original baseline removes 6,431 LUT (17.94%) and 20,634 FF (38.32%). Wide DRM use is 57.10%, leaving 66.5 DRM; LUT use is 44.16%, FF use 24.93%. Rounded PDS table percentages (45/25/58) should not be mistaken for exact ratios.

## RAM mapping evidence

Wide `synthesize/apm_drm_lutram_utilization.log` lines 549-559 explicitly maps `u_npu/u_wdma/param_bm` (64 x 256) to four 64 x 64 GTP_DRM36K_E1 SIMPLE_DUAL_PORT instances, and `param_shift` (8 x 256) to four 8 x 64 GTP_DRM36K_E1 instances. This accounts for all 8 additional DRM units. It is genuine block-RAM mapping, not just a source attribute or inference wish. The shallow banks waste memory bit capacity but replace large register/mux/write-decode structures. The scalar utilization report contains neither parameter RAM block mapping. Distributed RAM remains 1,505 and APM remains 90 in all three runs.

## Provenance and limits

- Original: `build/pds/20261101-130420-0ed52a5d/flow.log`, dev_map table near line 30389.
- Scalar: `build/resource_gate/20261101-202028-476220/flow.log`, table near line 30365; `gate-manifest.json` says Drift=[], only WDMA replaced, StopAfter=dev_map. Candidate SHA256 5AAF9453C83936A677FEA4B9D9969716BC89FC8C848748667B4A06CB5960DE8E; snapshot SHA differs solely because `module wdma_corrected` was renamed to `wdma`.
- Wide: `build/resource_gate/20261101-202029-216909/flow.log`, table near line 17477; corresponding manifest says Drift=[], only WDMA replaced, StopAfter=dev_map. Candidate/snapshot SHA256 160B0D7F0C0A86E046469964F329F93007DE04E9D7CAA8F90660A6E7F949A732.
- Both runs explicitly finish dev_map successfully. Neither enters PNR or generates a bitstream/timing report. These gates keep the old NPU topology except WDMA, so they are not resource estimates of the newer complete activation-store/FC candidate.

## Rebuild decision

Wide is the better measured next routing candidate for this frozen topology: it removes enough LUT/FF to justify a controlled PNR trial. The present evidence only makes reduced logic congestion plausible; RAM-column placement, high-fanout control and local routing can still dominate. Aggregate 57.10% DRM occupancy does not identify a local routing bottleneck.

Before a new full build: freeze the intended source manifest, include the verified complete-chain fixes explicitly if they are in scope, rerun its native golden regression, then dev_map the exact combined topology to recheck resources. Run only one PDS process; preserve prior logs, and start PNR only after the current run has ended or an explicit decision has safely closed it. Judge success from actual unrouted-net convergence, setup/hold timing and generated bitstream, followed by board validation. This assessment performed no PDS launch, no source RTL edits and no downloader operations.
