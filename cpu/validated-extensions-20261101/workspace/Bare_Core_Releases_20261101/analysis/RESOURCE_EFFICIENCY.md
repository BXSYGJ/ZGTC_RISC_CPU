# Bare-core resource efficiency

The physical CPU DUT contains no cache or peripheral. All core functionality is preserved in eight unchanged RTL files. The separate scan fixture keeps every interface bit controllable or observable; its resources are excluded from the core denominator.

| Release | MHz | Core physical LUT range | Core FF | Effective uncertainty (ns) | Setup slack (ns) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original_155250 | 155.250 | 4,028–4,031 | 1,543 | 0.200 | 0.176 |
| H3_Retained_145125 | 145.125 | 4,143–4,147 | 1,554 | 0.200 | 0.019 |
| H3_Base_145125 | 145.125 | 4,095–4,107 | 1,528 | 0.200 | 0.047 |

| Release | CoreMark/MHz | CoreMark at target (derived) | CoreMark/LUT (conservative) | CoreMark/MHz/kLUT (conservative) |
| --- | ---: | ---: | ---: | ---: |
| Original_155250 | 3.365739 | 522.531 | 0.129628 | 0.834964 |
| H3_Retained_145125 | 3.442075 | 499.531 | 0.120456 | 0.830016 |
| H3_Base_145125 | 3.441903 | 499.506 | 0.121623 | 0.838058 |

Efficiency uses core-only area with explicitly external cached-system services. The execution counts come from completed 6,000-iteration source simulations, joined to the bare DUT through exact source/configuration/firmware hashes and fresh two-million-edge extraction comparisons. These are service-dependent CPU metrics. They are not a new standalone cacheless-memory benchmark or a full new bare-wrapper run.

The conservative area denominator assigns every shared or unattributed physical LUT site to the CPU. The lower bound includes only core-exclusive cells and core-exclusive tool-generated constant sites. Distributed RAM sites are already included in LUT totals. All three CPUs retain four APM blocks and no DRM or PLL inside the core.

Each row passes every checked setup, hold, recovery, removal and pulse-width requirement at both timing corners. Effective uncertainty is reported as observed. It meets or exceeds the 0.150 ns minimum; excess uncertainty is not added to the reported slack.

| Release | Core-exclusive LUT | Fixture-exclusive LUT | Shared / unattributed LUT | Full physical LUT | Core / fixture FF |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original_155250 | 4,028 | 355 | 1 / 2 | 4,386 | 1,543 / 1,232 |
| H3_Retained_145125 | 4,143 | 403 | 1 / 3 | 4,550 | 1,554 / 1,296 |
| H3_Base_145125 | 4,095 | 391 | 11 / 1 | 4,498 | 1,528 / 1,298 |

RELEASES.json and each SELECTED_BUILD.json identify exact reports, constraints, tests and source hashes. [Extraction evidence](EXTRACTION_QUALIFICATION.md), [native area methodology](physical-attribution/README.md), and [reproduction instructions](../README.md).