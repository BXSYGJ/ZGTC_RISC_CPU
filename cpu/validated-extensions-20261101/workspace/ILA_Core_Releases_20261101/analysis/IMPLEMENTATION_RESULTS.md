# Local ILA implementation and execution results

All waveform recordings originate from local RTL simulation. Each full benchmark uses the exact frozen V0 firmware with 6,000 iterations. UART bytes, validation CRCs, execution cycles and retired instructions match the respective reference. No board programming or remote ILA capture is part of this task.

| Release | Configured MHz | Data / trigger bits | Cycles | CoreMark/MHz | Routed LUT / FF | Setup slack (ns) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original_155250 | 155.250 | 42 / 33 | 1,782,669,419 | 3.365739 | 6,609 / 3,573 | 0.119 |
| H3_Retained_145125 | 145.125 | 24 / 17 | 1,743,134,699 | 3.442075 | 6,456 / 3,024 | 0.000 |
| H3_Base_145125 | 145.125 | 24 / 17 | 1,743,221,870 | 3.441903 | 6,421 / 3,024 | 0.074 |

Every full run retires 1,649,428,429 measured instructions. The CPU timing constraints include 0.150 ns setup uncertainty. Slack is reported after that deduction. A printed 0.000 ns result has no additional reported margin. RELEASES.json links the all-corner result for each selected layout.

| Release | CoreMark at configured clock | CoreMark/LUT | CoreMark/MHz/kLUT | DRM / APM |
| --- | ---: | ---: | ---: | ---: |
| Original_155250 | 522.531 | 0.079064 | 0.509266 | 22.5 / 4 |
| H3_Retained_145125 | 499.531 | 0.077375 | 0.533159 | 26 / 4 |
| H3_Base_145125 | 499.506 | 0.077793 | 0.536038 | 26 / 4 |

The 42-bit local observer records a superset of the selected physical probes. The H3 Lean24 data comprise EX PC [15:0], IF/ID/EX/MEM/WB validity and ID/EX/MEM transfer. Its trigger is EX PC [15:0] plus EX transfer. SOURCE_TO_SELECTED_BINDING.json verifies the exact subset mapping. Sixteen PC bits identify the current firmware functions within its 64-KiB image; high-address diagnostics are outside that smaller physical probe set.

Nine 1,024-edge windows cover entry into core_bench_list, core_bench_matrix and core_bench_state. Each has packed/decoded CSV and VCD, plus an overview and 32-edge zoom in PNG and SVG. The renderer checked 387,072 bits against packed observations and VCD. [Waveform index](README.md); [contact sheet](LOCAL_WAVEFORM_CONTACT_SHEET.png).

Waveform axes use CPU-edge indices. The configured FPGA frequency is separate from the actual simulator timebase and accelerated UART settings. Window-level WB counts and held-stage cycles describe the recorded intervals. CoreMark is derived from complete measured cycle counts at the configured target; it is not a new physical-board measurement.