# Local RTL simulation waveform recordings

All nine windows contain 1024 consecutive CPU rising-edge observations from the selected RTL and firmware. Each 42-bit CSV is checked against its recorded VCD at every edge. The PNG and SVG views retain the label LOCAL RTL SIMULATION.

The horizontal axis counts recorded CPU edges. Target FPGA frequency, actual simulator timestamps and accelerated UART settings are separate metadata. These local event counts describe the window and do not replace full-run CoreMark counters.

| Core | Function | WB events /1024 | Local WB event rate | ID held | EX held | MEM held | Frontend transfers | MEM fire | MEM flush | Plots |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Original_155250 | core_bench_list | 596 | 0.582031 | 166 | 160 | 158 | 634 | 596 | 6 | [1024 edges](../Original_155250/waveforms/analysis/core_bench_list/full1024.png) / [32-edge zoom](../Original_155250/waveforms/analysis/core_bench_list/trigger-zoom.png) / [VCD](../Original_155250/waveforms/core_bench_list.vcd) |
| Original_155250 | core_bench_matrix | 652 | 0.636719 | 142 | 119 | 119 | 694 | 651 | 0 | [1024 edges](../Original_155250/waveforms/analysis/core_bench_matrix/full1024.png) / [32-edge zoom](../Original_155250/waveforms/analysis/core_bench_matrix/trigger-zoom.png) / [VCD](../Original_155250/waveforms/core_bench_matrix.vcd) |
| Original_155250 | core_bench_state | 641 | 0.625977 | 106 | 89 | 87 | 681 | 642 | 1 | [1024 edges](../Original_155250/waveforms/analysis/core_bench_state/full1024.png) / [32-edge zoom](../Original_155250/waveforms/analysis/core_bench_state/trigger-zoom.png) / [VCD](../Original_155250/waveforms/core_bench_state.vcd) |
| H3_Base_145125 | core_bench_list | 604 | 0.589844 | 163 | 159 | 158 | 634 | 605 | 5 | [1024 edges](../H3_Base_145125/waveforms/analysis/core_bench_list/full1024.png) / [32-edge zoom](../H3_Base_145125/waveforms/analysis/core_bench_list/trigger-zoom.png) / [VCD](../H3_Base_145125/waveforms/core_bench_list.vcd) |
| H3_Base_145125 | core_bench_matrix | 675 | 0.659180 | 123 | 117 | 117 | 699 | 674 | 0 | [1024 edges](../H3_Base_145125/waveforms/analysis/core_bench_matrix/full1024.png) / [32-edge zoom](../H3_Base_145125/waveforms/analysis/core_bench_matrix/trigger-zoom.png) / [VCD](../H3_Base_145125/waveforms/core_bench_matrix.vcd) |
| H3_Base_145125 | core_bench_state | 674 | 0.658203 | 106 | 96 | 94 | 697 | 673 | 1 | [1024 edges](../H3_Base_145125/waveforms/analysis/core_bench_state/full1024.png) / [32-edge zoom](../H3_Base_145125/waveforms/analysis/core_bench_state/trigger-zoom.png) / [VCD](../H3_Base_145125/waveforms/core_bench_state.vcd) |
| H3_Retained_145125 | core_bench_list | 604 | 0.589844 | 163 | 159 | 158 | 634 | 605 | 5 | [1024 edges](../H3_Retained_145125/waveforms/analysis/core_bench_list/full1024.png) / [32-edge zoom](../H3_Retained_145125/waveforms/analysis/core_bench_list/trigger-zoom.png) / [VCD](../H3_Retained_145125/waveforms/core_bench_list.vcd) |
| H3_Retained_145125 | core_bench_matrix | 675 | 0.659180 | 123 | 117 | 117 | 699 | 674 | 0 | [1024 edges](../H3_Retained_145125/waveforms/analysis/core_bench_matrix/full1024.png) / [32-edge zoom](../H3_Retained_145125/waveforms/analysis/core_bench_matrix/trigger-zoom.png) / [VCD](../H3_Retained_145125/waveforms/core_bench_matrix.vcd) |
| H3_Retained_145125 | core_bench_state | 674 | 0.658203 | 106 | 96 | 94 | 697 | 673 | 1 | [1024 edges](../H3_Retained_145125/waveforms/analysis/core_bench_state/full1024.png) / [32-edge zoom](../H3_Retained_145125/waveforms/analysis/core_bench_state/trigger-zoom.png) / [VCD](../H3_Retained_145125/waveforms/core_bench_state.vcd) |

MEM flush counts the recorded late MEM flush signal. It does not count every early redirect or identify branch-prediction errors. ID/EX/MEM held counts mean valid and no corresponding fire at that edge; they do not assign a cause to the hold.

Each window also has editable SVG versions and a waveform-analysis.json receipt beside its PNGs. WAVEFORM_ANALYSIS.json binds all nine source manifests, input hashes, CSV/VCD cross-checks, function labels and rendering outputs.
